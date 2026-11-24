from __future__ import annotations

import typing
from abc import ABCMeta
from socket import timeout as SocketTimeout
from types import TracebackType

if typing.TYPE_CHECKING:
    from ...._async.response import AsyncHTTPResponse
    from ....backend import HttpVersion
    from ....backend._async._base import AsyncDirectStreamAccess
    from ....util._async.traffic_police import AsyncTrafficPolice

from ....exceptions import (
    BaseSSLError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
    MustRedialError,
)


class AsyncExtensionFromHTTP(metaclass=ABCMeta):
    """Exchange extension payloads asynchronously through an HTTP response.

    Implementations include HTTP/1.1 upgrades, HTTP/2 and HTTP/3 extended CONNECT,
    and ordinary streaming responses such as Server-Sent Events.
    """

    def __init__(self) -> None:
        self._dsa: AsyncDirectStreamAccess | None = None
        self._response: AsyncHTTPResponse | None = None
        self._police_officer: AsyncTrafficPolice | None = None  # type: ignore[type-arg]

    def _read_error_catcher(self) -> _AsyncReadErrorCatcher:
        return _AsyncReadErrorCatcher(self)

    def _write_error_catcher(self) -> _AsyncWriteErrorCatcher:
        return _AsyncWriteErrorCatcher(self)

    @property
    def urlopen_kwargs(self) -> dict[str, typing.Any]:
        return {}

    async def start(self, response: AsyncHTTPResponse) -> None:
        """The HTTP server gave us the go-to start negotiating another protocol."""
        if response._fp is None or not hasattr(response._fp, "_dsa"):
            raise OSError("The HTTP extension is closed or uninitialized")

        self._dsa = response._fp._dsa
        self._police_officer = response._police_officer
        self._response = response

    @property
    def closed(self) -> bool:
        return self._dsa is None

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        """Hint about supported parent SVN for this extension."""
        raise NotImplementedError

    @staticmethod
    def implementation() -> str:
        raise NotImplementedError

    @staticmethod
    def supported_schemes() -> set[str]:
        """Recognized schemes for the extension."""
        raise NotImplementedError

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        """Convert the extension scheme to a known http scheme (either http or https)"""
        raise NotImplementedError

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        """Return the opening request headers for the selected HTTP version."""
        raise NotImplementedError

    async def close(self) -> None:
        """End/Notify close for sub protocol."""
        raise NotImplementedError

    async def next_payload(self) -> str | bytes | None:
        """Unpack the next received message/payload from remote. This call does read from the socket.
        If the method return None, it means that the remote closed the (extension) pipeline.
        """
        raise NotImplementedError

    async def send_payload(self, buf: str | bytes) -> None:
        """Dispatch a buffer to remote."""
        raise NotImplementedError

    async def on_payload(
        self, callback: typing.Callable[[str | bytes | None], typing.Awaitable[None]]
    ) -> None:
        """Set up a callback that will be invoked automatically once a payload is received.
        Meaning that you stop calling manually next_payload()."""
        raise NotImplementedError


class _AsyncReadErrorCatcher:
    """Translate read errors, preserving the extension on read timeouts."""

    __slots__ = ("_owner",)

    def __init__(self, owner: AsyncExtensionFromHTTP) -> None:
        self._owner = owner

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> typing.Literal[False]:
        if exc is None:
            return False
        owner = self._owner
        clean_exit = False
        try:
            if isinstance(exc, SocketTimeout):
                clean_exit = True  # A read timeout leaves the extension usable.
                pool = (
                    owner._response._pool
                    if owner._response and hasattr(owner._response, "_pool")
                    else None
                )
                raise ReadTimeoutError(pool, None, "Read timed out.") from exc  # type: ignore[arg-type]
            elif isinstance(exc, BaseSSLError):
                if "read operation timed out" not in str(exc):
                    raise SSLError(exc) from exc
                clean_exit = True  # A read timeout leaves the extension usable.
                pool = (
                    owner._response._pool
                    if owner._response and hasattr(owner._response, "_pool")
                    else None
                )
                raise ReadTimeoutError(pool, None, "Read timed out.") from exc  # type: ignore[arg-type]
            elif isinstance(exc, (OSError, MustRedialError)):
                raise ProtocolError(f"Connection broken: {exc!r}", exc) from exc
            return False
        finally:
            if not clean_exit:
                if owner._response:
                    await owner.close()


class _AsyncWriteErrorCatcher:
    """Translate write errors and close the extension on failure."""

    __slots__ = ("_owner",)

    def __init__(self, owner: AsyncExtensionFromHTTP) -> None:
        self._owner = owner

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> typing.Literal[False]:
        if exc is None:
            return False
        owner = self._owner
        try:
            if isinstance(exc, SocketTimeout):
                pool = (
                    owner._response._pool
                    if owner._response and hasattr(owner._response, "_pool")
                    else None
                )
                raise ReadTimeoutError(pool, None, "Read timed out.") from exc  # type: ignore[arg-type]
            elif isinstance(exc, BaseSSLError):
                raise SSLError(exc) from exc
            elif isinstance(exc, OSError):
                raise ProtocolError(f"Connection broken: {exc!r}", exc) from exc
            return False
        finally:
            if owner._response:
                await owner.close()
