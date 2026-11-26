from __future__ import annotations

import asyncio
import time
from socket import timeout as SocketTimeout
import typing

if typing.TYPE_CHECKING:
    from ...._async.response import AsyncHTTPResponse
    from ...._async.connection import AsyncHTTPConnection

from wsproto import ConnectionType, WSConnection
from wsproto.connection import Connection
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Ping,
    Pong,
    Request,
    TextMessage,
)
from wsproto.extensions import PerMessageDeflate
from wsproto.utilities import ProtocolError as WebSocketProtocolError

from ....backend import HttpVersion
from ....exceptions import ProtocolError, ReadTimeoutError
from ...ssa import AsyncSocket
from ....util.traffic_police import UnavailableTraffic
from .protocol import AsyncExtensionFromHTTP


class AsyncWebSocketExtensionFromHTTP(AsyncExtensionFromHTTP):
    def __init__(self) -> None:
        super().__init__()
        self._protocol: WSConnection | Connection = WSConnection(ConnectionType.CLIENT)
        self._request_headers: dict[str, str] | None = None
        self._remote_shutdown: bool = False
        self._read_closed = False
        self._read_lock: asyncio.Lock | None = None
        self._ready_socket: AsyncSocket | None = None
        self._read_deadline: float | None = None
        self._read_timeout: float | None = None

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11}

    @staticmethod
    def implementation() -> str:
        return "wsproto"

    async def start(self, response: AsyncHTTPResponse) -> None:
        await super().start(response)

        fake_http_response = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"

        fake_http_response += b"Sec-Websocket-Accept: "

        accept_token: str | None = response.headers.get("Sec-Websocket-Accept")

        if accept_token is None:
            raise ProtocolError(
                "The WebSocket HTTP extension requires 'Sec-Websocket-Accept' header in the server response but was not present."
            )

        fake_http_response += accept_token.encode() + b"\r\n"

        if "sec-websocket-extensions" in response.headers:
            fake_http_response += (
                b"Sec-Websocket-Extensions: "
                + response.headers.get("sec-websocket-extensions").encode()  # type: ignore[union-attr]
                + b"\r\n"
            )

        fake_http_response += b"\r\n"

        try:
            self._protocol.receive_data(fake_http_response)
        except WebSocketProtocolError as e:
            raise ProtocolError from e

        event = next(self._protocol.events())

        if not isinstance(event, AcceptConnection):
            raise RuntimeError(  # Defensive: a validated wsproto handshake must emit AcceptConnection.
                "The WebSocket state-machine did not pass the handshake phase when expected."
            )

        # The HTTP upgrade is complete. Keep the established state machine;
        # the handshake wrapper adds no further protocol work.
        if isinstance(self._protocol, WSConnection):
            assert self._protocol.connection is not None
            self._protocol = self._protocol.connection

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        """Specific HTTP headers required (request) before the 101 status response."""
        if self._request_headers is not None:
            return self._request_headers

        try:
            raw_data_to_socket = self._protocol.send(
                Request(
                    host="example.com", target="/", extensions=(PerMessageDeflate(),)
                )
            )
        except (
            WebSocketProtocolError
        ) as e:  # Defensive: fixed opening request on a fresh wsproto connection.
            raise ProtocolError from e

        raw_headers = raw_data_to_socket.split(b"\r\n")[2:-2]
        request_headers: dict[str, str] = {}

        for raw_header in raw_headers:
            k, v = raw_header.decode().split(": ")
            request_headers[k.lower()] = v

        if http_version != HttpVersion.h11:
            del request_headers["upgrade"]
            del request_headers["connection"]
            request_headers[":protocol"] = "websocket"
            request_headers[":method"] = "CONNECT"

        self._request_headers = request_headers

        return request_headers

    async def close(self) -> None:
        """End the WebSocket and release its transport ownership."""
        self._read_closed = True
        response, police = self._response, self._police_officer
        if self._dsa is not None and police is not None:
            try:
                async with police.borrow(response):
                    dsa = self._dsa
                    if dsa is None:
                        return
                    if not self._remote_shutdown:
                        try:
                            data_to_send = self._protocol.send(CloseConnection(0))
                            await dsa.sendall(data_to_send)
                        except (WebSocketProtocolError, OSError, AssertionError):
                            pass
                    try:
                        await dsa.close()
                    except (OSError, AssertionError):
                        pass
                    if response is not None and response.version == 11:
                        # An H1 upgrade owns the transport. Removing it closes
                        # the socket and wakes socket and connection waiters.
                        await police.kill_cursor()
                    self._dsa = None
            except UnavailableTraffic:
                self._dsa = None
        else:
            self._dsa = None
        if response is not None:
            if police is not None:
                police.forget(response)
            else:
                await response.close()  # Defensive: externally constructed responses may lack a TrafficPolice owner.
        self._response = None
        self._police_officer = None

    async def next_payload(self) -> str | bytes | None:
        """Unpack the next received message/payload from remote."""
        if self._dsa is None or self._response is None or self._police_officer is None:
            raise OSError("The HTTP extension is closed or uninitialized")

        response, police = self._response, self._police_officer
        cooperative = response.version == 11 and not police.busy
        if cooperative:
            if self._read_lock is None:
                self._read_lock = asyncio.Lock()
            await self._read_lock.acquire()
        try:
            if self._read_closed:
                return None
            text_buf: list[str] = []
            bytes_buf: list[bytes] = []
            before_pick = None
            self._read_deadline = None
            self._ready_socket = None
            while True:
                yield_to_writer = False
                borrow = (
                    police.borrow(response)
                    if before_pick is None
                    else police.borrow(
                        response,
                        timeout=None
                        if self._read_deadline is None
                        else max(0, self._read_deadline - time.monotonic()),
                        conn_pre_pick_callable=before_pick,
                    )
                )
                async with borrow as conn:
                    if self._read_closed:
                        return None
                    # wsproto uses bare ``assert`` statements inside ``events()`` and
                    # the per-message-deflate inbound decompression to validate frame
                    # payloads. We treat such failures as a protocol violation.
                    try:
                        for event in self._protocol.events():
                            if isinstance(event, TextMessage):
                                if event.message_finished and not text_buf:
                                    return event.data
                                text_buf.append(event.data)
                                if event.message_finished:
                                    return "".join(text_buf)
                            elif isinstance(event, BytesMessage):
                                if event.message_finished and not bytes_buf:
                                    return event.data
                                bytes_buf.append(event.data)
                                if event.message_finished:
                                    return b"".join(bytes_buf)
                            elif isinstance(event, CloseConnection):
                                self._remote_shutdown = True
                                await self.close()
                                return None
                            elif isinstance(event, Ping):
                                try:
                                    data_to_send: bytes = self._protocol.send(
                                        event.response()
                                    )
                                except WebSocketProtocolError as e:  # Defensive: PONG is generated from a validated PING before closing.
                                    await self.close()
                                    raise ProtocolError from e

                                async with self._write_error_catcher():
                                    await self._dsa.sendall(data_to_send)
                    except AssertionError as e:
                        await self.close()
                        raise ProtocolError from e

                    while True:
                        # Reuse this ownership while buffered input can satisfy
                        # the receive. A deferred wait must run after release.
                        if cooperative and self._before_read_pick(conn) is not None:
                            break
                        async with self._read_error_catcher():
                            sock = conn.sock if cooperative else None
                            if self._read_deadline is not None:
                                remaining = self._read_deadline - time.monotonic()
                                if remaining <= 0:
                                    raise SocketTimeout("Read timed out")
                                sock.settimeout(remaining)
                            try:
                                data, eot, _ = await self._dsa.recv_extended(None)
                            finally:
                                if (
                                    self._read_deadline is not None
                                    and conn.sock is sock
                                ):
                                    sock.settimeout(self._read_timeout)
                        self._read_deadline = None
                        self._ready_socket = None

                        try:
                            # EOF must emit wsproto's abnormal-close event.
                            self._protocol.receive_data(
                                None if not data and eot else data
                            )
                        except WebSocketProtocolError as e:  # Defensive: wsproto receive_data only rejects an already-closed local state.
                            await self.close()
                            raise ProtocolError from e

                        try:
                            for event in self._protocol.events():
                                if isinstance(event, TextMessage):
                                    if event.message_finished and not text_buf:
                                        return event.data
                                    text_buf.append(event.data)
                                    if event.message_finished:
                                        return "".join(text_buf)
                                elif isinstance(event, BytesMessage):
                                    if event.message_finished and not bytes_buf:
                                        return event.data
                                    bytes_buf.append(event.data)
                                    if event.message_finished:
                                        return b"".join(bytes_buf)
                                elif isinstance(event, CloseConnection):
                                    self._remote_shutdown = True
                                    await self.close()
                                    return None
                                elif isinstance(event, Ping):
                                    try:
                                        data_to_send = self._protocol.send(
                                            event.response()
                                        )
                                    except WebSocketProtocolError as e:  # Defensive: PONG is generated from a validated PING before closing.
                                        await self.close()
                                        raise ProtocolError from e
                                    async with self._write_error_catcher():
                                        await self._dsa.sendall(data_to_send)
                                elif isinstance(event, Pong):
                                    continue
                        except AssertionError as e:
                            await self.close()
                            raise ProtocolError from e
                        if cooperative:
                            yield_to_writer = True
                            break
                if yield_to_writer:
                    await asyncio.sleep(0)
                before_pick = self._before_read_pick
        except (SocketTimeout, TimeoutError) as e:
            # Queue and socket timeouts are distinct before Python 3.10.
            pool = self._response._pool if self._response is not None else None
            raise ReadTimeoutError(pool, None, "Read timed out.") from e  # type: ignore[arg-type]
        except UnavailableTraffic:
            if self._read_closed:
                return None
            raise
        except asyncio.CancelledError:
            # A cancelled active reader may have consumed part of a message.
            await self.close()
            raise
        finally:
            if cooperative:
                assert self._read_lock is not None
                self._read_lock.release()

    def _before_read_pick(
        self, conn: AsyncHTTPConnection
    ) -> typing.Callable[[], typing.Awaitable[None]] | None:
        if self._read_closed:
            raise UnavailableTraffic("The WebSocket is closed")
        assert self._dsa is not None and conn._protocol is not None
        assert conn.sock is not None
        if self._dsa._buffer or self._dsa._eot or conn._protocol.has_pending_event():
            return None
        sock = conn.sock
        if sock is self._ready_socket:
            return None
        if sock.read_ready():
            return None
        if self._read_deadline is None:
            self._read_timeout = sock.gettimeout()
            if self._read_timeout is not None:
                self._read_deadline = time.monotonic() + self._read_timeout
        return lambda: self._wait_for_read(sock)

    async def _wait_for_read(self, sock: AsyncSocket) -> None:
        if self._read_closed:
            return
        remaining = (
            None
            if self._read_deadline is None
            else max(0, self._read_deadline - time.monotonic())
        )
        async with self._read_error_catcher():
            try:
                await sock.until_data_available(remaining)
            except (OSError, ValueError):
                if self._read_closed:
                    return
                raise
        self._ready_socket = sock

    async def send_payload(self, buf: str | bytes) -> None:
        """Dispatch a buffer to remote."""
        if self._dsa is None or self._response is None or self._police_officer is None:
            raise OSError("The HTTP extension is closed or uninitialized")

        async with self._police_officer.borrow(self._response):
            # the per-message-deflate outbound path uses a bare ``assert`` to
            # protect against compressing a CONTINUATION frame; treat such a
            # failure as a protocol violation.
            try:
                if isinstance(buf, str):
                    data_to_send: bytes = self._protocol.send(TextMessage(buf))
                else:
                    data_to_send = self._protocol.send(BytesMessage(buf))
            except (WebSocketProtocolError, AssertionError) as e:
                await self.close()
                raise ProtocolError from e

            async with self._write_error_catcher():
                await self._dsa.sendall(data_to_send)

    async def ping(self) -> None:
        if self._dsa is None or self._response is None or self._police_officer is None:
            raise OSError("The HTTP extension is closed or uninitialized")

        async with self._police_officer.borrow(self._response):
            try:
                data_to_send: bytes = self._protocol.send(Ping())
            except (
                WebSocketProtocolError
            ) as e:  # Defensive: empty PING on an owned, open wsproto connection.
                await self.close()
                raise ProtocolError from e

            async with self._write_error_catcher():
                await self._dsa.sendall(data_to_send)

    @staticmethod
    def supported_schemes() -> set[str]:
        return {"ws", "wss"}

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        return {"ws": "http", "wss": "https"}[scheme]


class AsyncWebSocketExtensionFromMultiplexedHTTP(AsyncWebSocketExtensionFromHTTP):
    """
    Plugin that support doing WebSocket over HTTP 2 and 3.
    This implement RFC8441. Beware that this isn't actually supported by much server around internet.
    """

    @staticmethod
    def implementation() -> str:
        return "rfc8441"

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11, HttpVersion.h2, HttpVersion.h3}
