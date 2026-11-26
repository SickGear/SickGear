from __future__ import annotations

import asyncio
import errno
import logging
import queue
import socket
import sys
import time
import typing
import warnings
from asyncio import Task
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from socket import timeout as SocketTimeout
from types import TracebackType
from weakref import proxy

from .._collections import HTTPHeaderDict
from .._constant import (
    DEFAULT_BACKGROUND_WATCH_WINDOW,
    DEFAULT_KEEPALIVE_DELAY,
    DEFAULT_KEEPALIVE_IDLE_WINDOW,
    MINIMAL_BACKGROUND_WATCH_WINDOW,
    MINIMAL_KEEPALIVE_IDLE_WINDOW,
)
from .._request_methods import AsyncRequestMethods
from .._typing import (
    _TYPE_ASYNC_BODY,
    _TYPE_BODY,
    _TYPE_BODY_POSITION,
    _TYPE_TIMEOUT,
    ProxyConfig,
)
from ..backend import ConnectionInfo, HttpVersion, ResponsePromise
from ..connection import _wrap_proxy_error
from ..connectionpool import _is_same_host, _normalize_host
from ..contrib.resolver import ProtocolResolver
from ..contrib.resolver._async import (
    AsyncBaseResolver,
    AsyncManyResolver,
    AsyncResolverDescription,
)
from ..contrib.ssa._timeout import timeout
from ..exceptions import (
    BaseSSLError,
    ClosedPoolError,
    EmptyPoolError,
    FullPoolError,
    HostChangedError,
    InsecureRequestWarning,
    LocationValueError,
    MaxRetryError,
    MustDowngradeError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ProxyError,
    ReadTimeoutError,
    RecoverableError,
    SSLError,
    TimeoutError as _TimeoutError,
)
from ..util._async.traffic_police import (  # type: ignore[attr-defined]
    AsyncTrafficPolice,
    UnavailableTraffic,
)
from ..util.connection import is_connection_dropped
from ..util.proxy import connection_requires_http_tunnel
from ..util.request import (
    NOT_FORWARDABLE_HEADERS,
    set_file_position,
    aset_file_position,
    is_async_file,
)
from ..util.retry import Retry
from ..util.ssl_match_hostname import CertificateError
from ..util.timeout import _DEFAULT_TIMEOUT, Timeout
from ..util.url import Url, _encode_host, _encode_target
from ..util.url import _normalize_host as normalize_host
from ..util.url import parse_url
from ..util.util import to_str
from .connection import (
    AsyncHTTPConnection,
    AsyncHTTPSConnection,
    BrokenPipeError,
    DummyConnection,
)
from .connection import port_by_scheme as port_by_scheme  # type: ignore[attr-defined]
from .response import AsyncHTTPResponse

if sys.platform == "wasi":
    # wasi don't support lazy import.
    from ..contrib.webextensions._async import load_extension as load_extension  # noqa: F401

if typing.TYPE_CHECKING:
    import ssl

    from typing_extensions import Literal

    from ..contrib.webextensions._async import AsyncExtensionFromHTTP

log = logging.getLogger(__name__)

_SelfT = typing.TypeVar("_SelfT")


# Pool objects
class AsyncConnectionPool:
    """
    Base class for all connection pools, such as
    :class:`.HTTPConnectionPool` and :class:`.HTTPSConnectionPool`.

    .. note::
       ConnectionPool.urlopen() does not normalize or percent-encode target URIs
       which is useful if your target server doesn't support percent-encoded
       target URIs.
    """

    scheme: str | None = None
    QueueCls = AsyncTrafficPolice

    def __init__(self, host: str, port: int | None = None) -> None:
        if not host:
            raise LocationValueError("No host specified.")

        self.host = _normalize_host(host, scheme=self.scheme)
        self.port = port

        # This property uses 'normalize_host()' (not '_normalize_host()')
        # to avoid removing square braces around IPv6 addresses.
        # This value is sent to `HTTPConnection.set_tunnel()` if called
        # because square braces are required for HTTP CONNECT tunneling.
        self._tunnel_host = normalize_host(host, scheme=self.scheme)

    def __str__(self) -> str:
        return f"{type(self).__name__}(host={self.host!r}, port={self.port!r})"

    async def __aenter__(self: _SelfT) -> _SelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        await self.close()
        # Return False to re-raise any potential exceptions
        return False

    async def close(self) -> None:
        """
        Close all pooled connections and disable the pool.
        """

    @property
    def is_idle(self) -> bool:
        raise NotImplementedError


# This is taken from http://hg.python.org/cpython/file/7aaba721ebc0/Lib/socket.py#l252
_blocking_errnos = {errno.EAGAIN, errno.EWOULDBLOCK}


async def idle_conn_watch_task(
    pool: AsyncHTTPConnectionPool,
    waiting_delay: float | int = 5.0,
    keepalive_delay: int | float | None = DEFAULT_KEEPALIVE_DELAY,
    keepalive_idle_window: int | float | None = DEFAULT_KEEPALIVE_IDLE_WINDOW,
) -> None:
    """Discrete background task that monitor incoming data
    and dispatch message to registered callbacks."""

    try:
        while pool.pool is not None:
            pool.num_background_watch_iter += 1

            await asyncio.sleep(waiting_delay)

            if pool.pool is None:
                return  # Defensive: pool may close after the stop-flag check above.
            connections = pool.pool.iter_idle()
            try:
                async for conn in connections:
                    now = time.monotonic()
                    last_used = conn.last_used_at
                    idle_delay = now - last_used

                    # don't peek into conn that just became idle
                    # waste of resource.
                    if idle_delay < 1.0:
                        continue

                    await conn.peek_and_react()

                    if (
                        keepalive_delay is not None
                        and keepalive_idle_window is not None
                    ):
                        connected_at = conn.connected_at

                        if connected_at is not None:
                            since_connection_delay = now - connected_at
                            if since_connection_delay <= keepalive_delay:
                                if idle_delay >= keepalive_idle_window:
                                    pool.num_pings += 1
                                    await conn.ping()
                                    await conn.peek_and_react(expect_frame=True)
            except AttributeError:
                return
            finally:
                # `async for` does not await generator cleanup on early exit.
                # Close iter_idle() here so its finally runs in this task.
                # Deferred finalization may run in another task, which cannot
                # release the watcher's TrafficPolice checkout.
                await connections.aclose()
    except asyncio.CancelledError:
        raise
    except ReferenceError:
        return


