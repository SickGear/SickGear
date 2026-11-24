from __future__ import annotations

import enum
import socket
import time
import typing
from base64 import b64encode
from datetime import datetime, timedelta
from secrets import token_bytes

if typing.TYPE_CHECKING:
    from ssl import SSLSocket, SSLContext, TLSVersion
    from .._typing import _TYPE_SOCKET_OPTIONS
    from ._async import AsyncLowLevelResponse

from .._collections import HTTPHeaderDict
from .._constant import (
    DEFAULT_BLOCKSIZE,
    DEFAULT_KEEPALIVE_DELAY,
    DEFAULT_BACKGROUND_WATCH_WINDOW,
    DEFAULT_KEEPALIVE_IDLE_WINDOW,
)

try:
    from jh2._hazmat import _BytesQueueBuffer as BytesQueueBuffer  # type: ignore[import-untyped]
except ImportError:
    from ..util.response import BytesQueueBuffer


class HttpVersion(str, enum.Enum):
    """Describe possible SVN protocols that can be supported."""

    h11 = "HTTP/1.1"
    # we know that it is rather "HTTP/2" than "HTTP/2.0"
    # it is this way to remain somewhat compatible with http.client
    # http_svn (int). 9 -> 11 -> 20 -> 30
    h2 = "HTTP/2.0"
    h3 = "HTTP/3.0"


class ConnectionInfo:
    def __init__(self) -> None:
        #: Time taken to establish the connection
        self.established_latency: timedelta | None = None

        #: HTTP protocol used with the remote peer (not the proxy)
        self.http_version: HttpVersion | None = None

        #: The SSL certificate presented by the remote peer (not the proxy)
        self.certificate_der: bytes | None = None
        self.certificate_dict: (
            dict[str, int | tuple[tuple[str, str], ...] | tuple[str, ...] | str] | None
        ) = None

        #: The SSL issuer certificate for the remote peer certificate (not the proxy)
        self.issuer_certificate_der: bytes | None = None
        self.issuer_certificate_dict: (
            dict[str, int | tuple[tuple[str, str], ...] | tuple[str, ...] | str] | None
        ) = None

        #: The IP address used to reach the remote peer (not the proxy), that was yield by your resolver.
        self.destination_address: tuple[str, int] | None = None

        #: The TLS cipher used to secure the exchanges (not the proxy)
        self.cipher: str | None = None
        #: The TLS revision used (not the proxy)
        self.tls_version: TLSVersion | None = None
        #: The time taken to reach a complete TLS liaison between the remote peer and us.  (not the proxy)
        self.tls_handshake_latency: timedelta | None = None
        #: Time taken to resolve a domain name into a reachable IP address.
        self.resolution_latency: timedelta | None = None
        #: ECH Accepted
        self.tls_ech_accepted: bool | None = None
        #: Time taken to encode and send the whole request through the socket.
        self.request_sent_latency: timedelta | None = None

    def __repr__(self) -> str:
        return str(
            {
                "established_latency": self.established_latency,
                "certificate_der": self.certificate_der,
                "certificate_dict": self.certificate_dict,
                "issuer_certificate_der": self.issuer_certificate_der,
                "issuer_certificate_dict": self.issuer_certificate_dict,
                "destination_address": self.destination_address,
                "cipher": self.cipher,
                "tls_version": self.tls_version,
                "tls_handshake_latency": self.tls_handshake_latency,
                "tls_ech_accepted": self.tls_ech_accepted,
                "http_version": self.http_version,
                "resolution_latency": self.resolution_latency,
                "request_sent_latency": self.request_sent_latency,
            }
        )

    def is_encrypted(self) -> bool:
        return self.certificate_der is not None


