from __future__ import annotations

import asyncio
import collections
import contextlib
import sys
import time
import typing
from dataclasses import dataclass, field

from ..traffic_police import (
    AtomicTraffic,
    OverwhelmedTraffic,
    TrafficState,
    UnavailableTraffic,
    traffic_state_of,
    ItemPlaceholder,
    _has_response_owner,
)
from ...contrib.ssa._timeout import timeout as ctx_expire_in
from ..._collections import GroupedDict

if typing.TYPE_CHECKING:
    from ..._async.connection import AsyncHTTPConnection
    from ..._async.connectionpool import AsyncConnectionPool
    from ..._async.response import AsyncHTTPResponse
    from ...backend import ResponsePromise
    from ...poolmanager import PoolKey

    MappableTraffic: typing.TypeAlias = typing.Union[
        AsyncHTTPResponse, ResponsePromise, PoolKey
    ]
    ManageableTraffic: typing.TypeAlias = typing.Union[
        AsyncHTTPConnection, AsyncConnectionPool
    ]

    T = typing.TypeVar("T", bound=ManageableTraffic)
else:
    T = typing.TypeVar("T")


@dataclass
class ActiveCursor(typing.Generic[T]):
    """Duplicated from sync part for typing reasons. 'T' in TrafficPolice sync is bound to sync types!"""

    obj_id: int
    conn_or_pool: T
    depth: int = 1
    # Only an untouched checkout retained for a returned response may be reclaimed.
    reserved_for: int | None = None


def _current_task_or_die() -> asyncio.Task[typing.Any]:
    t = asyncio.current_task()
    if t is None:
        raise RuntimeError(  # Defensive: overly protective
            "Attempt to call function outside of (async) running event loop"
        )
    return t


@dataclass
class AsyncPendingSignal(typing.Generic[T]):
    """A task may want to block on a specific signal to avoid consuming CPU needlessly."""

    owner_task: asyncio.Task[typing.Any] = field(default_factory=_current_task_or_die)
    #: the signal itself, when the condition is met, it's set.
    event: asyncio.Event = field(default_factory=asyncio.Event)

    #: the target makes the signal only trigger for that particular conn_or_pool
    target_conn_or_pool: T | None = None
    target_obj_id: int | None = None

    #: what conn_or_pool you get after the signal is received (if it's there, it's safe to use)
    conn_or_pool: T | None = None

    #: limited suite of state we want for the conn_or_pool or None
    states: tuple[TrafficState, ...] = (
        TrafficState.IDLE,
        TrafficState.USED,
        TrafficState.SATURATED,
    )


# Target delay in seconds (100 µs). This is the approximate time we want
# the event-loop thread to stall so the kernel can accumulate
# several incoming segments before the next recv() call.
_COALESCE_DELAY: float = 0.0001

if sys.platform == "win32":
    # Windows lacks nanosleep, let's improvise!
    # A perf_counter spin-wait is the only portable way to get consistent
    # sub-millisecond blocking on Windows. 100 µs of busy-waiting is
    # negligible in practice (< 0.5 % of a typical request lifecycle).
    _perf_counter = time.perf_counter

    def _kernel_recv_coalesce() -> None:
        deadline = _perf_counter() + _COALESCE_DELAY
        while _perf_counter() < deadline:
            pass

else:
    # Every POSIX platform (Linux, macOS, FreeBSD, ...) exposes nanosleep
    # through time.sleep() with µs-level accuracy.  This is both precise
    # and CPU-friendly: the thread truly sleeps instead of spinning.
    # we are effectively letting the kernel coalesce as much packet as possible.
    def _kernel_recv_coalesce() -> None:
        time.sleep(_COALESCE_DELAY)


def _intent_to_write(*states: TrafficState) -> bool:
    """Infer whether the caller wants to WRITE (True) or READ (False)
    based on the traffic states being queried.

    Querying exclusively for states with remaining request capacity
    (IDLE, USED) implies a WRITE intent — looking for a connection to
    send a new request on.
    Querying for states with open streams that may be at capacity
    (SATURATED) implies a READ intent — waiting to consume responses.
    """
    return TrafficState.SATURATED not in states


