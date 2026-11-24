"""
the Wassima library is a simple library.
It aims to provide a pythonic way to retrieve root CAs from your system without any difficulties or hazmat.
"""

from __future__ import annotations

import time
from functools import wraps
from threading import RLock
from typing import TYPE_CHECKING, Any

from ._os import (
    IS_BSD,
    IS_LINUX,
)
from ._os import (
    root_der_certificates as _root_der_certificates,
)
from ._os._embed import root_der_certificates as fallback_der_certificates
from ._version import VERSION, __version__
from .utils import DER_cert_to_PEM_cert, PEM_cert_to_DER_cert

if TYPE_CHECKING:
    import ssl
    from typing import Callable, Protocol, TypeVar

    from typing_extensions import ParamSpec

    _P = ParamSpec("_P")
    _R = TypeVar("_R", covariant=True)

    class _CachedFunc(Protocol[_P, _R]):
        def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R: ...
        def cache_clear(self) -> None: ...


# Mozilla TLS recommendations for ciphers
# General-purpose servers with a variety of clients, recommended for almost all systems.
MOZ_INTERMEDIATE_CIPHERS: str = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305"  # noqa: E501
#: Contain user custom CAs
_MANUALLY_REGISTERED_CA: list[bytes] = []
#: Lock for shared register-ca
_USER_APPEND_CA_LOCK = RLock()

#: Default cache TTL (seconds). Twelve hours. The cache is automatically
#: invalidated after this duration so that, e.g., a fresh CA being added to
#: the OS trust store does not require restarting the running process.
#: Twelve hours (rather than twenty-four) so that, in environments where CAs
#: are rotated daily, the cache is guaranteed to refresh at least once
#: between two rotations.
DEFAULT_CACHE_TTL_SECONDS: int = 43200

_CACHE_TTL_SECONDS: int = DEFAULT_CACHE_TTL_SECONDS


def _ttl_lru_cache(func: Callable[_P, _R]) -> _CachedFunc[_P, _R]:
    """A minimal, thread-safe memorizing decorator with a per-call-site TTL."""
    sentinel = object()
    cache: dict[Any, Any] = {}
    state: dict[str, float] = {"expires_at": 0.0}
    lock = RLock()

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = (args, tuple(sorted(kwargs.items()))) if kwargs else args
        with lock:
            now = time.monotonic()
            if now >= state["expires_at"]:
                cache.clear()
                state["expires_at"] = now + _CACHE_TTL_SECONDS
            result = cache.get(key, sentinel)
            if result is sentinel:
                result = func(*args, **kwargs)
                cache[key] = result
            return result

    def cache_clear() -> None:
        with lock:
            cache.clear()
            state["expires_at"] = 0.0

    wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def set_cache_ttl(seconds: int) -> None:
    """Override the default cache TTL (in seconds) used by
    :func:`root_der_certificates` and :func:`root_pem_certificates`.

    A value of ``0`` disables caching entirely (each call recomputes).
    Any pending cached result is dropped immediately.
    """
    global _CACHE_TTL_SECONDS
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise TypeError("cache TTL must be an int (seconds)")
    if seconds < 0:
        raise ValueError("cache TTL cannot be negative")
    _CACHE_TTL_SECONDS = seconds
    root_der_certificates.cache_clear()
    root_pem_certificates.cache_clear()


@_ttl_lru_cache
def root_der_certificates(hybrid_store: bool = False) -> list[bytes]:
    """Retrieve a list of root certificates from your operating system trust store,
    DER (binary) encoded.

    When ``hybrid_store`` is ``True``, the embedded CCADB Mozilla bundle is
    forcibly merged in addition to the OS trusted CAs. This is also implicitly
    enabled on Linux/BSD when the system trust store appears to be stale
    (older than 3 years without update).

    The OS-specific backends already guarantee a duplicate-free list; this
    function only re-deduplicates when extra sources (CCADB fallback, hybrid
    bundle, user-registered CAs) are merged on top.
    """
    certificates = _root_der_certificates()

    force_hybrid = hybrid_store

    if IS_LINUX or IS_BSD:
        from ._os._linux import is_trust_store_stale

        if is_trust_store_stale():
            force_hybrid = True

    # Track what's already in the resulting list so that any extension
    # below (CCADB fallback, hybrid bundle, manually-registered CAs) can
    # avoid re-adding a DER that is already present.
    if not certificates:
        certificates = fallback_der_certificates()
    elif force_hybrid:
        seen = set(certificates)
        certificates = list(certificates)
        for cert in fallback_der_certificates():
            if cert not in seen:
                seen.add(cert)
                certificates.append(cert)

    manually_registered = tuple(_MANUALLY_REGISTERED_CA)  # snapshot

    if manually_registered:
        seen = set(certificates)
        for cert in manually_registered:
            if cert not in seen:
                seen.add(cert)
                certificates.append(cert)

    return certificates


@_ttl_lru_cache
def root_pem_certificates(hybrid_store: bool = False) -> list[str]:
    """
    Retrieve a list of root certificate from your operating system trust store.
    They will be PEM encoded.

    See :func:`root_der_certificates` for the meaning of ``hybrid_store``.
    """
    pem_certs = []

    for bin_cert in root_der_certificates(hybrid_store=hybrid_store):
        pem_certs.append(DER_cert_to_PEM_cert(bin_cert))

    return pem_certs


def generate_ca_bundle(hybrid_store: bool = False) -> str:
    """
    Generate an aggregated CA bundle that originate from your system trust store.
    Simply put, concatenated root PEM certificate.

    See :func:`root_der_certificates` for the meaning of ``hybrid_store``.
    """
    return "\n\n".join(root_pem_certificates(hybrid_store=hybrid_store))


def register_ca(pem_or_der_certificate: bytes | str) -> None:
    """
    You may register your own CA certificate in addition to your system trust store.
    """
    with _USER_APPEND_CA_LOCK:
        if isinstance(pem_or_der_certificate, str):
            pem_or_der_certificate = PEM_cert_to_DER_cert(pem_or_der_certificate)

        if pem_or_der_certificate not in _MANUALLY_REGISTERED_CA:
            _MANUALLY_REGISTERED_CA.append(pem_or_der_certificate)

            root_pem_certificates.cache_clear()
            root_der_certificates.cache_clear()


def create_default_ssl_context(hybrid_store: bool = False) -> ssl.SSLContext:
    """
    Instantiate a native SSLContext (client purposes) that ships with your system root CAs.
    In addition to that, assign it the default OpenSSL ciphers suite and set
    TLS 1.2 as the minimum supported version. Also disable commonName check and enforce
    hostname altName verification. The Mozilla Recommended Cipher Suite is used instead of system default.

    See :func:`root_der_certificates` for the meaning of ``hybrid_store``.
    """
    import ssl

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    ctx.load_verify_locations(cadata=generate_ca_bundle(hybrid_store=hybrid_store))

    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(MOZ_INTERMEDIATE_CIPHERS)
    ctx.verify_mode = ssl.CERT_REQUIRED

    try:
        ctx.hostname_checks_common_name = False
    except AttributeError:
        pass

    try:
        ctx.check_hostname = True
    except AttributeError:  # Defensive: very old 3.7 branch
        pass

    return ctx


__all__ = (
    "root_der_certificates",
    "root_pem_certificates",
    "generate_ca_bundle",
    "create_default_ssl_context",
    "register_ca",
    "set_cache_ttl",
    "DEFAULT_CACHE_TTL_SECONDS",
    "__version__",
    "VERSION",
)
