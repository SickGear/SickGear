from __future__ import annotations

import asyncio
import functools
import socket
import threading
import typing
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from time import monotonic

AddrInfo = typing.Tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    typing.Union[str, bytes],
    typing.Union[typing.Tuple[str, int], typing.Tuple[str, int, int, int]],
]
CacheKey = typing.Tuple[
    str,
    socket.AddressFamily,
    socket.SocketKind,
    int,
    int,
    bool,
]

_MAX_TTL = 2**31 - 1


def sanitize_ttl(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    if value > _MAX_TTL:
        return 0
    return value


def calculate_effective_ttl(values: typing.Iterable[object]) -> int:
    effective_ttl: int | None = None
    for value in values:
        ttl = sanitize_ttl(value)
        if ttl is None:
            return 0
        if effective_ttl is None or ttl < effective_ttl:
            effective_ttl = ttl
    return effective_ttl if effective_ttl is not None else 0


@dataclass(frozen=True)
class _CacheEntry:
    records: tuple[AddrInfo, ...]
    expires_at: float


class ResolutionResult(list):  # type: ignore[type-arg]
    """A resolver result carrying the shortest authoritative DNS TTL."""

    def __init__(self, records: typing.Iterable[AddrInfo], ttl: int) -> None:
        super().__init__(records)
        self.ttl = ttl


def _make_key(
    host: bytes | str | None,
    family: socket.AddressFamily,
    type: socket.SocketKind,
    proto: int,
    flags: int,
    quic_upgrade_via_dns_rr: bool,
) -> CacheKey:
    if host is None:
        normalized_host = ""
    elif isinstance(host, bytes):
        normalized_host = host.decode("ascii").lower()
    else:
        normalized_host = host.lower()

    return (
        normalized_host,
        family,
        type,
        proto,
        flags,
        quic_upgrade_via_dns_rr,
    )


def _set_port(records: typing.Iterable[AddrInfo], port: int) -> list[AddrInfo]:
    result = []
    for family, type, proto, canonname, sockaddr in records:
        if len(sockaddr) == 2:
            rebound_sockaddr: typing.Union[
                typing.Tuple[str, int], typing.Tuple[str, int, int, int]
            ] = (sockaddr[0], port)
        else:
            rebound_sockaddr = (sockaddr[0], port, sockaddr[2], sockaddr[3])
        result.append((family, type, proto, canonname, rebound_sockaddr))
    return result


class ResolverCache:
    def __init__(self, maxsize: int = 1024, max_ttl: int = 60) -> None:
        self._maxsize = max(0, maxsize)
        self._max_ttl = max(0, max_ttl)
        self._cache: OrderedDict[CacheKey, _CacheEntry] = OrderedDict()
        self._inflight: dict[CacheKey, Future[tuple[AddrInfo, ...]]] = {}
        self._lock = threading.Lock()

    def get_or_resolve(
        self,
        key: CacheKey,
        port: int,
        resolver: typing.Callable[[], list[AddrInfo]],
    ) -> list[AddrInfo]:
        now = monotonic()
        leader = False

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if entry.expires_at > now:
                    self._cache.move_to_end(key)
                    return _set_port(entry.records, port)
                del self._cache[key]

            future = self._inflight.get(key)
            if future is None:
                future = Future()
                self._inflight[key] = future
                leader = True

        if not leader:
            return _set_port(future.result(), port)

        try:
            resolved = resolver()
            records = tuple(_set_port(resolved, 0))

            if (
                self._maxsize
                and self._max_ttl
                and isinstance(resolved, ResolutionResult)
                and resolved.ttl > 0
            ):
                entry = _CacheEntry(
                    records, monotonic() + min(resolved.ttl, self._max_ttl)
                )
                with self._lock:
                    self._cache[key] = entry
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._maxsize:
                        self._cache.popitem(last=False)

            future.set_result(records)
            with self._lock:
                self._inflight.pop(key, None)
            return _set_port(records, port)
        except BaseException as e:
            future.set_exception(e)
            with self._lock:
                self._inflight.pop(key, None)
            raise


class AsyncResolverCache:
    def __init__(self, maxsize: int = 1024, max_ttl: int = 60) -> None:
        self._maxsize = max(0, maxsize)
        self._max_ttl = max(0, max_ttl)
        self._cache: OrderedDict[CacheKey, _CacheEntry] = OrderedDict()
        self._inflight: dict[CacheKey, asyncio.Task[tuple[AddrInfo, ...]]] = {}
        self._lock = asyncio.Lock()

    async def get_or_resolve(
        self,
        key: CacheKey,
        port: int,
        resolver: typing.Callable[[], typing.Awaitable[list[AddrInfo]]],
    ) -> list[AddrInfo]:
        now = monotonic()

        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if entry.expires_at > now:
                    self._cache.move_to_end(key)
                    return _set_port(entry.records, port)
                del self._cache[key]

            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._resolve(key, resolver))
                task.add_done_callback(self._consume_exception)
                self._inflight[key] = task

        return _set_port(await asyncio.shield(task), port)

    async def _resolve(
        self,
        key: CacheKey,
        resolver: typing.Callable[[], typing.Awaitable[list[AddrInfo]]],
    ) -> tuple[AddrInfo, ...]:
        try:
            resolved = await resolver()
            records = tuple(_set_port(resolved, 0))

            async with self._lock:
                if (
                    self._maxsize
                    and self._max_ttl
                    and isinstance(resolved, ResolutionResult)
                    and resolved.ttl > 0
                ):
                    self._cache[key] = _CacheEntry(
                        records, monotonic() + min(resolved.ttl, self._max_ttl)
                    )
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._maxsize:
                        self._cache.popitem(last=False)
                self._inflight.pop(key, None)

            return records
        except BaseException:
            async with self._lock:
                self._inflight.pop(key, None)
            raise

    @staticmethod
    def _consume_exception(task: asyncio.Task[tuple[AddrInfo, ...]]) -> None:
        try:
            task.exception()
        except BaseException:
            pass


def cache_resolution(
    func: typing.Callable[..., list[AddrInfo]],
) -> typing.Callable[..., list[AddrInfo]]:
    @functools.wraps(func)
    def wrapper(
        self: typing.Any,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[AddrInfo]:
        normalized_port = int(port) if port is not None else 0
        key = _make_key(host, family, type, proto, flags, quic_upgrade_via_dns_rr)
        cache = typing.cast(ResolverCache, self._resolver_cache)
        return cache.get_or_resolve(
            key,
            normalized_port,
            lambda: func(
                self,
                host,
                port,
                family,
                type,
                proto,
                flags,
                quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
            ),
        )

    return wrapper


def async_cache_resolution(
    func: typing.Callable[..., typing.Awaitable[list[AddrInfo]]],
) -> typing.Callable[..., typing.Awaitable[list[AddrInfo]]]:
    @functools.wraps(func)
    async def wrapper(
        self: typing.Any,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[AddrInfo]:
        normalized_port = int(port) if port is not None else 0
        key = _make_key(host, family, type, proto, flags, quic_upgrade_via_dns_rr)
        cache = typing.cast(AsyncResolverCache, self._resolver_cache)
        return await cache.get_or_resolve(
            key,
            normalized_port,
            lambda: func(
                self,
                host,
                port,
                family,
                type,
                proto,
                flags,
                quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
            ),
        )

    return wrapper