class AsyncSignals(typing.Generic[T]):
    """The signal mgr counterpart of our synchronous implementation but for monothreaded/goto label version."""

    def __init__(
        self, cursors: dict[asyncio.Task[typing.Any], ActiveCursor[T]]
    ) -> None:
        self._priority_signals: collections.deque[AsyncPendingSignal[T]] = (
            collections.deque()
        )
        self._furthest_signals: collections.deque[AsyncPendingSignal[T]] = (
            collections.deque()
        )

        #: set if there is no waiter for write + no specific target
        self._generic_waiters: asyncio.Event = asyncio.Event()
        self._generic_waiters.set()

        self._saturated_signals: dict[int, asyncio.Event] = {}

        #: ref to higher cursors held in AsyncTrafficPolice
        self._cursors: dict[asyncio.Task[typing.Any], ActiveCursor[T]] = cursors

        self._writing_tasks: set[asyncio.Task[typing.Any]] = set()

        self._last_dispatch_end = 0.0
        self._ema_gap = 0.0

    def declare_writing(self) -> None:
        self._writing_tasks.add(_current_task_or_die())

    def terminate_writing(self) -> bool:
        current_task = _current_task_or_die()
        if current_task in self._writing_tasks:
            self._writing_tasks.remove(current_task)
            return self._refresh_generic_waiters()
        return False

    def _refresh_generic_waiters(self) -> bool:
        if self._writing_tasks or self._priority_signals:
            if self._generic_waiters.is_set():
                self._generic_waiters.clear()
                return True
        else:
            if not self._generic_waiters.is_set():
                self._generic_waiters.set()
                return True

        return False

    def register(
        self,
        target_conn_or_pool: T | None,
        *states: TrafficState,
    ) -> AsyncPendingSignal[T]:
        signal = AsyncPendingSignal(
            states=states,
            target_conn_or_pool=target_conn_or_pool,
        )

        if target_conn_or_pool is not None:
            obj_id = id(target_conn_or_pool)
            signal.target_obj_id = obj_id

            if obj_id not in self._saturated_signals:
                self._saturated_signals[obj_id] = asyncio.Event()

        if _intent_to_write(*states):
            self._priority_signals.appendleft(signal)
        else:
            self._furthest_signals.append(signal)

        return signal

    def unregister(
        self,
        signal: AsyncPendingSignal[T],
        unblock: bool = False,
    ) -> None:
        try:
            if signal in self._priority_signals:
                self._priority_signals.remove(signal)
            else:
                self._furthest_signals.remove(signal)
        except ValueError:  # Defensive: no longer in deque racing.
            pass
        if unblock:
            signal.event.set()

    def should_queue_read_operation(
        self,
        target_conn_or_pool: T,
    ) -> bool:
        if self._generic_waiters.is_set():
            return False
        elif traffic_state_of(target_conn_or_pool) is TrafficState.SATURATED:
            return False

        obj_id = id(target_conn_or_pool)

        if obj_id not in self._saturated_signals:
            self._saturated_signals[obj_id] = asyncio.Event()

        if self._saturated_signals[obj_id].is_set():
            return False
        elif self._priority_signals:
            return True

        return False

    def kill(self, obj_id: int) -> bool:
        any_broadcast_push: bool = False

        if obj_id in self._saturated_signals:
            condition = self._saturated_signals.pop(obj_id)
            condition.set()
            any_broadcast_push = True

        awoken_signals = []

        if self._priority_signals:
            awoken_signal = self._priority_signals.popleft()
            awoken_signal.event.set()
            any_broadcast_push = True

        for signal in self._furthest_signals:
            if signal.target_obj_id is None or signal.target_obj_id == obj_id:
                signal.event.set()
                awoken_signals.append(signal)

        for awoken_signal in awoken_signals:
            self._furthest_signals.remove(awoken_signal)

        tasks = [
            task for task, cursor in self._cursors.items() if cursor.obj_id == obj_id
        ]
        for task in tasks:
            del self._cursors[task]
            self._writing_tasks.discard(task)
        self._refresh_generic_waiters()

        if awoken_signals:
            return True

        return any_broadcast_push

    def next(self) -> bool:
        current_task = _current_task_or_die()

        if current_task not in self._cursors:
            raise AtomicTraffic

        cursor = self._cursors[current_task]

        # this code will certainly surprise most people
        # in our investigations, the signal management
        # was often "too fast" to let the Kernel stack
        # into the buffer coalesced TCP packets, leading
        # the event loop to wasting a couple of iterations
        # (e.g. epoll_wait) when a single one was sufficient
        # and asyncio/OSes don't have a "wake me when
        # we have more than x bytes".
        # so we were creative (or foolish) enough to
        # stall the event loop in highly concurrent scenarii
        # where we expect plenty of bytes into the socket.
        # below is heuristic, caution. it's not a silver
        # bullet.
        if not getattr(cursor.conn_or_pool, "_fast_recv_mode", True):
            now = time.perf_counter()

            # Natural gap = time the event loop spent between dispatches
            # (excludes our own sleep from last time)
            if self._last_dispatch_end > 0:
                natural_gap = now - self._last_dispatch_end
                # Smooth with EMA to avoid reacting to transient spikes
                self._ema_gap = self._ema_gap * 0.7 + natural_gap * 0.3

                remaining = _COALESCE_DELAY - self._ema_gap

                if remaining > 0:
                    _kernel_recv_coalesce()  # or spin-wait on Windows

            # ... bookkeeping, signal dispatch ...
            self._last_dispatch_end = time.perf_counter()

        if not (
            self._priority_signals or self._furthest_signals or self._saturated_signals
        ):
            return False

        current_state = traffic_state_of(cursor.conn_or_pool)
        can_write_more: bool = current_state is not TrafficState.SATURATED

        if cursor.obj_id in self._saturated_signals:
            event = self._saturated_signals[cursor.obj_id]

            if current_state is TrafficState.SATURATED:
                if not event.is_set():
                    event.set()
            else:
                if event.is_set():
                    event.clear()

        anything_pending_write: bool = bool(self._priority_signals)

        if anything_pending_write and can_write_more:
            early_unpack_signal = self._priority_signals.pop()

            early_unpack_signal.conn_or_pool = cursor.conn_or_pool

            # transfer the cursor
            del self._cursors[current_task]
            self._cursors[early_unpack_signal.owner_task] = cursor
            cursor.reserved_for = None
            cursor.depth = 1

            # The caller cleared the previous writer; register the new owner.
            self._writing_tasks.add(early_unpack_signal.owner_task)

            early_unpack_signal.event.set()
            self._refresh_generic_waiters()
            return True

        late_signal_elected: AsyncPendingSignal[T] | None = None

        for signal in self._furthest_signals:
            if current_state not in signal.states:
                continue

            if signal.target_obj_id is None or signal.target_obj_id == cursor.obj_id:
                late_signal_elected = signal
                break

        if late_signal_elected is not None:
            late_signal_elected.conn_or_pool = cursor.conn_or_pool
            del self._cursors[current_task]
            self._cursors[late_signal_elected.owner_task] = cursor
            cursor.reserved_for = None
            cursor.depth = 1

            late_signal_elected.event.set()

            self._furthest_signals.remove(late_signal_elected)

            self._refresh_generic_waiters()
            return True

        return False


