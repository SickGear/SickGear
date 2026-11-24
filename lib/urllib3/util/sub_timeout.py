from __future__ import annotations

import time
import typing
from socket import timeout as SocketTimeout

if typing.TYPE_CHECKING:
    from socket import socket as _sync_socket

    from ..contrib.ssa import AsyncSocket as _async_socket


class SubTimeout:
    """Context manager that temporarily lowers a socket's timeout to honor
    a secondary deadline (e.g. a QUIC state-machine timer).

    When the secondary deadline expires before the primary timeout, the
    *on_timer* callback is invoked and the ``SocketTimeout`` exception is
    suppressed.  The caller can inspect :attr:`timer_fired` after the
    ``with`` block to decide whether to retry the I/O operation.

    When *next_timer* is ``None`` or falls after the primary timeout the
    context manager is a lightweight no-op, the original socket timeout
    is left untouched and any ``SocketTimeout`` raised inside the block
    propagates as a regular user timeout.

    Usage::

        sub = SubTimeout(sock, protocol.next_timer(), send_pending)
        with sub:
            data = sock.recv(blocksize)
        if sub.timer_fired:
            continue  # timer was handled, retry
    """

    __slots__ = (
        "sock",
        "next_timer",
        "on_timer",
        "timer_fired",
        "_original_timeout",
        "_adjusted",
    )

    def __init__(
        self,
        sock: _sync_socket,
        next_timer: float | None,
        on_timer: typing.Callable[[], None],
    ) -> None:
        self.sock = sock
        self.next_timer = next_timer
        self.on_timer = on_timer
        self.timer_fired: bool = False
        self._original_timeout: float | None = None
        self._adjusted: bool = False

    def __enter__(self) -> SubTimeout:
        self._original_timeout = self.sock.gettimeout()

        if self.next_timer is not None:
            time_to_timer = self.next_timer - time.time()
            # Clamp to a tiny positive value so the socket stays in
            # blocking-with-timeout mode.  settimeout(0.0) would switch
            # to non-blocking and raise BlockingIOError instead of
            # SocketTimeout.
            time_to_timer = max(time_to_timer, 1e-6)

            if self._original_timeout is None or time_to_timer < self._original_timeout:
                self.sock.settimeout(time_to_timer)
                self._adjusted = True
            # When the existing timeout is shorter than time_to_timer we
            # intentionally leave the socket untouched so the user
            # timeout fires normally and is never mistaken for a timer
            # event.

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: typing.Any,
    ) -> bool:
        if self._adjusted:
            self.sock.settimeout(self._original_timeout)

        if exc_type is SocketTimeout and self._adjusted:
            self.timer_fired = True
            self.on_timer()
            return True  # suppress the timeout exception

        return False


class AsyncSubTimeout:
    """Async counterpart of :class:`SubTimeout`."""

    __slots__ = (
        "sock",
        "next_timer",
        "on_timer",
        "timer_fired",
        "_original_timeout",
        "_adjusted",
    )

    def __init__(
        self,
        sock: _async_socket,
        next_timer: float | None,
        on_timer: typing.Callable[[], typing.Awaitable[None]],
    ) -> None:
        self.sock = sock
        self.next_timer = next_timer
        self.on_timer = on_timer
        self.timer_fired: bool = False
        self._original_timeout: float | None = None
        self._adjusted: bool = False

    async def __aenter__(self) -> AsyncSubTimeout:
        self._original_timeout = self.sock.gettimeout()

        if self.next_timer is not None:
            time_to_timer = self.next_timer - time.time()
            time_to_timer = max(time_to_timer, 1e-6)

            if self._original_timeout is None or time_to_timer < self._original_timeout:
                self.sock.settimeout(time_to_timer)
                self._adjusted = True

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: typing.Any,
    ) -> bool:
        if self._adjusted:
            self.sock.settimeout(self._original_timeout)

        if exc_type is SocketTimeout and self._adjusted:
            self.timer_fired = True
            await self.on_timer()
            return True

        return False
