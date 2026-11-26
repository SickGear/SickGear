from __future__ import annotations

import socket
import typing
from email.errors import MessageDefect

if typing.TYPE_CHECKING:
    from ._async.connection import AsyncHTTPConnection
    from ._async.connectionpool import AsyncConnectionPool
    from ._async.response import AsyncHTTPResponse
    from ._typing import _TYPE_REDUCE_RESULT
    from .backend import ResponsePromise
    from .connection import HTTPConnection
    from .connectionpool import ConnectionPool
    from .response import HTTPResponse
    from .util.retry import Retry

# Base Exceptions
# Use the stdlib ssl.SSLError as base so we catch both stdlib and non-stdlib
# (rtls/utls) SSL errors. rtls.SSLError / utls.SSLError both subclass the
# stdlib ssl.SSLError, so isinstance checks work both ways.
from .contrib.anytls import stdlib_ssl as _stdlib_ssl

if _stdlib_ssl is not None:
    BaseSSLError = _stdlib_ssl.SSLError
else:

    class BaseSSLError(BaseException):  # type: ignore[no-redef]
        pass


class HTTPError(Exception):
    """Base exception used by this module."""


class HTTPWarning(Warning):
    """Base warning used by this module."""


class PoolError(HTTPError):
    """Base exception for errors caused within a pool."""

    def __init__(
        self, pool: ConnectionPool | AsyncConnectionPool, message: str
    ) -> None:
        self.pool = pool
        super().__init__(f"{pool}: {message}")

    def __reduce__(self) -> _TYPE_REDUCE_RESULT:
        # For pickling purposes.
        return self.__class__, (None, None)


class RequestError(PoolError):
    """Base exception for PoolErrors that have associated URLs."""

    def __init__(
        self, pool: ConnectionPool | AsyncConnectionPool, url: str, message: str
    ) -> None:
        self.url = url
        super().__init__(pool, message)

    def __reduce__(self) -> _TYPE_REDUCE_RESULT:
        # For pickling purposes.
        return self.__class__, (None, self.url, None)


class SSLError(HTTPError):
    """Raised when SSL certificate fails in an HTTPS connection."""


class ProxyError(HTTPError):
    """Raised when the connection to a proxy fails."""

    # The original error is also available as __cause__.
    original_error: Exception

    def __init__(self, message: str, error: Exception) -> None:
        super().__init__(message, error)
        self.original_error = error


class DecodeError(HTTPError):
    """Raised when automatic decoding based on Content-Type fails."""


class ProtocolError(HTTPError):
    """Raised when something unexpected happens mid-request/response."""


#: Renamed to ProtocolError but aliased for backwards compatibility.
ConnectionError = ProtocolError


# Leaf Exceptions


class MaxRetryError(RequestError):
    """Raised when the maximum number of retries is exceeded.

    :param pool: The connection pool
    :type pool: :class:`~urllib3.connectionpool.HTTPConnectionPool`
    :param str url: The requested Url
    :param reason: The underlying error
    :type reason: :class:`Exception`

    """

    def __init__(
        self,
        pool: ConnectionPool | AsyncConnectionPool,
        url: str,
        reason: Exception | None = None,
    ) -> None:
        self.reason = reason

        message = f"Max retries exceeded with url: {url} (Caused by {reason!r})"

        super().__init__(pool, url, message)


class HostChangedError(RequestError):
    """Raised when an existing pool gets a request for a foreign host."""

    def __init__(
        self,
        pool: ConnectionPool | AsyncConnectionPool,
        url: str,
        retries: Retry | int = 3,
    ) -> None:
        message = f"Tried to open a foreign host with url: {url}"
        super().__init__(pool, url, message)
        self.retries = retries


class TimeoutStateError(HTTPError):
    """Raised when passing an invalid state to a timeout"""


class TimeoutError(HTTPError):
    """Raised when a socket timeout error occurs.

    Catching this error will catch both :exc:`ReadTimeoutErrors
    <ReadTimeoutError>` and :exc:`ConnectTimeoutErrors <ConnectTimeoutError>`.
    """


class ReadTimeoutError(TimeoutError, RequestError):
    """Raised when a socket timeout occurs while receiving data from a server"""


# This timeout error does not have a URL attached and needs to inherit from the
# base HTTPError
class ConnectTimeoutError(TimeoutError):
    """Raised when a socket timeout occurs while connecting to a server"""


class NewConnectionError(ConnectTimeoutError, HTTPError):
    """Raised when we fail to establish a new connection. Usually ECONNREFUSED."""

    def __init__(
        self,
        conn: HTTPConnection
        | AsyncHTTPConnection
        | ConnectionPool
        | AsyncConnectionPool,
        message: str,
    ) -> None:
        self.conn = conn
        super().__init__(f"{conn}: {message}")

    def __reduce__(self) -> _TYPE_REDUCE_RESULT:
        # For pickling purposes.
        return self.__class__, (None, None)


class NameResolutionError(NewConnectionError):
    """Raised when host name resolution fails."""

    def __init__(
        self,
        host: str,
        conn: HTTPConnection
        | AsyncHTTPConnection
        | ConnectionPool
        | AsyncConnectionPool,
        reason: socket.gaierror,
    ):
        message = f"Failed to resolve '{host}' ({reason})"
        super().__init__(conn, message)

    def __reduce__(self) -> _TYPE_REDUCE_RESULT:
        # For pickling purposes.
        return self.__class__, (None, None, None)


