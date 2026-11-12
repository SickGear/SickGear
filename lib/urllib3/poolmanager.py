from __future__ import annotations

import functools
import logging
import socket
import sys
import typing
import warnings
from types import TracebackType
from urllib.parse import urljoin

from ._collections import HTTPHeaderDict
from ._constant import DEFAULT_BLOCKSIZE
from ._request_methods import RequestMethods
from ._typing import (
    _TYPE_BODY,
    _TYPE_BODY_POSITION,
    _TYPE_SOCKET_OPTIONS,
    _TYPE_TIMEOUT,
    ProxyConfig,
)
from .backend import HttpVersion, QuicPreemptiveCacheType, ResponsePromise
from .connectionpool import (
    HTTPConnectionPool,
    HTTPSConnectionPool,
    _is_same_host,
    port_by_scheme,
)
from .contrib.resolver import (
    BaseResolver,
    ManyResolver,
    ProtocolResolver,
    ResolverDescription,
)
from .exceptions import (
    LocationValueError,
    MaxRetryError,
    ProxySchemeUnknown,
    URLSchemeUnknown,
)
from .response import HTTPResponse
from .util.proxy import connection_requires_http_tunnel
from .util.request import NOT_FORWARDABLE_HEADERS
from .util.retry import Retry
from .util.timeout import Timeout
from .util.traffic_police import TrafficPolice, UnavailableTraffic
from .util.url import Url, _encode_host, parse_extension, parse_url

if sys.platform == "wasi":
    # wasi don't support lazy import.
    from .contrib.webextensions import load_extension as load_extension  # noqa: F401

if typing.TYPE_CHECKING:
    import ssl

    from typing_extensions import Literal

__all__ = ["PoolManager", "ProxyManager", "proxy_from_url"]


log = logging.getLogger(__name__)

SSL_KEYWORDS = (
    "key_file",
    "cert_file",
    "cert_reqs",
    "ca_certs",
    "ssl_version",
    "ssl_minimum_version",
    "ssl_maximum_version",
    "ssl_backend",
    "ca_cert_dir",
    "ca_cert_data",
    "ssl_context",
    "key_password",
    "server_hostname",
    "assert_hostname",
    "assert_fingerprint",
    "cert_data",
    "key_data",
    "ciphers",
)

_SelfT = typing.TypeVar("_SelfT")


class PoolKey(typing.NamedTuple):
    """
    All known keyword arguments that could be provided to the pool manager, its
    pools, or the underlying connections.

    All custom key schemes should include the fields in this key at a minimum.
    """

    key_scheme: str
    key_host: str
    key_port: int | None
    key_timeout: Timeout | float | int | None
    key_retries: Retry | bool | int | None
    key_block: bool | None
    key_source_address: tuple[str, int] | None
    key_socket_family: socket.AddressFamily | None
    key_key_file: str | None
    key_key_password: str | None
    key_cert_file: str | None
    key_cert_reqs: str | None
    key_ca_certs: str | None
    key_ssl_version: int | str | None
    key_ssl_minimum_version: ssl.TLSVersion | None
    key_ssl_maximum_version: ssl.TLSVersion | None
    key_ssl_backend: str | None
    key_ca_cert_dir: str | None
    key_ca_cert_data: str | bytes | None
    key_ssl_context: ssl.SSLContext | None
    key_ciphers: str | None
    key_maxsize: int | None
    key_headers: frozenset[tuple[str, str]] | None
    key__proxy: Url | None
    key__proxy_headers: frozenset[tuple[str, str]] | None
    key__proxy_config: ProxyConfig | None
    key_socket_options: _TYPE_SOCKET_OPTIONS | None
    key__socks_options: frozenset[tuple[str, str]] | None
    key_assert_hostname: bool | str | None
    key_assert_fingerprint: str | None
    key_server_hostname: str | None
    key_blocksize: int | None
    key_disabled_svn: set[HttpVersion] | None
    key_cert_data: str | bytes | None
    key_key_data: str | bytes | None
    key_happy_eyeballs: bool | int | None
    key_background_watch_delay: float | int | None
    key_keepalive_delay: float | int | None
    key_keepalive_idle_window: float | int | None


@functools.lru_cache(maxsize=8)
def _empty_context(key_class: type[PoolKey]) -> dict[str, typing.Any]:
    return {k: None for k in key_class._fields}


