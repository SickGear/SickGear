from __future__ import annotations

import enum
import sys
from asyncio import CancelledError, events, tasks
from types import TracebackType

__all__ = (
    "Timeout",
    "timeout",
)

_HAS_CANCELLATION_COUNT = sys.version_info >= (3, 11)


class _State(enum.Enum):
    CREATED = "created"
    ENTERED = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    EXITED = "finished"


class Timeout:
    """Asynchronous context manager for cancelling overdue coroutines.

    Use `timeout()` or `timeout_at()` rather than instantiating this class directly.
    """

    def __init__(self, when: float | None) -> None:
        """Schedule a timeout that will trigger at a given loop time.

        - If `when` is `None`, the timeout will never trigger.
        - If `when < loop.time()`, the timeout will trigger on the next
          iteration of the event loop.
        """
        self._state = _State.CREATED

        self._timeout_handler: events.TimerHandle | events.Handle | None = None
        self._task: tasks.Task | None = None  # type: ignore[type-arg]
        self._when = when

    def when(self) -> float | None:
        """Return the current deadline."""
        return self._when

    def reschedule(self, when: float | None) -> None:
        """Reschedule the timeout."""
        if self._state is not _State.ENTERED:
            if self._state is _State.CREATED:
                raise RuntimeError("Timeout has not been entered")
            raise RuntimeError(
                f"Cannot change state of {self._state.value} Timeout",
            )

        self._when = when

        if self._timeout_handler is not None:
            self._timeout_handler.cancel()

        if when is None:
            self._timeout_handler = None
        else:
            loop = events.get_running_loop()
            if when <= loop.time():
                self._timeout_handler = loop.call_soon(self._on_timeout)
            else:
                self._timeout_handler = loop.call_at(when, self._on_timeout)

    def expired(self) -> bool:
        """Is timeout expired during execution?"""
        return self._state in (_State.EXPIRING, _State.EXPIRED)

    def __repr__(self) -> str:
        info = [""]
        if self._state is _State.ENTERED:
            when = round(self._when, 3) if self._when is not None else None
            info.append(f"when={when}")
        info_str = " ".join(info)
        return f"<Timeout [{self._state.value}]{info_str}>"

    async def __aenter__(self) -> "Timeout":
        if self._state is not _State.CREATED:
            raise RuntimeError("Timeout has already been entered")
        task = tasks.current_task()
        if task is None:
            raise RuntimeError(  # Defensive: coroutine advanced outside a Task.
                "Timeout should be used inside a task"
            )
        self._state = _State.ENTERED
        self._task = task
        self._cancelling = task.cancelling() if _HAS_CANCELLATION_COUNT else 0
        self.reschedule(self._when)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._state in (_State.ENTERED, _State.EXPIRING)
        assert self._task is not None

        if self._timeout_handler is not None:
            self._timeout_handler.cancel()
            self._timeout_handler = None

        if self._state is _State.EXPIRING:
            self._state = _State.EXPIRED

            cancelling = self._task.uncancel() if _HAS_CANCELLATION_COUNT else 0
            if cancelling <= self._cancelling and exc_type is CancelledError:
                # Since there are no new cancel requests, we're
                # handling this.
                raise TimeoutError from exc_val
        elif self._state is _State.ENTERED:
            self._state = _State.EXITED

        return None

    def _on_timeout(self) -> None:
        assert self._state is _State.ENTERED
        assert self._task is not None

        self._task.cancel()
        self._state = _State.EXPIRING
        # drop the reference early
        self._timeout_handler = None


def timeout(delay: float | None) -> Timeout:
    """Timeout async context manager.

    Useful in cases when you want to apply timeout logic around block
    of code or in cases when asyncio.wait_for is not suitable. For example:

    >>> async with asyncio.timeout(10):  # 10 seconds timeout
    ...     await long_running_task()


    delay - value in seconds or None to disable timeout logic

    long_running_task() is interrupted by raising asyncio.CancelledError,
    the top-most affected timeout() context manager converts CancelledError
    into TimeoutError.
    """
    if sys.platform == "wasi":
        return Timeout(None)

    loop = events.get_running_loop()
    return Timeout(loop.time() + delay if delay is not None else None)