class DirectStreamAccess:
    def __init__(
        self,
        stream_id: int,
        read: typing.Callable[
            [int | None, int | None, bool, bool],
            tuple[list[bytes], bool, HTTPHeaderDict | None],
        ]
        | None = None,
        write: typing.Callable[[bytes, int, bool], None] | None = None,
    ) -> None:
        self._stream_id = stream_id

        if read is not None:
            self._read: (
                typing.Callable[
                    [int | None, bool], tuple[list[bytes], bool, HTTPHeaderDict | None]
                ]
                | None
            ) = lambda amt, fo: read(amt, self._stream_id, amt is not None, fo)
        else:
            self._read = (
                None  # Defensive: built-in streams always supply both callbacks.
            )

        # Per-frame chunks are buffered here so a frame-aligned ``recv``
        # returns the protocol's original bytes object zero-copy (instead
        # of eagerly concatenating every frame on each call).
        self._buffer: BytesQueueBuffer = BytesQueueBuffer()
        self._eot: bool = False

        if write is not None:
            self._write: typing.Callable[[bytes, bool], None] | None = lambda buf, eot: (
                write(buf, self._stream_id, eot)
            )
        else:
            self._write = (
                None  # Defensive: built-in streams always supply both callbacks.
            )

    @property
    def closed(self) -> bool:
        return self._read is None and self._write is None

    def readinto(
        self, b: bytearray
    ) -> int:  # Defensive: incidental http.client compatibility.
        if self._read is None:
            raise OSError("read operation on a closed stream")

        temp = self.recv(len(b))

        if len(temp) == 0:
            return 0
        else:
            b[: len(temp)] = temp
            return len(temp)

    def readable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return self._read is not None

    def writable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return self._write is not None

    def seekable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return False

    def fileno(self) -> int:  # Defensive: incidental http.client compatibility.
        return -1

    def name(self) -> int:  # Defensive: incidental http.client compatibility.
        return -1

    def recv(
        self, __bufsize: int, __flags: int = 0
    ) -> bytes:  # Defensive: incidental http.client compatibility.
        data, _, _ = self.recv_extended(__bufsize)
        return data

    def recv_extended(
        self, __bufsize: int | None
    ) -> tuple[bytes, bool, HTTPHeaderDict | None]:
        if self._read is None:
            raise OSError("stream closed error")

        trailers = None

        # Only hit the wire when we have nothing buffered to satisfy the
        # caller; otherwise serve leftover frames first.
        if not self._eot and len(self._buffer) == 0:
            chunks, self._eot, trailers = self._read(__bufsize, False)
            # An unbounded extension read can return a single protocol chunk
            # directly; there are no leftovers to enqueue.
            if __bufsize is None and len(chunks) == 1 and isinstance(chunks[0], bytes):
                if self._eot:
                    self._read = None
                return chunks[0], self._eot, trailers
            self._buffer.put_many(chunks)

        if len(self._buffer):
            data = self._buffer.get(
                __bufsize
                if __bufsize is not None and __bufsize > 0
                else len(self._buffer)
            )
        else:
            data = b""

        # Only signal end-of-transmission once every buffered frame has
        # been handed out, otherwise a bounded recv() at eot would make
        # the caller drop still-buffered bytes.
        eot = self._eot and len(self._buffer) == 0

        if eot:
            self._read = None

        return data, eot, trailers

    def sendall(self, __data: bytes, __flags: int = 0) -> None:
        if self._write is None:
            raise OSError("stream write not permitted")

        self._write(__data, False)

    def write(
        self, __data: bytes
    ) -> int:  # Defensive: incidental http.client compatibility.
        if self._write is None:
            raise OSError("stream write not permitted")

        self._write(__data, False)

        return len(__data)

    def sendall_extended(
        self, __data: bytes, __close_stream: bool = False
    ) -> None:  # Defensive: extended-send compatibility API; built-in extensions use sendall and close.
        if self._write is None:
            raise OSError("stream write not permitted")

        self._write(__data, __close_stream)

    def close(self) -> None:
        if self._write is not None:
            self._write(b"", True)
            self._write = None
        if self._read is not None:
            self._read(None, True)
            self._read = None


