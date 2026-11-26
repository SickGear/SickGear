from __future__ import annotations

import codecs
import socket
import sys
import time
import typing
from collections import deque
from threading import Lock
from contextlib import nullcontext
from typing import cast

from websockets.client import ClientProtocol
from websockets.exceptions import WebSocketException
from websockets.extensions.permessage_deflate import ClientPerMessageDeflateFactory
from websockets.frames import Frame, Opcode, CloseCode
from websockets.http11 import Response
from websockets.protocol import CLOSED, OPEN
from websockets.uri import parse_uri

from ..._collections import HTTPHeaderDict
from ...backend import HttpVersion
from ...exceptions import ProtocolError, ReadTimeoutError
from ...util.traffic_police import UnavailableTraffic
from ...util.ssltransport import SSLTransport
from ...util.wait import wait_for_read
from .protocol import ExtensionFromHTTP

if typing.TYPE_CHECKING:
    from ...response import HTTPResponse
    from ...connection import HTTPConnection


_NEED_DATA = object()


class _WebsocketsEngine:
    """Shared Sans-I/O behavior; transports retain ownership of all I/O."""

    def _init_engine(self) -> None:
        self._protocol = ClientProtocol(
            parse_uri("ws://example.com/"),
            extensions=[ClientPerMessageDeflateFactory()],
            max_size=None,
        )
        self._request_headers: dict[str, str] | None = None
        self._events: deque[Frame] = deque()
        self._decoder: codecs.IncrementalDecoder | None = None
        self._text_parts: list[str] = []
        self._bytes_parts: list[bytes] = []
        self._remote_shutdown = False
        self._read_closed = False
        self._read_deadline: float | None = None
        self._read_timeout: float | None = None

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        if self._request_headers is None:
            request = self._protocol.connect()
            self._protocol.send_request(request)
            # HTTP handles the actual request, with the actual target and host.
            self._protocol.data_to_send()
            self._request_headers = {
                key.lower(): value
                for key, value in request.headers.raw_items()
                if key.lower() != "host"
            }
        return self._request_headers

    def _accept(self, headers: HTTPHeaderDict) -> None:
        data = b"HTTP/1.1 101 Switching Protocols\r\n"
        data += b"".join(
            key.encode("ascii") + b": " + value.encode("latin-1") + b"\r\n"
            for key, value in headers.items()
        )
        self._protocol.receive_data(data + b"\r\n")
        events = self._protocol.events_received()
        if self._protocol.handshake_exc is not None:
            raise ProtocolError(
                "WebSocket handshake failed"
            ) from self._protocol.handshake_exc
        if not events or not isinstance(events[0], Response):
            raise ProtocolError(
                "WebSocket handshake did not complete"
            )  # Defensive: a complete validated handshake must emit Response.
        self._events.extend(event for event in events[1:] if isinstance(event, Frame))

    def _feed(self, data: bytes) -> None:
        if data:
            self._protocol.receive_data(data)
        else:
            self._protocol.receive_eof()
        # Once the handshake completes, the Sans-I/O engine emits only frames.
        self._events.extend(cast("list[Frame]", self._protocol.events_received()))

    def _next_message(self) -> str | bytes | None | object:
        try:
            while self._events:
                event = self._events.popleft()
                opcode = event.opcode
                if opcode is Opcode.CLOSE:
                    self._remote_shutdown = True
                    return None
                if opcode is Opcode.TEXT:
                    if event.fin:
                        return codecs.decode(event.data, "utf-8")
                    self._decoder = codecs.getincrementaldecoder("utf-8")()
                    self._text_parts.append(self._decoder.decode(event.data))
                elif opcode is Opcode.BINARY:
                    if event.fin:
                        return bytes(event.data)
                    self._bytes_parts.append(bytes(event.data))
                elif opcode is Opcode.CONT:
                    if self._decoder is not None:
                        self._text_parts.append(
                            self._decoder.decode(event.data, final=event.fin)
                        )
                        if event.fin:
                            text = "".join(self._text_parts)
                            self._text_parts.clear()
                            self._decoder = None
                            return text
                    else:
                        self._bytes_parts.append(bytes(event.data))
                        if event.fin:
                            data = b"".join(self._bytes_parts)
                            self._bytes_parts.clear()
                            return data
                # Ping/Pong handling and frame validation belong to the engine.
        except UnicodeDecodeError:
            self._protocol.fail(CloseCode.INVALID_DATA, "invalid UTF-8")
            self._remote_shutdown = True
            return None
        if self._protocol.parser_exc is not None or self._protocol.state is CLOSED:
            self._remote_shutdown = True
            return None
        return _NEED_DATA

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11}

    @staticmethod
    def implementation() -> str:
        return "fast"

    @staticmethod
    def supported_schemes() -> set[str]:
        return {"ws", "wss"}

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        return {"ws": "http", "wss": "https"}[scheme]


