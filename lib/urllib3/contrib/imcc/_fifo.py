from __future__ import annotations

import os
import stat
import tempfile
import threading
import typing
from io import UnsupportedOperation

if typing.TYPE_CHECKING:
    import ssl


def load_cert_chain(
    ctx: ssl.SSLContext,
    certdata: str | bytes,
    keydata: str | bytes | None = None,
    password: typing.Callable[[], str | bytes] | str | bytes | None = None,
) -> None:
    """Load cert chain using named pipes (FIFOs) instead of shm (linux).

    Creates temporary FIFOs, feeds PEM data through background threads,
    and lets ssl.SSLContext.load_cert_chain read from them. Data flows
    through kernel pipe buffers without ever touching disk.

    A single FIFO would deadlock on the second open.

    The idea came from https://github.com/jawah/urllib3.future/issues/325#issuecomment-4069433443

    :raise UnsupportedOperation: If anything goes wrong in the process.
    """
    if not hasattr(os, "mkfifo"):
        raise UnsupportedOperation(
            "Unable to provide support for in-memory client certificate: "
            "os.mkfifo is not available on this platform."
        )

    if isinstance(certdata, str):
        certdata = certdata.encode("ascii")
    if keydata is not None and isinstance(keydata, str):
        keydata = keydata.encode("ascii")

    tmpdir = tempfile.mkdtemp(prefix="urllib3_imcc_")
    cert_fifo = os.path.join(tmpdir, "cert.fifo")
    key_fifo = os.path.join(tmpdir, "key.fifo") if keydata is not None else None

    try:
        os.mkfifo(cert_fifo, stat.S_IRUSR | stat.S_IWUSR)

        if key_fifo is not None:
            os.mkfifo(key_fifo, stat.S_IRUSR | stat.S_IWUSR)

        writer_exc: BaseException | None = None

        def _write_fifo(path: str, data: bytes) -> None:
            nonlocal writer_exc
            try:
                with open(path, "wb") as f:
                    f.write(data)
            except BaseException as e:  # Defensive: host FIFO write failure.
                writer_exc = e

        cert_thread = threading.Thread(
            target=_write_fifo, args=(cert_fifo, certdata), daemon=True
        )
        cert_thread.start()

        key_thread: threading.Thread | None = None

        if key_fifo is not None and keydata is not None:
            key_thread = threading.Thread(
                target=_write_fifo, args=(key_fifo, keydata), daemon=True
            )
            key_thread.start()

        ctx.load_cert_chain(cert_fifo, keyfile=key_fifo, password=password)

        cert_thread.join(timeout=1.0)

        if key_thread is not None:
            key_thread.join(timeout=1.0)

        if writer_exc is not None:  # Defensive: report the guarded writer failure.
            raise UnsupportedOperation(
                "Unable to provide support for in-memory client certificate: "
                f"FIFO writer failed: {writer_exc}"
            )
    finally:
        for p in (cert_fifo, key_fifo):
            if p is not None:
                try:
                    os.unlink(p)
                except OSError:  # Defensive:
                    pass
        try:
            os.rmdir(tmpdir)
        except OSError:  # Defensive:
            pass