class LowLevelResponse:
    """Implemented for backward compatibility purposes. It is there to impose http.client like
    basic response object. So that we don't have to change urllib3 tested behaviors."""

    def __init__(
        self,
        method: str,
        status: int,
        version: int,
        reason: str,
        headers: HTTPHeaderDict,
        body: typing.Callable[
            [int | None, int | None], tuple[list[bytes], bool, HTTPHeaderDict | None]
        ]
        | None,
        *,
        authority: str | None = None,
        port: int | None = None,
        stream_id: int | None = None,
        sock: socket.socket | None = None,
        # this obj should not be always available[...]
        dsa: DirectStreamAccess | None = None,
        stream_abort: typing.Callable[[int], None] | None = None,
    ):
        self.status = status
        self.version = version
        self.reason = reason
        self.msg = headers
        self._method = method

        self.__internal_read_st = body

        has_body = self.__internal_read_st is not None or dsa is not None

        self.closed = has_body is False
        self._eot = self.closed

        # is kept to determine if we can upgrade conn
        self.authority = authority
        self.port = port

        # http.client additional compat layer
        # although rarely used, some 3rd party library may
        # peek at those for whatever reason. most of the time they
        # are wrong to do so.
        self.debuglevel: int = 0  # no-op flag, kept for strict backward compatibility!
        self.chunked: bool = (  # is "chunked" being used? http1 only!
            self.version == 11 and "chunked" == self.msg.get("transfer-encoding")
        )
        self.chunk_left: int | None = None  # bytes left to read in current chunk
        self.length: int | None = None  # number of bytes left in response
        self.will_close: bool = (
            False  # no-op flag, kept for strict backward compatibility!
        )

        if not self.chunked:
            content_length = self.msg.get("content-length")
            self.length = int(content_length) if content_length else None

        #: not part of http.client but useful to track (raw) download speeds!
        self.data_in_count = 0

        # tricky part...
        # sometime 3rd party library tend to access hazardous materials...
        # they want a direct socket access.
        self._sock = sock
        self._fp: socket.SocketIO | None = None
        self._dsa = dsa
        self._stream_abort = stream_abort

        self._stream_id = stream_id

        self.__buffer_excess: BytesQueueBuffer = BytesQueueBuffer()
        self.__promise: ResponsePromise | None = None

        self.trailers: HTTPHeaderDict | None = None

    @property
    def fp(
        self,
    ) -> (
        socket.SocketIO | DirectStreamAccess | None
    ):  # Defensive: incidental http.client file-pointer compatibility.
        if self._sock is None:
            if self.status == 101 or (
                self._method == "CONNECT" and 200 <= self.status < 300
            ):
                return self._dsa

            # well, there's nothing we can do more :'(
            raise AttributeError

        if self._fp is None:
            self._fp = self._sock.makefile("rb")  # type: ignore[assignment]

        return self._fp

    @property
    def from_promise(self) -> ResponsePromise | None:
        return self.__promise

    @from_promise.setter
    def from_promise(self, value: ResponsePromise) -> None:
        if value.stream_id != self._stream_id:
            raise ValueError(  # Defensive: built-in responses are assigned the promise for their own stream.
                "Trying to assign a ResponsePromise to an unrelated LowLevelResponse"
            )
        self.__promise = value

    @property
    def method(self) -> str:
        """Original HTTP verb used in the request."""
        return self._method

    def isclosed(self) -> bool:
        """Here we do not create a fp sock like http.client Response."""
        return self.closed

    def read(self, __size: int | None = None) -> bytes:
        return self._read(__size, read1=False)

    def read1(self, __size: int | None = None) -> bytes:
        return self._read(__size, read1=True)

    def _read(self, __size: int | None, *, read1: bool) -> bytes:
        if self.closed is True or self.__internal_read_st is None:
            # overly protective, just in case.
            raise ValueError(
                "I/O operation on closed file."
            )  # Defensive: Should not be reachable in normal condition

        if __size == 0:
            return b""  # Defensive: This is unreachable, this case is already covered higher in the stack.

        buf_capacity = len(self.__buffer_excess)
        # any buffered data must be served first, even if smaller than
        # __size: reaching for the socket while holding deliverable bytes
        # can block forever on a live stream (e.g. SSE).
        # see https://github.com/jawah/urllib3.future/issues/379
        data_ready_to_go = __size is not None and buf_capacity > 0

        if self._eot is False and not data_ready_to_go:
            chunks, self._eot, self.trailers = self.__internal_read_st(
                __size, self._stream_id
            )

            self.__buffer_excess.put_many(chunks)
            buf_capacity = len(self.__buffer_excess)

        if not read1 and __size is not None and __size > 0:
            while self._eot is False and buf_capacity < __size:
                chunks, self._eot, self.trailers = self.__internal_read_st(
                    __size - buf_capacity, self._stream_id
                )
                self.__buffer_excess.put_many(chunks)
                buf_capacity = len(self.__buffer_excess)
                if not chunks:
                    break

        data = (
            self.__buffer_excess.get(
                __size if __size is not None and __size > 0 else buf_capacity
            )
            if buf_capacity
            else b""
        )

        size_in = len(data)

        buf_capacity -= size_in

        if self._eot and buf_capacity == 0:
            self._stream_abort = None
            if not self._dsa:
                self.closed = True
                self._sock = None

        if self.chunked:
            self.chunk_left = buf_capacity if buf_capacity else None
        elif self.length is not None:
            self.length -= size_in

        self.data_in_count += size_in

        return data

    def abort(self) -> None:
        try:
            # Upgraded responses have no HTTP body, but their stream can still be open.
            if self._stream_abort is not None and (
                not self._eot or self._dsa is not None
            ):
                if self._stream_id is not None:
                    self._stream_abort(self._stream_id)
        finally:
            self._eot = True
            self.close()

    def close(self) -> None:
        self._stream_abort = None
        self.__buffer_excess = BytesQueueBuffer()
        self.__internal_read_st = None
        self.closed = True
        self._sock = None
        self._dsa = None


