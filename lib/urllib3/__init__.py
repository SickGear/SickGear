"""
Python HTTP library with thread-safe connection pooling, file post support, user-friendly, and more
"""

from __future__ import annotations

# Set default logging handler to avoid "No handler found" warnings.
import logging
import sys
import typing
import warnings
from logging import NullHandler
from os import environ

if sys.platform == "wasi":
    # we have to eager import it, otherwise p1
    # socket fallback will crash.
    import encodings.idna as _idna  # noqa: F401

from . import exceptions
from ._async.connectionpool import AsyncHTTPConnectionPool, AsyncHTTPSConnectionPool
from ._async.connectionpool import connection_from_url as async_connection_from_url
from ._async.poolmanager import AsyncPoolManager, AsyncProxyManager
from ._async.poolmanager import proxy_from_url as async_proxy_from_url
from ._async.response import AsyncHTTPResponse
from ._collections import HTTPHeaderDict
from ._typing import _TYPE_BODY, _TYPE_FIELDS
from ._version import __version__
from .backend import ConnectionInfo, HttpVersion, ResponsePromise
from .connectionpool import HTTPConnectionPool, HTTPSConnectionPool, connection_from_url
from .contrib.resolver import ResolverDescription
from .contrib.resolver._async import AsyncResolverDescription
from .filepost import encode_multipart_formdata
from .poolmanager import PoolManager, ProxyManager, proxy_from_url
from .response import BaseHTTPResponse, HTTPResponse
from .util.request import make_headers
from .util.retry import Retry
from .util.timeout import Timeout

__author__ = "Andrey Petrov (andrey.petrov@shazow.net)"
__license__ = "MIT"
__version__ = __version__

__all__ = (
    "HTTPConnectionPool",
    "HTTPHeaderDict",
    "HTTPSConnectionPool",
    "PoolManager",
    "ProxyManager",
    "HTTPResponse",
    "Retry",
    "Timeout",
    "add_stderr_logger",
    "connection_from_url",
    "disable_warnings",
    "encode_multipart_formdata",
    "make_headers",
    "proxy_from_url",
    "request",
    "BaseHTTPResponse",
    "HttpVersion",
    "ConnectionInfo",
    "ResponsePromise",
    "ResolverDescription",
    "AsyncHTTPResponse",
    "AsyncResolverDescription",
    "AsyncHTTPConnectionPool",
    "AsyncHTTPSConnectionPool",
    "AsyncPoolManager",
    "AsyncProxyManager",
    "async_proxy_from_url",
    "async_connection_from_url",
)

logging.getLogger(__name__).addHandler(NullHandler())


def add_stderr_logger(
    level: int = logging.DEBUG,
) -> logging.StreamHandler[typing.TextIO]:
    """
    Helper for quickly adding a StreamHandler to the logger. Useful for
    debugging.

    Returns the handler after adding it.
    """
    # This method needs to be in this __init__.py to get the __name__ correct
    # even if urllib3 is vendored within another package.
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.debug("Added a stderr logging handler to logger: %s", __name__)
    return handler


# ... Clean up.
del NullHandler


if (
    environ.get("SSLKEYLOGFILE", None) is not None
    or environ.get("QUICLOGDIR", None) is not None
):
    warnings.warn(  # Defensive: security warning only. not feature.
        "urllib3.future detected that development/debug environment variable are set. "
        "If you are unaware of it please audit your environment. "
        "Variables 'SSLKEYLOGFILE' and 'QUICLOGDIR' can only be set in a non-production environment.",
        exceptions.SecurityWarning,
    )

# All warning filters *must* be appended unless you're really certain that they
# shouldn't be: otherwise, it's very hard for users to use most Python
# mechanisms to silence them.
# SecurityWarning's always go off by default.
warnings.simplefilter("always", exceptions.SecurityWarning, append=True)
# InsecurePlatformWarning's don't vary between requests, so we keep it default.
warnings.simplefilter("default", exceptions.InsecurePlatformWarning, append=True)


def disable_warnings(category: type[Warning] = exceptions.HTTPWarning) -> None:
    """
    Helper for quickly disabling all urllib3 warnings.
    """
    warnings.simplefilter("ignore", category)


_DEFAULT_POOL = PoolManager()


def request(
    method: str,
    url: str,
    *,
    body: _TYPE_BODY | None = None,
    fields: _TYPE_FIELDS | None = None,
    headers: typing.Mapping[str, str] | None = None,
    preload_content: bool | None = True,
    decode_content: bool | None = True,
    redirect: bool | None = True,
    retries: Retry | bool | int | None = None,
    timeout: Timeout | float | int | None = 3,
    json: typing.Any | None = None,
) -> HTTPResponse:
    """
    A convenience, top-level request method. It uses a module-global ``PoolManager`` instance.
    Therefore, its side effects could be shared across dependencies relying on it.
    To avoid side effects create a new ``PoolManager`` instance and use it instead.
    The method does not accept low-level ``**urlopen_kw``.
    """

    return _DEFAULT_POOL.request(
        method,
        url,
        body=body,
        fields=fields,
        headers=headers,
        preload_content=preload_content,
        decode_content=decode_content,
        redirect=redirect,
        retries=retries,
        timeout=timeout,
        json=json,
    )
