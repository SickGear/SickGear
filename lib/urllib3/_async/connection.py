from __future__ import annotations

import logging
import os
import socket
import time
import typing
import warnings
from datetime import datetime, timedelta
from socket import timeout as SocketTimeout

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from .response import AsyncHTTPResponse
    from .._typing import (
        _TYPE_BODY,
        _TYPE_PEER_CERT_RET_DICT,
        _TYPE_SOCKET_OPTIONS,
        _TYPE_TIMEOUT_INTERNAL,
        ProxyConfig,
        _TYPE_ASYNC_BODY,
    )
    from ..util._async.traffic_police import AsyncTrafficPolice
    from ..backend._async._base import AsyncLowLevelResponse

from .._constant import (
    DEFAULT_BLOCKSIZE,
    DEFAULT_KEEPALIVE_DELAY,
    DEFAULT_BACKGROUND_WATCH_WINDOW,
    DEFAULT_KEEPALIVE_IDLE_WINDOW,
)
from ..util.timeout import _DEFAULT_TIMEOUT, Timeout
from ..util.util import to_str

from ..contrib.anytls import ssl


from ..backend import HttpVersion, QuicPreemptiveCacheType, ResponsePromise
from ..backend._async import AsyncHfaceBackend
from ..connection import (
    _CONTAINS_CONTROL_CHAR_RE,
    _get_default_user_agent,
    _match_hostname,
    _ResponseOptions,
    port_by_scheme,
)
from ..contrib.resolver._async import AsyncBaseResolver, AsyncResolverDescription
from ..contrib.ssa import AsyncSocket, SSLAsyncSocket
from ..exceptions import BaseSSLError, ConnectTimeoutError, EarlyResponse  # noqa: F401
from ..exceptions import HTTPError as HTTPException  # noqa
from ..exceptions import (  # noqa: F401
    NameResolutionError,
    NewConnectionError,
    ResponseNotReady,
)
from ..util import SKIP_HEADER, SKIPPABLE_HEADERS
from ..util._async.ssl_ import ssl_wrap_socket
from ..util.request import body_to_chunks
from ..util.ssl_ import (
    assert_fingerprint as _assert_fingerprint,
    convert_ssl_ctx_nonstdlib,
)
from ..util.ssl_ import (
    is_capable_for_quic,
    is_ipaddress,
    resolve_cert_reqs,
    resolve_ssl_version,
    HAS_NEVER_CHECK_COMMON_NAME,
)
from ..util.url import Url
from ..util.socket_state import is_established

# Not a no-op, we're adding this to the namespace so it can be imported.
ConnectionError = ConnectionError
BrokenPipeError = BrokenPipeError


log = logging.getLogger(__name__)