class FastWebSocketExtensionFromHTTP(_WebsocketsEngine, ExtensionFromHTTP):
    def __init__(self) -> None:
        super().__init__()
        self._init_engine()
        self._read_lock = Lock()
        self._read_wait_lock = (
            Lock()
            if sys.platform == "darwin" or sys.platform.startswith("dragonfly")
            else nullcontext()
        )
        self._ready_socket: socket.socket | SSLTransport | None = None

    def start(self, response: HTTPResponse) -> None:
        super().start(response)
        self._accept(response.headers)

    def _flush(self) -> None:
        assert self._dsa is not None
        for data in self._protocol.data_to_send():
            if data:
                with self._write_error_catcher():
                    self._dsa.sendall(data)

    def close(self) -> None:
        """End the WebSocket and release its transport ownership."""
        self._read_closed = True
        response, police = self._response, self._police_officer
        if self._dsa is not None and police is not None:
            try:
                with police.borrow(response) as conn:
                    dsa = self._dsa
                    if dsa is None:
                        return  # Defensive: HTTP/1 close removes the connection before a queued closer can reenter.
                    try:
                        if self._protocol.state is OPEN:
                            self._protocol.send_close()
                        for data in self._protocol.data_to_send():
                            if data:
                                dsa.sendall(data)
                    except (WebSocketException, OSError, AssertionError):
                        pass
                    try:
                        dsa.close()
                    except (OSError, AssertionError):
                        pass
                    if response is not None and response.version == 11:
                        # Wake the reader before closing its descriptor: macOS
                        # and DragonFly BSD can discard a pending poll/kqueue
                        # notification when the descriptor is closed.
                        sock = conn.sock
                        while isinstance(sock, SSLTransport):
                            sock = sock.socket
                        if sock is not None:
                            try:
                                sock.shutdown(socket.SHUT_RD)
                            except OSError:
                                pass
                        with self._read_wait_lock:
                            police.kill_cursor()
                    self._dsa = None
            except UnavailableTraffic:
                self._dsa = None
        else:
            self._dsa = None
        if response is not None:
            if police is not None:
                police.forget(response)
            else:
                response.close()  # Defensive: externally constructed responses may lack a TrafficPolice owner.
        self._response = None
        self._police_officer = None

    def next_payload(self) -> str | bytes | None:
        """Unpack the next received message/payload from remote."""
        if self._dsa is None or self._response is None or self._police_officer is None:
            raise OSError("The HTTP extension is closed or uninitialized")

        response, police = self._response, self._police_officer
        cooperative = response.version == 11 and not police.busy
        if cooperative:
            self._read_lock.acquire()
        try:
            if self._read_closed:
                return None
            before_pick = None
            self._read_deadline = None
            self._ready_socket = None
            while True:
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
                with borrow as conn:
                    if self._read_closed:
                        return None
                    message = self._next_message()
                    if message is not _NEED_DATA:
                        if message is None:
                            self.close()
                        return typing.cast("str | bytes | None", message)

                    while True:
                        # Reuse this ownership while buffered input can satisfy
                        # the receive. A deferred wait must run after release.
                        if cooperative and self._before_read_pick(conn) is not None:
                            break
                        with self._read_error_catcher():
                            sock = conn.sock if cooperative else None
                            if self._read_deadline is not None:
                                remaining = self._read_deadline - time.monotonic()
                                if remaining <= 0:
                                    raise socket.timeout("Read timed out")
                                sock.settimeout(remaining)
                            try:
                                data, eot, _ = self._dsa.recv_extended(None)
                            finally:
                                if (
                                    self._read_deadline is not None
                                    and conn.sock is sock
                                ):
                                    sock.settimeout(self._read_timeout)
                        self._read_deadline = None
                        self._ready_socket = None

                        self._feed(data)
                        self._flush()
                        message = self._next_message()
                        if message is not _NEED_DATA:
                            if message is None:
                                self.close()
                            return typing.cast("str | bytes | None", message)
                        if cooperative:
                            break
                before_pick = self._before_read_pick
        except (socket.timeout, TimeoutError) as e:
            # Queue and socket timeouts are distinct before Python 3.10.
            pool = self._response._pool if self._response is not None else None
            raise ReadTimeoutError(pool, None, "Read timed out.") from e  # type: ignore[arg-type]
        except UnavailableTraffic:
            if self._read_closed:
                return None
            raise
        finally:
            if cooperative:
                self._read_lock.release()

    def _before_read_pick(
        self, conn: HTTPConnection
    ) -> typing.Callable[[], None] | None:
        if self._read_closed:
            raise UnavailableTraffic("The WebSocket is closed")
        assert self._dsa is not None and conn._protocol is not None
        assert conn.sock is not None
        if self._dsa._buffer or self._dsa._eot or conn._protocol.has_pending_event():
            return None
        sock = conn.sock
        if sock is self._ready_socket:
            return None
        pending_sock = sock
        while isinstance(pending_sock, SSLTransport):
            if pending_sock.sslobj.pending() or pending_sock.incoming.pending:
                return None
            pending_sock = pending_sock.socket
        pending = getattr(pending_sock, "pending", None)
        if pending is not None and pending():
            return None
        if self._read_deadline is None:
            self._read_timeout = sock.gettimeout()
            if self._read_timeout is not None:
                self._read_deadline = time.monotonic() + self._read_timeout
        return lambda: self._wait_for_read(sock)

    def _wait_for_read(self, sock: socket.socket | SSLTransport) -> None:
        remaining = (
            None
            if self._read_deadline is None
            else max(0, self._read_deadline - time.monotonic())
        )
        with self._read_error_catcher():
            with self._read_wait_lock:
                if self._read_closed:
                    return
                try:
                    if not wait_for_read(sock, remaining):  # type: ignore[arg-type]
                        raise socket.timeout("Read timed out")
                except (OSError, ValueError):
                    if self._read_closed:
                        return
                    raise
        self._ready_socket = sock

    def send_payload(self, buf: str | bytes) -> None:
        response, police = self._response, self._police_officer
        if self._dsa is None or response is None or police is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        with police.borrow(response):
            try:
                if isinstance(buf, str):
                    self._protocol.send_text(buf.encode("utf-8"))
                else:
                    self._protocol.send_binary(buf)
            except WebSocketException as exc:
                self.close()
                raise ProtocolError from exc
            self._flush()

    def ping(self) -> None:
        response, police = self._response, self._police_officer
        if self._dsa is None or response is None or police is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        with police.borrow(response):
            try:
                self._protocol.send_ping(b"")
            except WebSocketException as exc:
                self.close()
                raise ProtocolError from exc
            self._flush()