def _default_key_normalizer(
    key_class: type[PoolKey], request_context: dict[str, typing.Any]
) -> PoolKey:
    """
    Create a pool key out of a request context dictionary.

    According to RFC 3986, both the scheme and host are case-insensitive.
    Therefore, this function normalizes both before constructing the pool
    key for an HTTPS request. If you wish to change this behaviour, provide
    alternate callables to ``key_fn_by_scheme``.

    :param key_class:
        The class to use when constructing the key. This should be a namedtuple
        with the ``scheme`` and ``host`` keys at a minimum.
    :type  key_class: namedtuple
    :param request_context:
        A dictionary-like object that contain the context for a request.
    :type  request_context: dict

    :return: A namedtuple that can be used as a connection pool key.
    :rtype:  PoolKey
    """
    # Since we mutate the dictionary, make a copy first
    context = request_context.copy()
    context["scheme"] = context["scheme"].lower()
    # Only the address portion of a scoped IPv6 host is case-insensitive.
    address, separator, zone = context["host"].partition("%")
    if separator and ":" in address:
        context["host"] = f"{address.lower()}{separator}{zone}"
    else:
        context["host"] = context["host"].lower()

    # These are both dictionaries and need to be transformed into frozensets
    for key in ("headers", "_proxy_headers", "_socks_options"):
        if key in context and context[key] is not None:
            context[key] = frozenset(context[key].items())

    if "disabled_svn" in context:
        context["disabled_svn"] = frozenset(context["disabled_svn"])

    # The socket_options key may be a list and needs to be transformed into a
    # tuple.
    if "socket_options" in context and context["socket_options"] is not None:
        context["socket_options"] = tuple(context["socket_options"])

    # Default key_blocksize to DEFAULT_BLOCKSIZE if missing from the context
    if "blocksize" not in context:
        context["blocksize"] = DEFAULT_BLOCKSIZE

    empty_default_ctx = _empty_context(key_class).copy()  # type: ignore[arg-type]
    # Map the kwargs to the names in the namedtuple - this is necessary since
    # namedtuples can't have fields starting with '_'.
    # Default to ``None`` for keys missing from the context
    empty_default_ctx.update({f"key_{k}": context[k] for k in context})

    return key_class(**empty_default_ctx)


#: A dictionary that maps a scheme to a callable that creates a pool key.
#: This can be used to alter the way pool keys are constructed, if desired.
#: Each PoolManager makes a copy of this dictionary so they can be configured
#: globally here, or individually on the instance.
key_fn_by_scheme = {
    "http": functools.partial(_default_key_normalizer, PoolKey),
    "https": functools.partial(_default_key_normalizer, PoolKey),
}

pool_classes_by_scheme = {"http": HTTPConnectionPool, "https": HTTPSConnectionPool}


