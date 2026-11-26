from __future__ import annotations

from ._ssl import (
    AdGuardResolver,
    CloudflareResolver,
    GoogleResolver,
    OpenDNSResolver,
    Quad9Resolver,
    TLSResolver,
)

__all__ = (
    "TLSResolver",
    "GoogleResolver",
    "CloudflareResolver",
    "AdGuardResolver",
    "Quad9Resolver",
    "OpenDNSResolver",
)
