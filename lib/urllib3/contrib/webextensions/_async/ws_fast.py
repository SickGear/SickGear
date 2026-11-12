from __future__ import annotations

import asyncio
import time
import typing
from socket import timeout as SocketTimeout

from websockets.exceptions import WebSocketException
from websockets.protocol import OPEN

from ....exceptions import ProtocolError, ReadTimeoutError
from ....util.traffic_police import UnavailableTraffic
from .protocol import AsyncExtensionFromHTTP
from ..ws_fast import _WebsocketsEngine, _NEED_DATA
from ...ssa import AsyncSocket

if typing.TYPE_CHECKING:
    from ...._async.response import AsyncHTTPResponse
    from ...._async.connection import AsyncHTTPConnection


class AsyncFastWebSocketExtensionFromHTTP(_WebsocketsEngine, AsyncExtensionFromHTTP):
    def __init__(self) -> None:
        super().__init__()
        self._init_engine()
        self._read_lock: asyncio.Lock | None = None
        self._ready_socket: AsyncSocket | None = None

    async def start(self, response: AsyncHTTPResponse) -> None:
        await super().start(response)
        self._accept(response.headers)

    async def _flush(self) -> None:
        assert self._dsa is not None
        for data in self._protocol.data_to_send():
            if data:
                async with self._write_error_catcher():
                    await self._dsa.sendall(data)

    async def close(self) -> None:
        """End the WebSocket and release its transport ownership."""
        self._read_closed = True
        response, police = self._response, self._police_officer
        if self._dsa is not None and police is not None:
            try:
                async with police.borrow(response):
                    dsa = self._dsa
                    if dsa is None:
                        return  # Defensive: HTTP/1 close removes the connection before a queued closer can reenter.
                    try:
                        if self._protocol.state is OPEN:
                            self._protocol.send_close()
                        for data in self._protocol.data_to_send():
                            if data:
                                await dsa.sendall(data)
                    except (WebSocketException, OSError, AssertionError):
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
                    message = self._next_message()
                    if message is not _NEED_DATA:
                        if message is None:
                            await self.close()
                        return typing.cast("str | bytes | None", message)

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

                        self._feed(data)
                        await self._flush()
                        message = self._next_message()
                        if message is not _NEED_DATA:
                            if message is None:
                                await self.close()
                            return typing.cast("str | bytes | None", message)
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
        response, police = self._response, self._police_officer
        if self._dsa is None or response is None or police is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        async with police.borrow(response):
            try:
                if isinstance(buf, str):
                    self._protocol.send_text(buf.encode("utf-8"))
                else:
                    self._protocol.send_binary(buf)
            except WebSocketException as exc:
                await self.close()
                raise ProtocolError from exc
            await self._flush()

    async def ping(self) -> None:
        response, police = self._response, self._police_officer
        if self._dsa is None or response is None or police is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        async with police.borrow(response):
            try:
                self._protocol.send_ping(b"")
            except WebSocketException as exc:
                await self.close()
                raise ProtocolError from exc
            await self._flush()