class AsyncHTTPConnection(AsyncHfaceBackend):
    """
    Based on :class:`urllib3.backend._async.AsyncBaseBackend` but provides an extra constructor
    backwards-compatibility layer between older and newer Pythons.

    Additional keyword parameters are used to configure attributes of the connection.
    Accepted parameters include:

    - ``source_address``: Set the source address for the current connection.
    - ``socket_options``: Set specific options on the underlying socket. If not specified, then
      defaults are loaded from ``HTTPConnection.default_socket_options`` which includes disabling
      Nagle's algorithm (sets TCP_NODELAY to 1) unless the connection is behind a proxy.

      For example, if you wish to enable TCP Keep Alive in addition to the defaults,
      you might pass:

      .. code-block:: python

         HTTPConnection.default_socket_options + [
             (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
         ]

      Or you may want to disable the defaults by passing an empty list (e.g., ``[]``).
    """

    scheme = "http"
    default_port: typing.ClassVar[int] = port_by_scheme[scheme]

    blocksize: int
    source_address: tuple[str, int] | None
    socket_options: _TYPE_SOCKET_OPTIONS | None

    _has_connected_to_proxy: bool
    _response_options: _ResponseOptions | None
    _tunnel_host: str | None
    _tunnel_port: int | None
    _tunnel_scheme: str | None

    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        timeout: _TYPE_TIMEOUT_INTERNAL = _DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        socket_options: _TYPE_SOCKET_OPTIONS
        | None = AsyncHfaceBackend.default_socket_options,
        proxy: Url | None = None,
        proxy_config: ProxyConfig | None = None,
        disabled_svn: set[HttpVersion] | None = None,
        preemptive_quic_cache: QuicPreemptiveCacheType | None = None,
        resolver: AsyncBaseResolver | None = None,
        socket_family: socket.AddressFamily = socket.AF_UNSPEC,
        keepalive_delay: float | int | None = DEFAULT_KEEPALIVE_DELAY,
        background_watch_delay: int | float | None = DEFAULT_BACKGROUND_WATCH_WINDOW,
        keepalive_idle_window: int | float | None = DEFAULT_KEEPALIVE_IDLE_WINDOW,
    ) -> None:
        super().__init__(
            host=host,
            port=port,
            timeout=Timeout.resolve_default_timeout(timeout),
            source_address=source_address,
            blocksize=blocksize,
            socket_options=socket_options,
            disabled_svn=disabled_svn,
            preemptive_quic_cache=preemptive_quic_cache,
            keepalive_delay=keepalive_delay,
            background_watch_delay=background_watch_delay,
            keepalive_idle_window=keepalive_idle_window,
        )
        self.proxy = proxy
        self.proxy_config = proxy_config

        self._has_connected_to_proxy = False

        if resolver is None:
            resolver = AsyncResolverDescription.from_url("system://").new()

        self._resolver: AsyncBaseResolver = resolver

        #: This struct hold: resolution delay, established delay, and after established datetime.
        self._connect_timings: tuple[timedelta, timedelta, datetime] | None = None

        if socket_family not in [socket.AF_UNSPEC, socket.AF_INET, socket.AF_INET6]:
            raise ValueError(  # Defensive: human error only
                "Unsupported socket_family argument value. Supported values are: socket.AF_UNSPEC, socket.AF_INET, socket.AF_INET6"
            )

        #: Restrict/Scope IP family per connection.
        self._socket_family = socket_family

    @property
    def host(self) -> str:
        """
        Getter method to remove any trailing dots that indicate the hostname is an FQDN.

        In general, SSL certificates don't include the trailing dot indicating a
        fully-qualified domain name, and thus, they don't validate properly when
        checked against a domain name that includes the dot. In addition, some
        servers may not expect to receive the trailing dot when provided.

        However, the hostname with trailing dot is critical to DNS resolution; doing a
        lookup with the trailing dot will properly only resolve the appropriate FQDN,
        whereas a lookup without a trailing dot will search the system's search domain
        list. Thus, it's important to keep the original host around for use only in
        those cases where it's appropriate (i.e., when doing DNS lookup to establish the
        actual TCP connection across which we're going to send HTTP requests).
        """
        return self._dns_host.rstrip(".")

    @host.setter
    def host(self, value: str) -> None:
        """
        Setter for the `host` property.

        We assume that only urllib3 uses the _dns_host attribute; httplib itself
        only uses `host`, and it seems reasonable that other libraries follow suit.
        """
        self._dns_host = value

    async def _new_conn(self) -> AsyncSocket:  # type: ignore[override]
        """Establish a socket connection and set nodelay settings on it.

        :return: New socket connection.
        """
        await super()._new_conn()

        backup_timeout: float | None = -1.0

        # we want to purposely mitigate the following scenario:
        #   "A server yield its support for HTTP/2 or HTTP/3 through Alt-Svc, but
        #    it cannot connect to the alt-svc, thus confusing the end-user on why it
        #    waits forever for the 2nd request."
        if (
            self._max_tolerable_delay_for_upgrade is not None
            and self.socket_kind != socket.SOCK_DGRAM
        ):
            backup_timeout = self.timeout
            self.timeout = self._max_tolerable_delay_for_upgrade

        try:
            sock = await self._resolver.create_connection(
                (self._dns_host, self.port or self.default_port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
                socket_kind=self.socket_kind,
                quic_upgrade_via_dns_rr=self.scheme == "https"
                and HttpVersion.h3 not in self._disabled_svn
                and self.socket_kind != socket.SOCK_DGRAM,
                timing_hook=lambda _: setattr(self, "_connect_timings", _),
                ech_config_hook=lambda _: setattr(self, "_ech_config", _),
                default_socket_family=self._socket_family,
            )
        except socket.gaierror as e:
            raise NameResolutionError(self.host, self, e) from e
        except SocketTimeout as e:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from e

        except OSError as e:
            raise NewConnectionError(
                self, f"Failed to establish a new connection: {e}"
            ) from e
        finally:
            if backup_timeout != -1:
                self.timeout = backup_timeout

        # We can, migrate to a DGRAM socket if DNS HTTPS/RR record exist and yield HTTP/3+QUIC support.
        if sock.type == socket.SOCK_DGRAM and self.socket_kind == socket.SOCK_STREAM:
            self.socket_kind = socket.SOCK_DGRAM
            self._svn = HttpVersion.h3

        return sock

    def set_tunnel(
        self,
        host: str,
        port: int | None = None,
        headers: typing.Mapping[str, str] | None = None,
        scheme: str = "http",
    ) -> None:
        if scheme not in ("http", "https"):
            raise ValueError(
                f"Invalid proxy scheme for tunneling: {scheme!r}, must be either 'http' or 'https'"
            )
        super().set_tunnel(host, port=port, headers=headers)
        self._tunnel_scheme = scheme

    async def connect(self) -> None:
        self.sock = await self._new_conn()
        if self._tunnel_host:
            await self._post_conn()
            # If we're tunneling it means we're connected to our proxy.
            self._has_connected_to_proxy = True

            # TODO: Fix tunnel so it doesn't depend on self.sock state.
            await self._tunnel()

        await self._post_conn()
        # If there's a proxy to be connected to we are fully connected.
        # This is set twice (once above and here) due to forwarding proxies
        # not using tunnelling.
        self._has_connected_to_proxy = bool(self.proxy)

        if self._has_connected_to_proxy:
            self.proxy_is_verified = False

    @property
    def is_closed(self) -> bool:
        return self.sock is None

    @property
    def is_connected(self) -> bool:
        if self.sock is None:
            return False

        if self.sock.fileno() == -1 or self._protocol is None:
            return False

        if self._promises or self._pending_responses:
            return True

        # consider the conn dead after our keep alive delay passed.
        if (
            self._keepalive_delay is not None
            and self.connected_at is not None
            and time.monotonic() - self.connected_at >= self._keepalive_delay
        ):
            return False

        if self._protocol.has_expired():
            return False

        return is_established(self.sock)

    @property
    def has_connected_to_proxy(self) -> bool:
        return self._has_connected_to_proxy

    @property
    def proxy_is_forwarding(self) -> bool:
        """
        Return True if a forwarding proxy is configured, else return False
        """
        return bool(self.proxy) and self._tunnel_host is None

    @property
    def proxy_is_tunneling(self) -> bool:
        """
        Return True if a tunneling proxy is configured, else return False
        """
        return self._tunnel_host is not None

    async def close(self) -> None:  # type: ignore[override]
        try:
            await super().close()
        finally:
            # Reset all stateful properties so connection
            # can be reused without leaking prior configs.
            self.sock = None
            self.is_verified = False
            self.proxy_is_verified = None
            self._has_connected_to_proxy = False
            self._response_options = None
            self._tunnel_host = None
            self._tunnel_port = None
            self._tunnel_scheme = None

    def putrequest(
        self,
        method: str,
        url: str,
        skip_host: bool = False,
        skip_accept_encoding: bool = False,
    ) -> None:
        """"""
        # Empty docstring because the indentation of CPython's implementation
        # is broken but we don't want this method in our documentation.
        match = _CONTAINS_CONTROL_CHAR_RE.search(method)
        if match:
            raise ValueError(
                f"Method cannot contain non-token characters {method!r} (found at least {match.group()!r})"
            )

        return super().putrequest(
            method, url, skip_host=skip_host, skip_accept_encoding=skip_accept_encoding
        )

    def putheader(self, header: str, *values: str) -> None:
        """"""
        if not any(isinstance(v, str) and v == SKIP_HEADER for v in values):
            super().putheader(header, *values)
        elif to_str(header.lower()) not in SKIPPABLE_HEADERS:
            skippable_headers = "', '".join(
                [str.title(header) for header in sorted(SKIPPABLE_HEADERS)]
            )
            raise ValueError(
                f"urllib3.util.SKIP_HEADER only supports '{skippable_headers}'"
            )

    async def request(
        self,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = None,
        headers: typing.Mapping[str, str] | None = None,
        *,
        chunked: bool = False,
        preload_content: bool = True,
        decode_content: bool = True,
        enforce_content_length: bool = True,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ]
        | None = None,
    ) -> ResponsePromise:
        # Update the inner socket's timeout value to send the request.
        # This only triggers if the connection is reused.
        if self.sock is not None:
            self.sock.settimeout(self.timeout)

        # Store these values to be fed into the HTTPResponse
        # object later. TODO: Remove this in favor of a real
        # HTTP lifecycle mechanism.

        # We have to store these before we call .request()
        # because sometimes we can still salvage a response
        # off the wire even if we aren't able to completely
        # send the request body.
        response_options = _ResponseOptions(
            request_method=method,
            request_url=url,
            preload_content=preload_content,
            decode_content=decode_content,
            enforce_content_length=enforce_content_length,
        )

        if headers is None:
            headers = {}
        header_keys = frozenset(to_str(k.lower()) for k in headers)
        skip_accept_encoding = "accept-encoding" in header_keys
        skip_host = "host" in header_keys
        self.putrequest(
            method, url, skip_accept_encoding=skip_accept_encoding, skip_host=skip_host
        )

        # Transform the body into an iterable of sendall()-able chunks
        # and detect if an explicit Content-Length is doable.
        chunks_and_cl = body_to_chunks(
            body,
            method=method,
            blocksize=self.max_frame_size,
            force=self._svn != HttpVersion.h11,
        )
        chunks = chunks_and_cl.chunks
        content_length = chunks_and_cl.content_length

        overrule_content_length: bool = False

        # users may send plain 'str' and assign a Content-Length that will
        # disagree with the actual amount of data to send (encoded, aka. bytes)
        if (
            isinstance(body, str)
            and "content-length" in header_keys
            and len(body) != content_length
        ):
            overrule_content_length = True

        # When chunked is explicit set to 'True' we respect that.
        if chunked:
            if "transfer-encoding" not in header_keys:
                self.putheader("Transfer-Encoding", "chunked")
        else:
            # Otherwise we go off the recommendation of 'body_to_chunks()'.
            if (
                "content-length" not in header_keys
                and "transfer-encoding" not in header_keys
            ):
                if content_length is None:
                    if chunks is not None:
                        self.putheader("Transfer-Encoding", "chunked")
                else:
                    self.putheader("Content-Length", str(content_length))

        # Now that framing headers are out of the way we send all the other headers.
        if "user-agent" not in header_keys:
            self.putheader("User-Agent", _get_default_user_agent())
        for header, value in headers.items():
            if overrule_content_length and header.lower() == "content-length":
                value = str(content_length)
            if chunks_and_cl.is_string and header.lower() == "content-type":
                value_lower = value.lower()
                # even if not "officially" supported
                # some may send values as bytes, and we have to
                # cast "temporarily" the value
                # this case is already covered in the parent class.
                if isinstance(value_lower, bytes):
                    value_lower = value_lower.decode()
                    value = value.decode()
                if "charset" in value_lower:
                    if (
                        "utf-8" not in value_lower
                        and "utf_8" not in value_lower
                        and "utf8" not in value_lower
                    ):
                        warnings.warn(
                            "A conflicting charset has been set in Content-Type while sending a 'string' as the body. "
                            "Beware that urllib3.future always encode a string to unicode. "
                            f"Expected 'charset=utf-8', got: {value} "
                            "Either encode your string to bytes or open your file in bytes mode.",
                            UserWarning,
                            stacklevel=2,
                        )

            self.putheader(header, value)

        try:
            rp = await self.endheaders(expect_body_afterward=chunks is not None)
        except BrokenPipeError as e:
            rp = e.promise  # type: ignore[attr-defined]
            assert rp is not None
            rp.set_parameter("response_options", response_options)
            raise e

        if rp:
            rp.set_parameter("response_options", response_options)
            return rp

        total_sent = 0

        try:
            # If we're given a body we start sending that in chunks.
            if chunks is not None:
                if hasattr(chunks, "__aiter__"):
                    async for chunk in chunks:
                        if not chunk:
                            continue  # Defensive: body_to_chunks filters empty async chunks.
                        if isinstance(chunk, str):
                            chunk = chunk.encode("utf-8")
                        await self.send(chunk)
                        total_sent += len(chunk)
                        if on_upload_body is not None:
                            await on_upload_body(
                                total_sent, content_length, False, False
                            )
                else:
                    for chunk in chunks:
                        # Sending empty chunks isn't allowed for TE: chunked
                        # as it indicates the end of the body.
                        if not chunk:
                            continue
                        if isinstance(chunk, str):
                            chunk = chunk.encode("utf-8")
                        await self.send(chunk)
                        total_sent += len(chunk)
                        if on_upload_body is not None:
                            await on_upload_body(
                                total_sent, content_length, False, False
                            )
                try:
                    rp = await self.send(b"", eot=True)
                except (
                    TypeError
                ):  # Defensive: legacy send overrides may reject the eot keyword.
                    # AWSConnection override the send() method
                    # thus preventing us to add an additional kwarg in send(...)
                    # reason (AWS side): urllib3 2.0 chunks and calls send potentially thousands of
                    # times inside `request` unlike the standard library[...]
                    # response (urllib3-future): not concerned by this. bypass the bypass.
                    rp = await super().send(b"", eot=True)
                if on_upload_body is not None:
                    await on_upload_body(total_sent, content_length, True, False)
        except EarlyResponse as e:
            rp = e.promise
            if on_upload_body is not None:
                await on_upload_body(total_sent, content_length, False, True)
        except BrokenPipeError as e:
            if (
                on_upload_body is not None
            ):  # Defensive: best-effort progress notification after a broken upload pipe.
                await on_upload_body(
                    total_sent,
                    content_length,
                    total_sent == content_length,
                    total_sent != content_length,
                )
            rp = e.promise  # type: ignore[attr-defined]
            assert rp is not None
            rp.set_parameter("response_options", response_options)
            raise e

        assert rp is not None
        rp.set_parameter("response_options", response_options)
        return rp

    async def getresponse(  # type: ignore[override]
        self,
        *,
        promise: ResponsePromise | None = None,
        police_officer: AsyncTrafficPolice[AsyncHTTPConnection] | None = None,
        early_response_callback: typing.Callable[
            [AsyncHTTPResponse], typing.Awaitable[None]
        ]
        | None = None,
    ) -> AsyncHTTPResponse:
        """
        Get the response from the server.

        If the HTTPConnection is in the correct state, returns an instance of HTTPResponse or of whatever object is returned by the response_class variable.

        If a request has not been sent or if a previous response has not be handled, ResponseNotReady is raised. If the HTTP response indicates that the connection should be closed, then it will be closed before the response is returned. When the connection is closed, the underlying socket is closed.
        """
        # Raise the same error as http.client.HTTPConnection
        if self.sock is None:
            raise ResponseNotReady()

        # Since the connection's timeout value may have been updated
        # we need to set the timeout on the socket.
        self.sock.settimeout(self.timeout)

        async def early_response_handler(
            early_low_response: AsyncLowLevelResponse,
        ) -> None:
            """Handle unexpected early response. Notify the upper stack!"""
            nonlocal promise, early_response_callback

            _promise = None

            if promise is None:
                _promise = early_low_response.from_promise
            else:
                _promise = promise

            if _promise is None:
                raise OSError  # Defensive: custom backends may omit originating promise metadata.

            if early_response_callback is None:
                early_response_callback = _promise.get_parameter("on_early_response")

            if early_response_callback is None:
                return

            early_resp_options: _ResponseOptions = _promise.get_parameter(  # type: ignore[assignment]
                "response_options"
            )

            early_response = AsyncHTTPResponse(
                body=early_low_response,
                headers=early_low_response.msg,
                status=early_low_response.status,
                version=early_low_response.version,
                reason=early_low_response.reason,
                preload_content=False,
                decode_content=early_resp_options.decode_content,
                original_response=early_low_response,
                enforce_content_length=False,
                request_method=early_resp_options.request_method,
                request_url=early_resp_options.request_url,
                connection=None,
                police_officer=None,
            )

            await early_response_callback(early_response)

        # This is needed here to avoid circular import errors
        from .response import AsyncHTTPResponse

        # Get the response from backend._base.BaseBackend
        low_response = await super().getresponse(
            promise=promise,
            early_response_callback=early_response_handler,
        )

        if promise is None:
            promise = low_response.from_promise

        if promise is None:
            raise OSError  # Defensive: custom backends may omit originating promise metadata.

        resp_options: _ResponseOptions = promise.get_parameter("response_options")  # type: ignore[assignment]
        headers = low_response.msg

        response = AsyncHTTPResponse(
            body=low_response,
            headers=headers,
            status=low_response.status,
            version=low_response.version,
            reason=low_response.reason,
            preload_content=resp_options.preload_content,
            decode_content=resp_options.decode_content,
            original_response=low_response,
            enforce_content_length=resp_options.enforce_content_length,
            request_method=resp_options.request_method,
            request_url=resp_options.request_url,
            connection=self,
            police_officer=police_officer,
        )

        # Remove fulfilled traffic before the connection can pass to another
        # get_response() caller during body preloading or on return.
        if police_officer is not None:
            police_officer.forget(promise)

        if resp_options.preload_content:
            response._body = await response.read(
                decode_content=resp_options.decode_content
            )

        return response


