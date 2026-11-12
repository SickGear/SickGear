from __future__ import annotations

from ._socket import (
    AdGuardResolver,
    CloudflareResolver,
    GoogleResolver,
    PlainResolver,
    Quad9Resolver,
)

__all__ = (
    "PlainResolver",
    "CloudflareResolver",
    "GoogleResolver",
    "Quad9Resolver",
    "AdGuardResolver",
)
