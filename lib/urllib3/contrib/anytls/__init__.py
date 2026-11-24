"""
urllib3.contrib.anytls
======================

Single point of resolution for the active TLS backend.

This module masks the conditional ``import rtls as ssl`` / ``import utls as
ssl`` / ``import ssl`` dance that would otherwise be duplicated in every
module that needs TLS. It picks the best available backend at import time
following the default priority:

    rtls (Rustls + AWS-LC)  ->  utls (BoringSSL)  ->  ssl (stdlib)
"""

from __future__ import annotations

import typing

from ._backend import _resolve

if typing.TYPE_CHECKING:
    # For static type-checkers, expose the stdlib ``ssl`` module. All three
    # backends share the same surface used by urllib3, so this is safe.
    import ssl

    stdlib_ssl = ssl
    Certificate: typing.Any = None
    BACKEND: str = "ssl"
    HAS_SSL: bool = True
    IS_NONSTDLIB: bool = False
    # Forced-backend accessors (see ``__getattr__``). All three backends share
    # the surface used by urllib3, so the stdlib ``ssl`` typing is safe.
    rtls = ssl
    utls = ssl
else:
    ssl, stdlib_ssl, BACKEND, Certificate = _resolve()
    HAS_SSL = ssl is not None
    IS_NONSTDLIB = BACKEND in ("rtls", "utls")


def __getattr__(name: str) -> typing.Any:
    """Lazily expose the individual TLS backends.

    ``rtls`` and ``utls`` resolve to their respective modules (or ``None`` when
    not installed), regardless of which backend was selected as the default
    ``ssl``. The stdlib ``ssl`` module is always available as ``stdlib_ssl``.
    This lets callers force a specific implementation, see
    :func:`urllib3.util.ssl_.create_urllib3_context` ``ssl_backend``.
    """
    if name in ("rtls", "utls"):
        from ._backend import _try_import

        module = _try_import(name)
        globals()[name] = module  # cache the result (module or None)
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "ssl",
    "stdlib_ssl",
    "BACKEND",
    "HAS_SSL",
    "IS_NONSTDLIB",
    "Certificate",
    "rtls",
    "utls",
)
