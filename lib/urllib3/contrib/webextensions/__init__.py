from __future__ import annotations

from .protocol import ExtensionFromHTTP
from .raw import RawExtensionFromHTTP
from .sse import ServerSideEventExtensionFromHTTP

try:
    from .ws import WebSocketExtensionFromHTTP, WebSocketExtensionFromMultiplexedHTTP
except ImportError:
    WebSocketExtensionFromHTTP = None  # type: ignore[misc, assignment]
    WebSocketExtensionFromMultiplexedHTTP = None  # type: ignore[misc, assignment]

try:
    from .ws_fast import FastWebSocketExtensionFromHTTP
except ImportError:
    FastWebSocketExtensionFromHTTP = None  # type: ignore[misc, assignment]

from typing import TypeVar

T = TypeVar("T")


def recursive_subclasses(cls: type[T]) -> list[type[T]]:
    all_subclasses = []

    for subclass in cls.__subclasses__():
        all_subclasses.append(subclass)
        all_subclasses.extend(recursive_subclasses(subclass))

    return all_subclasses


def load_extension(
    scheme: str | None, implementation: str | None = None
) -> type[ExtensionFromHTTP]:
    if scheme is None:
        return RawExtensionFromHTTP

    scheme = scheme.lower()

    if implementation:
        implementation = implementation.lower()

    for extension in recursive_subclasses(ExtensionFromHTTP):
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
    "ExtensionFromHTTP",
    "RawExtensionFromHTTP",
    "WebSocketExtensionFromHTTP",
    "WebSocketExtensionFromMultiplexedHTTP",
    "ServerSideEventExtensionFromHTTP",
    "FastWebSocketExtensionFromHTTP",
    "load_extension",
)
