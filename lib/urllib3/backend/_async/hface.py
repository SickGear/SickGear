from __future__ import annotations

import sys
import time
import typing
from datetime import datetime, timezone
from socket import SOCK_DGRAM, SOCK_STREAM
from socket import timeout as SocketTimeout

from ...contrib.anytls import ssl, Certificate

from ..._collections import HTTPHeaderDict
from ..._constant import (
    DEFAULT_BLOCKSIZE,
    DEFAULT_KEEPALIVE_DELAY,
    UDP_DEFAULT_BLOCKSIZE,
    responses,
    HTTP1_ONLY_HEADERS,
    DEFAULT_BACKGROUND_WATCH_WINDOW,
    DEFAULT_KEEPALIVE_IDLE_WINDOW,
)
from ...contrib.hface import (
    HTTP1Protocol,
    HTTP2Protocol,
    HTTP3Protocol,
    HTTPOverQUICProtocol,
    HTTPOverTCPProtocol,
    HTTPProtocolFactory,
    QuicTLSConfig,
)
from ...contrib.hface.events import (
    ConnectionTerminated,
    DataReceived,
    EarlyHeadersReceived,
    Event,
    HandshakeCompleted,
    HeadersReceived,
    StreamResetReceived,
    StreamStopSendingReceived,
)
from ...contrib.ssa import AsyncSocket, SSLAsyncSocket, _has_complete_support_dgram
from ...exceptions import (
    EarlyResponse,
    IncompleteRead,
    InvalidHeader,
    MustDowngradeError,
    ProtocolError,
    ResponseNotReady,
    SSLError,
)
from ...util import parse_alt_svc, resolve_cert_reqs, parse_url
from ...util.ssl_ import _cert_store_stats, _get_ca_certs, _load_default_certs_eagerly
from ...util.socket_state import enable_keepalive
from ...util.sub_timeout import AsyncSubTimeout
from .._base import (
    ConnectionInfo,
    HttpVersion,
    QuicPreemptiveCacheType,
    ResponsePromise,
)
from ..hface import _HAS_HTTP3_SUPPORT, _HAS_SYS_AUDIT
from ._base import AsyncBaseBackend, AsyncDirectStreamAccess, AsyncLowLevelResponse

if sys.platform == "wasi":
    try:
        from ...contrib.wasi._async.socket import AsyncSocket, SSLAsyncSocket
    except ImportError:
        pass

if typing.TYPE_CHECKING:
    from ..._typing import _TYPE_SOCKET_OPTIONS

_HAS_DGRAM_SUPPORT = _has_complete_support_dgram()


