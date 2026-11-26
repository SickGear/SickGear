from __future__ import annotations

import contextlib
import queue
import time
import typing
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock, Event, get_ident

from .._collections import GroupedDict

if typing.TYPE_CHECKING:
    from ..backend._base import ResponsePromise
    from ..connection import HTTPConnection
    from ..connectionpool import ConnectionPool
    from ..poolmanager import PoolKey
    from ..response import HTTPResponse

    MappableTraffic: typing.TypeAlias = typing.Union[
        HTTPResponse, ResponsePromise, PoolKey
    ]
    ManageableTraffic: typing.TypeAlias = typing.Union[HTTPConnection, ConnectionPool]

    from ._async.traffic_police import ManageableTraffic as AsyncManageableTraffic

    T = typing.TypeVar("T", bound=ManageableTraffic)
else:
    T = typing.TypeVar("T")


def _has_response_owner(conn: object, police: object) -> bool:
    """A formed response or returned promise still owns this connection."""
    return bool(getattr(conn, "_pending_responses", None)) or any(
        promise.get_parameter("police_officer") is police
        for promise in tuple(getattr(conn, "_promises", {}).values())
    )


class TrafficState(int, Enum):
    #: can be used to issue new request
    IDLE = 0
    #: can be used to issue new request + have stream opened
    USED = 1
    #: cannot be used to issue new request + have stream opened
    SATURATED = 2


class ItemPlaceholder:
    """A dummy placeholder to be inserted for spot reservation into the TrafficPolice."""

    @property
    def is_saturated(self) -> typing.Literal[True]:
        return True

    def close(self) -> None:
        pass


class TrafficPoliceFine(Exception): ...


class OverwhelmedTraffic(TrafficPoliceFine, queue.Full): ...


class UnavailableTraffic(TrafficPoliceFine, queue.Empty): ...


class AtomicTraffic(TrafficPoliceFine, queue.Empty): ...


def traffic_state_of(
    manageable_traffic: ManageableTraffic | AsyncManageableTraffic,
) -> TrafficState:
    if getattr(manageable_traffic, "is_saturated", False):
        return TrafficState.SATURATED
    else:
        return TrafficState.IDLE if manageable_traffic.is_idle else TrafficState.USED


@dataclass
class ActiveCursor(typing.Generic[T]):
    """Each Thread/Task is bound to a maximum of a single conn_or_pool. This represents the 'bound'."""

    obj_id: int
    conn_or_pool: T
    depth: int = 1
    # Only an untouched checkout retained for a returned response may be reclaimed.
    reserved_for: int | None = None


@dataclass
class PendingSignal(typing.Generic[T]):
    """A thread may want to sleep on a specific signal to avoid consuming CPU needlessly."""

    #: the owner thread must declare itself for the conn_or_pool transfer
    owner_thread_id: int = field(default_factory=get_ident)
    #: the inter-threads signal, when the condition is met, it's set.
    event: Event = field(default_factory=Event)

    #: the target makes the signal only trigger for that particular conn_or_pool
    target_conn_or_pool: T | None = None

    #: what conn_or_pool you get after the signal is received (if it's there, it's safe to use)
    conn_or_pool: T | None = None

    #: limited suite of state we want for the conn_or_pool
    states: tuple[TrafficState, ...] = (
        TrafficState.IDLE,
        TrafficState.USED,
        TrafficState.SATURATED,
    )