class ResponsePromise:
    def __init__(
        self,
        conn: BaseBackend,
        stream_id: int,
        request_headers: list[tuple[bytes, bytes]],
        **parameters: typing.Any,
    ) -> None:
        self._uid: str = b64encode(token_bytes(16)).decode("ascii")
        self._conn: BaseBackend = conn
        self._stream_id: int = stream_id
        self._response: LowLevelResponse | AsyncLowLevelResponse | None = None
        self._request_headers = request_headers
        self._parameters: typing.MutableMapping[str, typing.Any] = parameters

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResponsePromise):
            return False
        return self.uid == other.uid

    def __repr__(self) -> str:
        return f"<ResponsePromise '{self.uid}' {self._conn._http_vsn_str} Stream[{self.stream_id}]>"

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def request_headers(self) -> list[tuple[bytes, bytes]]:
        return self._request_headers

    @property
    def stream_id(self) -> int:
        return self._stream_id

    @property
    def is_ready(self) -> bool:
        return self._response is not None

    @property
    def response(self) -> LowLevelResponse | AsyncLowLevelResponse:
        if not self._response:
            raise OSError
        return self._response

    @response.setter
    def response(self, value: LowLevelResponse | AsyncLowLevelResponse) -> None:
        self._response = value

    def set_parameter(self, key: str, value: typing.Any) -> None:
        self._parameters[key] = value

    def get_parameter(self, key: str) -> typing.Any | None:
        return self._parameters[key] if key in self._parameters else None

    def update_parameters(self, data: dict[str, typing.Any]) -> None:
        self._parameters.update(data)


_HostPortType: typing.TypeAlias = typing.Tuple[str, int]
QuicPreemptiveCacheType: typing.TypeAlias = typing.MutableMapping[
    _HostPortType, typing.Optional[_HostPortType]
]


