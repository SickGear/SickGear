from __future__ import annotations

import typing
from io import UnsupportedOperation

if typing.TYPE_CHECKING:
    import ssl

try:
    from ._ctypes import load_cert_chain as _ctypes_load_cert_chain
except ImportError:  # Defensive: Python not built with ctype extension.

    def _ctypes_load_cert_chain(*args, **kwargs):  # type: ignore[no-untyped-def,misc]
        raise UnsupportedOperation("ctypes not available")


from ._shm import load_cert_chain as _shm_load_cert_chain
from ._fifo import load_cert_chain as _fifo_load_cert_chain

SUPPORTED_METHODS: list[
    typing.Callable[
        [
            ssl.SSLContext,
            bytes | str,
            bytes | str,
            bytes | str | typing.Callable[[], str | bytes] | None,
        ],
        None,
    ]
] = [
    _ctypes_load_cert_chain,
    _shm_load_cert_chain,
    _fifo_load_cert_chain,  # MacOS last resort(...)
]


def load_cert_chain(
    ctx: ssl.SSLContext,
    certdata: bytes | str,
    keydata: bytes | str,
    password: bytes | str | typing.Callable[[], str | bytes] | None = None,
) -> None:
    """
    Unique workaround the known limitation of CPython inability to initialize the mTLS context without files.
    :raise UnsupportedOperation: If anything goes wrong in the process.
    """
    err = None

    for supported in SUPPORTED_METHODS:
        try:
            supported(
                ctx,
                certdata,
                keydata,
                password,
            )
            return
        except UnsupportedOperation as e:
            if err is None:
                err = e

    if err is not None:
        raise err

    raise UnsupportedOperation("unable to initialize mTLS using in-memory cert and key")


__all__ = ("load_cert_chain",)
