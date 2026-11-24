from __future__ import annotations

from ._urllib3 import (
    AdGuardResolver,
    CloudflareResolver,
    GoogleResolver,
    HTTPSResolver,
    NextDNSResolver,
    OpenDNSResolver,
    Quad9Resolver,
)

__all__ = (
    "HTTPSResolver",
    "GoogleResolver",
    "CloudflareResolver",
    "AdGuardResolver",
    "OpenDNSResolver",
    "Quad9Resolver",
    "NextDNSResolver",
)
