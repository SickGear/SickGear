"""Internal resolution helpers for :mod:`urllib3.contrib.anytls`."""

from __future__ import annotations

import importlib
import os
import warnings
from types import ModuleType
from typing import Tuple

ENV_VAR = "URLLIB3_FUTURE_SSL_BACKEND"

# Default preference order.
_DEFAULT_ORDER: Tuple[str, ...] = ("rtls", "utls", "ssl")

# Map of accepted env-var tokens (lowercased, stripped) -> canonical backend.
_TOKEN_MAP = {
    "rtls": "rtls",
    "rustls": "rtls",
    "aws-lc": "rtls",
    "aws_lc": "rtls",
    "awslc": "rtls",
    "utls": "utls",
    "boringssl": "utls",
    "boring-ssl": "utls",
    "boring_ssl": "utls",
    "ssl": "ssl",
    "stdlib": "ssl",
    "stdlib_ssl": "ssl",
}

# Mapping from canonical backend name -> import path.
_IMPORT_NAME = {
    "rtls": "rtls",
    "utls": "utls",
    "ssl": "ssl",
}


def _parse_pref(value: str | None) -> list[str]:
    """Build the ordered list of backends to attempt.

    The user-requested backend (if any) is tried first, then the remaining
    defaults in the default order, de-duplicated.
    """
    order: list[str] = []

    if value:
        token = value.strip().lower()
        if token in _TOKEN_MAP:
            order.append(_TOKEN_MAP[token])
        elif token:
            warnings.warn(
                f"Unknown value {value!r} for environment variable "
                f"{ENV_VAR}; falling back to default backend resolution "
                f"order (rtls -> utls -> ssl).",
                stacklevel=3,
            )

    for name in _DEFAULT_ORDER:
        if name not in order:
            order.append(name)

    return order


def _try_import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(_IMPORT_NAME[name])
    except ImportError:
        return None
    except Exception:  # Defensive: broken optional backend.
        return None


def _load_certificate(backend: str) -> type | None:
    """Best-effort import of the Certificate type used for peer-cert chain
    extraction. rtls/utls expose it directly; for stdlib ssl, fall back to the
    private ``_ssl.Certificate`` (used by ``backend/hface.py``).
    """
    if backend in ("rtls", "utls"):
        try:
            mod = importlib.import_module(backend)
            return getattr(mod, "Certificate", None)
        except ImportError:
            return None
    # CPython stdlib
    try:
        _ssl = importlib.import_module("_ssl")
        cert = getattr(_ssl, "Certificate", None)
        if cert is not None:
            return cert  # type: ignore[no-any-return]
    except ImportError:
        pass
    # PyPy: same type lives here instead of on _ssl
    try:
        from _cffi_ssl._stdssl.certificate import Certificate  # type: ignore[import-not-found]

        return Certificate  # type: ignore[no-any-return]
    except ImportError:
        return None


def _resolve() -> tuple[ModuleType | None, ModuleType | None, str, object | None]:
    """Resolve and return (ssl, stdlib_ssl, BACKEND, Certificate)."""
    try:
        stdlib_ssl: ModuleType | None = importlib.import_module("ssl")
    except ImportError:
        stdlib_ssl = None

    order = _parse_pref(os.environ.get(ENV_VAR))

    chosen_name = "none"
    chosen_mod: ModuleType | None = None

    for name in order:
        mod = _try_import(name)
        if mod is not None:
            chosen_name = name
            chosen_mod = mod
            break

    if chosen_mod is None:
        return None, stdlib_ssl, "none", None

    certificate = _load_certificate(chosen_name)
    return chosen_mod, stdlib_ssl, chosen_name, certificate