class AsyncHTTPConnectionPool(AsyncConnectionPool, AsyncRequestMethods):
    """
    Task-safe async connection pool for one host.

    :param host:
        Host used for this HTTP Connection (e.g. "localhost"), passed into
        :class:`http.client.HTTPConnection`.

    :param port:
        Port used for this HTTP Connection (None is equivalent to 80), passed
        into :class:`http.client.HTTPConnection`.

    :param timeout:
        Socket timeout in seconds for each individual connection. This can
        be a float or integer, which sets the timeout for the HTTP request,
        or an instance of :class:`urllib3.util.Timeout` which gives you more
        fine-grained control over request timeouts. After the constructor has
        been parsed, this is always a `urllib3.util.Timeout` object.

    :param maxsize:
        Connection capacity of this pool, defaulting to 1 for direct
        construction. A PoolManager supplies its num_pools value when maxsize
        was not specified. HTTP/2 and HTTP/3 connections can carry multiple
        requests, so this is not a request-concurrency limit.

    :param block:
        Retained for urllib3 compatibility. The built-in scheduler can wait at
        capacity with either value; block=False does not provide disposable
        overflow connections. Use pool_timeout on a request to bound acquisition.

    :param headers:
        Headers to include with all requests, unless other headers are given
        explicitly.

    :param retries:
        Retry configuration to use by default with requests in this pool.

    :param _proxy:
        Parsed proxy URL, should not be used directly, instead, see
        :class:`urllib3.ProxyManager`

    :param _proxy_headers:
        A dictionary with proxy headers, should not be used directly,
        instead, see :class:`urllib3.AsyncProxyManager`

    :param resolver:
        A manual configuration to use for DNS resolution.
        Can be a support DSN/str (e.g. "doh+cloudflare://") or a
        :class:`urllib3.AsyncResolverDescription` or a list of DSN/str or
        :class:`urllib3.AsyncResolverDescription`

    :param happy_eyeballs:
        Enable IETF Happy Eyeballs algorithm when trying to
        connect by concurrently try multiple IPv4/IPv6 endpoints.
        By default, tries at most 4 endpoints simultaneously.
        You may specify an int that override this default.
        Default, set to False.

    :param background_watch_delay:
        The window delay used by our discrete scheduler that run in
        dedicated task to collect unsolicited incoming data and react
        if necessary.

    :param keepalive_delay:
        The delay expressed in seconds on how long we should make sure
        the connection is kept alive by sending pings to the remote peer.
        Set it to None to void this feature.

    :param keepalive_idle_window:
        Immediately related to the parameter keepalive_delay.
        This one, expressed in seconds, specify how long after
        a connection is marked as idle we should send out a
        ping to the remote peer.

    :param \\**conn_kw:
        Additional parameters are used to create fresh :class:`urllib3._async.connection.AsyncHTTPConnection`,
        :class:`urllib3._async.connection.AsyncHTTPSConnection` instances.
    """

    scheme = "http"
    ConnectionCls: type[AsyncHTTPConnection] | type[AsyncHTTPSConnection] = (
        AsyncHTTPConnection
    )

    def __init__(
        self,
        host: str,
        port: int | None = None,
        timeout: _TYPE_TIMEOUT | None = _DEFAULT_TIMEOUT,
        maxsize: int = 1,
        block: bool = False,
        headers: typing.Mapping[str, str] | None = None,
        retries: Retry | bool | int | None = None,
        _proxy: Url | None = None,
        _proxy_headers: typing.Mapping[str, str] | None = None,
        _proxy_config: ProxyConfig | None = None,
        resolver: AsyncResolverDescription
        | list[AsyncResolverDescription]
        | str
        | list[str]
        | AsyncBaseResolver
        | None = None,
        happy_eyeballs: bool | int = False,
        background_watch_delay: int | float | None = DEFAULT_BACKGROUND_WATCH_WINDOW,
        keepalive_delay: int | float | None = DEFAULT_KEEPALIVE_DELAY,
        keepalive_idle_window: int | float | None = DEFAULT_KEEPALIVE_IDLE_WINDOW,
        **conn_kw: typing.Any,
    ):
        AsyncConnectionPool.__init__(self, host, port)
        AsyncRequestMethods.__init__(self, headers)

        if not isinstance(timeout, Timeout):
            timeout = Timeout.from_float(timeout)

        if retries is None:
            retries = Retry.DEFAULT

        self.timeout = timeout
        self.retries = retries
        self.happy_eyeballs = happy_eyeballs

        self._maxsize = maxsize

        if self.QueueCls is not AsyncTrafficPolice and not issubclass(
            self.QueueCls, AsyncTrafficPolice
        ):
            warnings.warn(
                "ConnectionPool QueueCls no longer support typical queue implementation "
                "due to its inability to answer urllib3.future needs to handle concurrent streams "
                "in a single connection. You may customize the implementation by passing a subclass of "
                "urllib3.util._async.traffic_police.AsyncTrafficPolice if necessary.",
                DeprecationWarning,
            )
            self.QueueCls = AsyncTrafficPolice

        self.block = block
        self.pool: AsyncTrafficPolice[AsyncHTTPConnection] | None = self.QueueCls(
            maxsize,
            concurrency=False,
            strict_maxsize=not self.block,
        )

        self._draining_pool: AsyncTrafficPolice[AsyncHTTPConnection] | None = None

        self.proxy = _proxy
        self.proxy_headers = _proxy_headers or {}
        self.proxy_config = _proxy_config

        # These are mostly for testing and debugging purposes.
        self.num_connections = 0
        self.num_requests = 0
        self.num_pings = 0
        self.num_background_watch_iter = 0

        # A protocol downgrade applies only to this origin pool.
        if "disabled_svn" in conn_kw:
            conn_kw["disabled_svn"] = set(conn_kw["disabled_svn"] or ())
        self.conn_kw = conn_kw

        if self.proxy:
            # Enable Nagle's algorithm for proxies, to avoid packet fragmentation.
            # We cannot know if the user has added default socket options, so we cannot replace the
            # list.
            self.conn_kw.setdefault("socket_options", [])

            self.conn_kw["proxy"] = self.proxy
            self.conn_kw["proxy_config"] = self.proxy_config

        self._own_resolver = not isinstance(resolver, AsyncBaseResolver)

        if resolver is None:
            resolver = [AsyncResolverDescription(ProtocolResolver.SYSTEM)]
        elif isinstance(resolver, str):
            resolver = [AsyncResolverDescription.from_url(resolver)]
        elif isinstance(resolver, AsyncResolverDescription):
            resolver = [resolver]

        self._resolvers: list[AsyncResolverDescription] = []

        if not isinstance(resolver, AsyncBaseResolver):
            can_resolve_localhost: bool = False

            for resolver_description in resolver:
                if isinstance(resolver_description, str):
                    self._resolvers.append(
                        AsyncResolverDescription.from_url(resolver_description)
                    )

                    if self._resolvers[-1].protocol == ProtocolResolver.SYSTEM:
                        can_resolve_localhost = True
                    continue

                self._resolvers.append(resolver_description)

                if self._resolvers[-1].protocol == ProtocolResolver.SYSTEM:
                    can_resolve_localhost = True

            if not can_resolve_localhost:
                self._resolvers.append(
                    AsyncResolverDescription.from_url(
                        "system://default?hosts=localhost"
                    )
                )

            #: We want to automatically forward ca_cert_data, ca_cert_dir, and ca_certs.
            for rd in self._resolvers:
                if "ca_cert_data" in conn_kw:
                    if "ca_cert_data" not in rd:
                        rd["ca_cert_data"] = conn_kw["ca_cert_data"]
                if "ca_cert_dir" in conn_kw:
                    if "ca_cert_dir" not in rd:
                        rd["ca_cert_dir"] = conn_kw["ca_cert_dir"]
                if "ca_certs" in conn_kw:
                    if "ca_certs" not in rd:
                        rd["ca_certs"] = conn_kw["ca_certs"]

        self._resolver: AsyncBaseResolver = (
            AsyncManyResolver(*[r.new() for r in self._resolvers])
            if not isinstance(resolver, AsyncBaseResolver)
            else resolver
        )

        self.conn_kw["resolver"] = self._resolver
        self.conn_kw["keepalive_delay"] = keepalive_delay

        self._background_watch_delay = background_watch_delay
        self._keepalive_delay = keepalive_delay
        self._keepalive_idle_window = keepalive_idle_window
        if (
            self._keepalive_idle_window is not None
            and self._keepalive_idle_window < MINIMAL_KEEPALIVE_IDLE_WINDOW
        ):
            self._keepalive_idle_window = MINIMAL_KEEPALIVE_IDLE_WINDOW
        self._background_monitoring: asyncio.Task | None = None  # type: ignore[type-arg]

    @property
    def is_idle(self) -> bool:
        police = self.pool
        if police is not None:
            return police.bag_only_idle
        police = self._draining_pool
        # Formed responses own their registry; only promises still need pool routing.
        return police is None or not police._has_pending_promises

    @property
    def is_saturated(self) -> bool:
        return self.pool is not None and self.pool.bag_only_saturated

    async def _new_conn(
        self, *, heb_timeout: Timeout | None = None
    ) -> AsyncHTTPConnection:
        """
        Return a fresh :class:`HTTPConnection`.
        """
        if self.pool is None:
            raise ClosedPoolError(
                self, "Pool is closed"
            )  # Defensive: callers normally reject closed pools before private connection creation.

        if (
            self._background_monitoring is None
            and self._background_watch_delay is not None
            and self._background_watch_delay >= MINIMAL_BACKGROUND_WATCH_WINDOW
        ):
            self._background_monitoring = asyncio.create_task(
                idle_conn_watch_task(
                    proxy(self),
                    self._background_watch_delay,
                    self._keepalive_delay,
                    self._keepalive_idle_window,
                )
            )

        self.num_connections += 1
        log.debug(
            "Starting new HTTP connection (%d): %s:%s",
            self.num_connections,
            self.host,
            self.port or "80",
        )

        conn = None

        async with self.pool.locate_or_hold(
            block=True, placeholder_set=True
        ) as swapper:
            # this path is applicable if resolver yield at least two records.
            # if A/AAAA records only (non-dual stack) -> spawn 4 (default) tasks with each record
            # if A/AAAA records mixed (dual stack)    -> spawn 4 (default) tasks following this pattern (IPv6, IPv4, IPv6, IPv4)
            # if single record A or AAAA -> ignore
            # Don't mind about HTTP/2 or 3 in here, we're unencrypted here!
            if self.happy_eyeballs:
                log.debug(
                    "Attempting Happy-Eyeball %s:%s",
                    self.host,
                    self.port or "443",
                )

                if heb_timeout is None:
                    heb_timeout = self.timeout

                override_timeout = (
                    heb_timeout.connect_timeout
                    if heb_timeout.connect_timeout is not None
                    and isinstance(heb_timeout.connect_timeout, (float, int))
                    else None
                )

                dt_pre_resolve = datetime.now(tz=timezone.utc)

                if override_timeout is not None:
                    try:
                        async with timeout(override_timeout):
                            ip_addresses = await self._resolver.getaddrinfo(
                                self.host,
                                self.port,
                                socket.AF_UNSPEC
                                if "socket_family" not in self.conn_kw
                                else self.conn_kw["socket_family"],
                                socket.SOCK_STREAM,
                                quic_upgrade_via_dns_rr=False,
                            )
                    except TimeoutError:
                        new_err = socket.gaierror(
                            f"unable to resolve '{self.host}' within {override_timeout}s"
                        )
                        raise NameResolutionError(self.host, self, new_err)
                else:
                    ip_addresses = await self._resolver.getaddrinfo(
                        self.host,
                        self.port,
                        socket.AF_UNSPEC
                        if "socket_family" not in self.conn_kw
                        else self.conn_kw["socket_family"],
                        socket.SOCK_STREAM,
                        quic_upgrade_via_dns_rr=False,
                    )

                delta_post_resolve = datetime.now(tz=timezone.utc) - dt_pre_resolve

                if len(ip_addresses) > 1:
                    ipv6_addresses = []
                    ipv4_addresses = []

                    for ip_address in ip_addresses:
                        if ip_address[0] == socket.AF_INET6:
                            ipv6_addresses.append(ip_address)
                        else:
                            ipv4_addresses.append(ip_address)

                    if ipv4_addresses and ipv6_addresses:
                        log.debug(
                            "Happy-Eyeball Dual-Stack %s:%s",
                            self.host,
                            self.port or "443",
                        )

                        intermediary_addresses = []
                        for ipv6_entry, ipv4_entry in zip_longest(
                            ipv6_addresses, ipv4_addresses
                        ):
                            if ipv6_entry:
                                intermediary_addresses.append(ipv6_entry)
                            if ipv4_entry:
                                intermediary_addresses.append(ipv4_entry)
                        ip_addresses = intermediary_addresses
                    else:
                        log.debug(
                            "Happy-Eyeball Single-Stack %s:%s",
                            self.host,
                            self.port or "443",
                        )

                    challengers = []
                    max_task = (
                        4
                        if isinstance(self.happy_eyeballs, bool)
                        else self.happy_eyeballs
                    )

                    ech_config_hex = ""
                    for ip_addr in ip_addresses:
                        if isinstance(ip_addr[3], bytes) and ip_addr[3]:
                            ech_config_hex = ip_addr[3].hex()
                            break

                    for ip_address in ip_addresses[:max_task]:
                        conn_kw = self.conn_kw.copy()
                        target_solo_addr = (
                            f"[{ip_address[-1][0]}]"
                            if ip_address[0] == socket.AF_INET6
                            else ip_address[-1][0]
                        )
                        inmemory_url = (
                            f"in-memory://default?hosts={self.host}:{target_solo_addr}"
                        )
                        if ech_config_hex:
                            inmemory_url += f"&ech_config={ech_config_hex}"
                        conn_kw["resolver"] = AsyncResolverDescription.from_url(
                            inmemory_url
                        ).new()
                        conn_kw["socket_family"] = ip_address[0]

                        if (
                            "source_address" in conn_kw
                            and conn_kw["source_address"] is not None
                        ):
                            conn_kw["source_address"] = (
                                conn_kw["source_address"][0],
                                0,
                            )

                        challengers.append(
                            self.ConnectionCls(
                                host=self.host,
                                port=self.port,
                                timeout=override_timeout,
                                **conn_kw,
                            )
                        )

                    tasks = [
                        asyncio.create_task(challenger.connect())
                        for i, challenger in enumerate(challengers)
                    ]

                    winner_task = None
                    pending: set[Task[None]] = set()

                    while True:
                        done, pending = await asyncio.wait(
                            tasks if not pending else pending,
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=override_timeout,
                        )

                        while done:
                            finished_task = done.pop()

                            if finished_task.exception() is None:
                                winner_task = finished_task

                            if finished_task.exception():
                                continue

                        if winner_task or not pending:
                            break

                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                    if winner_task is None:
                        await asyncio.gather(
                            *(challenger.close() for challenger in challengers),
                            return_exceptions=True,
                        )
                        within_delay_msg: str = (
                            f" within {override_timeout}s" if override_timeout else ""
                        )
                        raise NewConnectionError(
                            challengers[0],
                            f"Failed to establish a new connection: No suitable address to connect to using Happy Eyeballs algorithm for {self.host}:{self.port}{within_delay_msg}",
                        ) from tasks[0].exception()

                    conn = challengers[tasks.index(winner_task)]

                    # we have to replace the resolution latency metric
                    if conn.conn_info:
                        conn.conn_info.resolution_latency = delta_post_resolve

                    await asyncio.gather(
                        *(
                            challenger.close()
                            for challenger in challengers
                            if challenger is not conn
                        ),
                        return_exceptions=True,
                    )
                else:
                    log.debug(
                        "Happy-Eyeball Ineligible %s:%s",
                        self.host,
                        self.port or "443",
                    )

            if conn is None:
                conn = self.ConnectionCls(
                    host=self.host,
                    port=self.port,
                    timeout=self.timeout.connect_timeout,
                    **self.conn_kw,
                )

            await swapper(conn)  # type: ignore[operator]

        return conn

    async def _get_conn(
        self, timeout: float | None = None, *, heb_timeout: Timeout | None = None
    ) -> AsyncHTTPConnection:
        """
        Get a connection. Will return a pooled connection if one is available.

        If no connections are available and :prop:`.block` is ``False``, then a
        fresh connection is returned.

        :param timeout:
            Seconds to wait before giving up and raising
            :class:`urllib3.exceptions.EmptyPoolError` if the pool is empty and
            :prop:`.block` is ``True``.
        """
        conn = None

        if self.pool is None:
            raise ClosedPoolError(self, "Pool is closed.")

        try:
            conn = await self.pool.get(
                block=True, timeout=timeout, non_saturated_only=True
            )
        except AttributeError:  # self.pool is None
            raise ClosedPoolError(self, "Pool is closed.") from None  # Defensive:

        except queue.Empty:
            if self.block:
                raise EmptyPoolError(
                    self,
                    "Pool is empty and a new connection can't be opened due to blocking mode.",
                ) from None
            pass  # Oh well, we'll create a new connection then

        # If this is a persistent connection, check if it got disconnected
        if conn and is_connection_dropped(conn):
            log.debug("Resetting dropped connection: %s", self.host)
            await conn.close()
        elif conn and getattr(conn, "expect_pong", False):
            await conn.peek_and_react()

            if conn.expect_pong:
                log.debug("Resetting dropped connection: %s", self.host)
                await conn.close()
        elif conn and conn.is_idle:
            if await conn.peek_and_react() and is_connection_dropped(conn):
                log.debug("Resetting dropped connection: %s", self.host)
                await conn.close()

        try:
            return conn or await self._new_conn(heb_timeout=heb_timeout)
        except (  # Defensive: legacy _new_conn overrides may not accept heb_timeout.
            TypeError
        ):  # this branch catch overridden pool that don't support Happy-Eyeballs!
            conn = await self._new_conn()
            # as this branch is meant for people bypassing our main logic, we have to memorize the conn immediately
            # into our pool of conn.
            await self.pool.put(conn, immediately_unavailable=True)
            return conn

    async def _put_conn(self, conn: AsyncHTTPConnection) -> None:
        """
        Put a connection back into the pool.

        :param conn:
            Connection object for the current host and port as returned by
            :meth:`._new_conn` or :meth:`._get_conn`.

        If the pool is already full, the connection is closed and discarded
        because we exceeded maxsize. If connections are discarded frequently,
        then maxsize should be increased.

        If the pool is closed, then the connection will be closed and discarded.
        """

        if self.pool is not None:
            try:
                await self.pool.put(conn, block=True)
                return  # Everything is dandy, done.
            except AttributeError:  # Defensive: a concurrent close or custom queue may remove the pool during return.
                # self.pool is None.
                pass
            except queue.Full:  # Defensive: legacy queues may reject a blocking put; TrafficPolice waits for capacity.
                # Connection never got put back into the pool, close it.
                if conn:
                    if conn.is_idle:
                        await conn.close()

                if self.block:
                    # This should never happen if you got the conn from self._get_conn
                    raise FullPoolError(
                        self,
                        "Pool reached maximum size and no more connections are allowed.",
                    ) from None
                else:
                    # multiplexed connection may still have in-flight request not converted into response
                    # we shall not discard it until responses are consumed.
                    if conn and conn.is_idle is False:
                        log.warning(
                            "Connection pool is full, temporary increase, keeping connection, "
                            "multiplexed and not idle: %s. Connection pool size: %s",
                            self.host,
                            self.pool.qsize(),
                        )

                        if self.pool.maxsize is not None:
                            self.pool.maxsize += 1
                        return await self._put_conn(conn)

                log.warning(
                    "Connection pool is full, discarding connection: %s. Connection pool size: %s",
                    self.host,
                    self.pool.qsize(),
                )
                self.num_connections -= 1
                return

        # Connection never got put back into the pool, close it.
        if conn:
            await conn.close()
            self.num_connections -= 1

    async def _validate_conn(self, conn: AsyncHTTPConnection) -> None:
        """
        Called right before a request is made, after the socket is created.
        """
        if conn.is_closed:
            await conn.connect()

    async def _prepare_proxy(self, conn: AsyncHTTPConnection) -> None:
        # Nothing to do for HTTP connections.
        pass

    def _get_timeout(self, timeout: _TYPE_TIMEOUT) -> Timeout:
        """Helper that always returns a :class:`urllib3.util.Timeout`"""
        if timeout is _DEFAULT_TIMEOUT:
            return self.timeout.clone()

        if isinstance(timeout, Timeout):
            return timeout.clone()
        else:
            # User passed us an int/float. This is for backwards compatibility,
            # can be removed later
            return Timeout.from_float(timeout)

    def _raise_timeout(
        self,
        err: BaseSSLError | OSError | SocketTimeout,
        url: str,
        timeout_value: _TYPE_TIMEOUT | None,
    ) -> None:
        """Is the error actually a timeout? Will raise a ReadTimeout or pass"""

        if isinstance(err, SocketTimeout):
            raise ReadTimeoutError(
                self, url, f"Read timed out. (read timeout={timeout_value})"
            ) from err

        # See the above comment about EAGAIN in Python 3.
        if hasattr(err, "errno") and err.errno in _blocking_errnos:
            raise ReadTimeoutError(
                self, url, f"Read timed out. (read timeout={timeout_value})"
            ) from err

    async def get_response(
        self, *, promise: ResponsePromise | None = None
    ) -> AsyncHTTPResponse | None:
        """
        Retrieve the first response available in the pool.
        This method should be called after issuing at least one request with ``multiplexed=True``.
        If none available, return None.
        """
        police = self.pool
        if police is None:
            police = self._draining_pool
        if police is None:
            raise ClosedPoolError(self, "Pool is closed")

        if promise is not None and not isinstance(promise, ResponsePromise):
            raise TypeError(
                f"get_response only support ResponsePromise but received {type(promise)} instead. "
                f"This may occur if you expected the remote peer to support multiplexing but did not."
            )

        clean_exit = True

        try:
            async with police.borrow(
                promise or ResponsePromise,
                block=promise is not None,
                not_idle_only=True,
            ) as conn:
                if promise is not None:
                    # Restore this request's read timeout after other requests used the connection.
                    conn.timeout = typing.cast(
                        typing.Optional[float], promise.get_parameter("read_timeout")
                    )
                try:
                    response = await conn.getresponse(
                        promise=promise, police_officer=police
                    )
                except (BaseSSLError, OSError) as e:
                    if promise is not None:
                        url = typing.cast(str, promise.get_parameter("url"))
                    else:
                        url = ""
                    self._raise_timeout(err=e, url=url, timeout_value=conn.timeout)
                    raise
        except UnavailableTraffic:
            # force a cooperative checkpoint to keep the event loop running
            # see https://github.com/jawah/urllib3.future/issues/384
            await asyncio.sleep(0)
            return None
        except (
            _TimeoutError,
            OSError,
            ProtocolError,
            BaseSSLError,
            SSLError,
            CertificateError,
            ProxyError,
            RecoverableError,
        ) as e:
            if self.pool is None and not police._has_pending_promises:
                self._draining_pool = None
                if police.parent is not None:
                    police.parent._map_clear(self)
            # Discard the connection for these exceptions. It will be
            # replaced during the next _get_conn() call.
            clean_exit = False
            new_e: Exception = e
            if isinstance(e, (BaseSSLError, CertificateError)):
                new_e = SSLError(e)
            if isinstance(
                new_e,
                (
                    OSError,
                    NewConnectionError,
                    _TimeoutError,
                    SSLError,
                ),
            ) and (conn and conn.proxy and not conn.has_connected_to_proxy):
                new_e = _wrap_proxy_error(
                    new_e, conn.proxy.scheme
                )  # Defensive: custom connections may fail before recording proxy establishment.
            elif isinstance(new_e, OSError):
                new_e = ProtocolError("Connection aborted.", new_e)

            if promise is not None:
                retries = typing.cast(Retry, promise.get_parameter("retries"))

                method = typing.cast(str, promise.get_parameter("method"))
                url = typing.cast(str, promise.get_parameter("url"))

                retries = retries.increment(
                    method, url, error=new_e, _pool=self, _stacktrace=sys.exc_info()[2]
                )
                # Carry the remaining budget into the next response wait.
                promise.set_parameter("retries", retries)
                await retries.async_sleep()
            else:
                raise new_e  # we only retry if we were specified a specific promise. we can't blindly assume to retry.

            # Keep track of the error for the retry warning.
            err = e

        if not clean_exit:
            log.warning(
                "Retrying (%r) after connection broken by '%r': %s",
                retries,
                err,
                url,
                extra={"__urllib3-retry-warning": {"host": self.host}},
            )

            return await self.get_response(promise=promise)

        if promise is not None and response is None:
            raise ValueError(  # Defensive: built-in connections return a response with promise metadata or raise.
                "Invoked get_response with promise=... that no connection in pool recognize"
            )

        if response is None:
            return None  # Defensive: built-in connections return a response with promise metadata or raise.

        from_promise = None

        if promise:
            from_promise = promise
        else:
            if (
                response._fp
                and hasattr(response._fp, "from_promise")
                and response._fp.from_promise
            ):
                from_promise = response._fp.from_promise

        if from_promise is None:
            raise ValueError(  # Defensive: built-in connections return a response with promise metadata or raise.
                "Internal: Unable to identify originating ResponsePromise from a LowLevelResponse"
            )

        # Once collected, the response replaces the promise as registry owner.
        if self.pool is None and not police._has_pending_promises:
            self._draining_pool = None
        from_promise.set_parameter("police_officer", None)

        # Retrieve request ctx
        method = typing.cast(str, from_promise.get_parameter("method"))
        redirect = typing.cast(bool, from_promise.get_parameter("redirect"))

        # Handle redirect?
        redirect_location = redirect and response.get_redirect_location()
        if redirect_location:
            url = typing.cast(str, from_promise.get_parameter("url"))
            body = typing.cast(
                typing.Optional[_TYPE_BODY], from_promise.get_parameter("body")
            )
            headers = typing.cast(HTTPHeaderDict, from_promise.get_parameter("headers"))
            preload_content = typing.cast(
                bool, from_promise.get_parameter("preload_content")
            )
            decode_content = typing.cast(
                bool, from_promise.get_parameter("decode_content")
            )
            timeout = typing.cast(
                typing.Optional[_TYPE_TIMEOUT], from_promise.get_parameter("timeout")
            )

            assert_same_host = typing.cast(
                bool, from_promise.get_parameter("assert_same_host")
            )
            pool_timeout = from_promise.get_parameter("pool_timeout")
            response_kw = typing.cast(
                typing.MutableMapping[str, typing.Any],
                from_promise.get_parameter("response_kw"),
            )
            chunked = typing.cast(bool, from_promise.get_parameter("chunked"))
            body_pos = typing.cast(
                typing.Optional[_TYPE_BODY_POSITION],
                from_promise.get_parameter("body_pos"),
            )
            retries = typing.cast(Retry, from_promise.get_parameter("retries"))

            if response.status == 303:
                method = "GET"
                body = None
                chunked = False
                body_pos = None
                headers = HTTPHeaderDict(headers)

                for should_be_removed_header in NOT_FORWARDABLE_HEADERS:
                    headers.discard(should_be_removed_header)

            # Strip headers marked as unsafe to forward to the redirected location.
            # Check remove_headers_on_redirect to avoid a potential network call within
            # self.is_same_host() which may use socket.gethostbyname() in the future.
            if retries.remove_headers_on_redirect and not self.is_same_host(
                redirect_location
            ):
                headers = HTTPHeaderDict(headers)
                for header in list(headers):
                    if header.lower() in retries.remove_headers_on_redirect:
                        headers.discard(header)

            try:
                retries = retries.increment(method, url, response=response, _pool=self)
            except MaxRetryError:
                if retries.raise_on_redirect:
                    await response.drain_conn()
                    raise
                return response

            if retries.cache_response_body and response._body is None:
                await response.read(cache_content=True)
            await response.drain_conn()
            await retries.async_sleep_for_retry(response)
            log.debug("Redirecting %s -> %s", url, redirect_location)
            new_promise = await self.urlopen(
                method,
                redirect_location,
                body,
                headers,
                retries=retries,
                redirect=redirect,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=True,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=True,
                extension=from_promise.get_parameter("extension"),
                **response_kw,
            )

            return await self.get_response(promise=new_promise if promise else None)

        # Check if we should retry the HTTP response.
        has_retry_after = bool(response.headers.get("Retry-After"))
        retries = typing.cast(Retry, from_promise.get_parameter("retries"))

        if retries.is_retry(method, response.status, has_retry_after):
            url = typing.cast(str, from_promise.get_parameter("url"))
            body = typing.cast(
                typing.Optional[_TYPE_BODY], from_promise.get_parameter("body")
            )
            headers = typing.cast(HTTPHeaderDict, from_promise.get_parameter("headers"))
            preload_content = typing.cast(
                bool, from_promise.get_parameter("preload_content")
            )
            decode_content = typing.cast(
                bool, from_promise.get_parameter("decode_content")
            )
            timeout = typing.cast(
                typing.Optional[_TYPE_TIMEOUT], from_promise.get_parameter("timeout")
            )

            assert_same_host = typing.cast(
                bool, from_promise.get_parameter("assert_same_host")
            )
            pool_timeout = from_promise.get_parameter("pool_timeout")
            response_kw = typing.cast(
                typing.MutableMapping[str, typing.Any],
                from_promise.get_parameter("response_kw"),
            )
            chunked = typing.cast(bool, from_promise.get_parameter("chunked"))
            body_pos = typing.cast(
                _TYPE_BODY_POSITION, from_promise.get_parameter("body_pos")
            )

            try:
                retries = retries.increment(method, url, response=response, _pool=self)
            except MaxRetryError:
                if retries.raise_on_status:
                    await response.drain_conn()
                    raise
                return response

            if retries.cache_response_body and response._body is None:
                await response.read(cache_content=True)
            await response.drain_conn()
            await retries.async_sleep(response)
            log.debug("Retry: %s", url)
            new_promise = await self.urlopen(
                method,
                url,
                body,
                headers,
                retries=retries,
                redirect=redirect,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=False,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=True,
                extension=from_promise.get_parameter("extension"),
                **response_kw,
            )

            return await self.get_response(promise=new_promise if promise else None)

        extension = from_promise.get_parameter("extension")

        if extension is not None:
            if response.status == 101 or (
                200 <= response.status < 300
                and (method == "CONNECT" or extension is not None)
            ):
                await response.start_extension(extension)

        return response

    @typing.overload
    async def _make_request(
        self,
        conn: AsyncHTTPConnection,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = ...,
        headers: typing.Mapping[str, str] | None = ...,
        retries: Retry | None = ...,
        timeout: _TYPE_TIMEOUT = ...,
        chunked: bool = ...,
        response_conn: AsyncHTTPConnection | None = ...,
        preload_content: bool = ...,
        decode_content: bool = ...,
        enforce_content_length: bool = ...,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = ...,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ] = ...,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = ...,
        extension: AsyncExtensionFromHTTP | None = ...,
        *,
        multiplexed: Literal[True],
    ) -> ResponsePromise: ...

    @typing.overload
    async def _make_request(
        self,
        conn: AsyncHTTPConnection,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = ...,
        headers: typing.Mapping[str, str] | None = ...,
        retries: Retry | None = ...,
        timeout: _TYPE_TIMEOUT = ...,
        chunked: bool = ...,
        response_conn: AsyncHTTPConnection | None = ...,
        preload_content: bool = ...,
        decode_content: bool = ...,
        enforce_content_length: bool = ...,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = ...,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ] = ...,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = ...,
        extension: AsyncExtensionFromHTTP | None = ...,
        *,
        multiplexed: Literal[False] = ...,
    ) -> AsyncHTTPResponse: ...

    async def _make_request(
        self,
        conn: AsyncHTTPConnection,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = None,
        headers: typing.Mapping[str, str] | None = None,
        retries: Retry | None = None,
        timeout: _TYPE_TIMEOUT = _DEFAULT_TIMEOUT,
        chunked: bool = False,
        response_conn: AsyncHTTPConnection | None = None,
        preload_content: bool = True,
        decode_content: bool = True,
        enforce_content_length: bool = True,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = None,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ]
        | None = None,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = None,
        extension: AsyncExtensionFromHTTP | None = None,
        multiplexed: Literal[False] | Literal[True] = False,
    ) -> AsyncHTTPResponse | ResponsePromise:
        """
        Perform a request on a given urllib connection object taken from our
        pool.

        :param conn:
            a connection from one of our connection pools

        :param method:
            HTTP request method (such as GET, POST, PUT, etc.)

        :param url:
            The URL to perform the request on.

        :param body:
            Data to send in the request body, either :class:`str`, :class:`bytes`,
            an iterable of :class:`str`/:class:`bytes`, or a file-like object.

        :param headers:
            Dictionary of custom headers to send, such as User-Agent,
            If-None-Match, etc. If None, pool headers are used. If provided,
            these headers completely replace any pool-specific headers.

        :param retries:
            Configure the number of retries to allow before raising a
            :class:`~urllib3.exceptions.MaxRetryError` exception.

            Pass ``None`` to use the pool's default retry configuration. Pass
            a :class:`~urllib3.util.retry.Retry` object for fine-grained control
            over different types of retries. An integer sets the total retry
            budget; allowed methods and other retry rules still apply.
            Pass zero to disable further attempts.

            If ``False``, then retries are disabled and any exception is raised
            immediately. Also, instead of raising a MaxRetryError on redirects,
            the redirect response will be returned.

        :type retries: :class:`~urllib3.util.retry.Retry`, False, or an int.

        :param timeout:
            If specified, overrides the default timeout for this one
            request. It may be a float (in seconds) or an instance of
            :class:`urllib3.util.Timeout`.

        :param chunked:
            If True, urllib3 will send the body using chunked transfer
            encoding. Otherwise, urllib3 will send the body using the standard
            content-length form. Defaults to False.

        :param response_conn:
            Set this to ``None`` if you will handle releasing the connection or
            set the connection to have the response release it.

        :param preload_content:
          If True, the response's body will be preloaded during construction.

        :param decode_content:
            If True, will attempt to decode the body based on the
            'content-encoding' header.

        :param enforce_content_length:
            Enforce content length checking. Body returned by server must match
            value of Content-Length header, if present. Otherwise, raise error.
        """
        self.num_requests += 1

        timeout_obj = self._get_timeout(timeout)
        timeout_obj.start_connect()
        conn.timeout = Timeout.resolve_default_timeout(timeout_obj.connect_timeout)

        try:
            # Trigger any extra validation we need to do.
            try:
                await self._validate_conn(conn)
            except (SocketTimeout, BaseSSLError) as e:
                self._raise_timeout(err=e, url=url, timeout_value=conn.timeout)
                raise

        # _validate_conn() starts the connection to an HTTPS proxy
        # so we need to wrap errors with 'ProxyError' here too.
        except (
            OSError,
            NewConnectionError,
            _TimeoutError,
            BaseSSLError,
            CertificateError,
            SSLError,
        ) as e:
            new_e: Exception = e
            if isinstance(e, (BaseSSLError, CertificateError)):
                new_e = SSLError(e)
            # If the connection didn't successfully connect to it's proxy
            # then there
            if isinstance(
                new_e, (OSError, NewConnectionError, _TimeoutError, SSLError)
            ) and (conn and conn.proxy and not conn.has_connected_to_proxy):
                new_e = _wrap_proxy_error(new_e, conn.proxy.scheme)
            raise new_e

        conn_info = getattr(conn, "conn_info", None)
        if on_post_connection is not None and conn_info is not None:
            # A second request does not redo handshake or DNS resolution.
            if getattr(conn, "_start_last_request", None) is not None:
                if conn_info.tls_handshake_latency:
                    conn_info.tls_handshake_latency = timedelta()
                if conn_info.established_latency:
                    conn_info.established_latency = timedelta()
                if conn_info.resolution_latency:
                    conn_info.resolution_latency = timedelta()
                if conn_info.request_sent_latency:
                    conn_info.request_sent_latency = None
            await on_post_connection(conn_info)

        if not conn.is_multiplexed and multiplexed:
            # overruling
            multiplexed = False

        if (
            extension is not None
            and conn_info is not None
            and conn_info.http_version is not None
        ):
            extension_headers = HTTPHeaderDict(
                extension.headers(conn_info.http_version)
            )

            if extension_headers:
                # allow overriding "Accept"
                # see https://github.com/jawah/urllib3.future/pull/333
                if (
                    headers is not None
                    and "Accept" in headers
                    and "Accept" in extension_headers
                ):
                    extension_headers["Accept"] = headers["Accept"]
                if headers is None:
                    headers = extension_headers  # Defensive: urlopen supplies headers; tolerate direct private-method calls.
                elif hasattr(headers, "copy"):
                    headers = headers.copy()
                    headers.update(extension_headers)  # type: ignore[union-attr]
                else:
                    merged_headers = HTTPHeaderDict()

                    for k, v in headers.items():
                        merged_headers.add(k, v)
                    for k, v in extension_headers.items():
                        merged_headers.add(k, v)

                    headers = merged_headers
        else:
            extension = None

        # utls -- BoringSSL have predefined headers
        # that we automatically insert.
        if conn_info is not None and conn_info.tls_version is not None:
            ssl_ctx: ssl.SSLContext | None = getattr(
                conn, "_custom_tls_context", None
            ) or getattr(conn.sock, "context", None)

            if ssl_ctx is not None and hasattr(ssl_ctx, "http_header_for_fingerprint"):
                try:
                    prefixed_headers = HTTPHeaderDict(
                        ssl_ctx.http_header_for_fingerprint()
                    )

                    if headers is not None:
                        # user specified headers always win.
                        if isinstance(headers, HTTPHeaderDict):
                            # Preserve duplicate values and the preset header order.
                            prefixed_headers._copy_from(headers)
                        else:
                            for k, v in headers.items():
                                prefixed_headers[k] = v

                    headers = prefixed_headers
                except ValueError:  # We can forbid it entirely
                    pass

        try:
            rp = await conn.request(
                method,
                url,
                body=body,
                headers=headers,
                chunked=chunked,
                preload_content=preload_content,
                decode_content=decode_content,
                enforce_content_length=enforce_content_length,
                on_upload_body=on_upload_body,
            )
        # We are swallowing BrokenPipeError (errno.EPIPE) since the server is
        # legitimately able to close the connection after sending a valid response.
        # With this behaviour, the received response is still readable.
        except BrokenPipeError as e:
            rp = e.promise  # type: ignore
        except OSError as e:
            rp = None
            # MacOS/Linux
            # EPROTOTYPE is needed on macOS
            # https://erickt.github.io/blog/2014/11/19/adventures-in-debugging-a-potential-osx-kernel-bug/
            if e.errno != errno.EPROTOTYPE:
                raise

        # Reset the timeout for the recv() on the socket
        read_timeout = timeout_obj.read_timeout

        if multiplexed:
            if rp is None:
                raise OSError  # Defensive: custom requests or legacy EPROTOTYPE handling may leave no promise.
            rp.set_parameter("read_timeout", read_timeout)
            rp.set_parameter("on_early_response", on_early_response)
            rp.set_parameter("extension", extension)
            return rp

        if not conn.is_closed:
            # In Python 3 socket.py will catch EAGAIN and return None when you
            # try and read into the file pointer created by http.client, which
            # instead raises a BadStatusLine exception. Instead of catching
            # the exception and assuming all BadStatusLine exceptions are read
            # timeouts, check for a zero timeout before making the request.
            if read_timeout == 0:
                raise ReadTimeoutError(
                    self, url, f"Read timed out. (read timeout={read_timeout})"
                )
            conn.timeout = read_timeout

        police = self.pool
        if police is None:
            raise ClosedPoolError(self, "Pool is closed")

        can_shelve_conn = conn.is_multiplexed is True and rp is not None

        if can_shelve_conn:
            assert rp is not None
            police.memorize(rp, conn)
            await self._put_conn(conn)

            # Receive the response from the server
            async with police.borrow(rp) as conn:
                try:
                    response = await conn.getresponse(
                        police_officer=police,
                        early_response_callback=on_early_response,
                        promise=rp,
                    )
                except (BaseSSLError, OSError) as e:
                    self._raise_timeout(err=e, url=url, timeout_value=read_timeout)
                    raise
                finally:
                    police.forget(rp)
        else:
            try:
                response = await conn.getresponse(
                    police_officer=police,
                    early_response_callback=on_early_response,
                    promise=rp,
                )
            except (BaseSSLError, OSError) as e:
                self._raise_timeout(err=e, url=url, timeout_value=read_timeout)
                raise

        http_vsn_str = (
            conn._http_vsn_str
        )  # keep vsn here, as conn may be upgraded afterward.

        # Set properties that are used by the pooling layer.
        response.retries = retries
        response._pool = self

        if response.status == 101 or (
            200 <= response.status < 300
            and (method == "CONNECT" or extension is not None)
        ):
            if extension is None:
                from ..contrib.webextensions._async import load_extension

                extension = load_extension(None)()
            await response.start_extension(extension)

        log.debug(
            '%s://%s:%s "%s %s %s" %s %s',
            self.scheme,
            self.host,
            self.port,
            method,
            url,
            # HTTP version
            http_vsn_str,
            response.status,
            response.length_remaining,
        )

        return response

    async def close(self) -> None:
        """
        Close the pool while allowing returned responses to finish reading.

        New requests are rejected; returned promises remain retrievable.
        """
        if self.pool is None:
            return

        # Retain routing for blind collection until all returned promises are collected.
        old_pool = self.pool
        self._draining_pool = old_pool
        self.pool = None

        if self._background_monitoring is not None:
            self._background_monitoring.cancel()
            try:
                await self._background_monitoring
            except asyncio.CancelledError:
                pass
            finally:
                self._background_monitoring = None

        # The watcher has returned its checkout; only user responses remain to drain.
        await old_pool.clear()
        if not old_pool._has_pending_promises:
            self._draining_pool = None

        # Close allocated resolver if we own it. (aka. not shared)
        if self._own_resolver and self._resolver.is_available():
            await self._resolver.close()

    def is_same_host(self, url: str) -> bool:
        """
        Check if the given ``url`` is a member of the same host as this
        connection pool.
        """
        return _is_same_host(url, self.scheme, self.host, self.port)

    @typing.overload  # type: ignore[override]
    async def urlopen(
        self,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = ...,
        headers: typing.Mapping[str, str] | None = ...,
        retries: Retry | bool | int | None = ...,
        redirect: bool = ...,
        assert_same_host: bool = ...,
        timeout: _TYPE_TIMEOUT = ...,
        pool_timeout: int | None = ...,
        release_conn: bool | None = ...,
        chunked: bool = ...,
        body_pos: _TYPE_BODY_POSITION | None = ...,
        preload_content: bool = ...,
        decode_content: bool = ...,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = ...,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ] = ...,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = ...,
        extension: AsyncExtensionFromHTTP | None = ...,
        *,
        multiplexed: Literal[False] = ...,
        **response_kw: typing.Any,
    ) -> AsyncHTTPResponse: ...

    @typing.overload
    async def urlopen(
        self,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = ...,
        headers: typing.Mapping[str, str] | None = ...,
        retries: Retry | bool | int | None = ...,
        redirect: bool = ...,
        assert_same_host: bool = ...,
        timeout: _TYPE_TIMEOUT = ...,
        pool_timeout: int | None = ...,
        release_conn: bool | None = ...,
        chunked: bool = ...,
        body_pos: _TYPE_BODY_POSITION | None = ...,
        preload_content: bool = ...,
        decode_content: bool = ...,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = ...,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ] = ...,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = ...,
        extension: AsyncExtensionFromHTTP | None = ...,
        *,
        multiplexed: Literal[True],
        **response_kw: typing.Any,
    ) -> ResponsePromise: ...

    async def urlopen(
        self,
        method: str,
        url: str,
        body: _TYPE_BODY | _TYPE_ASYNC_BODY | None = None,
        headers: typing.Mapping[str, str] | None = None,
        retries: Retry | bool | int | None = None,
        redirect: bool = True,
        assert_same_host: bool = True,
        timeout: _TYPE_TIMEOUT = _DEFAULT_TIMEOUT,
        pool_timeout: int | None = None,
        release_conn: bool | None = None,
        chunked: bool = False,
        body_pos: _TYPE_BODY_POSITION | None = None,
        preload_content: bool = True,
        decode_content: bool = True,
        on_post_connection: typing.Callable[[ConnectionInfo], typing.Awaitable[None]]
        | None = None,
        on_upload_body: typing.Callable[
            [int, int | None, bool, bool], typing.Awaitable[None]
        ]
        | None = None,
        on_early_response: typing.Callable[[AsyncHTTPResponse], typing.Awaitable[None]]
        | None = None,
        extension: AsyncExtensionFromHTTP | None = None,
        multiplexed: bool = False,
        **response_kw: typing.Any,
    ) -> AsyncHTTPResponse | ResponsePromise:
        """
        Get a connection from the pool and perform an HTTP request. This is the
        lowest level call for making a request, so you'll need to specify all
        the raw details.

        .. note::

           More commonly, it's appropriate to use a convenience method
           such as :meth:`request`.

        .. note::

           For streaming, use ``preload_content=False`` and consume or close
           the returned response. Returning connection ownership alone does
           not discard an unread body.

        :param method:
            HTTP request method (such as GET, POST, PUT, etc.)

        :param url:
            The URL to perform the request on.

        :param body:
            Data to send in the request body, either :class:`str`, :class:`bytes`,
            an iterable of :class:`str`/:class:`bytes`, or a file-like object.

        :param headers:
            Dictionary of custom headers to send, such as User-Agent,
            If-None-Match, etc. If None, pool headers are used. If provided,
            these headers completely replace any pool-specific headers.

        :param retries:
            Configure the number of retries to allow before raising a
            :class:`~urllib3.exceptions.MaxRetryError` exception.

            Pass ``None`` to use the pool's default retry configuration. Pass
            a :class:`~urllib3.util.retry.Retry` object for fine-grained control
            over different types of retries. An integer sets the total retry
            budget; allowed methods and other retry rules still apply.
            Pass zero to disable further attempts.

            If ``False``, then retries are disabled and any exception is raised
            immediately. Also, instead of raising a MaxRetryError on redirects,
            the redirect response will be returned.

        :type retries: :class:`~urllib3.util.retry.Retry`, False, or an int.

        :param redirect:
            If True, automatically handle redirects (status codes 301, 302,
            303, 307, 308). Each redirect counts as a retry. Disabling retries
            will disable redirect, too.

        :param assert_same_host:
            If ``True``, will make sure that the host of the pool requests is
            consistent else will raise HostChangedError. When ``False``, you can
            use the pool on an HTTP proxy and request foreign hosts.

        :param timeout:
            If specified, overrides the default timeout for this one
            request. It may be a float (in seconds) or an instance of
            :class:`urllib3.util.Timeout`.

        :param pool_timeout:
            Maximum seconds to wait for connection acquisition. The default,
            None, has no acquisition deadline. This is separate from connect
            and read timeouts and can apply with either value of block.
            Raises EmptyPoolError if no connection becomes available in time.

        :param bool preload_content:
            If True, the response's body will be preloaded into memory.

        :param bool decode_content:
            If True, will attempt to decode the body based on the
            'content-encoding' header.

        :param release_conn:
            Whether to return acquired connection ownership after receiving
            response headers. If None, defaults to preload_content. Reading the
            whole body normally releases ownership automatically. Consume,
            drain, or close an unused response; release_conn() alone does not
            consume or abort its unread body.

        :param bool chunked:
            If True, urllib3 will send the body using chunked transfer
            encoding. Otherwise, urllib3 will send the body using the standard
            content-length form. Defaults to False.

        :param int body_pos:
            Position to seek to in file-like body in the event of a retry or
            redirect. Typically this won't need to be set because urllib3 will
            auto-populate the value when needed.

        :param on_post_connection:
            Callable to be invoked that will inform you of the connection specifications
            for the request to be sent. See ``urllib3.ConnectionInfo`` class for more.

        :param on_upload_body:
            Callable that will be invoked upon body upload in order to be able to track
            the progress. The values are expressed in bytes. It is possible that the total isn't
            available, thus set to None. In order, arguments are:
            (total_sent, total_to_be_sent, completed, any_error)

        :param on_early_response:
            Callable that will be invoked upon early responses, can be invoked one or several times.
            All informational responses except HTTP/101 (Switching Protocol) are concerned here.
            The callback takes only one positional argument, the fully constructed HTTPResponse.
            Those responses never have bodies, only headers.

        :param multiplexed:
            Defer response retrieval on HTTP/2 or HTTP/3 and return a
            ResponsePromise for get_response(). Sending the request still
            awaits network I/O. HTTP/1.1 returns an immediate response.
        """
        if self.pool is None:
            raise ClosedPoolError(self, "Pool is closed")

        # Retrying must not decode IPv6 zone identifiers a second time.
        original_url = url
        parsed_url = parse_url(url)
        destination_scheme = parsed_url.scheme

        if headers is None:
            headers = self.headers

        if not isinstance(retries, Retry):
            retries = Retry.from_int(retries, redirect=redirect, default=self.retries)

        if release_conn is None:
            # we want to release the connection by default
            # each and every time. TrafficPolice brings safety.
            release_conn = True

        # Check host
        if assert_same_host and not self.is_same_host(url):
            raise HostChangedError(self, url, retries)

        # Ensure that the URL we're connecting to is properly encoded
        if url.startswith("/"):
            url = to_str(_encode_target(url))
        else:
            url = to_str(parsed_url._replace(fragment=None).url)

        conn = None

        # Track whether `conn` needs to be released before
        # returning/raising/recursing. Update this variable if necessary, and
        # leave `release_conn` constant throughout the function. That way, if
        # the function recurses, the original value of `release_conn` will be
        # passed down into the recursive call, and its value will be respected.
        #
        # See issue #651 [1] for details.
        #
        # [1] <https://github.com/urllib3/urllib3/issues/651>
        release_this_conn = release_conn

        http_tunnel_required = connection_requires_http_tunnel(
            self.proxy, self.proxy_config, destination_scheme
        )

        # Merge the proxy headers. Only done when not using HTTP CONNECT. We
        # have to copy the headers dict so we can safely change it without those
        # changes being reflected in anyone else's copy.
        if not http_tunnel_required:
            # Mapping implementations need not provide dict.copy().
            headers = headers.copy() if hasattr(headers, "copy") else dict(headers)
            headers.update(self.proxy_headers)

        # Must keep the exception bound to a separate variable or else Python 3
        # complains about UnboundLocalError.
        err = None

        # Keep track of whether we cleanly exited the except block. This
        # ensures we do proper cleanup in finally.
        clean_exit = False

        # Rewind body position, if needed. Record current position
        # for future rewinds in the event of a redirect/retry.
        if not is_async_file(body):
            body_pos = set_file_position(body, body_pos)
        else:
            body_pos = await aset_file_position(body, body_pos)

        try:
            # Request a connection from the queue.
            timeout_obj = self._get_timeout(timeout)
            conn = await self._get_conn(timeout=pool_timeout, heb_timeout=timeout_obj)

            conn.timeout = timeout_obj.connect_timeout  # type: ignore[assignment]

            # Is this a closed/new connection that requires CONNECT tunnelling?
            if self.proxy is not None and http_tunnel_required and conn.is_closed:
                try:
                    await self._prepare_proxy(conn)
                except (BaseSSLError, OSError, SocketTimeout) as e:
                    self._raise_timeout(
                        err=e, url=self.proxy.url, timeout_value=conn.timeout
                    )
                    raise

            # If we're going to release the connection in ``finally:``, then
            # the response doesn't need to know about the connection. Otherwise
            # it will also try to release it and we'll have a double-release
            # mess.
            response_conn = conn if not release_conn else None

            # Make the request on the HTTPConnection object
            response = await self._make_request(  # type: ignore[call-overload,misc]
                conn,
                method,
                url,
                body=body,
                headers=headers,
                retries=retries,
                timeout=timeout_obj,
                chunked=chunked,
                response_conn=response_conn,
                preload_content=preload_content,
                decode_content=decode_content,
                enforce_content_length=True,
                on_post_connection=on_post_connection,
                on_upload_body=on_upload_body,
                on_early_response=on_early_response,
                extension=extension,
                multiplexed=multiplexed,
            )

            # it was established a non-multiplexed connection. fallback to original behavior.
            if not isinstance(response, ResponsePromise):
                multiplexed = False

            if multiplexed:
                response.update_parameters(
                    {
                        "method": method,
                        "url": original_url,
                        "body": body,
                        "headers": headers,
                        "retries": retries,
                        "preload_content": preload_content,
                        "decode_content": decode_content,
                        "timeout": timeout,
                        "redirect": redirect,
                        "response_kw": response_kw,
                        "pool_timeout": pool_timeout,
                        "assert_same_host": assert_same_host,
                        "chunked": chunked,
                        "body_pos": body_pos,
                    }
                )

            # Everything went great!
            clean_exit = True

        except EmptyPoolError:
            # Didn't get a connection from the pool, no need to clean up
            clean_exit = True
            release_this_conn = False
            raise

        except (
            _TimeoutError,
            OSError,
            ProtocolError,
            BaseSSLError,
            SSLError,
            CertificateError,
            ProxyError,
            RecoverableError,
            UnavailableTraffic,
        ) as e:
            if isinstance(e, UnavailableTraffic) and self.pool is None:
                raise ClosedPoolError(self, "Pool is closed") from e
            # Discard the connection for these exceptions. It will be
            # replaced during the next _get_conn() call.
            clean_exit = False
            new_e: Exception = e
            if isinstance(e, (BaseSSLError, CertificateError)):
                new_e = SSLError(e)
            if isinstance(
                new_e,
                (
                    OSError,
                    NewConnectionError,
                    _TimeoutError,
                    SSLError,
                ),
            ) and (conn and conn.proxy and not conn.has_connected_to_proxy):
                new_e = _wrap_proxy_error(new_e, conn.proxy.scheme)
            elif isinstance(new_e, OSError):
                new_e = ProtocolError("Connection aborted.", new_e)

            retries = retries.increment(
                method, url, error=new_e, _pool=self, _stacktrace=sys.exc_info()[2]
            )
            await retries.async_sleep()

            # todo: allow the conn to be reusable.
            #       the MustDowngradeError only means that a single request cannot be
            #       served over the current svn. does not means all requests to endpoint
            #       are concerned.
            if isinstance(new_e, MustDowngradeError) and conn is not None:
                self.conn_kw.setdefault("disabled_svn", set()).add(conn._svn)

            # Keep track of the error for the retry warning.
            err = e

        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Closing before a response is formed invalidates the backend state.
            if self.pool is None:
                raise ClosedPoolError(self, "Pool is closed") from e
            raise

        finally:
            if not clean_exit:
                # We hit some kind of exception, handled or otherwise. We need
                # to throw the connection away unless explicitly told not to.
                # Close the connection, set the variable to None, and make sure
                # we put the None back in the pool to avoid leaking it.
                if conn:
                    police = self.pool
                    if police is None:
                        await conn.close()
                    else:
                        # Response retrieval may already have returned the checkout.
                        await police.kill(conn)
                    conn = None
                release_this_conn = True

            if (
                self.pool is None
                and clean_exit
                and conn is not None
                and isinstance(response, ResponsePromise)
            ):
                await conn.close()
                raise ClosedPoolError(self, "Pool is closed")

            if self.pool is not None:
                if (
                    clean_exit
                    and conn is not None
                    and isinstance(response, ResponsePromise)
                ):
                    response.set_parameter("police_officer", self.pool)
                    self.pool.memorize(response, conn)
                    # we can always use ConnectionPool without PoolManager!
                    if self.pool.parent is not None:
                        self.pool.parent.memorize(response, self)

                if release_this_conn:
                    if conn is not None:
                        # Put the connection back to be reused. If the connection is
                        # expired then it will be None, which will get replaced with a
                        # fresh connection during _get_conn.
                        if self.pool.is_held(conn):
                            await self._put_conn(conn)
                    else:
                        await self.pool.kill_cursor()

        if not conn:
            # Try again
            log.warning(
                "Retrying (%r) after connection broken by '%r': %s",
                retries,
                err,
                url,
                extra={"__urllib3-retry-warning": {"host": self.host}},
            )
            return await self.urlopen(  # type: ignore[no-any-return,call-overload,misc]
                method,
                original_url,
                body,
                headers,
                retries,
                redirect,
                assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=release_conn,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                on_early_response=on_early_response,
                on_upload_body=on_upload_body,
                on_post_connection=on_post_connection,
                multiplexed=multiplexed,
                extension=extension,
                **response_kw,
            )

        if multiplexed:
            assert isinstance(response, ResponsePromise)
            return response  # actually a response promise!

        assert isinstance(response, AsyncHTTPResponse)

        if redirect and response.get_redirect_location():
            # Handle redirect?
            redirect_location = response.get_redirect_location()

            if response.status == 303:
                method = "GET"
                body = None
                chunked = False
                body_pos = None
                headers = HTTPHeaderDict(headers)

                for should_be_removed_header in NOT_FORWARDABLE_HEADERS:
                    headers.discard(should_be_removed_header)

            # Strip headers marked as unsafe to forward to the redirected location.
            # Check remove_headers_on_redirect to avoid a potential network call within
            # self.is_same_host() which may use socket.gethostbyname() in the future.
            if retries.remove_headers_on_redirect and not self.is_same_host(
                redirect_location  # type: ignore[arg-type]
            ):
                headers = HTTPHeaderDict(headers)
                for header in list(headers):
                    if header.lower() in retries.remove_headers_on_redirect:
                        headers.discard(header)

            try:
                retries = retries.increment(method, url, response=response, _pool=self)
            except MaxRetryError:
                if retries.raise_on_redirect:
                    await response.drain_conn()
                    raise
                if not release_conn and self.pool is not None:
                    self.pool.memorize(response, conn, reserve=True)
                return response

            if retries.cache_response_body and response._body is None:
                await response.read(cache_content=True)
            await response.drain_conn()
            await retries.async_sleep_for_retry(response)

            log.debug("Redirecting %s -> %s", url, redirect_location)

            return await self.urlopen(  # type: ignore[call-overload,no-any-return,misc]
                method,
                redirect_location,
                body=body,
                headers=headers,
                retries=retries,
                redirect=redirect,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=release_conn,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=False,
                extension=extension,
                **response_kw,
            )

        # Check if we should retry the HTTP response.
        has_retry_after = bool(response.headers.get("Retry-After"))
        if retries.is_retry(method, response.status, has_retry_after):
            try:
                retries = retries.increment(method, url, response=response, _pool=self)
            except MaxRetryError:
                if retries.raise_on_status:
                    await response.drain_conn()
                    raise
                if not release_conn and self.pool is not None:
                    self.pool.memorize(response, conn, reserve=True)
                return response

            if retries.cache_response_body and response._body is None:
                await response.read(cache_content=True)
            await response.drain_conn()
            await retries.async_sleep(response)
            log.debug("Retry: %s", url)
            return await self.urlopen(
                method,
                original_url,
                body,
                headers,
                retries=retries,
                redirect=redirect,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=release_conn,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=False,
                extension=extension,
                **response_kw,
            )

        if not release_conn and self.pool is not None:
            self.pool.memorize(response, conn, reserve=True)
        return response

    def __repr__(self) -> str:
        return f"<AsyncHTTPConnection {self.host}:{self.port or 80} {self.pool or '(Closed)'}>"