class AsyncHfaceBackend(AsyncBaseBackend):
    supported_svn = [HttpVersion.h11, HttpVersion.h2, HttpVersion.h3]

    def __init__(
        self,
        host: str,
        port: int | None = None,
        timeout: int | float | None = -1,
        source_address: tuple[str, int] | None = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        *,
        socket_options: _TYPE_SOCKET_OPTIONS
        | None = AsyncBaseBackend.default_socket_options,
        disabled_svn: set[HttpVersion] | None = None,
        preemptive_quic_cache: QuicPreemptiveCacheType | None = None,
        keepalive_delay: float | int | None = DEFAULT_KEEPALIVE_DELAY,
        background_watch_delay: int | float | None = DEFAULT_BACKGROUND_WATCH_WINDOW,
        keepalive_idle_window: int | float | None = DEFAULT_KEEPALIVE_IDLE_WINDOW,
    ):
        if not _HAS_HTTP3_SUPPORT() or not _HAS_DGRAM_SUPPORT:
            if disabled_svn is None:
                disabled_svn = set()
            disabled_svn.add(HttpVersion.h3)

        super().__init__(
            host,
            port,
            timeout,
            source_address,
            blocksize,
            socket_options=socket_options,
            disabled_svn=disabled_svn,
            preemptive_quic_cache=preemptive_quic_cache,
            keepalive_delay=keepalive_delay,
            background_watch_delay=background_watch_delay,
            keepalive_idle_window=keepalive_idle_window,
        )

        self._proxy_protocol: HTTPOverTCPProtocol | None = None
        self._protocol: HTTPOverQUICProtocol | HTTPOverTCPProtocol | None = None

        self._svn: HttpVersion | None = None

        self._stream_id: int | None = None

        # prep buffer, internal usage only.
        # not suited for HTTPHeaderDict
        self.__headers: list[tuple[bytes, bytes]] = []
        self.__expected_body_length: int | None = None
        self.__remaining_body_length: int | None = None
        self.__authority_bit_set: bool = False
        self.__legacy_host_entry: bytes | None = None
        self.__protocol_bit_set: bool = False

        # h3 specifics
        self.__custom_tls_settings: QuicTLSConfig | None = None
        self.__alt_authority: tuple[str, int] | None = None
        self.__alt_svc_checked: bool = False
        self.__origin_port: int | None = port

        # automatic upgrade shield against errors!
        self._max_tolerable_delay_for_upgrade: float | None = None

    @property
    def is_saturated(self) -> bool:
        if self._protocol is None:
            return False
        # is_available also includes whether we must goaway
        # we want to focus on stream capacity here.
        if not self._protocol.is_available():
            return not self._protocol.has_expired()
        return False

    @property
    def expect_pong(self) -> bool:
        if self._protocol is None:
            return False
        return self._protocol.expect_pong()

    @property
    def is_multiplexed(self) -> bool:
        return self._protocol is not None and self._protocol.multiplexed

    @property
    def max_frame_size(self) -> int:
        """
        The remote may require us to a lower blocksize
        than defined. This property will avoid relying
        too much on defined blocksize.
        """
        if self._protocol is None:
            return self.blocksize

        try:
            remote_max_size = self._protocol.max_frame_size()
        except NotImplementedError:
            return self.blocksize

        return remote_max_size if self.blocksize > remote_max_size else self.blocksize

    async def _new_conn(self) -> AsyncSocket | None:  # type: ignore[override]
        # handle if set up, quic cache capability. thus avoiding first TCP request prior to upgrade.
        if (
            self._svn is None
            and HttpVersion.h3 not in self._disabled_svn
            and self.scheme == "https"
        ):
            if (
                self._preemptive_quic_cache
                and (self.host, self.port) in self._preemptive_quic_cache
            ):
                self.__alt_authority = self._preemptive_quic_cache[
                    (self.host, self.port or 443)
                ]
                if self.__alt_authority:
                    self._max_tolerable_delay_for_upgrade = 1.0
                    self._svn = HttpVersion.h3
                    # we ignore alt-host as we do not trust cache security
                    self.port: int = self.__alt_authority[1]
            elif (
                HttpVersion.h11 in self._disabled_svn
                and HttpVersion.h2 in self._disabled_svn
            ):
                self.__alt_authority = (self.host, self.port or 443)
                self._svn = HttpVersion.h3
                self.port = self.__alt_authority[1]

        if self._svn == HttpVersion.h3:
            if self.blocksize == DEFAULT_BLOCKSIZE:
                self.blocksize = UDP_DEFAULT_BLOCKSIZE
            self.socket_kind = SOCK_DGRAM

            # undo local memory on whether conn supposedly support quic/h3
            # if conn target another host.
            if self._response and self._response.authority != self.host:
                self._svn = None
                self._response = None
                if self.blocksize == UDP_DEFAULT_BLOCKSIZE:
                    self.blocksize = DEFAULT_BLOCKSIZE
                self.socket_kind = SOCK_STREAM
        else:
            if self.blocksize == UDP_DEFAULT_BLOCKSIZE:
                self.blocksize = DEFAULT_BLOCKSIZE
            self.socket_kind = SOCK_STREAM

        return None

    async def _upgrade(self) -> None:  # type: ignore[override]
        assert self._response is not None, (
            "attempt to call _upgrade() prior to successful getresponse()"
        )
        assert self.sock is not None
        assert self._svn is not None

        #: Don't search for alt-svc again after finding one or after the first
        #: successful response without one.
        if self.__alt_svc_checked or self.__alt_authority is not None:
            return

        #: are we on a plain conn? unencrypted?
        is_plain_socket = type(self.sock) is AsyncSocket

        #: did the user purposely killed h3/h2 support?
        is_h3_disabled = HttpVersion.h3 in self._disabled_svn
        is_h2_disabled = HttpVersion.h2 in self._disabled_svn
        is_successful_response = 200 <= self._response.status < 300

        upgradable_svn: HttpVersion | None = None

        if is_plain_socket:
            if is_h2_disabled or self._svn == HttpVersion.h2:
                if is_successful_response:
                    self.__alt_svc_checked = True
                return
            upgradable_svn = HttpVersion.h2

            self.__alt_authority = self.__altsvc_probe(
                svc="h2c"
            )  # h2c = http2 over cleartext
        else:
            # do not upgrade if not coming from TLS already.

            # already maxed out!
            if (
                self._svn == HttpVersion.h3
            ):  # Defensive: normal QUIC connections already have an alternative authority.
                if is_successful_response:
                    self.__alt_svc_checked = True
                return

            if not is_h3_disabled and _HAS_HTTP3_SUPPORT():
                upgradable_svn = HttpVersion.h3
                self.__alt_authority = self.__altsvc_probe(svc="h3")

            # no h3 target found[...] try to locate h2 support if appropriated!
            if (
                not self.__alt_authority
                and not is_h2_disabled
                and self._svn == HttpVersion.h11
            ):
                upgradable_svn = HttpVersion.h2
                self.__alt_authority = self.__altsvc_probe(svc="h2")

        if self.__alt_authority:
            self.__alt_svc_checked = True
            # we want to infer a "best delay" to wait for silent upgrade.
            # for that we use the previous known delay for handshake or establishment.
            # and apply a "safe" margin of 50%.
            if (
                self.conn_info is not None
                and self.conn_info.established_latency is not None
            ):
                self._max_tolerable_delay_for_upgrade = (
                    self.conn_info.established_latency.total_seconds()
                )
                if self.conn_info.tls_handshake_latency is not None:
                    self._max_tolerable_delay_for_upgrade += (
                        self.conn_info.tls_handshake_latency.total_seconds()
                    )
                # initial rtt for HTTP/3 is set to 333ms
                # we need to let the QUIC state machine
                # to start loss detector at least once or
                # two before giving up.
                self._max_tolerable_delay_for_upgrade = max(
                    self._max_tolerable_delay_for_upgrade,
                    1.0,
                )
            else:  # by default (safe/conservative fallback) to 1000ms (3x 333ms rtt)
                self._max_tolerable_delay_for_upgrade = 1.0

            if upgradable_svn == HttpVersion.h3:
                if self._preemptive_quic_cache is not None:
                    self._preemptive_quic_cache[(self.host, self.port or 443)] = (
                        self.__alt_authority
                    )

                    if (self.host, self.port or 443) not in self._preemptive_quic_cache:
                        return

            self._svn = upgradable_svn
            self.__origin_port = self.port or 443
            # We purposely ignore setting the Hostname. Avoid MITM attack from local cache attack.
            self.port = self.__alt_authority[1]
            await self.close()
        elif is_successful_response:
            self.__alt_svc_checked = True

    def _custom_tls(
        self,
        ssl_context: ssl.SSLContext | None = None,
        ca_certs: str | None = None,
        ca_cert_dir: str | None = None,
        ca_cert_data: None | str | bytes = None,
        ssl_minimum_version: int | None = None,
        ssl_maximum_version: int | None = None,
        cert_file: str | bytes | None = None,
        key_file: str | bytes | None = None,
        key_password: str | bytes | None = None,
        cert_fingerprint: str | None = None,
        assert_hostname: None | str | typing.Literal[False] = None,
        cert_reqs: int | str | None = None,
    ) -> bool:
        """Meant to support TLS over QUIC meanwhile cpython does not ship with its native implementation."""
        if self._svn is not HttpVersion.h3:
            return False

        cert_use_common_name = False
        default_context = ssl_context is None

        allow_insecure: bool = False

        if not allow_insecure and resolve_cert_reqs(cert_reqs) == ssl.CERT_NONE:
            allow_insecure = True

        try:
            cert_stats = (
                _cert_store_stats(ssl_context) if ssl_context is not None else None
            )
            ssl_ctx_have_certs: bool = (
                cert_stats is not None
                and "x509_ca" in cert_stats
                and cert_stats["x509_ca"] > 0
            )
        except (
            AttributeError,
            NotImplementedError,
        ):  # Defensive: in case of ssl monkeypatch
            ssl_ctx_have_certs = False

        if (
            not allow_insecure
            and ca_certs is None
            and ca_cert_dir is None
            and ca_cert_data is None
            and not ssl_ctx_have_certs
        ):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

            if hasattr(ssl_context, "load_default_certs"):
                ssl_context.load_default_certs()
            else:
                ssl_context = None  # Defensive: alternate TLS contexts may lack load_default_certs.

        self._custom_tls_context = ssl_context

        if ssl_context:
            cert_use_common_name = (
                getattr(ssl_context, "hostname_checks_common_name", False) or False
            )

            if ssl_context.verify_mode == ssl.CERT_NONE:
                allow_insecure = True

            if ca_certs is None and ca_cert_dir is None and ca_cert_data is None:
                try:
                    ctx_root_certificates: list[bytes] = _get_ca_certs(ssl_context)
                except (
                    AttributeError,
                    NotImplementedError,
                ):  # Defensive: in case of ssl monkeypatch
                    ctx_root_certificates = []

                if not ctx_root_certificates and not allow_insecure and default_context:
                    _load_default_certs_eagerly(ssl_context)
                    ctx_root_certificates = _get_ca_certs(ssl_context)

                if ctx_root_certificates:
                    ca_cert_data = "\n".join(
                        ssl.DER_cert_to_PEM_cert(cert) for cert in ctx_root_certificates
                    )

            if (
                assert_hostname is None
                and hasattr(ssl_context, "check_hostname")
                and ssl_context.check_hostname is False
            ):
                assert_hostname = False

            # BoringSSL case ctx.
            if hasattr(ssl_context, "set_fingerprint"):
                try:
                    ssl_context.http_header_for_fingerprint()  # type: ignore[attr-defined]
                except ValueError:
                    ssl_context.set_fingerprint("chrome:stable")
                except AttributeError:  # Defensive: should be unreachable
                    pass

        self.__custom_tls_settings = QuicTLSConfig(
            insecure=allow_insecure,
            cafile=ca_certs,
            capath=ca_cert_dir,
            cadata=ca_cert_data.encode()
            if isinstance(ca_cert_data, str)
            else ca_cert_data,
            # mTLS start
            certfile=cert_file,
            keyfile=key_file,
            keypassword=key_password,
            # mTLS end
            cert_fingerprint=cert_fingerprint,
            cert_use_common_name=cert_use_common_name,
            verify_hostname=assert_hostname
            if isinstance(assert_hostname, bool)
            else True,
            assert_hostname=assert_hostname
            if isinstance(assert_hostname, str)
            else None,
            idle_timeout=self._keepalive_delay or 300.0,
            ech_config_list=self._ech_config,
        )

        self.is_verified = not self.__custom_tls_settings.insecure

        return True

    def __altsvc_probe(self, svc: str = "h3") -> tuple[str, int] | None:
        """Determine if remote yield support for an alternative service protocol."""
        # need at least first request being made
        assert self._response is not None

        for alt_svc in self._response.msg.getlist("alt-svc"):
            for protocol, alt_authority in parse_alt_svc(alt_svc):
                if protocol != svc:
                    continue

                server, port = alt_authority.split(":")

                # Security: We don't accept Alt-Svc with switching Host
                # It's up to consideration, can be a security risk.
                if server and server != self.host:
                    continue

                try:
                    return server, int(port)
                except ValueError:
                    pass

        return None

    async def _post_conn(self) -> None:  # type: ignore[override]
        if self._tunnel_host is not None:
            # Proxy-side connection: discard any stale _svn from a previous
            # target-side negotiation so ALPN (or the h11 default) takes effect.
            self._svn = None
            self._protocol = None
        else:
            assert self._protocol is None, (
                "_post_conn() must be called when socket is closed or unset"
            )
        assert self.sock is not None, (
            "probable attempt to call _post_conn() prior to successful _new_conn()"
        )

        # first request was not made yet
        if self._svn is None:
            # if we are on a TLS connection, inspect ALPN.
            is_tcp_tls_conn = isinstance(self.sock, SSLAsyncSocket)

            if is_tcp_tls_conn:
                alpn: str | None = self.sock.selected_alpn_protocol()  # type: ignore[attr-defined]

                if alpn is not None:
                    if alpn == "h2":
                        self._protocol = HTTPProtocolFactory.new(HTTP2Protocol)  # type: ignore[type-abstract]
                        self._svn = HttpVersion.h2
                    elif alpn == "http/1.1":
                        self._protocol = HTTPProtocolFactory.new(HTTP1Protocol)  # type: ignore[type-abstract]
                        self._svn = HttpVersion.h11
                    else:
                        raise ProtocolError(  # Defensive: This should be unreachable as ALPN is explicit higher in the stack.
                            f"Unsupported ALPN '{alpn}' during handshake. Did you try to reach a non-HTTP server ?"
                        )
                else:
                    # no-alpn, let's decide between H2 or H11
                    # by default, try HTTP/1.1
                    if HttpVersion.h11 not in self._disabled_svn:
                        self._protocol = HTTPProtocolFactory.new(HTTP1Protocol)  # type: ignore[type-abstract]
                        self._svn = HttpVersion.h11
                    elif HttpVersion.h2 not in self._disabled_svn:
                        self._protocol = HTTPProtocolFactory.new(HTTP2Protocol)  # type: ignore[type-abstract]
                        self._svn = HttpVersion.h2
                    else:
                        raise RuntimeError(
                            "No compatible protocol are enabled to emit request. You currently are connected using "
                            "TCP TLS and must have HTTP/1.1 or/and HTTP/2 enabled to pursue."
                        )
            else:
                # no-TLS, let's decide between H2 or H11
                # by default, try HTTP/1.1
                if HttpVersion.h11 not in self._disabled_svn:
                    self._protocol = HTTPProtocolFactory.new(HTTP1Protocol)  # type: ignore[type-abstract]
                    self._svn = HttpVersion.h11
                elif HttpVersion.h2 not in self._disabled_svn:
                    self._protocol = HTTPProtocolFactory.new(HTTP2Protocol)  # type: ignore[type-abstract]
                    self._svn = HttpVersion.h2
                else:
                    raise RuntimeError(
                        "No compatible protocol are enabled to emit request. You currently are connected using "
                        "TCP Unencrypted and must have HTTP/1.1 or/and HTTP/2 enabled to pursue."
                    )
        else:
            if self._svn == HttpVersion.h2:
                self._protocol = HTTPProtocolFactory.new(HTTP2Protocol)  # type: ignore[type-abstract]
            elif self._svn == HttpVersion.h3:
                assert self.__custom_tls_settings is not None

                self._protocol = HTTPProtocolFactory.new(
                    HTTP3Protocol,  # type: ignore[type-abstract]
                    remote_address=self.sock.getpeername(),
                    server_name=self.__custom_tls_settings.assert_hostname
                    if self.__custom_tls_settings.assert_hostname
                    else self.host,
                    tls_config=self.__custom_tls_settings,
                )

        self.conn_info = ConnectionInfo()
        self.conn_info.http_version = self._svn

        if hasattr(self, "_connect_timings") and self._connect_timings:
            self.conn_info.resolution_latency = self._connect_timings[0]
            self.conn_info.established_latency = self._connect_timings[1]

        if self._svn is not HttpVersion.h3:
            cipher_tuple: tuple[str, str, int] | None = None

            if hasattr(self.sock, "sslobj"):
                if hasattr(self.sock.sslobj, "ech_status"):  # Rustls path
                    self.conn_info.tls_ech_accepted = (
                        self.sock.sslobj.ech_status == "accepted"
                    )
                elif hasattr(self.sock.sslobj, "ech_accepted"):  # BoringSSL path
                    self.conn_info.tls_ech_accepted = self.sock.sslobj.ech_accepted()
                else:
                    self.conn_info.tls_ech_accepted = False

                self.conn_info.certificate_der = self.sock.sslobj.getpeercert(
                    binary_form=True
                )
                try:
                    self.conn_info.certificate_dict = self.sock.sslobj.getpeercert(
                        binary_form=False
                    )
                except ValueError:  # Defensive: alternate TLS engines may not expose parsed peer certificates.
                    # not supported on MacOS!
                    self.conn_info.certificate_dict = None

                self.conn_info.destination_address = None
                cipher_tuple = self.sock.sslobj.cipher()

                # Python 3.10+
                if hasattr(self.sock.sslobj, "_sslobj") and hasattr(
                    self.sock.sslobj._sslobj, "get_verified_chain"
                ):
                    chain = self.sock.sslobj._sslobj.get_verified_chain()

                    cert_in_chain_count: int = len(chain)
                    parsed_certs: bool = (
                        all(isinstance(crt, Certificate) for crt in chain)
                        if Certificate is not None
                        else False
                    )

                    if parsed_certs:
                        if not self.conn_info.certificate_dict and cert_in_chain_count:
                            self.conn_info.certificate_dict = chain[0].get_info()

                        if cert_in_chain_count > 1:
                            issuer_public_bytes = chain[1].public_bytes()
                            if isinstance(issuer_public_bytes, bytes):
                                self.conn_info.issuer_certificate_der = (
                                    issuer_public_bytes
                                )
                            elif hasattr(ssl, "PEM_cert_to_DER_cert"):
                                self.conn_info.issuer_certificate_der = (
                                    ssl.PEM_cert_to_DER_cert(issuer_public_bytes)
                                )
                            self.conn_info.issuer_certificate_dict = chain[1].get_info()
                    elif cert_in_chain_count > 1:
                        self.conn_info.issuer_certificate_der = chain[1]

            if cipher_tuple:
                self.conn_info.cipher = cipher_tuple[0]
                if cipher_tuple[1] == "TLSv1.0":
                    self.conn_info.tls_version = ssl.TLSVersion.TLSv1
                elif cipher_tuple[1] == "TLSv1.1":
                    self.conn_info.tls_version = ssl.TLSVersion.TLSv1_1  # Defensive: metadata compatibility for explicitly enabled legacy TLS 1.1.
                elif cipher_tuple[1] == "TLSv1.2":
                    self.conn_info.tls_version = ssl.TLSVersion.TLSv1_2
                elif cipher_tuple[1] == "TLSv1.3":
                    self.conn_info.tls_version = ssl.TLSVersion.TLSv1_3
                else:
                    self.conn_info.tls_version = None

            if self.conn_info.destination_address is None and hasattr(
                self.sock, "getpeername"
            ):
                self.conn_info.destination_address = self.sock.getpeername()[:2]

        # fallback to http/1.1
        if self._protocol is None or self._svn == HttpVersion.h11:
            if (
                self._protocol is None and HttpVersion.h11 in self._disabled_svn
            ):  # Defensive: custom initialization may leave protocol selection incomplete.
                self._protocol = HTTPProtocolFactory.new(HTTP2Protocol)  # type: ignore[type-abstract]
                self._svn = HttpVersion.h2
            else:
                self._protocol = HTTPProtocolFactory.new(HTTP1Protocol)  # type: ignore[type-abstract]
                self._svn = HttpVersion.h11

                if self._background_watch_delay and self._keepalive_idle_window:
                    enable_keepalive(
                        self.sock,
                        int(self._keepalive_idle_window),
                        int(self._background_watch_delay),
                    )

            self.conn_info.http_version = self._svn

            if (
                self.conn_info.certificate_der
                and hasattr(self, "_connect_timings")
                and self._connect_timings
            ):
                self.conn_info.tls_handshake_latency = (
                    datetime.now(tz=timezone.utc) - self._connect_timings[-1]
                )

            self._connected_at = time.monotonic()
            return

        # we want to purposely mitigate the following scenario:
        #   "A server yield its support for HTTP/2 or HTTP/3 through Alt-Svc, but
        #    it cannot connect to the alt-svc, thus confusing the end-user on why it
        #    waits forever for the 2nd request."
        if self._max_tolerable_delay_for_upgrade is not None:
            self.sock.settimeout(self._max_tolerable_delay_for_upgrade)

        # it may be required to send some initial data, aka. magic header (PRI * HTTP/2..)
        try:
            await self.__exchange_until(
                HandshakeCompleted,
                receive_first=False,
            )
        except (
            ProtocolError,
            TimeoutError,
            SocketTimeout,
            ConnectionRefusedError,
            ConnectionResetError,
            PermissionError,
        ) as e:
            # DNS HTTPS records can select QUIC without an Alt-Svc authority.
            if self._svn is HttpVersion.h3 or (
                self.__alt_authority is not None and not isinstance(e, PermissionError)
            ):
                # we want to remove invalid quic cache capability
                # because the alt-svc was probably bogus...
                if (
                    self._svn == HttpVersion.h3
                    and self._preemptive_quic_cache is not None
                ):
                    alt_key = (self.host, self.__origin_port or 443)
                    if alt_key in self._preemptive_quic_cache:
                        del self._preemptive_quic_cache[alt_key]

                # this avoid the close() to attempt reuse the (dead) sock
                self._protocol = None

                # we don't want to force downgrade if the user specifically said
                # to kill support for all other supported protocols!
                if (
                    HttpVersion.h11 not in self.disabled_svn
                    or HttpVersion.h2 not in self.disabled_svn
                ):
                    raise MustDowngradeError(
                        f"Could not complete the {self._svn} handshake with {self.host}:{self.port}."
                    ) from e
            raise

        self._connected_at = time.monotonic()

        if self._max_tolerable_delay_for_upgrade is not None:
            self.sock.settimeout(self.timeout)

        self._max_tolerable_delay_for_upgrade = (
            None  # upgrade went fine. discard the value!
        )

        if isinstance(self._protocol, HTTPOverQUICProtocol):
            self.conn_info.certificate_der = self._protocol.getpeercert(
                binary_form=True
            )
            self.conn_info.certificate_dict = self._protocol.getpeercert(
                binary_form=False
            )
            self.conn_info.destination_address = self.sock.getpeername()[:2]
            self.conn_info.cipher = self._protocol.cipher()
            self.conn_info.tls_version = ssl.TLSVersion.TLSv1_3
            self.conn_info.tls_ech_accepted = self._protocol.ech_accepted()
            self.conn_info.issuer_certificate_dict = self._protocol.getissuercert(
                binary_form=False
            )
            self.conn_info.issuer_certificate_der = self._protocol.getissuercert(
                binary_form=True
            )

        if (
            self.conn_info.certificate_der
            and hasattr(self, "_connect_timings")
            and not self.conn_info.tls_handshake_latency
        ):
            self.conn_info.tls_handshake_latency = (
                datetime.now(tz=timezone.utc) - self._connect_timings[-1]
            )

    def set_tunnel(
        self,
        host: str,
        port: int | None = None,
        headers: typing.Mapping[str, str] | None = None,
        scheme: str = "http",
    ) -> None:
        if self.sock:
            # overly protective, checks are made higher, this is unreachable.
            raise RuntimeError(  # Defensive: highly controlled, should be unreachable.
                "Can't set up tunnel for established connection"
            )

        # We either support tunneling or http/3. Need complex developments.
        if HttpVersion.h3 not in self._disabled_svn:
            self._disabled_svn.add(HttpVersion.h3)

        self._tunnel_host: str | None = host
        self._tunnel_port: int | None = port

        if headers:
            self._tunnel_headers = headers
        else:
            self._tunnel_headers = {}

    async def _tunnel(self) -> None:  # type: ignore[override]
        assert self._protocol is not None
        assert self.sock is not None
        assert self._tunnel_host is not None
        assert self._tunnel_port is not None

        if self._svn != HttpVersion.h11:
            raise NotImplementedError(
                """Unable to establish a tunnel using other than HTTP/1.1."""
            )

        self._stream_id = self._protocol.get_available_stream_id()

        req_context = [
            (b":method", b"CONNECT"),
            (
                b":authority",
                f"{self._tunnel_host}:{self._tunnel_port}".encode("ascii"),
            ),
        ]

        for header, value in self._tunnel_headers.items():
            req_context.append((header.lower().encode(), value.encode("iso-8859-1")))

        self._protocol.submit_headers(
            self._stream_id,
            req_context,
            True,
        )

        events = await self.__exchange_until(
            HeadersReceived,
            receive_first=False,
            # Consume informational proxy responses; only final headers decide success.
            event_type_collectable=(HeadersReceived, EarlyHeadersReceived),
            # special case for CONNECT
            respect_end_stream_signal=False,
        )

        status: int | None = None

        for event in events:
            if isinstance(event, HeadersReceived):
                for raw_header, raw_value in event.headers:
                    if raw_header == b":status":
                        status = int(raw_value.decode())
                        break

        tunnel_accepted: bool = status is not None and (200 <= status < 300)

        if not tunnel_accepted:
            await self.close()
            message: str = (
                responses[status] if status and status in responses else "Unknown"
            )
            raise OSError(f"Tunnel connection failed: {status} {message}")

        # We will re-initialize those afterward
        # to be in phase with Us --> NotIntermediary
        self._svn = None
        self._protocol = None
        self._protocol_factory = None

    async def peek_and_react(self, expect_frame: bool = False) -> bool:
        """Inspect unsolicited input while holding the connection checkout.

        Return True when input or a connection failure was observed, so the
        caller can recheck connection state. False means no new state was seen.
        The idle watcher coordinates this operation through TrafficPolice.

        Multiplexed peers can send control frames without a new request. QUIC
        peers may also require acknowledgements to keep an idle connection alive.
        See the `quiche idle-connection change
        <https://github.com/google/quiche/commit/c4bb0723f0a03e135bc9328b59a39382761f3de6>`_.

        :param expect_frame: Allow a short receive wait when a peer frame is expected.
        """
        if self.sock is None or self._protocol is None:
            return False

        # An empty reader only means the transport has not delivered input yet.
        # PONG checks retain their bounded wait for the transport callback.
        try:
            if not expect_frame and not self.expect_pong and not self.sock.read_ready():
                return False
        except OSError:
            self._protocol.connection_lost()
            return True

        bck_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.1 if expect_frame else 0.001)

        try:
            try:
                peek_data = await self.sock.recv(self.blocksize)
            except (SocketTimeout, BlockingIOError):
                return False
            except OSError:
                self._protocol.connection_lost()
                return True

            if not peek_data:
                if self.sock.type == SOCK_STREAM:
                    self._protocol.connection_lost()
                return True

            try:
                if isinstance(peek_data, list):
                    self._protocol.many_bytes_received(peek_data)  # type: ignore[union-attr]
                else:
                    self._protocol.bytes_received(peek_data)
            except self._protocol.exceptions():
                self._protocol.connection_lost()
                return True

            while True:
                data_out = self._protocol.bytes_to_send()

                if not data_out:
                    break

                try:
                    await self.sock.sendall(data_out)
                except OSError:
                    self._protocol.connection_lost()
                    return True

            self._last_used_at = time.monotonic()

            return True
        finally:
            self.sock.settimeout(bck_timeout)

    async def __exchange_until(
        self,
        event_type: type[Event] | tuple[type[Event], ...],
        *,
        receive_first: bool = False,
        event_type_collectable: type[Event] | tuple[type[Event], ...] | None = None,
        respect_end_stream_signal: bool = True,
        maximal_data_in_read: int | None = None,
        data_in_len_from: typing.Callable[[Event], int] | None = None,
        stream_id: int | None = None,
    ) -> list[Event]:
        """This method simplify socket exchange in/out based on what the protocol state machine orders.
        Can be used for the initial handshake for instance."""
        assert self.sock is not None and self._protocol is not None

        protocol = self._protocol
        sock = self.sock
        blocksize = self.blocksize
        is_h3 = self._svn is HttpVersion.h3
        _has_next_timer = hasattr(protocol, "next_timer")
        _proto_exc = protocol.exceptions()

        async def send_pending() -> None:
            tbs: list[bytes] = []
            while True:
                data_out = protocol.bytes_to_send()
                if not data_out:
                    break
                tbs.append(data_out)
            if is_h3 and len(tbs) > 1:
                await sock.sendall(tbs)
            else:
                for chunk in tbs:
                    await sock.sendall(chunk)

        if maximal_data_in_read is not None:
            if not (maximal_data_in_read >= 0 or maximal_data_in_read == -1):
                maximal_data_in_read = None  # Defensive: public response reads normalize negative sizes first.

        data_in: bytes | list[bytes]

        data_in_len: int = 0

        events: list[Event] = []
        reshelve_events: list[Event] = []

        if maximal_data_in_read == 0:
            # The '0' case amt is handled higher in the stack.
            return events  # Defensive: This should be unreachable in the current project state.

        if maximal_data_in_read and maximal_data_in_read < 0:
            respect_end_stream_signal = False
            maximal_data_in_read = None
            data_in_len_from = None

        while True:
            reach_socket: bool = False
            if not protocol.has_pending_event(stream_id=stream_id):
                if not receive_first:
                    await send_pending()

                next_timer = protocol.next_timer() if _has_next_timer else None  # type: ignore[union-attr]
                sub = AsyncSubTimeout(sock, next_timer, send_pending)
                try:
                    async with sub:
                        data_in = await sock.recv(blocksize)
                except (
                    ConnectionAbortedError,
                    ConnectionResetError,
                    ConnectionRefusedError,
                ) as e:
                    if isinstance(e, ConnectionResetError) and (
                        event_type is HandshakeCompleted
                        or (
                            isinstance(event_type, tuple)
                            and HandshakeCompleted in event_type
                        )
                    ):
                        raise e
                    data_in = b""

                if sub.timer_fired:
                    continue

                reach_socket = True

                if not data_in:
                    # in some cases (merely http/1 legacy)
                    # server can signify "end-of-transmission" by simply closing the socket.
                    # pretty much dirty.

                    # must have at least one event received, otherwise we can't declare a proper eof.
                    if (events or self._response is not None) and hasattr(
                        protocol, "eof_received"
                    ):
                        try:
                            protocol.eof_received()
                        except _proto_exc as e:  # Defensive: built-in EOF handlers report termination through events.
                            # overly protective, we hide exception that are behind urllib3.
                            # should not happen, but one truly never known.
                            raise ProtocolError(e) from e  # Defensive:
                    else:
                        protocol.connection_lost()
                else:
                    if isinstance(data_in, list):
                        try:
                            protocol.many_bytes_received(data_in)  # type: ignore[union-attr]
                        except _proto_exc as e:
                            # h2 has a dedicated exception for IncompleteRead (InvalidBodyLengthError)
                            # we convert the exception to our "IncompleteRead" instead.
                            if hasattr(e, "expected_length") and hasattr(
                                e, "actual_length"
                            ):
                                raise IncompleteRead(
                                    partial=e.actual_length,
                                    expected=e.expected_length,
                                ) from e  # Defensive:
                            raise ProtocolError(e) from e  # Defensive:
                    else:
                        incoming_buffer_size = len(data_in)
                        self._recv_size_ema = (
                            self._recv_size_ema * 0.7 + incoming_buffer_size * 0.3
                        )

                        try:
                            protocol.bytes_received(data_in)
                        except _proto_exc as e:
                            # h2 has a dedicated exception for IncompleteRead (InvalidBodyLengthError)
                            # we convert the exception to our "IncompleteRead" instead.
                            if hasattr(e, "expected_length") and hasattr(
                                e, "actual_length"
                            ):
                                raise IncompleteRead(
                                    partial=e.actual_length, expected=e.expected_length
                                ) from e  # Defensive:
                            raise ProtocolError(e) from e  # Defensive:

                if receive_first:
                    await send_pending()

            for event in protocol.events(stream_id=stream_id):  # type: Event
                if isinstance(event, StreamStopSendingReceived):
                    continue  # Only the upload ended; keep waiting for the response.
                stream_related_event: bool = hasattr(event, "stream_id")

                if not stream_related_event and isinstance(event, ConnectionTerminated):
                    self._protocol = (
                        None  # the state machine protocol reached final state and
                    )

                    await self.close()
                    # Only HTTP/1 can delimit a response body by closing the connection.
                    # HTTP/2 and HTTP/3 require the response stream to end explicitly.
                    if (
                        self._svn is HttpVersion.h11
                        and event.error_code == 0
                        and stream_id is not None
                        and (
                            event_type is DataReceived
                            or (
                                isinstance(event_type, tuple)
                                and DataReceived in event_type
                            )
                        )
                    ):
                        events.append(
                            DataReceived(
                                stream_id,
                                b"",
                                end_stream=True,
                            )
                        )

                        return events

                    # we can receive a zero-length payload, that usually means the remote closed the socket.
                    # while we could retry this, we should not as some servers can have tricky edge cases
                    # where a request could actually be executed without you knowing so.
                    # see https://github.com/jawah/urllib3.future/issues/280 for the rationale behind this change.
                    if (
                        reach_socket
                        and data_in == b""
                        and (
                            (
                                isinstance(event_type, tuple)
                                and HeadersReceived in event_type
                            )
                            or (event_type is HeadersReceived)
                        )
                        and not any(isinstance(e, HeadersReceived) for e in events)
                    ):
                        # Let downstream retry handlers recognize the remote close.
                        message = "Remote end closed connection without response"
                        raise ProtocolError(message) from ConnectionResetError(message)

                    if event.is_tls_error:
                        raise SSLError(event.message)
                    if (
                        event.error_code == 400
                        and event.message
                        and "header" in event.message
                    ):
                        raise InvalidHeader(event.message)

                    # we shall convert the ProtocolError to IncompleteRead
                    # so that users aren't caught off guard.
                    try:
                        if (
                            event.message
                            and "without sending complete message body" in event.message
                        ):
                            msg = event.message.replace(
                                "peer closed connection without sending complete message body ",
                                "",
                            ).strip("()")

                            received, expected = (
                                int("".join(c for c in _ if c.isdigit()).strip())
                                for _ in tuple(msg.split(", "))
                            )

                            raise IncompleteRead(
                                partial=received,
                                expected=expected - received,
                            )
                    except (ValueError, IndexError):
                        pass

                    raise ProtocolError(event.message)
                elif stream_related_event and isinstance(event, StreamResetReceived):
                    # we want to catch MUST_USE_HTTP_1_1 or H3_VERSION_FALLBACK
                    # HTTP/2 https://www.rfc-editor.org/rfc/rfc9113.html#name-error-codes
                    # HTTP/3 https://www.iana.org/assignments/http3-parameters/http3-parameters.xhtml#http3-parameters-error-codes
                    if (self._svn == HttpVersion.h2 and event.error_code == 0xD) or (
                        self._svn == HttpVersion.h3 and event.error_code == 0x0110
                    ):
                        if HttpVersion.h11 not in self.disabled_svn:
                            raise MustDowngradeError(
                                f"The remote server is unable to serve this resource over {self._svn}"
                            )

                    raise ProtocolError(
                        f"Stream {event.stream_id} was reset by remote peer. Reason: {hex(event.error_code)}."
                    )

                if not event_type_collectable:
                    events.append(event)
                else:
                    if isinstance(event, event_type_collectable):
                        events.append(event)

                        if data_in_len_from:
                            try:
                                data_in_len += data_in_len_from(event)
                            except AttributeError:
                                pass
                    else:
                        reshelve_events.append(event)

                # Finish inspecting queued events before accepting the handshake.
                # A peer may already have rejected it; no further socket read is needed.
                if event_type is HandshakeCompleted:
                    continue

                target_cap_reached: bool = (
                    maximal_data_in_read is not None
                    and data_in_len >= maximal_data_in_read
                )

                if isinstance(event, event_type) or target_cap_reached:
                    # if event type match, make sure it is the latest one
                    # simply put, end_stream should be True.
                    if (
                        not target_cap_reached
                        and respect_end_stream_signal
                        and stream_related_event
                    ):
                        if event.end_stream:  # type: ignore[attr-defined]
                            if reshelve_events:
                                protocol.reshelve(*reshelve_events)
                            return events

                        # serving a sized body read (maximal_data_in_read is set)
                        # and some data has been collected already: return it now
                        # instead of blocking on the socket until the cap is
                        # reached. A live stream (e.g. SSE) may leave the
                        # connection idle long after sending a partial payload.
                        # see https://github.com/jawah/urllib3.future/issues/379
                        if maximal_data_in_read is not None and data_in_len > 0:
                            if reshelve_events:
                                protocol.reshelve(*reshelve_events)
                            return events

                        continue

                    if reshelve_events:
                        protocol.reshelve(*reshelve_events)
                    return events
                elif (
                    stream_related_event
                    and event.end_stream  # type: ignore[attr-defined]
                    and respect_end_stream_signal
                ):
                    if reshelve_events:
                        protocol.reshelve(*reshelve_events)
                    return events
                elif (
                    stream_related_event
                    and event.end_stream  # type: ignore[attr-defined]
                    and maximal_data_in_read is None
                    and event_type_collectable is not None
                    and stream_id == event.stream_id  # type: ignore[attr-defined]
                ):
                    if reshelve_events:
                        protocol.reshelve(*reshelve_events)
                    return events

            if event_type is HandshakeCompleted and any(
                isinstance(event, HandshakeCompleted) for event in events
            ):
                return events

    def putrequest(
        self,
        method: str,
        url: str,
        skip_host: bool = False,
        skip_accept_encoding: bool = False,
    ) -> None:
        """Internally fhace translate this into what putrequest does. e.g. initial trame."""
        self.__expected_body_length = None
        self.__remaining_body_length = None
        self.__legacy_host_entry = None
        self.__authority_bit_set = False
        self.__protocol_bit_set = False

        self._start_last_request = datetime.now(timezone.utc)

        if self._tunnel_host is not None:
            host, port = self._tunnel_host, self._tunnel_port
        else:
            host, port = self.host, self.port

            if url.startswith("http"):
                # stdlib http.client always set "Host" to
                # url parsed netloc by default.
                # bug originally found at https://github.com/jawah/niquests/issues/355
                parsed_url = parse_url(url)

                if parsed_url.host != host:
                    host, port = parsed_url.host, parsed_url.port or self.default_port  # type: ignore[attr-defined,assignment]

        self.__headers = [
            (b":method", method.encode("ascii")),
        ]

        if not skip_host:
            authority: bytes = host.encode("idna")

            self.__headers.append(
                (
                    b":authority",
                    authority
                    if port == self.default_port or port is None  # type: ignore[attr-defined]
                    else authority + f":{port}".encode(),
                ),
            )
            self.__authority_bit_set = True

        self.__headers.extend(
            [
                (
                    b":scheme",
                    self.scheme.encode("ascii"),
                ),
                (b":path", url.encode("ascii")),
            ]
        )

        if not skip_accept_encoding:
            self.__headers.append(
                (
                    b"accept-encoding",
                    b"identity",
                )
            )

    def putheader(self, header: str, *values: str) -> None:
        # note: requests allow passing headers as bytes (seen in requests/tests)
        # warn: always lowercase header names, quic transport crash if not lowercase.
        header = header.lower()

        encoded_header = header.encode("ascii") if isinstance(header, str) else header

        # only h11 support chunked transfer encoding, we internally translate
        # it to the right method for h2 and h3.
        support_te_chunked: bool = self._svn == HttpVersion.h11

        # We MUST never use that header in h2 and h3 over quic.
        # Passing 'Connection' header is actually a protocol violation above h11.
        # We assume it is passed as-is (meaning 'keep-alive' lower-cased)
        # It may(should) break the connection.
        if not support_te_chunked:
            if encoded_header in HTTP1_ONLY_HEADERS:
                return

        if self.__expected_body_length is None and encoded_header == b"content-length":
            try:
                self.__expected_body_length = int(values[0])
            except ValueError:
                raise ProtocolError(
                    f"Invalid content-length set. Given '{values[0]}' when only digits are allowed."
                )
        elif self.__legacy_host_entry is None and encoded_header == b"host":
            if isinstance(values[0], str):
                self.__legacy_host_entry = values[0].encode("idna")
            elif isinstance(values[0], bytes):
                self.__legacy_host_entry = values[0]
            else:
                self.__legacy_host_entry = str(values[0]).encode("iso-8859-1")
            return

        for value in values:
            if isinstance(value, str):
                encoded_value = value.encode("iso-8859-1")
            elif isinstance(value, bytes):
                encoded_value = value
            else:  # best effort branch
                encoded_value = str(value).encode("iso-8859-1")

            if encoded_header.startswith(b":"):
                if encoded_header == b":protocol":
                    self.__protocol_bit_set = True
                item_to_remove = None

                for _k, _v in self.__headers:
                    if not _k.startswith(b":"):
                        break
                    if _k == encoded_header:
                        item_to_remove = (_k, _v)
                        break

                if item_to_remove is not None:
                    self.__headers.remove(item_to_remove)

                self.__headers.insert(
                    0,
                    (
                        encoded_header,
                        encoded_value,
                    ),
                )
            else:
                self.__headers.append(
                    (
                        encoded_header,
                        encoded_value,
                    )
                )

    async def endheaders(  # type: ignore[override]
        self,
        message_body: bytes | None = None,
        *,
        encode_chunked: bool = False,
        expect_body_afterward: bool = False,
    ) -> ResponsePromise | None:
        if self.sock is None:
            await self.connect()  # type: ignore[attr-defined]

        # some libraries override connect(), thus bypassing our state machine initialization.
        if self._protocol is None:
            await self._post_conn()

        assert self.sock is not None and self._protocol is not None

        # only h2 and h3 support streams, it is faked/simulated for h1.
        self._stream_id = self._protocol.get_available_stream_id()
        # unless anything hint the opposite, the request head frame is the end stream
        should_end_stream: bool = (
            not expect_body_afterward and not self.__protocol_bit_set
        )

        # handle cases where 'Host' header is set manually
        if self.__legacy_host_entry is not None:
            existing_authority = None

            for cursor_header, cursor_value in self.__headers:
                if cursor_header == b":authority":
                    existing_authority = (cursor_header, cursor_value)
                    break
                if not cursor_header.startswith(b":"):
                    break

            if existing_authority is not None:
                self.__headers.remove(existing_authority)

            self.__headers.insert(3, (b":authority", self.__legacy_host_entry))
            self.__authority_bit_set = True

        if not self.__authority_bit_set:
            raise ProtocolError(
                (
                    "urllib3.future do not support emitting HTTP requests without the `Host` header ",
                    "It was only permitted in HTTP/1.0 and prior. This client support HTTP/1.1+.",
                )
            )

        try:
            self._protocol.submit_headers(
                self._stream_id,
                self.__headers,
                end_stream=should_end_stream,
            )
        except self._protocol.exceptions() as e:  # Defensive:
            # overly protective, designed to avoid exception leak below urllib3.
            raise ProtocolError(e) from e  # Defensive:

        try:
            tbs = []

            while True:
                buf = self._protocol.bytes_to_send()
                if not buf:
                    break
                tbs.append(buf)

            if self._svn is HttpVersion.h3 and len(tbs) > 1:
                await self.sock.sendall(tbs)
            else:
                for chunk in tbs:
                    await self.sock.sendall(chunk)
        except BrokenPipeError as e:
            rp = ResponsePromise(self, self._stream_id, self.__headers)
            self._promises[rp.uid] = rp
            self._promises_per_stream[rp.stream_id] = rp
            e.promise = rp  # type: ignore[attr-defined]

            raise e
        else:
            self._last_used_at = time.monotonic()

        if not expect_body_afterward:
            if self._start_last_request and self.conn_info:
                self.conn_info.request_sent_latency = (
                    datetime.now(tz=timezone.utc) - self._start_last_request
                )

            rp = ResponsePromise(self, self._stream_id, self.__headers)
            self._promises[rp.uid] = rp
            self._promises_per_stream[rp.stream_id] = rp
            return rp

        return None

    async def __write_st(
        self, __buf: bytes, __stream_id: int, __close_stream: bool = False
    ) -> None:
        assert self._protocol is not None
        assert self.sock is not None

        _has_next_timer = hasattr(self._protocol, "next_timer")

        async def send_pending() -> None:
            while True:
                data_out = self._protocol.bytes_to_send()  # type: ignore[union-attr]
                if not data_out:
                    break
                await self.sock.sendall(data_out)  # type: ignore[union-attr]

        while (
            self._protocol.should_wait_remote_flow_control(__stream_id, len(__buf))
            is True
        ):
            next_timer = self._protocol.next_timer() if _has_next_timer else None  # type: ignore[union-attr]
            sub = AsyncSubTimeout(self.sock, next_timer, send_pending)
            async with sub:
                data_in = await self.sock.recv(self.blocksize)

            if sub.timer_fired:
                continue

            # TCP EOF cannot replenish flow-control credit.
            if not data_in and self._svn is not HttpVersion.h3:
                self._protocol.connection_lost()
                raise ProtocolError("Connection closed while waiting for flow control")

            if isinstance(data_in, list):
                for gro_segment in data_in:
                    self._protocol.bytes_received(gro_segment)
            else:
                self._protocol.bytes_received(data_in)

            await send_pending()

        self._protocol.submit_data(
            __stream_id,
            __buf,
            end_stream=__close_stream,
        )

        while True:
            data_out = self._protocol.bytes_to_send()

            if not data_out:
                break

            await self.sock.sendall(data_out)

        self._last_used_at = time.monotonic()

    async def __abort_st(self, __stream_id: int) -> None:
        """Kill a stream properly."""
        self._pending_responses.pop(__stream_id, None)
        if self._protocol is None or self.sock is None:
            return

        self._protocol.submit_stream_reset(stream_id=__stream_id)

        while True:
            data_out = self._protocol.bytes_to_send()

            if not data_out:
                break

            await self.sock.sendall(data_out)

        # remote can refuse future inquiries, so no need to go further with this conn.
        if self._protocol.has_expired():
            await self.close()

        self._last_used_at = time.monotonic()

    async def __read_st(
        self,
        __amt: int | None,
        __stream_id: int | None,
        __respect_end_signal: bool = True,
        __dummy_operation: bool = False,
    ) -> tuple[list[bytes], bool, HTTPHeaderDict | None]:
        """Allows us to defer the body loading after constructing the response object.

        Returns the body as a list of per-frame chunks (not concatenated):
        the caller feeds them straight into its ``BytesQueueBuffer`` so
        contiguity is produced lazily and, for frame-aligned reads,
        zero-copy. Joining here would defeat that buffer.
        """

        # we may want to just remove the response as "pending"
        # e.g. HTTP Extension; making reads on sub protocol close may
        # ends up in a blocking situation (forever).
        if __dummy_operation:
            try:
                del self._pending_responses[__stream_id]  # type: ignore[arg-type]
            except KeyError:
                pass  # Hmm... this should be impossible.

            if self._protocol is not None:
                # remote can refuse future inquiries, so no need to go further with this conn.
                if self._protocol.is_idle() and self._protocol.has_expired():
                    await self.close()
            return [], True, None

        eot = False

        events: list[DataReceived | HeadersReceived] = await self.__exchange_until(  # type: ignore[assignment]
            DataReceived,
            receive_first=True,
            event_type_collectable=(
                DataReceived,
                HeadersReceived,
            ),
            maximal_data_in_read=__amt,
            # Unbounded reads have no byte target to track.
            data_in_len_from=(
                (lambda x: len(x.data)) if __amt is not None else None  # type: ignore[attr-defined]
            ),
            stream_id=__stream_id,
            respect_end_stream_signal=__respect_end_signal,
        )

        self._last_used_at = time.monotonic()

        if events and events[-1].end_stream:
            eot = True

            try:
                del self._pending_responses[__stream_id]  # type: ignore[arg-type]
            except KeyError:
                pass  # Hmm... this should be impossible.

            if self._protocol is not None:
                # remote can refuse future inquiries, so no need to go further with this conn.
                if self._protocol.is_idle() and self._protocol.has_expired():
                    await self.close()
                elif self.is_idle:
                    # probe for h3/quic if available, and remember it.
                    await self._upgrade()

        trailers = None

        if eot:
            idx = None

            if isinstance(events[-1], HeadersReceived):
                idx = -1
            elif len(events) >= 2 and isinstance(events[-2], HeadersReceived):
                idx = -2

            # http-trailers SHOULD be received LAST!
            # but we should tolerate a DataReceived of len=0 last, just in case.
            if idx is not None:
                trailers = HTTPHeaderDict()

                for raw_header, raw_value in events[idx].headers:  # type: ignore[union-attr]
                    # ignore...them? special headers. aka. starting with semicolon
                    if raw_header[0] == 0x3A:
                        continue
                    else:
                        trailers.add(
                            raw_header.decode("ascii"), raw_value.decode("iso-8859-1")
                        )

                events.pop(idx)

                if not events:
                    return [], True, trailers

        return (
            [e.data for e in events],  # type: ignore[union-attr]
            eot,
            trailers,
        )

    async def getresponse(  # type: ignore[override]
        self,
        *,
        promise: ResponsePromise | None = None,
        early_response_callback: typing.Callable[
            [AsyncLowLevelResponse], typing.Awaitable[None]
        ]
        | None = None,
    ) -> AsyncLowLevelResponse:
        if self.sock is None or self._protocol is None or not self._promises:
            raise ResponseNotReady()  # Defensive: Comply with http.client, actually tested but not reported?

        headers = HTTPHeaderDict()
        status: int | None = None

        if not self.is_multiplexed:
            stream_id = self._stream_id
        else:
            stream_id = promise.stream_id if promise else None

        head_event: HeadersReceived | EarlyHeadersReceived = (
            await self.__exchange_until(  # type: ignore[assignment]
                (
                    HeadersReceived,
                    EarlyHeadersReceived,
                ),
                receive_first=True,
                event_type_collectable=(
                    HeadersReceived,
                    EarlyHeadersReceived,
                ),
                respect_end_stream_signal=False,
                stream_id=stream_id,
            )
        ).pop()

        # we want to have a view on last conn was used
        # ...in the sense that we spoke with the remote peer.
        self._last_used_at = time.monotonic()

        for raw_header, raw_value in head_event.headers:
            # special headers that represent (usually) the HTTP response status, version and reason.
            if status is None and raw_header[0] == 0x3A:
                if raw_header == b":status":
                    status = int(raw_value)
            else:
                headers.add(raw_header.decode("ascii"), raw_value.decode("iso-8859-1"))

        # 101 = Switching Protocol! It's our final HTTP response, but the stream remains open!
        is_early_response = (
            isinstance(head_event, EarlyHeadersReceived) and status != 101
        )

        if promise is None:
            try:
                if is_early_response:
                    promise = self._promises_per_stream[head_event.stream_id]
                else:
                    promise = self._promises_per_stream.pop(head_event.stream_id)
            except KeyError as e:  # Defensive: built-in protocols filter streams without an originating promise.
                raise ProtocolError(
                    f"Response received (stream: {head_event.stream_id}) but no promise in-flight"
                ) from e
        else:
            if not is_early_response:
                del self._promises_per_stream[promise.stream_id]

        # this should be unreachable
        if status is None:
            raise ProtocolError(  # Defensive: This is unreachable, all three implementations crash before.
                "Got an HTTP response without a status code. This is a violation."
            )

        eot = head_event.end_stream
        http_verb = b""

        for raw_header, raw_value in promise.request_headers:
            if raw_header == b":method":
                http_verb = raw_value
                break

        if status == 101 or (http_verb == b"CONNECT" and (200 <= status < 300)):
            dsa: AsyncDirectStreamAccess | None = AsyncDirectStreamAccess(
                promise.stream_id,
                self.__read_st,
                self.__write_st,
            )
        else:
            dsa = None

        try:
            reason: str = responses[status]
        except KeyError:
            reason = "Unknown"

        if is_early_response:
            if early_response_callback is not None:
                early_response = AsyncLowLevelResponse(
                    http_verb.decode("ascii"),
                    status,
                    self._http_vsn,
                    reason,
                    headers,
                    body=None,
                    authority=self.host,
                    port=self.port,
                    stream_id=promise.stream_id,
                )
                early_response.from_promise = promise

                await early_response_callback(early_response)

            return await AsyncHfaceBackend.getresponse(
                self, promise=promise, early_response_callback=early_response_callback
            )

        self._response = AsyncLowLevelResponse(
            http_verb.decode("ascii"),
            status,
            self._http_vsn,
            reason,
            headers,
            self.__read_st if not eot and dsa is None else None,
            authority=self.host,
            port=self.port,
            stream_id=promise.stream_id,
            dsa=dsa,
            stream_abort=self.__abort_st,
        )

        promise.response = self._response
        self._response.from_promise = promise

        # we delivered a response, we can safely remove the promise from queue.
        del self._promises[promise.uid]

        if eot:
            # remote can refuse future inquiries, so no need to go further with this conn.
            if self._protocol.has_expired():
                await self.close()
            elif self.is_idle:
                await self._upgrade()
        else:
            self._pending_responses[promise.stream_id] = self._response

        return self._response

    async def send(  # type: ignore[override]
        self,
        data: bytes | bytearray,
        *,
        eot: bool = False,
    ) -> ResponsePromise | None:
        """We might be receiving a chunk constructed downstream"""
        if self.sock is None or self._stream_id is None or self._protocol is None:
            # this is unreachable in normal condition as urllib3
            # is strict on his workflow.
            raise RuntimeError(  # Defensive:
                "Trying to send data from a closed connection"
            )

        if (
            self.__remaining_body_length is None
            and self.__expected_body_length is not None
        ):
            self.__remaining_body_length = self.__expected_body_length

        _has_next_timer = hasattr(self._protocol, "next_timer")

        async def send_pending() -> None:
            while True:
                data_out = self._protocol.bytes_to_send()  # type: ignore[union-attr]
                if not data_out:
                    break
                await self.sock.sendall(data_out)  # type: ignore[union-attr]

        protocol, stream_id = self._protocol, self._stream_id

        def check_early_response() -> None:
            if protocol.has_pending_event(
                stream_id=stream_id, excl_event=(EarlyHeadersReceived,)
            ):
                if self._start_last_request and self.conn_info:
                    self.conn_info.request_sent_latency = (
                        datetime.now(tz=timezone.utc) - self._start_last_request
                    )

                rp = ResponsePromise(self, stream_id, self.__headers)
                self._promises[rp.uid] = rp
                self._promises_per_stream[rp.stream_id] = rp

                raise EarlyResponse(promise=rp)

        try:
            # Check before another body chunk even when no ACK wait is needed.
            # A FIN-only call can still complete an otherwise finished upload.
            if data:
                check_early_response()
            while (
                self._protocol.should_wait_remote_flow_control(
                    self._stream_id, len(data)
                )
                is True
            ):
                next_timer = self._protocol.next_timer() if _has_next_timer else None  # type: ignore[union-attr]
                sub = AsyncSubTimeout(self.sock, next_timer, send_pending)
                async with sub:
                    data_in = await self.sock.recv(self.blocksize)

                if sub.timer_fired:
                    continue

                # TCP EOF cannot replenish flow-control credit.
                if not data_in and self._svn is not HttpVersion.h3:
                    self._protocol.connection_lost()
                    raise ProtocolError(
                        "Connection closed while waiting for flow control"
                    )

                if not isinstance(data_in, list):
                    self._protocol.bytes_received(data_in)
                else:
                    for gro_segment in data_in:
                        self._protocol.bytes_received(gro_segment)

                check_early_response()

                await send_pending()

            if self.__remaining_body_length:
                self.__remaining_body_length -= len(data)

            self._protocol.submit_data(
                self._stream_id,
                data,
                end_stream=eot,
            )

            if _HAS_SYS_AUDIT:
                sys.audit("http.client.send", self, data)

            remote_pipe_shutdown: BrokenPipeError | None = None

            # some protocols may impose regulated frame size
            # so expect multiple frame per send()
            while True:
                data_out = self._protocol.bytes_to_send()

                if not data_out:
                    break

                try:
                    await self.sock.sendall(data_out)
                except BrokenPipeError as e:
                    remote_pipe_shutdown = e

            if eot or remote_pipe_shutdown:
                if self._start_last_request and self.conn_info:
                    self.conn_info.request_sent_latency = (
                        datetime.now(tz=timezone.utc) - self._start_last_request
                    )

                rp = ResponsePromise(self, self._stream_id, self.__headers)
                self._promises[rp.uid] = rp
                self._promises_per_stream[rp.stream_id] = rp
                if remote_pipe_shutdown:
                    remote_pipe_shutdown.promise = rp  # type: ignore[attr-defined]
                    raise remote_pipe_shutdown
                return rp

        except self._protocol.exceptions() as e:
            raise ProtocolError(  # Defensive: In the unlikely event that exception may leak from below
                e
            ) from e

        return None

    async def ping(self) -> None:  # type: ignore[override]
        """Send a ping frame if possible. Otherwise, fail silently."""
        if self.sock is None or self._protocol is None:
            return

        if self._protocol.has_expired():
            return

        try:
            self._protocol.ping()
        except NotImplementedError:  # http/1 case.
            return
        except (
            self._protocol.exceptions()
        ):  # Defensive: protocol-engine fallback after validating PING availability.
            return

        while True:
            ping_frame = self._protocol.bytes_to_send()

            if not ping_frame:
                break

            try:
                await self.sock.sendall(ping_frame)
            except (
                OSError,
                ssl.SSLError,
            ):
                break

        self._last_used_at = time.monotonic()

    async def close(self) -> None:  # type: ignore[override]
        # Claim teardown before yielding
        sock, self.sock = self.sock, None
        protocol, self._protocol = self._protocol, None

        self._stream_id = None
        self._promises = {}
        self._promises_per_stream = {}
        self._pending_responses = {}
        self.__custom_tls_settings = None
        self.conn_info = None
        self.__expected_body_length = None
        self.__remaining_body_length = None
        self._start_last_request = None
        self._cached_http_vsn = None
        self._connected_at = None
        self._last_used_at = time.monotonic()
        self._recv_size_ema = 0.0
        self._ech_config = None
        self._custom_tls_context = None

        if sock is None:
            return

        try:
            if protocol is not None:
                try:
                    protocol.submit_close()
                except protocol.exceptions() as e:  # Defensive:
                    # overly protective, made in case of possible exception leak.
                    raise ProtocolError(e) from e  # Defensive:
                else:
                    while True:
                        goodbye_frame = protocol.bytes_to_send()
                        if not goodbye_frame:
                            break
                        try:
                            await sock.sendall(goodbye_frame)
                        except (
                            OSError,
                            ssl.SSLEOFError,
                        ):  # don't want our goodbye, never mind then!
                            break
        finally:
            # Cancellation or a protocol error must still close the socket.
            try:
                sock.close()
                # this avoids having SelectorSocketTransport in "closing" state
                # pending. Thus avoid a ResourceWarning.
                await sock.wait_for_close()
            except OSError:
                pass