class AsyncHTTPSConnection(AsyncHTTPConnection):
    """
    Many of the parameters to this constructor are passed to the underlying SSL
    socket by means of :py:func:`urllib3.util.ssl_wrap_socket`.
    """

    scheme = "https"
    default_port = port_by_scheme[scheme]

    cert_reqs: int | str | None = None
    ca_certs: str | None = None
    ca_cert_dir: str | None = None
    ca_cert_data: None | str | bytes = None
    ssl_version: int | str | None = None
    ssl_minimum_version: int | None = None
    ssl_maximum_version: int | None = None
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = None
    assert_fingerprint: str | None = None
    cert_file: str | None = None
    key_file: str | None = None
    key_password: str | None = None
    cert_data: str | bytes | None = None
    key_data: str | bytes | None = None
    ciphers: str | None = None

    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        timeout: _TYPE_TIMEOUT_INTERNAL = _DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        socket_options: _TYPE_SOCKET_OPTIONS
        | None = AsyncHTTPConnection.default_socket_options,
        disabled_svn: set[HttpVersion] | None = None,
        preemptive_quic_cache: QuicPreemptiveCacheType | None = None,
        resolver: AsyncBaseResolver | None = None,
        socket_family: socket.AddressFamily = socket.AF_UNSPEC,
        keepalive_delay: float | int | None = DEFAULT_KEEPALIVE_DELAY,
        proxy: Url | None = None,
        proxy_config: ProxyConfig | None = None,
        cert_reqs: int | str | None = None,
        assert_hostname: None | str | Literal[False] = None,
        assert_fingerprint: str | None = None,
        server_hostname: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
        ca_certs: str | None = None,
        ca_cert_dir: str | None = None,
        ca_cert_data: None | str | bytes = None,
        ssl_minimum_version: int | None = None,
        ssl_maximum_version: int | None = None,
        ssl_version: int | str | None = None,
        ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_password: str | None = None,
        cert_data: str | bytes | None = None,
        key_data: str | bytes | None = None,
        ciphers: str | None = None,
    ) -> None:
        if ssl_context is not None:
            ssl_context = convert_ssl_ctx_nonstdlib(ssl_context)

        if not is_capable_for_quic(ssl_context, ssl_maximum_version):
            if disabled_svn is None:
                disabled_svn = set()

            disabled_svn.add(HttpVersion.h3)

        super().__init__(
            host,
            port=port,
            timeout=timeout,
            source_address=source_address,
            blocksize=blocksize,
            socket_options=socket_options,
            proxy=proxy,
            proxy_config=proxy_config,
            disabled_svn=disabled_svn,
            preemptive_quic_cache=preemptive_quic_cache,
            resolver=resolver,
            socket_family=socket_family,
            keepalive_delay=keepalive_delay,
        )

        self.key_file = key_file
        self.cert_file = cert_file
        self.cert_data = cert_data
        self.key_data = key_data
        self.key_password = key_password
        self.ssl_context = ssl_context
        self.server_hostname = server_hostname
        self.assert_hostname = assert_hostname
        self.assert_fingerprint = assert_fingerprint
        self.ssl_version = ssl_version
        self.ssl_minimum_version = ssl_minimum_version
        self.ssl_maximum_version = ssl_maximum_version
        self.ssl_backend = ssl_backend
        self.ca_certs = ca_certs and os.path.expanduser(ca_certs)
        self.ca_cert_dir = ca_cert_dir and os.path.expanduser(ca_cert_dir)
        self.ca_cert_data = ca_cert_data
        self.ciphers = ciphers

        # cert_reqs depends on ssl_context so calculate last.
        if cert_reqs is None:
            if self.ssl_context is not None:
                cert_reqs = self.ssl_context.verify_mode
            else:
                cert_reqs = resolve_cert_reqs(None)
        self.cert_reqs = cert_reqs

        #: used to store the last used/working ssl context
        self._upgrade_ctx: ssl.SSLContext | None = None

    async def connect(self) -> None:
        sock: AsyncSocket | SSLAsyncSocket
        self.sock = sock = await self._new_conn()

        # the protocol/state-machine may also ship with an external TLS Engine.
        if (
            self._custom_tls(
                self.ssl_context or self._upgrade_ctx,
                self.ca_certs,
                self.ca_cert_dir,
                self.ca_cert_data,
                self.ssl_minimum_version,
                self.ssl_maximum_version,
                self.cert_file or self.cert_data,
                self.key_file or self.key_data,
                self.key_password,
                self.assert_fingerprint,
                self.assert_hostname,
                self.cert_reqs,
            )
            is False
        ):
            server_hostname: str = self.host
            tls_in_tls = False

            alpn_protocols: list[str] = []

            # we explicitly skip h3 while still over TCP
            for svn in reversed(AsyncHTTPSConnection.supported_svn):
                if svn in self.disabled_svn:
                    continue
                if svn == HttpVersion.h11:
                    alpn_protocols.append("http/1.1")
                elif svn == HttpVersion.h2:
                    alpn_protocols.append("h2")

            # Do we need to establish a tunnel?
            if self.proxy_is_tunneling:
                # We're tunneling to an HTTPS origin so need to do TLS-in-TLS.
                if self._tunnel_scheme == "https":
                    self.sock = sock = await self._connect_tls_proxy(
                        self.host, sock, ["http/1.1"]
                    )
                    tls_in_tls = True
                elif self._tunnel_scheme == "http":
                    self.proxy_is_verified = False

                await self._post_conn()

                # If we're tunneling it means we're connected to our proxy.
                self._has_connected_to_proxy = True

                await self._tunnel()
                # Override the host with the one we're requesting data from.
                server_hostname = self._tunnel_host  # type: ignore[assignment]

            if self.server_hostname is not None:
                server_hostname = self.server_hostname

            if self.proxy_is_forwarding and self.proxy_config is not None:
                proxy_sock = await self._connect_tls_proxy(
                    self.host, sock, alpn_protocols or None
                )
                sock_and_verified = _WrappedAndVerifiedSocket(
                    proxy_sock, self.proxy_is_verified is True
                )
            else:
                sock_and_verified = await _ssl_wrap_socket_and_match_hostname(
                    sock=sock,
                    cert_reqs=self.cert_reqs,
                    ssl_version=self.ssl_version,
                    ssl_minimum_version=self.ssl_minimum_version,
                    ssl_maximum_version=self.ssl_maximum_version,
                    ssl_backend=self.ssl_backend,
                    ca_certs=self.ca_certs,
                    ca_cert_dir=self.ca_cert_dir,
                    ca_cert_data=self.ca_cert_data,
                    cert_file=self.cert_file,
                    key_file=self.key_file,
                    key_password=self.key_password,
                    server_hostname=server_hostname,
                    ssl_context=self.ssl_context,
                    tls_in_tls=tls_in_tls,
                    assert_hostname=self.assert_hostname,
                    assert_fingerprint=self.assert_fingerprint,
                    alpn_protocols=alpn_protocols or None,
                    cert_data=self.cert_data,
                    key_data=self.key_data,
                    ciphers=self.ciphers,
                    ech_config_list=self._ech_config,
                )

            # we want the http3 upgrade to behave
            # exactly as http1/http2 ssl handshake
            # configuration CAstore wise for example
            # only if not using tls in tls
            if hasattr(sock_and_verified.socket, "context"):
                self._upgrade_ctx = sock_and_verified.socket.context

            self.sock = sock_and_verified.socket

            # If there's a proxy to be connected to we are fully connected.
            # This is set twice (once above and here) due to forwarding proxies
            # not using tunnelling.
            self._has_connected_to_proxy = bool(self.proxy)

            # Forwarding proxies can never have a verified target since
            # the proxy is the one doing the verification. Should instead
            # use a CONNECT tunnel in order to verify the target.
            # See: https://github.com/urllib3/urllib3/issues/3267.
            if self.proxy_is_forwarding:
                self.is_verified = False
            else:
                self.is_verified = sock_and_verified.is_verified

            # If there's a proxy to be connected to we are fully connected.
            # This is set twice (once above and here) due to forwarding proxies
            # not using tunnelling.
            self._has_connected_to_proxy = bool(self.proxy)

            # Set `self.proxy_is_verified` unless it's already set while
            # establishing a tunnel.
            if self._has_connected_to_proxy and self.proxy_is_verified is None:
                self.proxy_is_verified = sock_and_verified.is_verified  # Defensive: normal proxy setup already records verification; retain custom-connection compatibility.

        await self._post_conn()

    async def _connect_tls_proxy(
        self,
        hostname: str,
        sock: AsyncSocket,
        alpn_protocols: list[str] | None = None,
    ) -> SSLAsyncSocket:
        """
        Establish a TLS connection using proxy-specific trust and identity.
        """
        assert self.proxy_config is not None
        proxy_config = self.proxy_config
        ssl_context = proxy_config.ssl_context
        cert_reqs: int | str | None

        if ssl_context is not None:
            cert_reqs = ssl_context.verify_mode
            ca_certs = ca_cert_dir = ca_cert_data = None
            ssl_version = ssl_minimum_version = ssl_maximum_version = None
            ssl_backend = None
            ciphers = None
        else:
            # Preserve the pool's TLS policy when no proxy context was supplied.
            ssl_context = self.ssl_context if self.proxy_is_forwarding else None
            cert_reqs = self.cert_reqs
            ca_certs = self.ca_certs
            ca_cert_dir = self.ca_cert_dir
            ca_cert_data = self.ca_cert_data
            ssl_version = self.ssl_version
            ssl_minimum_version = self.ssl_minimum_version
            ssl_maximum_version = self.ssl_maximum_version
            ssl_backend = self.ssl_backend
            ciphers = self.ciphers

        sock_and_verified = await _ssl_wrap_socket_and_match_hostname(
            sock,
            cert_reqs=cert_reqs,
            ssl_version=ssl_version,
            ssl_minimum_version=ssl_minimum_version,
            ssl_maximum_version=ssl_maximum_version,
            ssl_backend=ssl_backend,
            ca_certs=ca_certs,
            ca_cert_dir=ca_cert_dir,
            ca_cert_data=ca_cert_data,
            server_hostname=hostname,
            ssl_context=ssl_context,
            assert_hostname=proxy_config.assert_hostname,
            assert_fingerprint=proxy_config.assert_fingerprint,
            ciphers=ciphers,
            # Proxy client credentials belong in proxy_ssl_context.
            cert_file=None,
            key_file=None,
            key_password=None,
            tls_in_tls=False,
            alpn_protocols=alpn_protocols,
            cert_data=None,
            key_data=None,
        )
        self.proxy_is_verified = sock_and_verified.is_verified
        return sock_and_verified.socket