class BaseBackend:
    """
    The goal here is to detach ourselves from the http.client package.
    At first, we'll strictly follow the methods in http.client.HTTPConnection. So that
    we would be able to implement other backend without disrupting the actual code base.
    Extend that base class in order to ship another backend with urllib3.
    """

    supported_svn: typing.ClassVar[list[HttpVersion] | None] = None
    scheme: typing.ClassVar[str]

    default_socket_kind: socket.SocketKind = socket.SOCK_STREAM
    #: Disable Nagle's algorithm by default.
    default_socket_options: typing.ClassVar[_TYPE_SOCKET_OPTIONS] = [
        (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1, "tcp")
    ]

    #: Whether this connection verifies the host's certificate.
    is_verified: bool = False

    #: Whether this proxy connection verified the proxy host's certificate.
    # If no proxy is currently connected to the value will be ``None``.
    proxy_is_verified: bool | None = None

    response_class = LowLevelResponse

    def __init__(
        self,
        host: str,
        port: int | None = None,
        timeout: int | float | None = -1,
        source_address: tuple[str, int] | None = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        *,
        socket_options: _TYPE_SOCKET_OPTIONS | None = default_socket_options,
        disabled_svn: set[HttpVersion] | None = None,
        preemptive_quic_cache: QuicPreemptiveCacheType | None = None,
        keepalive_delay: float | int | None = DEFAULT_KEEPALIVE_DELAY,
        background_watch_delay: int | float | None = DEFAULT_BACKGROUND_WATCH_WINDOW,
        keepalive_idle_window: int | float | None = DEFAULT_KEEPALIVE_IDLE_WINDOW,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.source_address = source_address
        self.blocksize = blocksize
        self.socket_kind = BaseBackend.default_socket_kind
        self.socket_options = socket_options
        self.sock: socket.socket | SSLSocket | None = None

        self._response: LowLevelResponse | AsyncLowLevelResponse | None = None
        # Set it as default
        self._svn: HttpVersion | None = HttpVersion.h11

        self._tunnel_host: str | None = None
        self._tunnel_port: int | None = None
        self._tunnel_scheme: str | None = None
        self._tunnel_headers: typing.Mapping[str, str] = dict()

        self._disabled_svn = disabled_svn if disabled_svn is not None else set()
        self._preemptive_quic_cache = preemptive_quic_cache

        if self._disabled_svn:
            if len(self._disabled_svn) == len(list(HttpVersion)):
                raise RuntimeError(
                    "You disabled every supported protocols. The HTTP connection object is left with no outcomes."
                )

        # valuable intel
        self.conn_info: ConnectionInfo | None = None

        self._promises: dict[str, ResponsePromise] = {}
        self._promises_per_stream: dict[int, ResponsePromise] = {}
        self._pending_responses: dict[
            int, LowLevelResponse | AsyncLowLevelResponse
        ] = {}

        self._start_last_request: datetime | None = None

        self._cached_http_vsn: int | None = None

        self._keepalive_delay: float | None = (
            keepalive_delay  # just forwarded for qh3 idle_timeout conf.
        )
        self._background_watch_delay = (
            background_watch_delay  # tcp keepalive http1.1 only
        )
        self._keepalive_idle_window = (
            keepalive_idle_window  # tcp keepalive http1.1 only
        )
        self._connected_at: float | None = None
        self._last_used_at: float = time.monotonic()

        self._recv_size_ema: float = 0.0
        self._ech_config: bytes | None = None
        self._custom_tls_context: SSLContext | None = None

    def __contains__(self, item: ResponsePromise) -> bool:
        return item.uid in self._promises

    @property
    def _fast_recv_mode(self) -> bool:
        if len(self._promises) <= 1 or self._svn is HttpVersion.h3:
            return True
        return self._recv_size_ema >= 1450

    @property
    def last_used_at(self) -> float:
        return self._last_used_at

    @property
    def connected_at(self) -> float | None:
        return self._connected_at

    @property
    def disabled_svn(self) -> set[HttpVersion]:
        return self._disabled_svn

    @property
    def _http_vsn_str(self) -> str:
        """Reimplemented for backward compatibility purposes."""
        if self._svn is None:
            return "HTTP/1.1"  # Defensive: http.client-compatible default before protocol negotiation.
        return self._svn.value

    @property
    def _http_vsn(self) -> int:
        """Reimplemented for backward compatibility purposes."""
        if self._svn is None:
            return 11  # Defensive: http.client-compatible default before protocol negotiation.
        if self._cached_http_vsn is None:
            self._cached_http_vsn = int(self._svn.value.split("/")[-1].replace(".", ""))
        return self._cached_http_vsn

    @property
    def is_saturated(self) -> bool:
        raise NotImplementedError

    @property
    def is_idle(self) -> bool:
        return not self._promises and not self._pending_responses

    @property
    def expect_pong(self) -> bool:
        raise NotImplementedError

    @property
    def is_multiplexed(self) -> bool:
        raise NotImplementedError

    @property
    def max_frame_size(self) -> int:
        raise NotImplementedError

    def _upgrade(self) -> None:
        """Upgrade conn from svn ver to max supported."""
        raise NotImplementedError

    def _tunnel(self) -> None:
        """Emit proper CONNECT request to the http (server) intermediary."""
        raise NotImplementedError

    def _new_conn(self) -> socket.socket | None:
        """Run protocol initialization from there. Return None to ensure that the child
        class correctly create the socket / connection."""
        raise NotImplementedError

    def _post_conn(self) -> None:
        """Should be called after _new_conn proceed as expected.
        Expect protocol handshake to be done here."""
        raise NotImplementedError

    def _custom_tls(
        self,
        ssl_context: SSLContext | None = None,
        ca_certs: str | None = None,
        ca_cert_dir: str | None = None,
        ca_cert_data: None | str | bytes = None,
        ssl_minimum_version: int | None = None,
        ssl_maximum_version: int | None = None,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_password: str | None = None,
    ) -> bool:
        """This method serve as bypassing any default tls setup.
        It is most useful when the encryption does not lie on the TCP layer. This method
        WILL raise NotImplementedError if the connection is not concerned."""
        raise NotImplementedError

    def set_tunnel(
        self,
        host: str,
        port: int | None = None,
        headers: typing.Mapping[str, str] | None = None,
        scheme: str = "http",
    ) -> None:
        """Prepare the connection to set up a tunnel. Does NOT actually do the socket and http connect.
        Here host:port represent the target (final) server and not the intermediary."""
        raise NotImplementedError

    def putrequest(
        self,
        method: str,
        url: str,
        skip_host: bool = False,
        skip_accept_encoding: bool = False,
    ) -> None:
        """It is the first method called, setting up the request initial context."""
        raise NotImplementedError

    def putheader(self, header: str, *values: str) -> None:
        """For a single header name, assign one or multiple value. This method is called right after putrequest()
        for each entries."""
        raise NotImplementedError

    def endheaders(
        self,
        message_body: bytes | None = None,
        *,
        encode_chunked: bool = False,
        expect_body_afterward: bool = False,
    ) -> ResponsePromise | None:
        """This method conclude the request context construction."""
        raise NotImplementedError

    def getresponse(
        self, *, promise: ResponsePromise | None = None
    ) -> LowLevelResponse:
        """Fetch the HTTP response. You SHOULD not retrieve the body in that method, it SHOULD be done
        in the LowLevelResponse, so it enable stream capabilities and remain efficient.
        """
        raise NotImplementedError

    def close(self) -> None:
        """End the connection, do some reinit, closing of fd, etc..."""
        raise NotImplementedError

    def send(
        self,
        data: bytes | bytearray,
        *,
        eot: bool = False,
    ) -> ResponsePromise | None:
        """The send() method SHOULD be invoked after calling endheaders() if and only if the request
        context specify explicitly that a body is going to be sent."""
        raise NotImplementedError

    def ping(self) -> None:
        """Send a PING to the remote peer."""
        raise NotImplementedError