class AsyncTrafficPolice(typing.Generic[T]):
    """Task-safe extended-Queue implementation.

    This class is made to enforce the 'I will have order!' psychopath philosophy.
    Rational: Recent HTTP protocols handle concurrent streams, therefore it is
    not as flat as before, we need to answer the following problems:

    1) we cannot just dispose of the oldest connection/pool, it may have a pending response in it.
    2) we need a map, a dumb and simple GPS, to avoid wasting CPU resources searching for a response (promise resolution).
       - that would permit doing read(x) on one response and then read(x) on another without compromising the concerned
         connection.
       - multiplexed protocols can permit temporary locking of a single connection even if response isn't consumed
         (instead of locking through entire lifecycle single request).

    This program is (very) complex and need, for patches, at least both unit tests and integration tests passing.
    """

    def __init__(
        self,
        maxsize: int | None = None,
        concurrency: bool = False,
        strict_maxsize: bool = True,
    ):
        """
        :param maxsize: Maximum number of items that can be contained.
        :param concurrency: Whether to allow a single item to be used across multiple tasks.
        :param strict_maxsize: If True the scheduler does not increase maxsize for a temporary increase.
        """
        # Resolve after module loading and retain for cleanup after imports stop.
        from ...backend import ResponsePromise
        from ..._async.response import AsyncHTTPResponse

        self._promise_type = ResponsePromise
        self._response_type = AsyncHTTPResponse

        self.maxsize = maxsize
        self.concurrency = concurrency
        self.strict_maxsize = strict_maxsize

        self._original_maxsize = maxsize

        self._registry: dict[int, T] = {}
        self._container: dict[int, T] = {}

        self._map: GroupedDict[int | PoolKey, T] = GroupedDict(key_fn=id)
        self._map_types: GroupedDict[int | PoolKey, type] = GroupedDict()

        self._shutdown: bool = False

        self._cursors: dict[asyncio.Task[typing.Any], ActiveCursor[T]] = {}
        self._gc_tasks: set[asyncio.Task[None]] = set()

        self.parent: AsyncTrafficPolice | None = None  # type: ignore[type-arg]

        self._signals = AsyncSignals(self._cursors)

    def _schedule_gc_close(self, response: AsyncHTTPResponse) -> None:
        # Invoked on the response's owning loop; retain tasks until they finish.
        task = asyncio.create_task(response._close_from_gc())
        self._gc_tasks.add(task)
        task.add_done_callback(self._gc_tasks.discard)

    @property
    def _cursor(self) -> ActiveCursor[T] | None:
        current_task = _current_task_or_die()
        return self._cursors.get(current_task)

    @property
    def busy(self) -> bool:
        return self._cursor is not None

    def _reclaim_reservation(self, traffic_indicator: MappableTraffic) -> T | None:
        current = _current_task_or_die()
        for owner, cursor in tuple(self._cursors.items()):
            if cursor.reserved_for != id(traffic_indicator):
                continue
            if current != owner and current in self._cursors:
                return None
            cursor.reserved_for = None
            if current != owner:
                self._cursors[current] = cursor
                del self._cursors[owner]
                if owner in self._signals._writing_tasks:
                    self._signals._writing_tasks.remove(owner)
                    self._signals._writing_tasks.add(current)
            return cursor.conn_or_pool
        return None

    def is_held(self, conn_or_pool: T) -> bool:
        active_cursor = self._cursor

        if active_cursor is None:
            return False

        return active_cursor.obj_id == id(conn_or_pool)

    @property
    def bag_only_idle(self) -> bool:
        return all(
            traffic_state_of(_) is TrafficState.IDLE for _ in self._registry.values()
        )

    @property
    def bag_only_saturated(self) -> bool:
        """All manageable traffic is saturated. No more capacity available."""
        if not self._registry:
            return False
        return all(
            traffic_state_of(_) is TrafficState.SATURATED
            for _ in self._registry.values()
        )

    @property
    def bag_not_saturated(self) -> bool:
        if not self._registry:
            return False

        for conn in self._registry.values():
            if traffic_state_of(conn) is not TrafficState.SATURATED:
                return True

        return False

    def __len__(self) -> int:
        return len(self._registry)

    def _map_clear(self, value: T) -> None:
        outdated_keys = list(self._map.keys_for(value))

        for key in outdated_keys:
            del self._map[key]
            del self._map_types[key]

    async def _find_by(self, traffic_type: type, block: bool = True) -> T | None:
        """Find the first available conn or pool that is linked to at least one traffic type."""
        eligible_object_count = 0

        for tk in self._map_types.keys_for(traffic_type):
            eligible_object_count += 1

            conn_or_pool = self._map[tk]
            obj_id = id(conn_or_pool)

            if obj_id in self._container or (
                self.concurrency and getattr(conn_or_pool, "pool", False) is None
            ):
                return conn_or_pool

        if not block or not eligible_object_count:
            return None

        signal = self._signals.register(
            None,
            # A drained connection must also wake readers so they can recheck
            # whether any matching traffic remains.
            TrafficState.IDLE,
            TrafficState.USED,
            TrafficState.SATURATED,
        )

        try:
            await signal.event.wait()
        except asyncio.CancelledError:
            self._signals.unregister(signal)
            raise

        if signal.conn_or_pool is not None:
            for mk in self._map.keys_for(signal.conn_or_pool):
                if self._map_types[mk] is not traffic_type:
                    continue
                return signal.conn_or_pool

            self.release()

        any_remaining_eligible_object = (
            next(self._map_types.keys_for(traffic_type).__iter__(), None) is not None
        )

        if not any_remaining_eligible_object:
            return None

        return await self._find_by(
            traffic_type=traffic_type,
            block=block,
        )

    async def kill_cursor(self) -> None:
        """Dispose of the object held by the current task after a failure."""
        active_cursor = self._cursor
        if active_cursor is not None:
            await self.kill(active_cursor.conn_or_pool)

    async def kill(self, target: T, *, idle_only: bool = False) -> bool:
        """Dispose of a registered target, independently of the current cursor."""
        obj_id = id(target)
        if (
            obj_id not in self._registry
            and not self._map.keys_for(target)
            and not self.is_held(target)
        ):
            return False
        pending_responses = getattr(target, "_pending_responses", None)
        if idle_only:
            # Returned promises and formed responses both keep the connection alive.
            busy = (
                _has_response_owner(target, self)
                if self._shutdown and pending_responses is not None
                else traffic_state_of(target) is not TrafficState.IDLE
            )
            if busy or any(
                cursor.obj_id == obj_id for cursor in self._cursors.values()
            ):
                return False

        # Detach before awaiting close so the target cannot be borrowed again.
        self._map_clear(target)
        self._registry.pop(obj_id, None)
        self._container.pop(obj_id, None)
        if not self._registry:
            self._shutdown = False
        signalled = self._signals.kill(obj_id)
        try:
            await target.close()
        except Exception:
            pass
        if signalled:
            await asyncio.sleep(0)
        return True

    async def _sacrifice_first_idle(self, block: bool = True) -> None:
        """When trying to fill the bag, arriving at the maxsize, we may want to remove an item.
        This method try its best to find the most appropriate idle item and removes it.
        """
        eligible_obj_id, eligible_conn_or_pool = None, None

        if not self._registry:
            return

        current_task = _current_task_or_die()
        for obj_id, conn_or_pool in self._registry.items():
            if (
                obj_id in self._container
                and traffic_state_of(conn_or_pool) is TrafficState.IDLE
                and not any(
                    task is not current_task and cursor.obj_id == obj_id
                    for task, cursor in self._cursors.items()
                )
            ):
                eligible_obj_id, eligible_conn_or_pool = obj_id, conn_or_pool
                break

        if eligible_obj_id is not None and eligible_conn_or_pool is not None:
            self._map_clear(eligible_conn_or_pool)

            del self._registry[eligible_obj_id]
            del self._container[eligible_obj_id]

            await self.put(
                ItemPlaceholder(),  # type: ignore[arg-type]
                immediately_unavailable=True,
                block=block,
            )

            try:
                await eligible_conn_or_pool.close()
            except Exception:
                pass

            return

        if not block:
            raise OverwhelmedTraffic(
                "Cannot select a disposable connection to ease the charge. "
                "This usually means that your pool sizing is insufficient, "
                "please increase your pool maxsize appropriately. "
                f"Currently set at maxsize={self.maxsize}. Usually you "
                "want as much as the number of active tasks/connections."
            )

        signal = self._signals.register(
            None,
            TrafficState.IDLE,
        )

        try:
            await signal.event.wait()
        except asyncio.CancelledError:
            self._signals.unregister(signal)
            raise

        if self.maxsize is not None and len(self._registry) < self.maxsize:
            return
        await self._sacrifice_first_idle(block=block)

    async def iter_idle(self) -> typing.AsyncGenerator[T, None]:
        """Iterate over idle conn contained in the container bag."""
        if self.busy:
            raise AtomicTraffic(
                "One connection/pool active per thread at a given time. "
                "Call release prior to calling this method."
            )

        current_task = _current_task_or_die()

        if self._container:
            idle_targets: list[tuple[int, T]] = []

            for cur_obj_id, cur_conn_or_pool in self._container.items():
                if traffic_state_of(cur_conn_or_pool) is not TrafficState.IDLE:
                    continue

                idle_targets.append((cur_obj_id, cur_conn_or_pool))

            for obj_id, conn_or_pool in idle_targets:
                if (
                    obj_id not in self._container
                    or traffic_state_of(conn_or_pool) is not TrafficState.IDLE
                ):
                    continue

                if (
                    not self.concurrency
                ):  # i.e. no exclusive access to conn_or_pool, no lock.
                    del self._container[obj_id]

                self._cursors[current_task] = ActiveCursor(obj_id, conn_or_pool)

                if (
                    hasattr(conn_or_pool, "is_connected")
                    and not conn_or_pool.is_connected
                ):
                    await self.kill_cursor()

                    continue

                try:
                    yield conn_or_pool
                finally:
                    self.release()

    async def put(
        self,
        conn_or_pool: T,
        *traffic_indicators: MappableTraffic,
        block: bool = True,
        immediately_unavailable: bool = False,
    ) -> None:
        current_task = _current_task_or_die()

        # clear was called, each conn/pool that gets back must be destroyed appropriately.
        if self._shutdown and not immediately_unavailable:
            if self.is_held(conn_or_pool) and self.release():
                await asyncio.sleep(0)
            await self.kill(conn_or_pool, idle_only=True)
            return

        if (
            self.maxsize is not None
            and len(self._registry) >= self.maxsize
            and id(conn_or_pool) not in self._registry
        ):
            await self._sacrifice_first_idle(block=block)

            # we need this because we await conn close
            # in sacrifice idle, and asyncio scheduler
            # yield control to another task.
            # so we placed a placeholder to avoid
            # another task taking the spot.
            active_cursor = self._cursors.get(current_task)
            if active_cursor is not None:
                del self._registry[active_cursor.obj_id]
                del self._cursors[current_task]

        should_schedule_another_task: bool = False
        active_cursor = self._cursors.get(current_task)

        try:
            obj_id = id(conn_or_pool)
            registered_conn_or_pool = obj_id in self._registry

            if registered_conn_or_pool:
                if obj_id in self._container:
                    # calling twice put? for the same conn_or_pool[...]
                    # we remain conservative here on purpose. BC constraints with upstream.
                    return

                if active_cursor is not None:
                    if active_cursor.obj_id != obj_id:
                        raise AtomicTraffic(
                            "You must release the previous connection prior to this."
                        )

                    active_cursor.reserved_for = None
                    active_cursor.depth -= 1

                    if active_cursor.depth == 0:
                        if not self.concurrency:
                            if self._signals.terminate_writing():
                                should_schedule_another_task = True

                            if self._signals.next():
                                should_schedule_another_task = True
                            else:
                                del self._cursors[current_task]
                                self._container[obj_id] = conn_or_pool
                        else:
                            del self._cursors[current_task]
            else:
                self._registry[obj_id] = conn_or_pool
                if not immediately_unavailable:
                    self._container[obj_id] = conn_or_pool

            if immediately_unavailable:
                # it's "registered" but not available to others. thus setting the cursor on it.
                self._cursors[current_task] = ActiveCursor(obj_id, conn_or_pool)

                is_placeholder = isinstance(conn_or_pool, ItemPlaceholder)

                if not is_placeholder and not self.concurrency:
                    self._signals.declare_writing()

                # even with immediately_unavailable, if we're on a non-exclusive bag, then it's shared.
                if self.concurrency is True and not is_placeholder:
                    self._container[obj_id] = conn_or_pool
                    should_schedule_another_task = True

            if traffic_indicators:
                for indicator in traffic_indicators:
                    self.memorize(indicator, conn_or_pool)
        finally:
            if should_schedule_another_task:
                await asyncio.sleep(0)

    async def get_nowait(
        self, non_saturated_only: bool = False, not_idle_only: bool = False
    ) -> T | None:
        return await self.get(
            block=False,
            non_saturated_only=non_saturated_only,
            not_idle_only=not_idle_only,
        )

    async def get(
        self,
        block: bool = True,
        timeout: float | None = None,
        non_saturated_only: bool = False,  # ie. wants WRITE
        not_idle_only: bool = False,  # ie. wants READ
    ) -> T | None:
        conn_or_pool = None

        current_task = _current_task_or_die()

        if current_task in self._cursors:
            raise AtomicTraffic(
                "One connection/pool active per task at a given time. "
                "Call release prior to calling this method."
            )

        # This part is ugly but set for backward compatibility
        # urllib3 used to fill the bag with 'None'. This simulates that
        # old and bad behavior.
        # Held objects must not hide spare capacity from new requests.
        candidates = self._container if non_saturated_only else self._registry
        if (
            not self._container
            or all(
                traffic_state_of(obj) is TrafficState.SATURATED
                for obj in candidates.values()
            )
        ) and self.maxsize is not None:
            if self.maxsize > len(self._registry):
                await self.put(
                    ItemPlaceholder(),  # type: ignore[arg-type]
                    immediately_unavailable=True,
                    block=block,
                )
                return None

        if self._container:
            if non_saturated_only:
                obj_id, conn_or_pool = None, None
                for cur_obj_id, cur_conn_or_pool in self._container.items():
                    if traffic_state_of(cur_conn_or_pool) is TrafficState.SATURATED:
                        continue
                    obj_id, conn_or_pool = cur_obj_id, cur_conn_or_pool
                    break
                if obj_id is not None:
                    del self._container[obj_id]
            else:
                if not not_idle_only:
                    obj_id, conn_or_pool = self._container.popitem()
                else:
                    obj_id, conn_or_pool = None, None
                    for cur_obj_id, cur_conn_or_pool in self._container.items():
                        if traffic_state_of(cur_conn_or_pool) is TrafficState.IDLE:
                            continue
                        obj_id, conn_or_pool = cur_obj_id, cur_conn_or_pool
                        break
                    if obj_id is not None:
                        del self._container[obj_id]

            if obj_id is not None and conn_or_pool is not None:
                self._cursors[current_task] = ActiveCursor(obj_id, conn_or_pool)

                if self.concurrency:
                    self._container[obj_id] = conn_or_pool
                else:
                    if non_saturated_only:
                        self._signals.declare_writing()

                return conn_or_pool

        if block:
            if not_idle_only:
                states: tuple[TrafficState, ...] = (
                    TrafficState.USED,
                    TrafficState.SATURATED,
                )
            elif non_saturated_only:
                states = (
                    TrafficState.USED,
                    TrafficState.IDLE,
                )
            else:
                states = (
                    TrafficState.IDLE,
                    TrafficState.USED,
                    TrafficState.SATURATED,
                )

            signal = self._signals.register(
                None,
                *states,
            )

            try:
                if timeout is not None:
                    try:
                        async with ctx_expire_in(delay=timeout):
                            await signal.event.wait()
                    except TimeoutError as e:
                        # A timed-out waiter must not receive a later handoff.
                        self._signals.unregister(signal)
                        raise UnavailableTraffic(
                            f"No connection available within {timeout} second(s)"
                        ) from e
                else:
                    await signal.event.wait()
            except asyncio.CancelledError:
                self._signals.unregister(signal)
                raise

            if (
                signal.conn_or_pool is None
            ):  # case where a slot is free. (previously killed)
                await self.put(
                    ItemPlaceholder(),  # type: ignore[arg-type]
                    immediately_unavailable=True,
                    block=block,
                )
                return None
            return signal.conn_or_pool

        raise UnavailableTraffic("No connection available")

    def memorize(
        self,
        traffic_indicator: MappableTraffic,
        conn_or_pool: T | None = None,
        *,
        reserve: bool = False,
    ) -> None:
        """Register a route; reserve marks an existing checkout at response return."""
        active_cursor = self._cursor

        if conn_or_pool is None and active_cursor is None:
            raise AtomicTraffic("No connection active on the current task")

        if conn_or_pool is None:
            assert active_cursor is not None
            obj_id, conn_or_pool = active_cursor.obj_id, active_cursor.conn_or_pool
        else:
            obj_id, conn_or_pool = id(conn_or_pool), conn_or_pool

        if obj_id not in self._registry:
            # we raised an exception before
            # after consideration, it's best just
            # to ignore!
            return

        if isinstance(traffic_indicator, tuple):
            self._map[traffic_indicator] = conn_or_pool
            self._map_types[traffic_indicator] = type(traffic_indicator)
        else:
            traffic_indicator_id = id(traffic_indicator)
            if reserve and self._map.get(traffic_indicator_id) is not conn_or_pool:
                return  # A consumed response may already have lost its route.
            self._map[traffic_indicator_id] = conn_or_pool
            self._map_types[traffic_indicator_id] = type(traffic_indicator)
            if (
                reserve
                and not self.concurrency
                and active_cursor is not None
                and active_cursor.depth == 1
                and active_cursor.obj_id == obj_id
            ):
                active_cursor.reserved_for = traffic_indicator_id

    def forget(self, traffic_indicator: MappableTraffic) -> None:
        key: PoolKey | int = (
            traffic_indicator
            if isinstance(traffic_indicator, tuple)
            else id(traffic_indicator)
        )

        if key in self._map:
            conn_or_pool = self._map[key]
            del self._map[key]
            del self._map_types[key]
            if self.concurrency and self._signals._priority_signals:
                self._notify_idle(conn_or_pool)

        if self.parent is not None:
            try:
                self.parent.forget(traffic_indicator)
            except UnavailableTraffic:
                pass

    @contextlib.asynccontextmanager
    async def locate_or_hold(
        self,
        traffic_indicator: MappableTraffic | None = None,
        block: bool = True,
        placeholder_set: bool = False,
    ) -> typing.AsyncGenerator[typing.Callable[[T], typing.Awaitable[None]] | T]:
        """Reserve a spot into the TrafficPolice instance while you construct your conn_or_pool.

        Creating a conn_or_pool may or may not take significant time, in order
        to avoid having many thread racing for TrafficPolice insert, we must
        have a way to instantly reserve a spot meanwhile we built what
        is required.
        """
        if traffic_indicator is not None:
            conn_or_pool = await self.locate(
                traffic_indicator=traffic_indicator, block=block
            )

            if conn_or_pool is not None:
                yield conn_or_pool
                return

        traffic_indicators = []

        if traffic_indicator is not None:
            traffic_indicators.append(traffic_indicator)

        if not placeholder_set:
            await self.put(
                ItemPlaceholder(),  # type: ignore[arg-type]
                *traffic_indicators,
                immediately_unavailable=True,
                block=block,
            )

        swap_made: bool = False

        async def inner_swap(swappable_conn_or_pool: T) -> None:
            nonlocal swap_made

            swap_made = True

            current_task = _current_task_or_die()
            active_cursor = self._cursors.get(current_task)

            if (
                active_cursor is not None
            ):  # only allowed in tests, should never occur in real conditions.
                del self._registry[active_cursor.obj_id]
                del self._cursors[current_task]

            await self.put(
                swappable_conn_or_pool,
                *traffic_indicators,
                immediately_unavailable=True,
                block=False,
            )

        yield inner_swap

        if not swap_made:
            await self.kill_cursor()

    async def locate(
        self,
        traffic_indicator: MappableTraffic,
        block: bool = True,
        timeout: float | None = None,
        *,
        conn_pre_pick_callable: typing.Callable[
            [T], typing.Callable[[], typing.Awaitable[None]] | None
        ]
        | None = None,
    ) -> T | None:
        """Locate and acquire the owner of a traffic indicator.

        The optional callback must not block. It returns None when ready, or a
        deferred wait to run without ownership. Reentrant borrows bypass it.
        """
        deadline = time.monotonic() + timeout if timeout is not None else None
        if conn_pre_pick_callable is not None:
            if self.concurrency:
                raise ValueError("Pre-pick callbacks require exclusive ownership")

        while True:
            if deadline is not None:
                timeout = max(0, deadline - time.monotonic())
            wait = None
            if not isinstance(traffic_indicator, type):
                key: PoolKey | int = (
                    traffic_indicator
                    if isinstance(traffic_indicator, tuple)
                    else id(traffic_indicator)
                )

                conn_or_pool = self._map.get(key)
                if conn_or_pool is None:
                    # we must fallback on beacon (sub police officer if any)
                    obj_id = None
                else:
                    obj_id = id(conn_or_pool)
            else:
                raise ValueError("unsupported traffic_indicator")

            if (
                conn_or_pool is None
                and obj_id is None
                and not isinstance(traffic_indicator, tuple)
            ):
                for r_obj_id, r_conn_or_pool in self._registry.items():
                    if hasattr(r_conn_or_pool, "pool") and isinstance(
                        r_conn_or_pool.pool, AsyncTrafficPolice
                    ):
                        if await r_conn_or_pool.pool.beacon(traffic_indicator):
                            conn_or_pool, obj_id = r_conn_or_pool, r_obj_id
                            break

            if isinstance(conn_or_pool, ItemPlaceholder):
                if deadline is None:
                    await asyncio.sleep(0)
                else:
                    async with ctx_expire_in(timeout):
                        await asyncio.sleep(0)
                continue

            if conn_or_pool is None or obj_id is None:
                return None

            active_cursor = self._cursor

            if active_cursor is not None:
                if active_cursor.obj_id == obj_id:
                    active_cursor.reserved_for = None
                    active_cursor.depth += 1
                    return active_cursor.conn_or_pool
                raise AtomicTraffic(
                    "Seeking to locate a connection when having another one used, did you forget a call to release?"
                )

            if (
                obj_id not in self._container
                and not (
                    self.concurrency and getattr(conn_or_pool, "pool", False) is None
                )
            ) or self._signals.should_queue_read_operation(conn_or_pool):
                if not block:
                    raise UnavailableTraffic("Unavailable connection")

                signal = self._signals.register(
                    conn_or_pool,
                    TrafficState.IDLE,  # The owner may finish its last response before handoff.
                    TrafficState.USED,
                    TrafficState.SATURATED,
                )

                try:
                    if deadline is None:
                        await signal.event.wait()
                    else:
                        async with ctx_expire_in(timeout):
                            await signal.event.wait()
                except asyncio.CancelledError:
                    self._signals.unregister(signal)
                    raise
                except TimeoutError:
                    if deadline is not None:
                        self._signals.unregister(signal)
                    raise

                if (
                    signal.conn_or_pool is None
                    or signal.target_obj_id not in self._registry
                ):
                    raise UnavailableTraffic("Connection was killed in flight")
                if conn_pre_pick_callable is None:
                    return conn_or_pool
                # A queued waiter already owns the connection after handoff.
                try:
                    wait = conn_pre_pick_callable(conn_or_pool)
                except BaseException:
                    if self.release():
                        await asyncio.sleep(0)
                    raise
                if wait is None:
                    return conn_or_pool
                if self.release():
                    await asyncio.sleep(0)
            else:
                if conn_pre_pick_callable is not None:
                    wait = conn_pre_pick_callable(conn_or_pool)
                if wait is None:
                    self._cursors[_current_task_or_die()] = ActiveCursor(
                        obj_id, conn_or_pool
                    )

                    if not self.concurrency:
                        del self._container[obj_id]

                    return conn_or_pool

            if not block:
                raise UnavailableTraffic("Candidate is not ready")
            assert wait is not None
            await wait()

    @contextlib.asynccontextmanager
    async def borrow(
        self,
        traffic_indicator: MappableTraffic | type | None = None,
        block: bool = True,
        timeout: float | None = None,
        not_idle_only: bool = False,
        *,
        conn_pre_pick_callable: typing.Callable[
            [T], typing.Callable[[], typing.Awaitable[None]] | None
        ]
        | None = None,
    ) -> typing.AsyncGenerator[T, None]:
        clean_exit = True
        conn_or_pool: T | None = None
        try:
            if traffic_indicator:
                if isinstance(traffic_indicator, type):
                    conn_or_pool = await self._find_by(traffic_indicator)

                    if conn_or_pool:
                        obj_id = id(conn_or_pool)
                        active_cursor = self._cursor

                        if active_cursor is not None:
                            if active_cursor.obj_id != obj_id:
                                raise AtomicTraffic(
                                    "Seeking to locate a connection when having another one used, did you forget a call to release?"
                                )
                        else:
                            self._cursors[_current_task_or_die()] = ActiveCursor(
                                obj_id, conn_or_pool
                            )

                            if not self.concurrency:
                                del self._container[obj_id]
                else:
                    conn_or_pool = await self.locate(
                        traffic_indicator,
                        block=block,
                        timeout=timeout,
                        conn_pre_pick_callable=conn_pre_pick_callable,
                    )
            else:
                # simulate reentrant lock/borrow
                # get_response PM -> get_response HPM -> read R
                active_cursor = self._cursor
                if active_cursor is not None:
                    active_cursor.reserved_for = None
                    active_cursor.depth += 1
                    obj_id, conn_or_pool = (
                        active_cursor.obj_id,
                        active_cursor.conn_or_pool,
                    )
                else:
                    conn_or_pool = await self.get(
                        block=block, timeout=timeout, not_idle_only=not_idle_only
                    )
            if conn_or_pool is None:
                if traffic_indicator is not None:
                    raise UnavailableTraffic(
                        "No connection matches the traffic indicator (promise, response, ...)"
                    )
                raise UnavailableTraffic("No connection are available")
            yield conn_or_pool
        except Exception:
            clean_exit = False
            raise
        finally:
            # do not release back to the pool a broken connection
            # we need kill_cursor() to take over.
            # clean_exit=False not necessarily mean conn broken.
            # see https://github.com/jawah/urllib3.future/issues/366
            withhold_conn: bool = not clean_exit and getattr(
                conn_or_pool, "is_closed", False
            )

            if withhold_conn:
                # killing the cursor immediately frees other coroutines waiting
                # in locate(...) (e.g. WebSocket reconnector calling close())
                # via UnavailableTraffic instead of letting them hang forever.
                # see https://github.com/jawah/urllib3.future/issues/371
                await self.kill_cursor()
            elif self.release():
                await asyncio.sleep(0)

            if self._shutdown and conn_or_pool is not None:
                # release_conn() may have already returned ownership while reading.
                await self.kill(conn_or_pool, idle_only=True)

    def release(self) -> bool:
        current_task = _current_task_or_die()
        active_cursor = self._cursors.get(current_task)
        cursor_transferred: bool = False
        if active_cursor is not None:
            active_cursor.reserved_for = None
            active_cursor.depth -= 1

            if active_cursor.depth == 0:
                if not self.concurrency:
                    self._signals.terminate_writing()
                    cursor_transferred = self._signals.next()
                    if not cursor_transferred:
                        self._container[active_cursor.obj_id] = (
                            active_cursor.conn_or_pool
                        )
                        del self._cursors[current_task]
                else:
                    del self._cursors[current_task]
                    if self._signals._priority_signals:
                        self._notify_idle(active_cursor.conn_or_pool)

        return cursor_transferred

    def _notify_idle(self, conn_or_pool: T) -> None:
        """Wake eviction waiters after a pool is released or its response finishes."""
        obj_id = id(conn_or_pool)
        if traffic_state_of(conn_or_pool) is TrafficState.IDLE and not any(
            cursor.obj_id == obj_id for cursor in self._cursors.values()
        ):
            # Wake all so cancellation cannot consume the notification.
            for signal in tuple(self._signals._priority_signals):
                if signal.target_conn_or_pool is None and signal.states == (
                    TrafficState.IDLE,
                ):
                    self._signals.unregister(signal, unblock=True)
            self._signals._refresh_generic_waiters()

    @property
    def _has_pending_promises(self) -> bool:
        """Inspect promise routes without borrowing a connection."""
        ResponsePromise = self._promise_type

        return bool(self._map_types.keys_for(ResponsePromise))

    async def clear(self) -> None:
        """Close child pools, retaining routes for returned promises until collected."""
        ResponsePromise = self._promise_type
        AsyncHTTPResponse = self._response_type

        self._shutdown = True
        current_task = _current_task_or_die()
        targets = list(self._registry.items())
        for obj_id, target in targets:
            child = getattr(target, "pool", None)
            if isinstance(child, AsyncTrafficPolice) and any(
                self._map_types[key] is ResponsePromise
                for key in self._map.keys_for(target)
            ):
                # Keep promise routes, but free the active cache slot before closing.
                self._registry.pop(obj_id, None)
                self._container.pop(obj_id, None)
                for key in list(self._map.keys_for(target)):
                    if self._map_types[key] is not ResponsePromise:
                        del self._map[key]
                        del self._map_types[key]
                with contextlib.suppress(Exception):
                    await target.close()
                continue
            pending_responses = getattr(target, "_pending_responses", None)
            if (
                isinstance(child, AsyncTrafficPolice)
                or (
                    pending_responses is not None
                    and not _has_response_owner(target, self)
                    # EOF can precede release of a formed response's borrow.
                    and not any(
                        issubclass(self._map_types[key], AsyncHTTPResponse)
                        for key in self._map.keys_for(target)
                    )
                )
                or (
                    traffic_state_of(target) is TrafficState.IDLE
                    and not any(
                        task is not current_task and cursor.obj_id == obj_id
                        for task, cursor in self._cursors.items()
                    )
                )
            ):
                await self.kill(target)
        self._shutdown = any(obj_id in self._registry for obj_id, _ in targets)
        if self.concurrency:
            for signal in tuple(self._signals._priority_signals):
                if signal.target_conn_or_pool is None and signal.states == (
                    TrafficState.IDLE,
                ):
                    self._signals.unregister(signal, unblock=True)

    def qsize(self) -> int:
        return len(self._container)

    def rsize(self) -> int:
        return len(self._registry)

    def empty(self) -> bool:
        return not self.rsize()

    async def beacon(self, traffic_indicator: MappableTraffic | type) -> bool:
        if not isinstance(traffic_indicator, type):
            key: PoolKey | int = (
                traffic_indicator
                if isinstance(traffic_indicator, tuple)
                else id(traffic_indicator)
            )
            return key in self._map

        pre_acquired_conn: bool = self.busy

        try:
            return await self._find_by(traffic_indicator) is not None
        finally:
            if not pre_acquired_conn and self.busy:
                self.release()

    def __repr__(self) -> str:
        is_saturated = self.bag_only_saturated
        is_idle = not is_saturated and self.bag_only_idle

        status: str

        if is_saturated:
            status = "Saturated"
        elif is_idle:
            status = "Idle"
        else:
            status = "Used"

        return f"<AsyncTrafficPolice {self.rsize()}/{self.maxsize} ({status})>"
