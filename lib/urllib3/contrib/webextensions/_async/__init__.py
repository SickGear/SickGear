from __future__ import annotations

from .protocol import AsyncExtensionFromHTTP
from .raw import AsyncRawExtensionFromHTTP
from .sse import AsyncServerSideEventExtensionFromHTTP

try:
    from .ws import (
        AsyncWebSocketExtensionFromHTTP,
        AsyncWebSocketExtensionFromMultiplexedHTTP,
    )
except ImportError:
    AsyncWebSocketExtensionFromHTTP = None  # type: ignore[misc, assignment]
    AsyncWebSocketExtensionFromMultiplexedHTTP = None  # type: ignore[misc, assignment]

from .. import recursive_subclasses


try:
    from .ws_fast import AsyncFastWebSocketExtensionFromHTTP
except ImportError:
    AsyncFastWebSocketExtensionFromHTTP = None  # type: ignore[misc, assignment]


def load_extension(
    scheme: str | None, implementation: str | None = None
) -> type[AsyncExtensionFromHTTP]:
    if scheme is None:
        return AsyncRawExtensionFromHTTP

    scheme = scheme.lower()

    if implementation:
        implementation = implementation.lower()

    for extension in recursive_subclasses(AsyncExtensionFromHTTP):
        if scheme in extension.supported_schemes():
            if (
                implementation is not None
                and extension.implementation() != implementation
            ):
                continue
            return extension

    raise ImportError(
        f"Tried to load HTTP extension '{scheme}' but no available plugin support it."
    )


__all__ = (
    "AsyncExtensionFromHTTP",
    "AsyncRawExtensionFromHTTP",
    "AsyncWebSocketExtensionFromHTTP",
    "AsyncWebSocketExtensionFromMultiplexedHTTP",
    "AsyncServerSideEventExtensionFromHTTP",
    "AsyncFastWebSocketExtensionFromHTTP",
    "load_extension",
)