class AsyncHTTPSConnectionPool(AsyncHTTPConnectionPool):
    """
    Same as :class:`.HTTPConnectionPool`, but HTTPS.

    :class:`.HTTPSConnection` uses one of ``assert_fingerprint``,
    ``assert_hostname`` and ``host`` in this order to verify connections.
    If ``assert_hostname`` is False, no verification is done.

    The ``key_file``, ``cert_file``, ``cert_reqs``, ``ca_certs``,
    ``ca_cert_dir``, ``ssl_version``, ``key_password`` are only used if :mod:`ssl`
    is available and are fed into :meth:`urllib3.util.ssl_wrap_socket` to upgrade
    the connection socket into an SSL socket.
    """

    scheme = "https"
    ConnectionCls: type[AsyncHTTPSConnection] = AsyncHTTPSConnection

    def __init__(
        self,
        host: str,
        port: int | None = None,
        timeout: _TYPE_TIMEOUT | None = _DEFAULT_TIMEOUT,
        maxsize: int = 1,
        block: bool = True,
        headers: typing.Mapping[str, str] | None = None,
        retries: Retry | bool | int | None = None,
        _proxy: Url | None = None,
        _proxy_headers: typing.Mapping[str, str] | None = None,
        key_file: str | None = None,
        cert_file: str | None = None,
        cert_reqs: int | str | None = None,
        key_password: str | None = None,
        ca_certs: str | None = None,
        ssl_version: int | str | None = None,
        ssl_minimum_version: ssl.TLSVersion | None = None,
        ssl_maximum_version: ssl.TLSVersion | None = None,
        ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
        assert_hostname: str | Literal[False] | None = None,
        assert_fingerprint: str | None = None,
        ca_cert_dir: str | None = None,
        ca_cert_data: None | str | bytes = None,
        cert_data: str | bytes | None = None,
        key_data: str | bytes | None = None,
        ciphers: str | None = None,
        **conn_kw: typing.Any,
    ) -> None:
        super().__init__(
            host,
            port,
            timeout,
            maxsize,
            block,
            headers,
            retries,
            _proxy,
            _proxy_headers,
            **conn_kw,
        )

        self.key_file = key_file
        self.cert_file = cert_file
        self.cert_reqs = cert_reqs
        self.key_password = key_password
        self.ca_certs = ca_certs
        self.ca_cert_dir = ca_cert_dir
        self.ca_cert_data = ca_cert_data
        self.cert_data = cert_data
        self.key_data = key_data
        self.ssl_version = ssl_version
        self.ssl_minimum_version = ssl_minimum_version
        self.ssl_maximum_version = ssl_maximum_version
        self.ssl_backend = ssl_backend
        self.assert_hostname = assert_hostname
        self.assert_fingerprint = assert_fingerprint
        self.ciphers = ciphers

    async def _prepare_proxy(self, conn: AsyncHTTPSConnection) -> None:  # type: ignore[override]
        """Establishes a tunnel connection through HTTP CONNECT."""
        if self.proxy and self.proxy.scheme == "https":
            tunnel_scheme = "https"
        else:
            tunnel_scheme = "http"

        conn.set_tunnel(
            scheme=tunnel_scheme,
            host=self._tunnel_host,
            port=self.port,
            headers=self.proxy_headers,
        )
        await conn.connect()

    async def _new_conn(
        self, *, heb_timeout: Timeout | None = None
    ) -> AsyncHTTPSConnection:
        """
        Return a fresh :class:`urllib3.connection.HTTPConnection`.
        """
        if self.pool is None:
            raise ClosedPoolError(
                self, "Pool is closed"
            )  # Defensive: callers normally reject closed pools before private connection creation.
        if (
            self._background_monitoring is None
            and self._background_watch_delay is not None
            and self._background_watch_delay >= MINIMAL_BACKGROUND_WATCH_WINDOW
        ):
            self._background_monitoring = asyncio.create_task(
                idle_conn_watch_task(
                    proxy(self),
                    self._background_watch_delay,
                    self._keepalive_delay,
                    self._keepalive_idle_window,
                )
            )
        self.num_connections += 1
        log.debug(
            "Starting new HTTPS connection (%d): %s:%s",
            self.num_connections,
            self.host,
            self.port or "443",
        )

        if not self.ConnectionCls or self.ConnectionCls is DummyConnection:  # type: ignore[comparison-overlap]
            raise ImportError(
                "Can't connect to HTTPS URL because the SSL module is not available."
            )

        actual_host: str = self.host
        actual_port = self.port
        if self.proxy is not None and self.proxy.host is not None:
            actual_host = self.proxy.host
            actual_port = self.proxy.port

        conn = None

        async with self.pool.locate_or_hold(
            block=True, placeholder_set=True
        ) as swapper:
            if self.happy_eyeballs:
                # Taking this path forward will establish a connection (aka. connect) prior to what usually
                # take place. This is the only place where it is the most convenient.
                log.debug(
                    "Attempting Happy-Eyeball %s:%s",
                    self.host,
                    self.port or "443",
                )

                if heb_timeout is None:
                    heb_timeout = self.timeout

                override_timeout = (
                    heb_timeout.connect_timeout
                    if heb_timeout.connect_timeout is not None
                    and isinstance(heb_timeout.connect_timeout, (float, int))
                    else None
                )

                # we have to get this metric here, as the underlying Connection object
                # will have the DNS resolution set to 0s!
                try_quic = HttpVersion.h3 not in self.conn_kw.get("disabled_svn", ())
                dt_pre_resolve = datetime.now(tz=timezone.utc)
                if override_timeout is not None:
                    try:
                        async with timeout(override_timeout):
                            ip_addresses = await self._resolver.getaddrinfo(
                                actual_host,
                                actual_port,
                                socket.AF_UNSPEC
                                if "socket_family" not in self.conn_kw
                                else self.conn_kw["socket_family"],
                                socket.SOCK_STREAM,
                                quic_upgrade_via_dns_rr=try_quic,
                            )
                    except TimeoutError:
                        new_err = socket.gaierror(
                            f"unable to resolve '{actual_host}' within {override_timeout}s"
                        )
                        raise NameResolutionError(actual_host, self, new_err)

                else:
                    ip_addresses = await self._resolver.getaddrinfo(
                        actual_host,
                        actual_port,
                        socket.AF_UNSPEC
                        if "socket_family" not in self.conn_kw
                        else self.conn_kw["socket_family"],
                        socket.SOCK_STREAM,
                        quic_upgrade_via_dns_rr=try_quic,
                    )

                delta_post_resolve = datetime.now(tz=timezone.utc) - dt_pre_resolve

                target_pqc = {}

                # does the user provided us with a quic capability cache? if so, use it!
                if (
                    "preemptive_quic_cache" in self.conn_kw
                    and self.conn_kw["preemptive_quic_cache"] is not None
                ):
                    target_pqc = self.conn_kw["preemptive_quic_cache"]

                # if the resolver hinted us toward using a DGRAM, we inject it into the quic capability cache.
                if any(_[1] == socket.SOCK_DGRAM for _ in ip_addresses):
                    if (self.host, self.port) not in target_pqc:
                        target_pqc[(self.host, self.port)] = (self.host, self.port)

                # HEB algorithm only make sense if the name resolution yield more than 1 record.
                if len(ip_addresses) > 1:
                    ipv6_addresses = []
                    ipv4_addresses = []

                    for ip_address in ip_addresses:
                        if ip_address[0] == socket.AF_INET6:
                            ipv6_addresses.append(ip_address)
                        else:
                            ipv4_addresses.append(ip_address)

                    # if we have BOTH IPv4 and IPv6 entries, we want to reorder the records
                    # so that we can be as fair as possible when spawning the tasks.
                    if ipv4_addresses and ipv6_addresses:
                        log.debug(
                            "Happy-Eyeball Dual-Stack %s:%s",
                            self.host,
                            self.port or "443",
                        )
                        intermediary_addresses = []
                        for ipv6_entry, ipv4_entry in zip_longest(
                            ipv6_addresses, ipv4_addresses
                        ):
                            if ipv6_entry:
                                intermediary_addresses.append(ipv6_entry)
                            if ipv4_entry:
                                intermediary_addresses.append(ipv4_entry)
                        ip_addresses = intermediary_addresses
                    else:
                        log.debug(
                            "Happy-Eyeball Single-Stack %s:%s",
                            self.host,
                            self.port or "443",
                        )

                    challengers = []
                    max_task = (
                        4
                        if isinstance(self.happy_eyeballs, bool)
                        else self.happy_eyeballs
                    )

                    ech_config_hex = ""
                    for ip_addr in ip_addresses:
                        if isinstance(ip_addr[3], bytes) and ip_addr[3]:
                            ech_config_hex = ip_addr[3].hex()
                            break

                    for ip_address in ip_addresses[:max_task]:
                        conn_kw = self.conn_kw.copy()
                        target_solo_addr = (
                            f"[{ip_address[-1][0]}]"
                            if ip_address[0] == socket.AF_INET6
                            else ip_address[-1][0]
                        )
                        inmemory_url = (
                            f"in-memory://default?hosts={self.host}:{target_solo_addr}"
                        )
                        if ech_config_hex:
                            inmemory_url += f"&ech_config={ech_config_hex}"
                        conn_kw["resolver"] = AsyncResolverDescription.from_url(
                            inmemory_url
                        ).new()
                        conn_kw["socket_family"] = ip_address[0]
                        conn_kw["preemptive_quic_cache"] = target_pqc

                        challengers.append(
                            self.ConnectionCls(
                                host=actual_host,
                                port=actual_port,
                                timeout=override_timeout,
                                cert_file=self.cert_file,
                                key_file=self.key_file,
                                key_password=self.key_password,
                                cert_reqs=self.cert_reqs,
                                ca_certs=self.ca_certs,
                                ca_cert_dir=self.ca_cert_dir,
                                ca_cert_data=self.ca_cert_data,
                                assert_hostname=self.assert_hostname,
                                assert_fingerprint=self.assert_fingerprint,
                                ssl_version=self.ssl_version,
                                ssl_minimum_version=self.ssl_minimum_version,
                                ssl_maximum_version=self.ssl_maximum_version,
                                ssl_backend=self.ssl_backend,
                                cert_data=self.cert_data,
                                key_data=self.key_data,
                                ciphers=self.ciphers,
                                **conn_kw,
                            )
                        )

                    tasks = [
                        asyncio.create_task(challenger.connect())
                        for i, challenger in enumerate(challengers)
                    ]

                    winner_task = None
                    pending: set[Task[None]] = set()

                    # here we'll need at least one task that ended successfully OR every task terminated/completed.
                    while True:
                        done, pending = await asyncio.wait(
                            tasks if not pending else pending,
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=override_timeout,
                        )

                        while done:
                            finished_task = done.pop()

                            if finished_task.exception() is None:
                                winner_task = finished_task

                            if finished_task.exception():
                                continue

                        if winner_task or not pending:
                            break

                    # we need to kill the remaining tasks.
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                    if winner_task is None:
                        await asyncio.gather(
                            *(challenger.close() for challenger in challengers),
                            return_exceptions=True,
                        )
                        # Preserve the downgrade when connection acquisition itself failed.
                        for task, challenger in zip(tasks, challengers):
                            if task.done() and not task.cancelled():
                                error = task.exception()
                                if isinstance(error, MustDowngradeError):
                                    self.conn_kw.setdefault("disabled_svn", set()).add(
                                        challenger._svn
                                    )
                                    raise error
                        within_delay_msg: str = (
                            f" within {override_timeout}s" if override_timeout else ""
                        )
                        raise NewConnectionError(
                            challengers[
                                0
                            ],  # that's a bummer, but it wasn't planned for this algorithm.
                            f"Failed to establish a new connection: No suitable address to connect to using Happy Eyeballs algorithm for {actual_host}:{actual_port}{within_delay_msg}",
                        ) from tasks[0].exception()

                    conn = challengers[tasks.index(winner_task)]

                    # we have to replace the resolution latency metric
                    if conn.conn_info:
                        conn.conn_info.resolution_latency = delta_post_resolve

                    await asyncio.gather(
                        *(
                            challenger.close()
                            for challenger in challengers
                            if challenger is not conn
                        ),
                        return_exceptions=True,
                    )
                else:
                    log.debug(
                        "Happy-Eyeball Ineligible %s:%s",
                        self.host,
                        self.port or "443",
                    )

            if conn is None:
                conn = self.ConnectionCls(
                    host=actual_host,
                    port=actual_port,
                    timeout=self.timeout.connect_timeout,
                    cert_file=self.cert_file,
                    key_file=self.key_file,
                    key_password=self.key_password,
                    cert_reqs=self.cert_reqs,
                    ca_certs=self.ca_certs,
                    ca_cert_dir=self.ca_cert_dir,
                    ca_cert_data=self.ca_cert_data,
                    assert_hostname=self.assert_hostname,
                    assert_fingerprint=self.assert_fingerprint,
                    ssl_version=self.ssl_version,
                    ssl_minimum_version=self.ssl_minimum_version,
                    ssl_maximum_version=self.ssl_maximum_version,
                    ssl_backend=self.ssl_backend,
                    cert_data=self.cert_data,
                    key_data=self.key_data,
                    ciphers=self.ciphers,
                    **self.conn_kw,
                )

            await swapper(conn)  # type: ignore[operator]

        return conn

    async def _validate_conn(self, conn: AsyncHTTPConnection) -> None:
        """
        Called right before a request is made, after the socket is created.
        """
        await super()._validate_conn(conn)

        if not conn.is_verified and not conn.proxy_is_verified:
            warnings.warn(
                (
                    f"Unverified HTTPS request is being made to host '{conn.host}'. "
                    "Adding certificate verification is strongly advised. See: "
                    "https://urllib3future.readthedocs.io/en/latest/advanced-usage.html"
                    "#tls-warnings"
                ),
                InsecureRequestWarning,
            )

    def __repr__(self) -> str:
        return f"<AsyncHTTPSConnection {self.host}:{self.port or 443} {self.pool or '(Closed)'}>"


def connection_from_url(url: str, **kw: typing.Any) -> AsyncHTTPConnectionPool:
    """
    Given a url, return an :class:`.ConnectionPool` instance of its host.

    This is a shortcut for not having to parse out the scheme, host, and port
    of the url before creating an :class:`.ConnectionPool` instance.

    :param url:
        Absolute URL string that must include the scheme. Port is optional.

    :param kw:
        Passes additional parameters to the constructor of the appropriate
        :class:`.ConnectionPool`. Useful for specifying things like
        timeout, maxsize, headers, etc.

    Example::

        >>> conn = connection_from_url('http://google.com/')
        >>> r = conn.request('GET', '/')
    """
    scheme, _, host, port, *_ = parse_url(url)
    host = _encode_host(host, scheme)
    scheme = scheme or "http"
    port = port or port_by_scheme.get(scheme, 80)
    if scheme == "https":
        return AsyncHTTPSConnectionPool(host, port=port, **kw)  # type: ignore[arg-type]
    else:
        return AsyncHTTPConnectionPool(host, port=port, **kw)  # type: ignore[arg-type]