class _WrappedAndVerifiedSocket(typing.NamedTuple):
    """
    Wrapped socket and whether the connection is
    verified after the TLS handshake
    """

    socket: SSLAsyncSocket
    is_verified: bool


async def _ssl_wrap_socket_and_match_hostname(
    sock: AsyncSocket,
    *,
    cert_reqs: None | str | int,
    ssl_version: None | str | int,
    ssl_minimum_version: int | None,
    ssl_maximum_version: int | None,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
    cert_file: str | None,
    key_file: str | None,
    key_password: str | None,
    ca_certs: str | None,
    ca_cert_dir: str | None,
    ca_cert_data: None | str | bytes,
    assert_hostname: None | str | Literal[False],
    assert_fingerprint: str | None,
    server_hostname: str | None,
    ssl_context: ssl.SSLContext | None,
    tls_in_tls: bool = False,
    alpn_protocols: list[str] | None = None,
    cert_data: str | bytes | None = None,
    key_data: str | bytes | None = None,
    ciphers: str | None = None,
    ech_config_list: bytes | None = None,
) -> _WrappedAndVerifiedSocket:
    """Logic for constructing an SSLContext from all TLS parameters, passing
    that down into ssl_wrap_socket, and then doing certificate verification
    either via hostname or fingerprint. This function exists to guarantee
    that both proxies and targets have the same behavior when connecting via TLS.
    """
    default_ssl_context = False

    if ssl_context is None:
        default_ssl_context = True
        context = None
    else:
        context = ssl_context

    check_hostname: bool | None = None

    # In some cases, we want to verify hostnames ourselves
    if (
        # `ssl` can't verify fingerprints or alternate hostnames
        assert_fingerprint
        or assert_hostname
        # assert_hostname can be set to False to disable hostname checking
        or assert_hostname is False
        or not HAS_NEVER_CHECK_COMMON_NAME
    ):
        check_hostname = False

    # Ensure that IPv6 addresses are in the proper format and don't have a
    # scope ID. Python's SSL module fails to recognize scoped IPv6 addresses
    # and interprets them as DNS hostnames.
    if server_hostname is not None:
        normalized = server_hostname.strip("[]")
        if "%" in normalized:
            normalized = normalized[: normalized.rfind("%")]
        if is_ipaddress(normalized):
            server_hostname = normalized

    ssl_sock = await ssl_wrap_socket(
        sock=sock,
        keyfile=key_file,
        certfile=cert_file,
        key_password=key_password,
        ca_certs=ca_certs,
        ca_cert_dir=ca_cert_dir,
        ca_cert_data=ca_cert_data,
        server_hostname=server_hostname,
        ssl_context=context,
        tls_in_tls=tls_in_tls,
        alpn_protocols=alpn_protocols,
        certdata=cert_data,
        keydata=key_data,
        ciphers=ciphers,
        cert_reqs=resolve_cert_reqs(cert_reqs),
        ssl_version=resolve_ssl_version(ssl_version, mitigate_tls_version=True),
        ssl_minimum_version=ssl_minimum_version,
        ssl_maximum_version=ssl_maximum_version,
        ssl_backend=ssl_backend,
        check_hostname=check_hostname,
        ech_config_list=ech_config_list,
    )

    context = ssl_sock.context

    try:
        if assert_fingerprint:
            _assert_fingerprint(
                ssl_sock.getpeercert(binary_form=True), assert_fingerprint
            )
        elif (
            context.verify_mode != ssl.CERT_NONE
            and not context.check_hostname
            and assert_hostname is not False
        ):
            cert: _TYPE_PEER_CERT_RET_DICT = ssl_sock.getpeercert()  # type: ignore[assignment]

            # Need to signal to our match_hostname whether to use 'commonName' or not.
            # If we're using our own constructed SSLContext we explicitly set 'False'
            # because PyPy hard-codes 'True' from SSLContext.hostname_checks_common_name.
            if default_ssl_context:
                hostname_checks_common_name = False
            else:
                hostname_checks_common_name = (
                    getattr(context, "hostname_checks_common_name", False) or False
                )

            _match_hostname(
                cert,
                assert_hostname or server_hostname,  # type: ignore[arg-type]
                hostname_checks_common_name,
            )

        return _WrappedAndVerifiedSocket(
            socket=ssl_sock,
            is_verified=context.verify_mode == ssl.CERT_REQUIRED
            or bool(assert_fingerprint),
        )
    except BaseException:
        ssl_sock.close()
        try:
            await ssl_sock.wait_for_close()
        except OSError:  # Defensive: preserve the verification error if transport cleanup also fails.
            pass
        raise


class DummyConnection:
    """Used to detect a failed ConnectionCls import."""


if not ssl:
    AsyncHTTPSConnection = DummyConnection  # type: ignore[misc,assignment] # noqa: F811


VerifiedAsyncHTTPSConnection = AsyncHTTPSConnection
