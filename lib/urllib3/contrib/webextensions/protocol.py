from __future__ import annotations

import typing
from abc import ABCMeta
from socket import timeout as SocketTimeout
from types import TracebackType

if typing.TYPE_CHECKING:
    from ...backend import HttpVersion
    from ...backend._base import DirectStreamAccess
    from ...response import HTTPResponse
    from ...util.traffic_police import TrafficPolice

from ...exceptions import (
    BaseSSLError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
    MustRedialError,
)


class ExtensionFromHTTP(metaclass=ABCMeta):
    """Exchange extension payloads through an HTTP response.

    Implementations include HTTP/1.1 upgrades, HTTP/2 and HTTP/3 extended CONNECT,
    and ordinary streaming responses such as Server-Sent Events.
    """

    def __init__(self) -> None:
        self._dsa: DirectStreamAccess | None = None
        self._response: HTTPResponse | None = None
        self._police_officer: TrafficPolice | None = None  # type: ignore[type-arg]

    def _read_error_catcher(self) -> _ReadErrorCatcher:
        return _ReadErrorCatcher(self)

    def _write_error_catcher(self) -> _WriteErrorCatcher:
        return _WriteErrorCatcher(self)

    @property
    def urlopen_kwargs(self) -> dict[str, typing.Any]:
        """Return prerequisites. Must be passed as additional parameters to urlopen."""
        return {}

    def start(self, response: HTTPResponse) -> None:
        """The HTTP server gave us the go-to start negotiating another protocol."""
        if response._fp is None or not hasattr(response._fp, "_dsa"):
            raise RuntimeError(
                "Attempt to start an HTTP extension without direct I/O access to the stream"
            )

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

    def close(self) -> None:
        """End/Notify close for sub protocol."""
        raise NotImplementedError

    def next_payload(self) -> str | bytes | None:
        """Unpack the next received message/payload from remote. This call does read from the socket.
        If the method return None, it means that the remote closed the (extension) pipeline.
        """
        raise NotImplementedError

    def send_payload(self, buf: str | bytes) -> None:
        """Dispatch a buffer to remote."""
        raise NotImplementedError

    def on_payload(self, callback: typing.Callable[[str | bytes | None], None]) -> None:
        """Set up a callback that will be invoked automatically once a payload is received.
        Meaning that you stop calling manually next_payload()."""
        raise NotImplementedError


class _ReadErrorCatcher:
    """Translate read errors, preserving the extension on read timeouts."""

    __slots__ = ("_owner",)

    def __init__(self, owner: ExtensionFromHTTP) -> None:
        self._owner = owner

    def __enter__(self) -> None:
        return None

    def __exit__(
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
                    owner.close()


class _WriteErrorCatcher:
    """Translate write errors and close the extension on failure."""

    __slots__ = ("_owner",)

    def __init__(self, owner: ExtensionFromHTTP) -> None:
        self._owner = owner

    def __enter__(self) -> None:
        return None

    def __exit__(
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
                owner.close()