class EmptyPoolError(PoolError):
    """Raised when a pool runs out of connections and no more are allowed."""


class FullPoolError(PoolError):
    """Raised when we try to add a connection to a full pool in blocking mode."""


class ClosedPoolError(PoolError):
    """Raised when a request enters a pool after the pool has been closed."""


class LocationValueError(ValueError, HTTPError):
    """Raised when there is something wrong with a given URL input."""


class LocationParseError(LocationValueError):
    """Raised when get_host or similar fails to parse the URL input."""

    def __init__(self, location: str) -> None:
        message = f"Failed to parse: {location}"
        super().__init__(message)

        self.location = location


class URLSchemeUnknown(LocationValueError):
    """Raised when a URL input has an unsupported scheme."""

    def __init__(self, scheme: str):
        message = f"Not supported URL scheme {scheme}"
        super().__init__(message)

        self.scheme = scheme


class ResponseError(HTTPError):
    """Used as a container for an error reason supplied in a MaxRetryError."""

    GENERIC_ERROR = "too many error responses"
    SPECIFIC_ERROR = "too many {status_code} error responses"


class SecurityWarning(HTTPWarning):
    """Warned when performing security reducing actions"""


class InsecureRequestWarning(SecurityWarning):
    """Warned when making an unverified HTTPS request."""


class NotOpenSSLWarning(SecurityWarning):
    """Warned when using unsupported SSL library"""


class SystemTimeWarning(SecurityWarning):
    """Warned when system time is suspected to be wrong"""


class InsecurePlatformWarning(SecurityWarning):
    """Warned when certain TLS/SSL configuration is not available on a platform."""


class DependencyWarning(HTTPWarning):
    """
    Warned when an attempt is made to import a module with missing optional
    dependencies.
    """


class ResponseNotChunked(ProtocolError, ValueError):
    """Response needs to be chunked in order to read it as chunks."""


class BodyNotHttplibCompatible(HTTPError):
    """
    Body should be :class:`http.client.HTTPResponse` like
    (have an fp attribute which returns raw chunks) for read_chunked().
    """


class IncompleteRead(ProtocolError):
    """
    Response length doesn't match expected Content-Length

    Subclass of :class:`http.client.IncompleteRead` to allow int value
    for ``partial`` to avoid creating large objects on streamed reads.
    """

    def __init__(self, partial: int, expected: int | None = None) -> None:
        self.partial = partial
        self.expected = expected

    def __repr__(self) -> str:
        if self.expected is not None:
            return f"IncompleteRead({self.partial} bytes read, {self.expected} more expected)"
        return f"IncompleteRead({self.partial} bytes read)"

    __str__ = object.__str__


class InvalidChunkLength(ProtocolError):
    """Invalid chunk length in a chunked response."""

    def __init__(
        self, response: HTTPResponse | AsyncHTTPResponse, length: bytes
    ) -> None:
        self.partial: int = response.tell()
        self.expected: int | None = response.length_remaining
        self.response = response
        self.length = length

    def __repr__(self) -> str:
        return "InvalidChunkLength(got length %r, %i bytes read)" % (
            self.length,
            self.partial,
        )


class InvalidHeader(HTTPError):
    """The header provided was somehow invalid."""


class ProxySchemeUnknown(AssertionError, URLSchemeUnknown):
    """ProxyManager does not support the supplied scheme"""

    # TODO(t-8ch): Stop inheriting from AssertionError in v2.0.

    def __init__(self, scheme: str | None) -> None:
        # 'localhost' is here because our URL parser parses
        # localhost:8080 -> scheme=localhost, remove if we fix this.
        if scheme == "localhost":
            scheme = None
        if scheme is None:
            message = "Proxy URL had no scheme, should start with http:// or https://"
        else:
            message = f"Proxy URL had unsupported scheme {scheme}, should use http:// or https://"
        super().__init__(message)


class ProxySchemeUnsupported(ValueError):
    """Fetching HTTPS resources through HTTPS proxies is unsupported"""


class HeaderParsingError(HTTPError):
    """Raised by assert_header_parsing, but we convert it to a log.warning statement."""

    def __init__(
        self, defects: list[MessageDefect], unparsed_data: bytes | str | None
    ) -> None:
        message = f"{defects or 'Unknown'}, unparsed data: {unparsed_data!r}"
        super().__init__(message)


class UnrewindableBodyError(HTTPError):
    """urllib3 encountered an error when trying to rewind a body"""


class EarlyResponse(HTTPError):
    """Stop the upload and collect its response, which may still be pending."""

    def __init__(self, promise: ResponsePromise) -> None:
        self.promise = promise


class ResponseNotReady(HTTPError):
    """Kept for BC"""


class RecoverableError(HTTPError):
    """This error is never leaked in the upper stack, it serves only an internal purpose."""


class MustDowngradeError(RecoverableError):
    """An error occurred with a protocol and can be circumvented using an older protocol."""


class MustRedialError(RecoverableError):
    """Unused legacy exception. Remove it in a next major."""
