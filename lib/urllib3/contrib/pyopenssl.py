from __future__ import annotations

import warnings

warnings.warn(
    (
        "'urllib3.contrib.pyopenssl' module has been removed in urllib3.future due to incompatibilities "
        "with our QUIC integration. While the import proceed without error for your convenience, it is rendered "
        "completely ineffective. Were you looking for in-memory client certificate? "
        "See https://urllib3future.readthedocs.io/en/latest/advanced-usage.html#in-memory-client-mtls-certificate"
    ),
    category=DeprecationWarning,
    stacklevel=2,
)

import OpenSSL.SSL  # type: ignore  # noqa

__all__ = ["inject_into_urllib3", "extract_from_urllib3"]


def inject_into_urllib3() -> None:
    """Kept for BC-purposes."""
    ...


def extract_from_urllib3() -> None:
    """Kept for BC-purposes."""
    ...