class PoolManager(RequestMethods):
    """
    Allows for arbitrary requests while transparently keeping track of
    necessary connection pools for you.

    :param num_pools:
        Number of connection pools to cache before discarding the least
        recently used pool.

    :param headers:
        Headers to include with all requests, unless other headers are given
        explicitly.

    :param \\**connection_pool_kw:
        Additional parameters are used to create fresh
        :class:`urllib3.connectionpool.ConnectionPool` instances.

    Example:

    .. code-block:: python

        import urllib3

        http = urllib3.PoolManager(num_pools=2)

        resp1 = http.request("GET", "https://google.com/")
        resp2 = http.request("GET", "https://google.com/mail")
        resp3 = http.request("GET", "https://yahoo.com/")

        print(len(http.pools))
        # 2

    """

    proxy: Url | None = None
    proxy_config: ProxyConfig | None = None

    def __init__(
        self,
        num_pools: int = 10,
        headers: typing.Mapping[str, str] | None = None,
        preemptive_quic_cache: QuicPreemptiveCacheType | None = None,
        resolver: ResolverDescription
        | list[ResolverDescription]
        | str
        | list[str]
        | BaseResolver
        | None = None,
        **connection_pool_kw: typing.Any,
    ) -> None:
        super().__init__(headers)

        # PoolManager handles redirects itself in PoolManager.urlopen().
        # It always passes redirect=False to the underlying connection pool to
        # suppress per-pool redirect handling. If the user supplied a non-Retry
        # value (int/bool/etc) for retries and we let the pool normalize it
        # while redirect=False, the resulting Retry object would have redirect
        # handling disabled, which can interfere with PoolManager's own
        # redirect logic. Normalize here so redirects remain governed solely by
        # PoolManager logic.
        if "retries" in connection_pool_kw:
            retries = connection_pool_kw["retries"]
            if not isinstance(retries, Retry):
                retries = Retry.from_int(retries)

                connection_pool_kw = connection_pool_kw.copy()
                connection_pool_kw["retries"] = retries

        self.connection_pool_kw = connection_pool_kw

        self._num_pools = num_pools

        self.block = (
            False if "block" not in connection_pool_kw else connection_pool_kw["block"]
        )

        self.pools: TrafficPolice[HTTPConnectionPool] = TrafficPolice(
            num_pools,
            concurrency=True,
            strict_maxsize=not self.block,
        )

        # Locally set the pool classes and keys so other PoolManagers can
        # override them.
        self.pool_classes_by_scheme = pool_classes_by_scheme
        self.key_fn_by_scheme = key_fn_by_scheme.copy()

        self._preemptive_quic_cache = preemptive_quic_cache

        self._own_resolver = not isinstance(resolver, BaseResolver)

        if resolver is None:
            resolver = [ResolverDescription(ProtocolResolver.SYSTEM)]
        elif isinstance(resolver, str):
            resolver = [ResolverDescription.from_url(resolver)]
        elif isinstance(resolver, ResolverDescription):
            resolver = [resolver]

        self._resolvers: list[ResolverDescription] = []

        if not isinstance(resolver, BaseResolver):
            can_resolve_localhost: bool = False

            for resolver_description in resolver:
                if isinstance(resolver_description, str):
                    self._resolvers.append(
                        ResolverDescription.from_url(resolver_description)
                    )

                    if self._resolvers[-1].protocol == ProtocolResolver.SYSTEM:
                        can_resolve_localhost = True

                    continue

                self._resolvers.append(resolver_description)

                if self._resolvers[-1].protocol == ProtocolResolver.SYSTEM:
                    can_resolve_localhost = True

            if not can_resolve_localhost:
                self._resolvers.append(
                    ResolverDescription.from_url("system://default?hosts=localhost")
                )

        #: We want to automatically forward ca_cert_data, ca_cert_dir, and ca_certs.
        for rd in self._resolvers:
            if "ca_cert_data" in connection_pool_kw:
                if "ca_cert_data" not in rd:
                    rd["ca_cert_data"] = connection_pool_kw["ca_cert_data"]
            if "ca_cert_dir" in connection_pool_kw:
                if "ca_cert_dir" not in rd:
                    rd["ca_cert_dir"] = connection_pool_kw["ca_cert_dir"]
            if "ca_certs" in connection_pool_kw:
                if "ca_certs" not in rd:
                    rd["ca_certs"] = connection_pool_kw["ca_certs"]

        self._resolver: BaseResolver = (
            ManyResolver(*[r.new() for r in self._resolvers])
            if not isinstance(resolver, BaseResolver)
            else resolver
        )

    def __enter__(self: _SelfT) -> _SelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self.clear()
        # Return False to re-raise any potential exceptions
        return False

    def _new_pool(
        self,
        scheme: str,
        host: str,
        port: int,
        request_context: dict[str, typing.Any] | None = None,
    ) -> HTTPConnectionPool:
        """
        Create a new :class:`urllib3.connectionpool.ConnectionPool` based on host, port, scheme, and
        any additional pool keyword arguments.

        If ``request_context`` is provided, it is provided as keyword arguments
        to the pool class used. This method is used to actually create the
        connection pools handed out by :meth:`connection_from_url` and
        companion methods. It is intended to be overridden for customization.
        """
        pool_cls: type[HTTPConnectionPool] = self.pool_classes_by_scheme[scheme]
        if request_context is None:
            request_context = self.connection_pool_kw.copy()

        # Default blocksize to DEFAULT_BLOCKSIZE if missing or explicitly
        # set to 'None' in the request_context.
        if request_context.get("blocksize") is None:
            request_context["blocksize"] = DEFAULT_BLOCKSIZE

        # Although the context has everything necessary to create the pool,
        # this function has historically only used the scheme, host, and port
        # in the positional args. When an API change is acceptable these can
        # be removed.
        for key in ("scheme", "host", "port"):
            request_context.pop(key, None)

        if scheme == "http":
            for kw in SSL_KEYWORDS:
                request_context.pop(kw, None)

        request_context["preemptive_quic_cache"] = self._preemptive_quic_cache

        if not self._resolver.is_available():
            self._resolver = self._resolver.recycle()

        request_context["resolver"] = self._resolver

        # By default, each HttpPool can have up to num_pools connections
        if "maxsize" not in request_context:
            request_context["maxsize"] = self._num_pools

        return pool_cls(host, port, **request_context)

    def clear(self) -> None:
        """
        Empty our store of pools and direct them all to close.

        Returned responses remain readable and returned promises remain
        retrievable. Requests that have not returned either may fail. This
        manager remains usable for new requests.
        """
        self.pools.clear()

        if self._own_resolver and self._resolver.is_available():
            self._resolver.close()

    def connection_from_host(
        self,
        host: str | None,
        port: int | None = None,
        scheme: str | None = "http",
        pool_kwargs: dict[str, typing.Any] | None = None,
    ) -> HTTPConnectionPool:
        """
        Get a :class:`urllib3.connectionpool.ConnectionPool` based on the host, port, and scheme.

        If ``port`` isn't given, it will be derived from the ``scheme`` using
        ``urllib3.connectionpool.port_by_scheme``. If ``pool_kwargs`` is
        provided, it is merged with the instance's ``connection_pool_kw``
        variable and used to create the new connection pool, if one is
        needed.
        """

        if not host:
            raise LocationValueError("No host specified.")

        request_context = self._merge_pool_kwargs(pool_kwargs)
        request_context["scheme"] = scheme or "http"
        if not port:
            port = port_by_scheme.get(request_context["scheme"].lower())
        request_context["port"] = port
        request_context["host"] = host

        return self.connection_from_context(request_context)

    def connection_from_context(
        self, request_context: dict[str, typing.Any]
    ) -> HTTPConnectionPool:
        """
        Get a :class:`urllib3.connectionpool.ConnectionPool` based on the request context.

        ``request_context`` must at least contain the ``scheme`` key and its
        value must be a key in ``key_fn_by_scheme`` instance variable.
        """
        if "strict" in request_context:
            request_context.pop("strict")

        scheme = request_context["scheme"].lower()

        pool_key_constructor = self.key_fn_by_scheme.get(scheme)

        if pool_key_constructor is None:
            target_scheme, target_implementation = parse_extension(scheme)
            # we defer the import until there to avoid loading wsproto and such early.
            from .contrib.webextensions import load_extension

            try:
                extension = load_extension(target_scheme, target_implementation)
            except ImportError:
                pass
            else:
                scheme = extension.scheme_to_http_scheme(target_scheme)

                pool_key_constructor = self.key_fn_by_scheme.get(scheme)

                request_context["scheme"] = scheme

                if "port" not in request_context or not request_context["port"]:
                    request_context["port"] = port_by_scheme.get(
                        request_context["scheme"].lower()
                    )

                supported_svn = extension.supported_svn()

                # Keep extension restrictions local to this pool.
                disabled_svn = (
                    set(request_context["disabled_svn"])
                    if "disabled_svn" in request_context
                    else set()
                )

                if len(supported_svn) != 3:
                    if HttpVersion.h11 not in supported_svn:
                        disabled_svn.add(HttpVersion.h11)

                    if HttpVersion.h2 not in supported_svn:
                        disabled_svn.add(HttpVersion.h2)

                    if HttpVersion.h3 not in supported_svn:
                        disabled_svn.add(HttpVersion.h3)

                request_context["disabled_svn"] = disabled_svn

        if not pool_key_constructor:
            raise URLSchemeUnknown(scheme)
        pool_key = pool_key_constructor(request_context)

        if self._preemptive_quic_cache is not None:
            request_context["preemptive_quic_cache"] = self._preemptive_quic_cache

        return self.connection_from_pool_key(pool_key, request_context=request_context)

    def connection_from_pool_key(
        self, pool_key: PoolKey, request_context: dict[str, typing.Any]
    ) -> HTTPConnectionPool:
        """
        Get a :class:`urllib3.connectionpool.ConnectionPool` based on the provided pool key.

        ``pool_key`` should be a namedtuple that only contains immutable
        objects. At a minimum it must have the ``scheme``, ``host``, and
        ``port`` fields.
        """

        # those two lines are there for compatibility purposes
        # urllib3-future has to be a "perfect" drop-in solution for
        # urllib3. here the explanation for them:
        # some programs may just invoke connection_from_xxx directly and
        # handle the underlying pool manually, thus bypassing the
        # internal lifecycle intended. this just make sure we declare
        # not using anything prior to what's next.
        # this constraint appeared after introducing TrafficPolice.
        if self.pools.busy:
            self.pools.release()

        with self.pools.locate_or_hold(pool_key, block=True) as swapper_or_pool:
            # If the scheme, host, or port doesn't match existing open
            # connections, open a new ConnectionPool.
            if not hasattr(swapper_or_pool, "is_idle"):
                # Make a fresh ConnectionPool of the desired type
                scheme = request_context["scheme"]
                host = request_context["host"]
                port = request_context["port"]

                pool = self._new_pool(
                    scheme, host, port, request_context=request_context
                )

                swapper_or_pool(pool)
            else:
                pool = swapper_or_pool  # type: ignore[assignment]

        # make the lower level PoliceTraffic aware
        # of his parent PoliceTraffic
        assert pool.pool is not None
        pool.pool.parent = self.pools

        return pool

    def connection_from_url(
        self, url: str, pool_kwargs: dict[str, typing.Any] | None = None
    ) -> HTTPConnectionPool:
        """
        Similar to :func:`urllib3.connectionpool.connection_from_url`.

        If ``pool_kwargs`` is not provided and a new pool needs to be
        constructed, ``self.connection_pool_kw`` is used to initialize
        the :class:`urllib3.connectionpool.ConnectionPool`. If ``pool_kwargs``
        is provided, it is used instead. Note that if a new pool does not
        need to be created for the request, the provided ``pool_kwargs`` are
        not used.
        """
        u = parse_url(url)
        return self.connection_from_host(
            _encode_host(u.host, u.scheme),
            port=u.port,
            scheme=u.scheme,
            pool_kwargs=pool_kwargs,
        )

    def _merge_pool_kwargs(
        self, override: dict[str, typing.Any] | None
    ) -> dict[str, typing.Any]:
        """
        Merge a dictionary of override values for self.connection_pool_kw.

        This does not modify self.connection_pool_kw and returns a new dict.
        Any keys in the override dictionary with a value of ``None`` are
        removed from the merged dictionary.
        """
        base_pool_kwargs = self.connection_pool_kw.copy()
        if override:
            base_pool_kwargs.update(
                {k: v for k, v in override.items() if v is not None}
            )
            return {
                k: v
                for k, v in base_pool_kwargs.items()
                if k not in override or override[k] is not None
            }
        return base_pool_kwargs

    def _proxy_requires_url_absolute_form(self, parsed_url: Url) -> bool:
        """
        Indicates if the proxy requires the complete destination URL in the
        request.  Normally this is only needed when not using an HTTP CONNECT
        tunnel.
        """
        if self.proxy is None:
            return False

        return not connection_requires_http_tunnel(
            self.proxy, self.proxy_config, parsed_url.scheme
        )

    def get_response(
        self, *, promise: ResponsePromise | None = None
    ) -> HTTPResponse | None:
        """
        Retrieve the first response available in the pools.
        This method should be called after issuing at least one request with ``multiplexed=True``.
        If none available, return None.
        """
        if promise is not None and not isinstance(promise, ResponsePromise):
            raise TypeError(
                f"get_response only support ResponsePromise but received {type(promise)} instead. "
                f"This may occur if you expected the remote peer to support multiplexing but did not."
            )

        try:
            with self.pools.borrow(
                promise or ResponsePromise, block=False, not_idle_only=True
            ) as pool:
                response = pool.get_response(promise=promise)
        except UnavailableTraffic:
            return None

        if (
            promise is not None and response is None
        ):  # Defensive: pool validates promises.
            raise ValueError(
                "Invoked get_response with promise=... that no connections across pools recognize"
            )

        if response is None:
            return None

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

        if from_promise is None:  # Defensive: pool attaches promise metadata.
            raise ValueError(
                "Internal: Unable to identify originating ResponsePromise from a LowLevelResponse"
            )

        self.pools.forget(from_promise)

        # Retrieve request ctx
        method = typing.cast(str, from_promise.get_parameter("method"))
        redirect = typing.cast(bool, from_promise.get_parameter("pm_redirect"))

        # Handle redirect?
        if redirect and response.get_redirect_location():
            url = typing.cast(str, from_promise.get_parameter("pm_url"))
            body = typing.cast(
                typing.Union[_TYPE_BODY, None], from_promise.get_parameter("body")
            )
            headers = typing.cast(
                typing.Union[HTTPHeaderDict, None],
                from_promise.get_parameter("headers"),
            )
            preload_content = typing.cast(
                bool, from_promise.get_parameter("preload_content")
            )
            decode_content = typing.cast(
                bool, from_promise.get_parameter("decode_content")
            )
            timeout = typing.cast(
                typing.Union[_TYPE_TIMEOUT, None], from_promise.get_parameter("timeout")
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

            redirect_location = response.get_redirect_location()
            assert isinstance(redirect_location, str)
            redirect_location = urljoin(url, redirect_location)

            if response.status == 303:
                method = "GET"
                body = None
                chunked = False
                body_pos = None
                headers = HTTPHeaderDict(headers)

                for should_be_removed_header in NOT_FORWARDABLE_HEADERS:
                    headers.discard(should_be_removed_header)

            # Compare request origins, including for deferred proxy responses.
            u = parse_url(url)
            scheme = u.scheme or "http"
            if headers is not None and not _is_same_host(
                redirect_location,
                scheme,
                u.host.strip("[]") if u.host is not None else None,
                u.port,
            ):
                headers_to_remove = retries.remove_headers_on_redirect | {"host"}
                new_headers = headers.copy()
                for header in headers:
                    if header.lower() in headers_to_remove:
                        new_headers.pop(header, None)
                headers = new_headers

            try:
                retries = retries.increment(
                    method, url, response=response, _pool=response._pool
                )
            except MaxRetryError:
                if retries.raise_on_redirect:
                    response.drain_conn()
                    raise
                return response

            if retries.cache_response_body and response._body is None:
                response.read(cache_content=True)
            response.drain_conn()
            retries.sleep_for_retry(response)
            log.debug("Redirecting %s -> %s", url, redirect_location)

            new_promise = self.urlopen(
                method,
                redirect_location,
                True,
                body=body,
                headers=headers,
                retries=retries,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=True,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=True,
                **response_kw,
            )

            return self.get_response(promise=new_promise if promise else None)

        # Check if we should retry the HTTP response.
        has_retry_after = bool(response.headers.get("Retry-After"))
        retries = typing.cast(Retry, from_promise.get_parameter("retries"))

        if retries.is_retry(method, response.status, has_retry_after):
            url = typing.cast(str, from_promise.get_parameter("pm_url"))
            body = typing.cast(
                typing.Union[_TYPE_BODY, None], from_promise.get_parameter("body")
            )
            headers = typing.cast(
                typing.Union[HTTPHeaderDict, None],
                from_promise.get_parameter("headers"),
            )
            preload_content = typing.cast(
                bool, from_promise.get_parameter("preload_content")
            )
            decode_content = typing.cast(
                bool, from_promise.get_parameter("decode_content")
            )
            timeout = typing.cast(
                typing.Union[_TYPE_TIMEOUT, None], from_promise.get_parameter("timeout")
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
                retries = retries.increment(
                    method, url, response=response, _pool=response._pool
                )
            except MaxRetryError:
                if (
                    retries.raise_on_status
                ):  # Defensive: pool handles status exhaustion.
                    response.drain_conn()
                    raise
                return response

            if retries.cache_response_body and response._body is None:
                response.read(cache_content=True)
            response.drain_conn()
            retries.sleep(response)
            log.debug("Retry: %s", url)
            new_promise = self.urlopen(
                method,
                url,
                True,
                body=body,
                headers=headers,
                retries=retries,
                assert_same_host=assert_same_host,
                timeout=timeout,
                pool_timeout=pool_timeout,
                release_conn=False,
                chunked=chunked,
                body_pos=body_pos,
                preload_content=preload_content,
                decode_content=decode_content,
                multiplexed=True,
                **response_kw,
            )

            return self.get_response(promise=new_promise if promise else None)

        extension = from_promise.get_parameter("extension")

        # Pool may have already set&start extension.
        if extension is not None and response.extension is None:
            if response.status == 101 or (
                200 <= response.status < 300 and method == "CONNECT"
            ):  # Defensive: extension startup fallback for custom pools.
                response.start_extension(extension)

        return response

    @typing.overload  # type: ignore[override]
    def urlopen(
        self,
        method: str,
        url: str,
        redirect: bool = True,
        *,
        multiplexed: Literal[False] = ...,
        **kw: typing.Any,
    ) -> HTTPResponse: ...

    @typing.overload
    def urlopen(
        self,
        method: str,
        url: str,
        redirect: bool = True,
        *,
        multiplexed: Literal[True],
        **kw: typing.Any,
    ) -> ResponsePromise: ...

    def urlopen(
        self, method: str, url: str, redirect: bool = True, **kw: typing.Any
    ) -> HTTPResponse | ResponsePromise:
        """
        Same as :meth:`urllib3.HTTPConnectionPool.urlopen`
        with custom cross-host redirect logic and only sends the request-uri
        portion of the ``url``.

        The given ``url`` parameter must be absolute, such that an appropriate
        :class:`urllib3.connectionpool.ConnectionPool` can be chosen for it.
        """
        u = parse_url(url)

        if u.scheme is None:
            warnings.warn(
                "URLs without a scheme (ie 'https://') are deprecated and will raise an error "
                "in a future version of urllib3. To avoid this DeprecationWarning ensure all URLs "
                "start with 'https://' or 'http://'. Read more in this issue: "
                "https://github.com/urllib3/urllib3/issues/2920",
                category=DeprecationWarning,
                stacklevel=2,
            )

        # if we passed manually an extension to urlopen, we want to manually
        # disable svn if they are incompatible with said extension.
        pool_kwargs = None

        extension = kw.get("extension")
        if extension is not None:
            disabled_svn = set()

            pool_kwargs = {}

            supported = extension.supported_svn()
            if len(supported) != 3:
                if HttpVersion.h11 not in supported:
                    disabled_svn.add(HttpVersion.h11)
                if HttpVersion.h2 not in supported:
                    disabled_svn.add(HttpVersion.h2)
                if HttpVersion.h3 not in supported:
                    disabled_svn.add(HttpVersion.h3)

            pool_kwargs["disabled_svn"] = disabled_svn

        conn = self.connection_from_host(
            _encode_host(u.host, u.scheme),
            port=u.port,
            scheme=u.scheme,
            pool_kwargs=pool_kwargs,
        )

        try:
            if u.scheme not in (None, "http", "https"):
                from .contrib.webextensions import load_extension

                extension = load_extension(*parse_extension(u.scheme))  # type: ignore[arg-type]
                kw["extension"] = extension()
                kw.update(kw["extension"].urlopen_kwargs)

            kw["assert_same_host"] = False
            kw["redirect"] = False

            if "headers" not in kw:
                kw["headers"] = self.headers

            if self._proxy_requires_url_absolute_form(u):
                # Leave URL normalization to the pool to avoid decoding zone IDs twice.
                response = conn.urlopen(method, url.split("#", 1)[0], **kw)
            else:
                response = conn.urlopen(method, u.request_uri, **kw)
        finally:
            self.pools.release()

        if kw.get("multiplexed"):
            if isinstance(response, ResponsePromise):
                response.set_parameter("pm_redirect", redirect)
                response.set_parameter("pm_url", url)

                return response

            # the established connection is not capable of doing multiplexed request
            kw["multiplexed"] = False

        # we are relaxing that constraint to behave properly
        # with 3rd party mocking tool such as vcrpy.
        # see https://github.com/jawah/urllib3.future/issues/320
        # for more details.
        # assert isinstance(response, HTTPResponse)
        response = typing.cast(HTTPResponse, response)

        redirect_location = redirect and response.get_redirect_location()
        if not redirect_location:
            return response

        # Support relative URLs for redirecting.
        redirect_location = urljoin(url, redirect_location)

        # RFC 7231, Section 6.4.4
        if response.status == 303:
            method = "GET"
            kw["body"] = None
            kw["chunked"] = False
            kw["body_pos"] = None
            kw["headers"] = HTTPHeaderDict(kw["headers"])

            for should_be_removed_header in NOT_FORWARDABLE_HEADERS:
                kw["headers"].discard(should_be_removed_header)

        retries = kw.get("retries", response.retries)
        if not isinstance(retries, Retry):
            retries = Retry.from_int(retries, redirect=redirect)

        # The pool may belong to the proxy. Compare destination origins instead,
        # and remove Host so it can be rebuilt for a cross-origin redirect.
        scheme = u.scheme or "http"
        if kw["headers"] is not None and not _is_same_host(
            redirect_location,
            scheme,
            u.host.strip("[]") if u.host is not None else None,
            u.port,
        ):
            headers_to_remove = retries.remove_headers_on_redirect | {"host"}
            new_headers = kw["headers"].copy()
            for header in kw["headers"]:
                if header.lower() in headers_to_remove:
                    new_headers.pop(header, None)
            kw["headers"] = new_headers

        try:
            retries = retries.increment(method, url, response=response, _pool=conn)
        except MaxRetryError:
            if retries.raise_on_redirect:
                response.drain_conn()
                raise
            return response

        kw["retries"] = retries
        kw["redirect"] = redirect

        log.info("Redirecting %s -> %s", url, redirect_location)

        response.drain_conn()
        return self.urlopen(method, redirect_location, **kw)  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        with self.pools._lock:
            inner_repr = "; ".join(repr(p) for p in self.pools._registry.values())

            if inner_repr:
                inner_repr += " "

            return f"<PoolManager {inner_repr}{self.pools}>"


class ProxyManager(PoolManager):
    """
    Behaves just like :class:`PoolManager`, but sends all requests through
    the defined proxy, using the CONNECT method for HTTPS URLs.

    :param proxy_url:
        The URL of the proxy to be used.

    :param proxy_headers:
        A dictionary containing headers that will be sent to the proxy. In case
        of HTTP they are being sent with each request, while in the
        HTTPS/CONNECT case they are sent only once. Could be used for proxy
        authentication.

    :param proxy_ssl_context:
        The proxy SSL context is used to establish the TLS connection to the
        proxy when using HTTPS proxies.

    :param use_forwarding_for_https:
        (Defaults to False) If set to True will forward requests to the HTTPS
        proxy to be made on behalf of the client instead of creating a TLS
        tunnel via the CONNECT method. **Enabling this flag means that request
        and response headers and content will be visible from the HTTPS proxy**
        whereas tunneling keeps request and response headers and content
        private.  IP address, target hostname, SNI, and port are always visible
        to an HTTPS proxy even when this flag is disabled.

    :param proxy_assert_hostname:
        The hostname of the certificate to verify against.

    :param proxy_assert_fingerprint:
        The fingerprint of the certificate to verify against.

    Example:

    .. code-block:: python

        import urllib3

        proxy = urllib3.ProxyManager("https://localhost:3128/")

        resp1 = proxy.request("GET", "https://google.com/")
        resp2 = proxy.request("GET", "https://httpbin.org/")

        print(len(proxy.pools))
        # 1

        resp3 = proxy.request("GET", "https://httpbin.org/")
        resp4 = proxy.request("GET", "https://twitter.com/")

        print(len(proxy.pools))
        # 3

    """

    def __init__(
        self,
        proxy_url: str,
        num_pools: int = 10,
        headers: typing.Mapping[str, str] | None = None,
        proxy_headers: typing.Mapping[str, str] | None = None,
        proxy_ssl_context: ssl.SSLContext | None = None,
        use_forwarding_for_https: bool = False,
        proxy_assert_hostname: None | str | Literal[False] = None,
        proxy_assert_fingerprint: str | None = None,
        **connection_pool_kw: typing.Any,
    ) -> None:
        if isinstance(proxy_url, HTTPConnectionPool):
            str_proxy_url = f"{proxy_url.scheme}://{proxy_url.host}:{proxy_url.port}"
        else:
            str_proxy_url = proxy_url
        proxy = parse_url(str_proxy_url)

        if proxy.scheme not in ("http", "https"):
            raise ProxySchemeUnknown(proxy.scheme)

        if not proxy.port:
            port = port_by_scheme.get(proxy.scheme, 80)
            proxy = proxy._replace(port=port)

        self.proxy = proxy
        self.proxy_headers = proxy_headers or {}
        self.proxy_ssl_context = proxy_ssl_context
        self.proxy_config = ProxyConfig(
            proxy_ssl_context,
            use_forwarding_for_https,
            proxy_assert_hostname,
            proxy_assert_fingerprint,
        )

        connection_pool_kw["_proxy"] = self.proxy
        connection_pool_kw["_proxy_headers"] = self.proxy_headers
        connection_pool_kw["_proxy_config"] = self.proxy_config

        if "disabled_svn" not in connection_pool_kw:
            connection_pool_kw["disabled_svn"] = set()

        connection_pool_kw["disabled_svn"].add(HttpVersion.h3)

        super().__init__(num_pools, headers, **connection_pool_kw)

    def connection_from_host(
        self,
        host: str | None,
        port: int | None = None,
        scheme: str | None = "http",
        pool_kwargs: dict[str, typing.Any] | None = None,
    ) -> HTTPConnectionPool:
        if scheme in {"https", "wss", "sse"}:
            return super().connection_from_host(
                host, port, scheme, pool_kwargs=pool_kwargs
            )

        assert self.proxy is not None

        return super().connection_from_host(
            _encode_host(self.proxy.host, self.proxy.scheme),
            self.proxy.port,
            self.proxy.scheme,
            pool_kwargs=pool_kwargs,
        )

    def _set_proxy_headers(
        self, url: str, headers: typing.Mapping[str, str] | None = None
    ) -> typing.Mapping[str, str]:
        """
        Sets headers needed by proxies: specifically, the Accept and Host
        headers. Only sets headers not provided by the user.
        """
        headers_ = {"Accept": "*/*"}

        netloc = parse_url(url).netloc
        if netloc:
            headers_["Host"] = netloc

        if headers:
            headers_.update(headers)
        return headers_

    @typing.overload  # type: ignore[override]
    def urlopen(
        self,
        method: str,
        url: str,
        redirect: bool = True,
        *,
        multiplexed: Literal[False] = ...,
        **kw: typing.Any,
    ) -> HTTPResponse: ...

    @typing.overload
    def urlopen(
        self,
        method: str,
        url: str,
        redirect: bool = True,
        *,
        multiplexed: Literal[True],
        **kw: typing.Any,
    ) -> ResponsePromise: ...

    def urlopen(
        self,
        method: str,
        url: str,
        redirect: bool = True,
        **kw: typing.Any,
    ) -> HTTPResponse | ResponsePromise:
        "Same as HTTP(S)ConnectionPool.urlopen, ``url`` must be absolute."
        u = parse_url(url)
        if not connection_requires_http_tunnel(self.proxy, self.proxy_config, u.scheme):
            # For connections using HTTP CONNECT, httplib sets the necessary
            # headers on the CONNECT to the proxy. If we're not using CONNECT,
            # we'll definitely need to set 'Host' at the very least.
            headers = kw.get("headers", self.headers)
            kw["headers"] = self._set_proxy_headers(url, headers)

        return super().urlopen(method, url, redirect=redirect, **kw)  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        with self.pools._lock:
            inner_repr = "; ".join(repr(p) for p in self.pools._registry.values())

            if inner_repr:
                inner_repr += " "

            return f"<ProxyManager {self.proxy} {inner_repr}{self.pools}>"


def proxy_from_url(url: str, **kw: typing.Any) -> ProxyManager:
    return ProxyManager(proxy_url=url, **kw)
