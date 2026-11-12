from __future__ import annotations

try:
    from ._qh3 import AdGuardResolver, NextDNSResolver, QUICResolver
except ImportError:
    QUICResolver = None  # type: ignore
    AdGuardResolver = None  # type: ignore
    NextDNSResolver = None  # type: ignore


__all__ = (
    "QUICResolver",
    "AdGuardResolver",
    "NextDNSResolver",
)
