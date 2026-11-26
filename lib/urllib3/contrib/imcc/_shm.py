from __future__ import annotations

import os
import secrets
import stat
import sys
import typing
import warnings
from hashlib import sha256
from io import UnsupportedOperation

if typing.TYPE_CHECKING:
    import ssl


def load_cert_chain(
    ctx: ssl.SSLContext,
    certdata: str | bytes,
    keydata: str | bytes | None = None,
    password: typing.Callable[[], str | bytes] | str | bytes | None = None,
) -> None:
    """
    Unique workaround the known limitation of CPython inability to initialize the mTLS context without files.
    Only supported on Linux, FreeBSD, and OpenBSD.
    :raise UnsupportedOperation: If anything goes wrong in the process.
    """
    if (
        sys.platform != "linux"
        and sys.platform.startswith("freebsd") is False
        and sys.platform.startswith("openbsd") is False
    ):
        raise UnsupportedOperation(
            f"Unable to provide support for in-memory client certificate: Unsupported platform {sys.platform}"
        )

    unique_name: str = f"{sha256(secrets.token_bytes(32)).hexdigest()}.pem"

    if isinstance(certdata, bytes):
        certdata = certdata.decode("ascii")

    if keydata is not None:
        if isinstance(keydata, bytes):
            keydata = keydata.decode("ascii")

    if hasattr(os, "memfd_create"):
        fd = os.memfd_create(unique_name, os.MFD_CLOEXEC)
    else:
        # this branch patch is for CPython <3.8 and PyPy 3.7+
        try:
            from ctypes import (
                c_int,
                c_ushort,
                cdll,
                create_string_buffer,
                get_errno,
                util,
            )
        except ImportError as e:  # Defensive: Python built without ctypes.
            raise UnsupportedOperation(
                "Unable to provide support for in-memory client certificate: "
                "ctypes is not available."
            ) from e

        loc = util.find_library("rt") or util.find_library("c")

        if not loc:
            raise UnsupportedOperation(  # Defensive: no usable system shared-memory library was found.
                "Unable to provide support for in-memory client certificate: libc or librt not found."
            )

        lib = cdll.LoadLibrary(loc)

        _shm_open = lib.shm_open
        # _shm_unlink = lib.shm_unlink

        buf_name = create_string_buffer(unique_name.encode())

        try:
            fd = _shm_open(
                buf_name,
                c_int(os.O_RDWR | os.O_CREAT),
                c_ushort(stat.S_IRUSR | stat.S_IWUSR),
            )
        except SystemError as e:
            raise UnsupportedOperation(
                f"Unable to provide support for in-memory client certificate: {e}"
            )

        if fd == -1:
            raise UnsupportedOperation(  # Defensive: the OS could not create the shared-memory object.
                f"Unable to provide support for in-memory client certificate: {os.strerror(get_errno())}"
            )

    # Linux 3.17+
    path = f"/proc/self/fd/{fd}"

    # Alt-path
    shm_path = f"/dev/shm/{unique_name}"

    if os.path.exists(path) is False:
        if os.path.exists(shm_path):
            path = shm_path
        else:  # Defensive: neither filesystem exposes the allocated shared-memory object.
            os.fdopen(fd).close()

            raise UnsupportedOperation(
                "Unable to provide support for in-memory client certificate: no virtual patch available?"
            )

    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    with open(path, "w") as fp:
        fp.write(certdata)

        if keydata:
            fp.write(keydata)

        path = fp.name

    ctx.load_cert_chain(path, password=password)

    # we shall start cleaning remnants
    os.fdopen(fd).close()

    if os.path.exists(shm_path):
        os.unlink(shm_path)

    if os.path.exists(path) or os.path.exists(shm_path):
        warnings.warn(  # Defensive: unexpected remnants after closing and unlinking shared memory.
            "In-memory client certificate: The kernel leaked a file descriptor outside of its expected lifetime.",
            ResourceWarning,
        )


__all__ = ("load_cert_chain",)