class TrafficPolice(typing.Generic[T]):
    """Thread-safe extended-Queue implementation.

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
        :param concurrency: Whether to allow a single item to be used across multiple threads.
            Delegating thread safety to another level.
        :param strict_maxsize: If True the scheduler does not increase maxsize for a temporary increase.
        """
        # Resolve after module loading and retain for cleanup after imports stop.
        # need to load class ref here to avoid cyclic deps and also avoid import
        # machinery in del gc teardown interpreter.
        from ..backend import ResponsePromise
        from ..response import HTTPResponse

        self._promise_type = ResponsePromise
        self._response_type = HTTPResponse

        self.maxsize = maxsize
        self.concurrency = concurrency
        self.strict_maxsize = strict_maxsize

        self._original_maxsize = maxsize

        #: the registry contain the conn_or_pool administrated
        self._registry: dict[int, T] = {}
        #: the container keep available conn_or_pool
        self._container: dict[int, T] = {}
        #: keeps track of what thread hold what conn_or_pool (and depth)
        self._cursor: dict[int, ActiveCursor[T]] = {}
        #: each thread can wait upon a specific container insertion
        self._signals: deque[PendingSignal[T]] = deque()

        #: we want to keep a mapping to know what object belong to what conn_or_pool
        #: this allows basic GPS
        self._map: GroupedDict[int | PoolKey, T] = GroupedDict(key_fn=id)
        self._map_types: GroupedDict[int | PoolKey, type] = GroupedDict()

        #: the police officer is unable to do more than one thread order at a time.
        self._lock = RLock()

        #: this toggle act the progressive disposal of all conn_or_pool registered.
        self._shutdown: bool = False

        self.parent: TrafficPolice | None = None  # type: ignore[type-arg]

    def _register_signal(
        self,
        expect_conn_or_pool: T | None = None,
        *states: TrafficState,
    ) -> PendingSignal[T]:
        """A thread declare waiting upon a specific condition."""
        signal = PendingSignal(
            target_conn_or_pool=expect_conn_or_pool,
        )

        if states:
            signal.states = states

        # We append right (prioritize) signal that usually wants to write new request
        if expect_conn_or_pool is not None:
            self._signals.append(signal)
        else:  # We deprioritize signal that wants to retrieve a response
            self._signals.appendleft(signal)

        # by doing the right/left append logic, we are leveraging multiplexing on capable conn_or_pool!
        return signal

    def _next_signal_or_container_insert(self, current_key: int) -> None:
        """We either transfer our cursor (active conn_or_pool) to some sleeping thread, or we reinsert it in the container."""
        active_cursor = self._cursor.pop(current_key)

        if not self._signals:
            self._container[active_cursor.obj_id] = active_cursor.conn_or_pool
            return

        cursor_state = traffic_state_of(active_cursor.conn_or_pool)

        next_signal: PendingSignal[T] | None = None

        for pending_signal in self._signals:
            if pending_signal.target_conn_or_pool is None:
                if cursor_state in pending_signal.states:
                    next_signal = pending_signal
                    break
            else:
                if (
                    id(pending_signal.target_conn_or_pool) == active_cursor.obj_id
                    and cursor_state in pending_signal.states
                ):
                    next_signal = pending_signal
                    break

        if next_signal is None:
            self._container[active_cursor.obj_id] = active_cursor.conn_or_pool
            return

        self._signals.remove(next_signal)
        next_signal.conn_or_pool = active_cursor.conn_or_pool

        self._cursor[next_signal.owner_thread_id] = ActiveCursor(
            obj_id=active_cursor.obj_id,
            conn_or_pool=active_cursor.conn_or_pool,
        )

        next_signal.event.set()

    @property
    def busy(self) -> bool:
        """Determine if the current thread hold a conn_or_pool that must be released asap."""
        with self._lock:
            return get_ident() in self._cursor

    @property
    def busy_with_placeholder(self) -> bool:
        """Determine if the current thread hold a conn_or_pool that must be released asap."""
        cursor_key = get_ident()
        with self._lock:
            return cursor_key in self._cursor and isinstance(
                self._cursor[cursor_key].conn_or_pool, ItemPlaceholder
            )

    def _reclaim_reservation(self, traffic_indicator: MappableTraffic) -> T | None:
        with self._lock:
            current = get_ident()
            for owner, cursor in tuple(self._cursor.items()):
                if cursor.reserved_for != id(traffic_indicator):
                    continue
                if current != owner and current in self._cursor:
                    return None
                cursor.reserved_for = None
                if current != owner:
                    # Publish the new owner before removing the old one.
                    self._cursor[current] = cursor
                    del self._cursor[owner]
                return cursor.conn_or_pool
            return None

    def is_held(self, conn_or_pool: T) -> bool:
        with self._lock:
            cursor_key = get_ident()

            if cursor_key not in self._cursor:
                return False

            active_cursor = self._cursor[cursor_key]

            return active_cursor.obj_id == id(conn_or_pool)

    @property
    def bag_only_idle(self) -> bool:
        """All manageable traffic is idle. No activities for all entries."""
        with self._lock:
            return all(
                traffic_state_of(_) is TrafficState.IDLE
                for _ in self._registry.values()
            )

    @property
    def bag_only_saturated(self) -> bool:
        """All manageable traffic is saturated. No more capacity available."""
        with self._lock:
            if not self._registry:
                return False
            return all(
                traffic_state_of(_) is TrafficState.SATURATED
                for _ in self._registry.values()
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._registry)

    def _map_clear(self, value: T) -> None:
        outdated_keys = list(self._map.keys_for(value))

        for key in outdated_keys:
            del self._map[key]
            del self._map_types[key]

    def _find_by(self, traffic_type: type, block: bool = True) -> T | None:
        """Find the first available conn or pool that is linked to at least one traffic type."""
        eligible_object_count = 0

        with self._lock:
            for kt in self._map_types.keys_for(traffic_type):
                eligible_object_count += 1

                conn_or_pool = self._map[kt]
                obj_id = id(conn_or_pool)

                if obj_id in self._container or (
                    self.concurrency and getattr(conn_or_pool, "pool", False) is None
                ):
                    # Reserve before unlocking, as we do when handing off to a waiter.
                    cursor_key = get_ident()
                    if cursor_key not in self._cursor:
                        if not self.concurrency:
                            del self._container[obj_id]
                        self._cursor[cursor_key] = ActiveCursor(obj_id, conn_or_pool)
                    return conn_or_pool

            if not block or not eligible_object_count:
                return None

            signal = self._register_signal(
                None,
                TrafficState.USED,
                TrafficState.SATURATED,
            )

        signal.event.wait()

        if signal.conn_or_pool is None:
            return None

        with self._lock:
            for mk in self._map.keys_for(signal.conn_or_pool):
                if self._map_types[mk] is not traffic_type:
                    continue
                return signal.conn_or_pool

            any_remaining_eligible_object = (
                next(self._map_types.keys_for(traffic_type).__iter__(), None)
                is not None
            )

        self.release()

        if not any_remaining_eligible_object:
            return None

        return self._find_by(
            traffic_type=traffic_type,
            block=block,
        )

    def kill_cursor(self) -> None:
        """Dispose of the object held by the current thread after a failure."""
        with self._lock:
            active_cursor = self._cursor.get(get_ident())
            if active_cursor is not None:
                self.kill(active_cursor.conn_or_pool)

    def kill(self, target: T, *, idle_only: bool = False) -> bool:
        """Dispose of a registered target, independently of the current cursor."""
        with self._lock:
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
                    cursor.obj_id == obj_id for cursor in self._cursor.values()
                ):
                    return False

            self._map_clear(target)
            self._registry.pop(obj_id, None)
            self._container.pop(obj_id, None)
            keys = [
                key for key, cursor in self._cursor.items() if cursor.obj_id == obj_id
            ]
            for key in keys:
                del self._cursor[key]
            if not self._registry:
                self._shutdown = False
            try:
                target.close()
            except Exception:  # Defensive: force cleanup phase
                pass

            signals_to_wake = []
            for pending_signal in self._signals:
                if not self._registry or pending_signal.target_conn_or_pool is target:
                    signals_to_wake.append(pending_signal)
            for pending_signal in signals_to_wake:
                self._signals.remove(pending_signal)

        for pending_signal in signals_to_wake:
            pending_signal.event.set()
        return True

    def _sacrifice_first_idle(self, block: bool = True) -> None:
        """When trying to fill the bag, arriving at the maxsize, we may want to remove an item.
        This method try its best to find the most appropriate idle item and removes it.
        """
        eligible_obj_id, eligible_conn_or_pool = None, None
        signal = None

        while True:
            with self._lock:
                if self.busy and self._cursor[get_ident()].obj_id in self._registry:
                    cursor_key = get_ident()
                    active_cursor = self._cursor[cursor_key]

                    if traffic_state_of(
                        active_cursor.conn_or_pool
                    ) is TrafficState.IDLE and not any(
                        key != cursor_key and cursor.obj_id == active_cursor.obj_id
                        for key, cursor in self._cursor.items()
                    ):
                        self._map_clear(active_cursor.conn_or_pool)

                        del self._registry[active_cursor.obj_id]
                        self._container.pop(active_cursor.obj_id, None)

                        try:
                            active_cursor.conn_or_pool.close()
                        except Exception:  # Defensive: force shutdown
                            pass

                        del self._cursor[cursor_key]
                        return

                if not self._registry:
                    return

                for obj_id, conn_or_pool in self._registry.items():
                    if (
                        obj_id in self._container
                        and traffic_state_of(conn_or_pool) is TrafficState.IDLE
                        and not any(
                            cursor.obj_id == obj_id for cursor in self._cursor.values()
                        )
                    ):
                        eligible_obj_id, eligible_conn_or_pool = obj_id, conn_or_pool
                        break

                if eligible_obj_id is not None and eligible_conn_or_pool is not None:
                    self._map_clear(eligible_conn_or_pool)

                    del self._registry[eligible_obj_id]
                    del self._container[eligible_obj_id]

                    try:
                        eligible_conn_or_pool.close()
                    except Exception:  # Defensive: force shutdown
                        pass

                    return

                if not block:
                    break

                signal = self._register_signal(None, TrafficState.IDLE)

            signal.event.wait()
            with self._lock:
                if self.maxsize is not None and len(self._registry) < self.maxsize:
                    return

        raise OverwhelmedTraffic(
            "Cannot select a disposable connection to ease the charge. "
            "This usually means that your pool sizing is insufficient, "
            "please increase your pool maxsize appropriately. "
            f"Currently set at maxsize={self.maxsize}. Usually you "
            "want as much as the number of active threads/connections."
        )

    def put(
        self,
        conn_or_pool: T,
        *traffic_indicators: MappableTraffic,
        block: bool = True,
        immediately_unavailable: bool = False,
    ) -> None:
        """Register and/or store the conn_or_pool into the TrafficPolice container."""

        cursor_key = get_ident()

        self._lock.acquire()

        # clear was called, each conn/pool that gets back must be destroyed appropriately.
        if self._shutdown and not immediately_unavailable:
            if self.is_held(conn_or_pool):
                self.release()
            self.kill(conn_or_pool, idle_only=True)
            self._lock.release()
            return

        # we want to dispose of conn_or_pool surplus as soon as possible
        if (
            self.maxsize is not None
            and len(self._registry) >= self.maxsize
            and id(conn_or_pool) not in self._registry
        ):
            self._lock.release()
            self._sacrifice_first_idle(block=block)
            self._lock.acquire()

        # Keep the shutdown check and ownership return atomic with clear().
        try:
            obj_id = id(conn_or_pool)
            registered_conn_or_pool = obj_id in self._registry

            # if we have already seen that one beforehand.
            if registered_conn_or_pool:
                # calling twice put? happen when release_conn=True & calling Response::release_conn() from error handler.
                if obj_id in self._container:
                    return
            else:  # register it
                self._registry[obj_id] = conn_or_pool

            if not immediately_unavailable:  # put back conn
                if not self.busy:
                    # that branch is mostly kept for backward compatibility
                    # with urllib3.
                    # e.g. get_conn multiple times (w/ maxsize=1), then put back any connection taken.
                    self._container[obj_id] = conn_or_pool
                else:
                    active_cursor = self._cursor[cursor_key]

                    active_cursor.reserved_for = None
                    active_cursor.depth -= 1

                    if active_cursor.depth == 0:
                        self._next_signal_or_container_insert(cursor_key)

            else:  # we may want to declare it unavailable immediately.
                if cursor_key not in self._cursor:
                    self._cursor[cursor_key] = ActiveCursor(obj_id, conn_or_pool)
                else:
                    raise AtomicTraffic(
                        "You must release the previous connection in order to acquire a new one."
                    )

                if self.concurrency is True and not isinstance(
                    conn_or_pool, ItemPlaceholder
                ):
                    self._container[obj_id] = conn_or_pool
        finally:
            self._lock.release()

        if traffic_indicators:
            for indicator in traffic_indicators:
                self.memorize(indicator, conn_or_pool)

    def iter_idle(self) -> typing.Generator[T, None, None]:
        with self._lock:
            if self.busy:
                raise AtomicTraffic(
                    "One connection/pool active per thread at a given time. "
                    "Call release prior to calling this method."
                )

            if self._container:
                idle_targets: list[tuple[int, T]] = []

                for cur_obj_id, cur_conn_or_pool in self._container.items():
                    if traffic_state_of(cur_conn_or_pool) is not TrafficState.IDLE:
                        continue

                    idle_targets.append((cur_obj_id, cur_conn_or_pool))

                cursor_key = get_ident()

                for obj_id, conn_or_pool in idle_targets:
                    del self._container[obj_id]

                    if cursor_key not in self._cursor:
                        self._cursor[cursor_key] = ActiveCursor(obj_id, conn_or_pool)
                    else:  # Defensive: unreachable
                        # this branch SHOULD never be evaluated!
                        self._cursor[cursor_key].reserved_for = None
                        self._cursor[cursor_key].depth += 1

                    if self.concurrency:
                        self._container[obj_id] = conn_or_pool

                    if (
                        hasattr(conn_or_pool, "is_connected")
                        and not conn_or_pool.is_connected
                    ):
                        self.kill_cursor()
                        continue

                    try:
                        yield conn_or_pool
                    finally:
                        self.release()

    def get_nowait(
        self, non_saturated_only: bool = False, not_idle_only: bool = False
    ) -> T | None:
        return self.get(
            block=False,
            non_saturated_only=non_saturated_only,
            not_idle_only=not_idle_only,
        )

    def get(
        self,
        block: bool = True,
        timeout: float | None = None,
        non_saturated_only: bool = False,
        not_idle_only: bool = False,
    ) -> T | None:
        if self.busy:
            raise AtomicTraffic(
                "One connection/pool active per thread at a given time. "
                "Call release prior to calling this method."
            )

        conn_or_pool = None
        signal = None

        with self._lock:
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
                    self.put(
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
                    cursor_key = get_ident()

                    if cursor_key not in self._cursor:
                        self._cursor[cursor_key] = ActiveCursor(obj_id, conn_or_pool)
                    else:  # Defensive: tolerate reentrant custom traffic objects.
                        self._cursor[cursor_key].reserved_for = None
                        self._cursor[cursor_key].depth += 1

                    if self.concurrency:
                        self._container[obj_id] = conn_or_pool

                    return conn_or_pool

            if block:
                signal = self._register_signal(
                    None,
                    TrafficState.IDLE,
                    TrafficState.USED,
                )

        if conn_or_pool is None:
            # hmm.. this should not exist..
            # unfortunately Requests has a weird test case
            # that set pool_size=0 to force trigger an
            # exception. don't remove that.
            if self.maxsize == 0:
                raise UnavailableTraffic("No connection available")

            if signal is not None:
                if not signal.event.wait(timeout=timeout):
                    with self._lock:
                        # Match locate(): a completed handoff wins the timeout race.
                        if not signal.event.is_set():
                            self._signals.remove(signal)
                            raise UnavailableTraffic(
                                f"No connection available within {timeout} second(s)"
                            )

                # in a very tight scenario (e.g. maxsize=1 and threads>=2)
                # a first thread can get 'None' and a reserved spot from get(...)
                # and the second can register a signal waiting for a conn being inserted
                # in container. but the first interaction with container will be
                # hotswapping of the initial "spot reserve" that will trigger
                # signal with conn_or_pool being None. we can safely go nested call
                # here.
                if signal.conn_or_pool is None:
                    return self.get(
                        block=block,
                        timeout=timeout,
                        non_saturated_only=non_saturated_only,
                        not_idle_only=not_idle_only,
                    )

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
        with self._lock:
            active_cursor = (
                self._cursor.get(get_ident())
                if conn_or_pool is None or reserve
                else None
            )
            if conn_or_pool is None:
                if active_cursor is None:
                    raise AtomicTraffic("No connection active on this thread")
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
        """Remove any referenced holder to map a traffic_indicator to his owner conn_or_pool."""
        key: PoolKey | int = (
            traffic_indicator
            if isinstance(traffic_indicator, tuple)
            else id(traffic_indicator)
        )

        with self._lock:
            if key in self._map:
                conn_or_pool = self._map[key]
                del self._map[key]
                del self._map_types[key]
                if self.concurrency and self._signals:
                    self._notify_idle(conn_or_pool)

        if self.parent is not None:
            try:
                self.parent.forget(traffic_indicator)
            except (
                UnavailableTraffic
            ):  # Defensive: unless specific bypasses higher/mock
                pass

    @contextlib.contextmanager
    def locate_or_hold(
        self,
        traffic_indicator: MappableTraffic | None = None,
        block: bool = True,
        placeholder_set: bool = False,
    ) -> typing.Generator[typing.Callable[[T], None] | T]:
        """Reserve a spot into the TrafficPolice instance while you construct your conn_or_pool.

        Creating a conn_or_pool may or may not take significant time, in order
        to avoid having many thread racing for TrafficPolice insert, we must
        have a way to instantly reserve a spot meanwhile we built what
        is required.
        """
        if traffic_indicator is not None:
            while True:
                conn_or_pool = self.locate(
                    traffic_indicator=traffic_indicator,
                    block=block,
                    release_on_missing=False,
                )

                if conn_or_pool is not None:
                    yield conn_or_pool
                    return

                if (
                    placeholder_set
                    or not self._registry
                    or self.maxsize is None
                    or len(self._registry) < self.maxsize
                ):
                    break
                # Waiting for capacity must not hold the lookup lock: other
                # threads need it to release the pools we could evict.
                self._lock.release()
                self._sacrifice_first_idle(block=block)

        traffic_indicators = []

        if traffic_indicator is not None:
            traffic_indicators.append(traffic_indicator)

        if not placeholder_set:
            self.put(
                ItemPlaceholder(),  # type: ignore[arg-type]
                *traffic_indicators,
                immediately_unavailable=True,
                block=block,
            )

        if traffic_indicator is not None:
            self._lock.release()

        swap_made: bool = False

        def inner_swap(swappable_conn_or_pool: T) -> None:
            nonlocal swap_made

            swap_made = True

            with self._lock:
                self.kill_cursor()
                self.put(
                    swappable_conn_or_pool,
                    *traffic_indicators,
                    immediately_unavailable=True,
                    block=False,
                )

        yield inner_swap

        if not swap_made:
            self.kill_cursor()

    def locate(
        self,
        traffic_indicator: MappableTraffic,
        block: bool = True,
        timeout: float | None = None,
        release_on_missing: bool = True,
        *,
        conn_pre_pick_callable: typing.Callable[[T], typing.Callable[[], None] | None]
        | None = None,
    ) -> T | None:
        """Locate and acquire the owner of a traffic indicator.

        The optional callback must not block. It returns None when ready, or a
        deferred wait to run without ownership. Reentrant borrows bypass it.
        """
        deadline = None
        if conn_pre_pick_callable is not None:
            if self.concurrency:
                raise ValueError("Pre-pick callbacks require exclusive ownership")
            if timeout is not None:
                deadline = time.monotonic() + timeout

        while True:
            if deadline is not None:
                timeout = max(0, deadline - time.monotonic())
            wait = None
            signal = None
            self._lock.acquire()

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
                self._lock.release()
                raise ValueError("unsupported traffic_indicator")

            if (
                conn_or_pool is None
                and obj_id is None
                and not isinstance(traffic_indicator, tuple)
            ):
                for r_obj_id, r_conn_or_pool in self._registry.items():
                    if hasattr(r_conn_or_pool, "pool") and isinstance(
                        r_conn_or_pool.pool, TrafficPolice
                    ):
                        if r_conn_or_pool.pool.beacon(traffic_indicator):
                            conn_or_pool, obj_id = r_conn_or_pool, r_obj_id
                            break

            if conn_or_pool is None or obj_id is None:
                if release_on_missing:
                    self._lock.release()
                return None

            if isinstance(conn_or_pool, ItemPlaceholder):
                signal_pre_locate = self._register_signal(
                    conn_or_pool, TrafficState.SATURATED
                )
                self._lock.release()

                if not signal_pre_locate.event.wait(timeout=timeout):
                    with self._lock:
                        if not signal_pre_locate.event.is_set():
                            if signal_pre_locate in self._signals:
                                self._signals.remove(signal_pre_locate)
                            raise TimeoutError(
                                "Timed out while waiting for conn_or_pool to become available"
                            )
                continue

            # Keep lookup and borrower/waiter registration atomic.
            try:
                cursor_key = get_ident()
                if obj_id not in self._registry and not (
                    self.concurrency and getattr(conn_or_pool, "pool", False) is None
                ):
                    raise UnavailableTraffic(
                        "The connection was closed before acquisition"
                    )
                active_cursor = self._cursor.get(cursor_key)
                if active_cursor is not None:
                    if active_cursor.obj_id == obj_id:
                        active_cursor.reserved_for = None
                        active_cursor.depth += 1

                        return active_cursor.conn_or_pool
                    raise AtomicTraffic(
                        "Seeking to locate a connection when having another one used, did you forget a call to release?"
                    )

                if obj_id not in self._container and not (
                    self.concurrency and getattr(conn_or_pool, "pool", False) is None
                ):
                    if not block:
                        raise UnavailableTraffic("Unavailable connection")
                else:
                    if conn_pre_pick_callable is not None:
                        wait = conn_pre_pick_callable(conn_or_pool)
                    if wait is None:
                        if not self.concurrency:
                            del self._container[obj_id]

                        if cursor_key not in self._cursor:
                            self._cursor[cursor_key] = ActiveCursor(
                                obj_id, conn_or_pool
                            )
                        else:  # Defensive: a custom readiness callback may reenter ownership.
                            self._cursor[cursor_key].reserved_for = None
                            self._cursor[cursor_key].depth += 1

                        return conn_or_pool

                if wait is None:
                    signal = self._register_signal(conn_or_pool)
            finally:
                self._lock.release()

            if signal is not None:
                if not signal.event.wait(timeout=timeout):
                    with self._lock:
                        # A transfer may have won the race with timeout. Otherwise
                        # remove the abandoned waiter so it cannot take ownership later.
                        if not signal.event.is_set():
                            self._signals.remove(signal)
                            raise TimeoutError(
                                "Timed out while waiting for conn_or_pool to become available"
                            )

                if signal.conn_or_pool is None or obj_id not in self._registry:
                    raise UnavailableTraffic(
                        "The signal was awaken without conn_or_pool assignment. "
                        "This means that a connection was broken, presumably in another thread."
                    )

                conn_or_pool = signal.conn_or_pool
                if conn_pre_pick_callable is None:
                    return conn_or_pool
                # A queued waiter already owns the connection after handoff.
                try:
                    wait = conn_pre_pick_callable(conn_or_pool)
                except BaseException:
                    self.release()
                    raise
                if wait is None:
                    return conn_or_pool
                self.release()

            if not block:
                raise UnavailableTraffic("Candidate is not ready")
            assert wait is not None
            wait()

    @contextlib.contextmanager
    def borrow(
        self,
        traffic_indicator: MappableTraffic | type | None = None,
        block: bool = True,
        timeout: float | None = None,
        not_idle_only: bool = False,
        *,
        conn_pre_pick_callable: typing.Callable[[T], typing.Callable[[], None] | None]
        | None = None,
    ) -> typing.Generator[T, None, None]:
        clean_exit = True
        conn_or_pool: T | None = None
        try:
            cursor_key = get_ident()

            if traffic_indicator:
                if isinstance(traffic_indicator, type):
                    conn_or_pool = self._find_by(traffic_indicator)

                    if conn_or_pool:
                        obj_id = id(conn_or_pool)
                        active_cursor = self._cursor[cursor_key]

                        if active_cursor.obj_id != obj_id:
                            raise AtomicTraffic(
                                "Seeking to locate a connection when having another one used, did you forget a call to release?"
                            )
                else:
                    conn_or_pool = self.locate(
                        traffic_indicator,
                        block=block,
                        timeout=timeout,
                        conn_pre_pick_callable=conn_pre_pick_callable,
                    )
            else:
                # simulate reentrant lock/borrow
                # get_response PM -> get_response HPM -> read R
                if self.busy:
                    active_cursor = self._cursor[cursor_key]
                    obj_id, conn_or_pool = (
                        active_cursor.obj_id,
                        active_cursor.conn_or_pool,
                    )
                    active_cursor.reserved_for = None
                    active_cursor.depth += 1
                else:
                    conn_or_pool = self.get(
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
                # killing the cursor immediately frees other threads waiting
                # in locate(...) (e.g. WebSocket reconnector calling close())
                # via UnavailableTraffic instead of letting them hang forever.
                # see https://github.com/jawah/urllib3.future/issues/371
                self.kill_cursor()
            else:
                self.release()

            if self._shutdown and conn_or_pool is not None:
                # release_conn() may have already returned ownership while reading.
                self.kill(conn_or_pool, idle_only=True)

    def release(self) -> None:
        with self._lock:
            cursor_key = get_ident()
            active_cursor = self._cursor.get(cursor_key)
            if active_cursor is None:
                # we want to allow calling release twice.
                # due to legacy urllib3 constraints[...]
                return

            active_cursor.reserved_for = None
            active_cursor.depth -= 1

            if active_cursor.depth == 0:
                if not self.concurrency:
                    self._next_signal_or_container_insert(cursor_key)
                else:
                    del self._cursor[cursor_key]
                    if self._signals:
                        self._notify_idle(active_cursor.conn_or_pool)

    def _notify_idle(self, conn_or_pool: T) -> None:
        """Wake eviction waiters after a pool is released or its response finishes.

        The caller holds our lock; waiters recheck availability before evicting.
        """
        obj_id = id(conn_or_pool)
        if traffic_state_of(conn_or_pool) is TrafficState.IDLE and not any(
            cursor.obj_id == obj_id for cursor in self._cursor.values()
        ):
            for signal in tuple(self._signals):
                if signal.target_conn_or_pool is None and signal.states == (
                    TrafficState.IDLE,
                ):
                    self._signals.remove(signal)
                    signal.event.set()

    @property
    def _has_pending_promises(self) -> bool:
        """Inspect promise routes without borrowing a connection."""
        ResponsePromise = self._promise_type

        with self._lock:
            return bool(self._map_types.keys_for(ResponsePromise))

    def clear(self) -> None:
        """Close child pools, retaining routes for returned promises until collected."""
        ResponsePromise = self._promise_type
        HTTPResponse = self._response_type

        with self._lock:
            self._shutdown = True
            cursor_key = get_ident()
            targets = list(self._registry.items())
            for obj_id, target in targets:
                child = getattr(target, "pool", None)
                if isinstance(child, TrafficPolice) and any(
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
                        target.close()
                    continue
                pending_responses = getattr(target, "_pending_responses", None)
                if (
                    isinstance(child, TrafficPolice)
                    or (
                        pending_responses is not None
                        and not _has_response_owner(target, self)
                        # EOF can precede release of a formed response's borrow.
                        and not any(
                            issubclass(self._map_types[key], HTTPResponse)
                            for key in self._map.keys_for(target)
                        )
                    )
                    or (
                        traffic_state_of(target) is TrafficState.IDLE
                        and not any(
                            key != cursor_key and cursor.obj_id == obj_id
                            for key, cursor in self._cursor.items()
                        )
                    )
                ):
                    self.kill(target)
            self._shutdown = any(obj_id in self._registry for obj_id, _ in targets)
            if self.concurrency:
                for signal in tuple(self._signals):
                    if signal.target_conn_or_pool is None and signal.states == (
                        TrafficState.IDLE,
                    ):
                        self._signals.remove(signal)
                        signal.event.set()

    def qsize(self) -> int:
        with self._lock:
            return len(self._container)

    def rsize(self) -> int:
        with self._lock:
            return len(self._registry)

    def empty(self) -> bool:
        return not self.rsize()

    def beacon(self, traffic_indicator: MappableTraffic | type) -> bool:
        """Answer the following question: Do this PoliceTraffic know about the traffic_indicator?"""
        if not isinstance(traffic_indicator, type):
            key: PoolKey | int = (
                traffic_indicator
                if isinstance(traffic_indicator, tuple)
                else id(traffic_indicator)
            )

            with self._lock:
                return key in self._map

        pre_acquired_conn: bool = self.busy

        try:
            return self._find_by(traffic_indicator) is not None
        finally:
            if not pre_acquired_conn and self.busy:
                self.release()

    def __repr__(self) -> str:
        with self._lock:
            is_saturated = self.bag_only_saturated
            is_idle = not is_saturated and self.bag_only_idle

            status: str

            if is_saturated:
                status = "Saturated"
            elif is_idle:
                status = "Idle"
            else:
                status = "Used"

            return f"<TrafficPolice {self.rsize()}/{self.maxsize} ({status})>"
