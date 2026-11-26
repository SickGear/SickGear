from __future__ import annotations

import sys

# WASI platform doesn't support lazy imports.
if sys.platform == "wasi":
    try:
        from . import doh as _doh  # noqa: F401
    except ImportError:
        pass

    try:
        from . import dot as _dot  # noqa: F401
    except ImportError:
        pass

    try:
        from . import in_memory as _in_memory  # noqa: F401
    except ImportError:
        pass

    try:
        from . import null as _null  # noqa: F401
    except ImportError:
        pass

    try:
        from . import system as _system  # noqa: F401
    except ImportError:
        pass

from .factories import ResolverDescription, ResolverFactory
from .protocols import BaseResolver, ManyResolver, ProtocolResolver

__all__ = (
    "ResolverFactory",
    "ProtocolResolver",
    "BaseResolver",
    "ManyResolver",
    "ResolverDescription",
)
