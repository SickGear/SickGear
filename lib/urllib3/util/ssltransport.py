from __future__ import annotations

import socket
import sys
import typing

from ..contrib.anytls import ssl
from ..contrib.anytls import (
    stdlib_ssl as _stdlib_ssl,
)  # Always import stdlib ssl for exception compatibility

from .._constant import DEFAULT_BLOCKSIZE
from ..exceptions import ProxySchemeUnsupported

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from .._typing import _TYPE_PEER_CERT_RET, _TYPE_PEER_CERT_RET_DICT


_SelfT = typing.TypeVar("_SelfT", bound="SSLTransport")
_WriteBuffer = typing.Union[bytearray, memoryview]
_ReturnValue = typing.TypeVar("_ReturnValue")


class SSLTransport:
    """
    The SSLTransport wraps an existing socket and establishes an SSL connection.

    Contrary to Python's implementation of SSLSocket, it allows you to chain
    multiple TLS connections together. It's particularly useful if you need to
    implement TLS within TLS.

    The class supports most of the socket API operations.
    """

    @staticmethod
    def _validate_ssl_context_for_tls_in_tls(ssl_context: ssl.SSLContext) -> None:
        """
        Raises a ProxySchemeUnsupported if the provided ssl_context can't be used
        for TLS in TLS.

        The only requirement is that the ssl_context provides the 'wrap_bio'
        methods.
        """

        if not hasattr(ssl_context, "wrap_bio"):
            raise ProxySchemeUnsupported(
                "TLS in TLS requires SSLContext.wrap_bio() which isn't "
                "available on non-native SSLContext"
            )

    def __init__(
        self,
        socket: socket.socket,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        suppress_ragged_eofs: bool = True,
    ) -> None:
        """
        Create an SSLTransport around socket using the provided ssl_context.
        """
        self.suppress_ragged_eofs = suppress_ragged_eofs
        self.socket = socket

        # Determine the correct MemoryBIO to use.  When a non-stdlib backend
        # (rtls/utls) is the default ``ssl`` but the caller passes a stdlib
        # SSLContext (or vice-versa), wrap_bio() will reject a foreign
        # MemoryBIO with a TypeError. Try the default ``ssl`` first, then
        # fall back to ``_stdlib_ssl``.
        _bio_factories: list[type[ssl.MemoryBIO]] = [ssl.MemoryBIO]
        if _stdlib_ssl is not None:
            _bio_factories.append(_stdlib_ssl.MemoryBIO)
        _bio_factories = list(dict.fromkeys(_bio_factories))
        for _MemoryBIO in _bio_factories:
            self.incoming: ssl.MemoryBIO = _MemoryBIO()
            self.outgoing: ssl.MemoryBIO = _MemoryBIO()
            try:
                self.sslobj: ssl.SSLObject = ssl_context.wrap_bio(
                    self.incoming, self.outgoing, server_hostname=server_hostname
                )
                self._ssl_module = ssl if _MemoryBIO is ssl.MemoryBIO else _stdlib_ssl
                break
            except TypeError:
                continue
        else:
            raise TypeError(
                "SSLTransport could not find a compatible MemoryBIO for "
                f"the provided ssl_context ({type(ssl_context)})"
            )

        # Perform initial handshake.
        self._ssl_io_loop(self.sslobj.do_handshake)

    def __enter__(self: _SelfT) -> _SelfT:
        return self

    def __exit__(self, *_: typing.Any) -> None:
        self.close()

    def fileno(self) -> int:
        return self.socket.fileno()

    @property
    def type(self) -> socket.SocketKind:
        return self.socket.type

    def read(self, len: int = 1024, buffer: typing.Any | None = None) -> int | bytes:
        return self._wrap_ssl_read(len, buffer)

    def recv(self, buflen: int = 1024, flags: int = 0) -> int | bytes:
        if flags != 0:
            raise ValueError("non-zero flags not allowed in calls to recv")
        return self._wrap_ssl_read(buflen)

    def recv_into(
        self,
        buffer: _WriteBuffer,
        nbytes: int | None = None,
        flags: int = 0,
    ) -> None | int | bytes:
        if flags != 0:
            raise ValueError("non-zero flags not allowed in calls to recv_into")
        if nbytes is None:
            nbytes = len(buffer)
        return self.read(nbytes, buffer)

    def sendall(self, data: bytes, flags: int = 0) -> None:
        if flags != 0:
            raise ValueError("non-zero flags not allowed in calls to sendall")
        count = 0
        with memoryview(data) as view, view.cast("B") as byte_view:
            amount = len(byte_view)
            while count < amount:
                v = self.send(byte_view[count:])
                count += v

    def send(self, data: bytes, flags: int = 0) -> int:
        if flags != 0:
            raise ValueError("non-zero flags not allowed in calls to send")
        return self._ssl_io_loop(self.sslobj.write, data)

    def unwrap(self) -> None:
        self._ssl_io_loop(self.sslobj.unwrap)

    def close(self) -> None:
        self.socket.close()

    @typing.overload
    def getpeercert(
        self, binary_form: Literal[False] = ...
    ) -> _TYPE_PEER_CERT_RET_DICT | None: ...

    @typing.overload
    def getpeercert(self, binary_form: Literal[True]) -> bytes | None: ...

    def getpeercert(self, binary_form: bool = False) -> _TYPE_PEER_CERT_RET:
        return self.sslobj.getpeercert(binary_form)  # type: ignore[return-value]

    def version(self) -> str | None:
        return self.sslobj.version()

    def cipher(self) -> tuple[str, str, int] | None:
        return self.sslobj.cipher()

    @property
    def context(self) -> ssl.SSLContext:
        return self.sslobj.context

    def selected_alpn_protocol(self) -> str | None:
        return self.sslobj.selected_alpn_protocol()

    def selected_npn_protocol(self) -> str | None:
        return self.sslobj.selected_npn_protocol()

    def shared_ciphers(self) -> list[tuple[str, str, int]] | None:
        return self.sslobj.shared_ciphers()

    def compression(self) -> str | None:
        return self.sslobj.compression()

    def settimeout(self, value: float | None) -> None:
        self.socket.settimeout(value)

    def gettimeout(self) -> float | None:
        return self.socket.gettimeout()

    if sys.platform == "win32":

        def ioctl(
            self, control: int, option: int | tuple[int, int, int] | bool
        ) -> None:
            return self.socket.ioctl(control, option)

    def setsockopt(self, __level: int, __optname: int, __value: int | bytes) -> None:
        self.socket.setsockopt(__level, __optname, __value)

    @typing.overload
    def getsockopt(self, __level: int, __optname: int) -> int: ...

    @typing.overload
    def getsockopt(self, __level: int, __optname: int, buflen: int) -> bytes: ...

    def getsockopt(
        self, __level: int, __optname: int, buflen: int | None = None
    ) -> int | bytes:
        if buflen is None:
            return self.socket.getsockopt(__level, __optname)
        return self.socket.getsockopt(__level, __optname, buflen)

    def _decref_socketios(self) -> None:  # Defensive: SocketIO compatibility.
        self.socket._decref_socketios()  # type: ignore[attr-defined]

    def _wrap_ssl_read(self, len: int, buffer: bytearray | None = None) -> int | bytes:
        try:
            return self._ssl_io_loop(self.sslobj.read, len, buffer)
        except _stdlib_ssl.SSLError as e:
            if e.errno == _stdlib_ssl.SSL_ERROR_EOF and self.suppress_ragged_eofs:
                return 0  # eof, return 0.
            else:
                raise

    # func is sslobj.do_handshake or sslobj.unwrap
    @typing.overload
    def _ssl_io_loop(self, func: typing.Callable[[], None]) -> None: ...

    # func is sslobj.write, arg1 is data
    @typing.overload
    def _ssl_io_loop(self, func: typing.Callable[[bytes], int], arg1: bytes) -> int: ...

    # func is sslobj.read, arg1 is len, arg2 is buffer
    @typing.overload
    def _ssl_io_loop(
        self,
        func: typing.Callable[[int, bytearray | None], bytes],
        arg1: int,
        arg2: bytearray | None,
    ) -> bytes: ...

    def _ssl_io_loop(
        self,
        func: typing.Callable[..., _ReturnValue],
        arg1: None | bytes | int = None,
        arg2: bytearray | None = None,
    ) -> _ReturnValue:
        """Performs an I/O loop between incoming/outgoing and the socket."""
        should_loop = True
        ret = None

        while should_loop:
            ssl_module = self._ssl_module
            assert ssl_module is not None
            want_read: bool | None = None
            try:
                if arg1 is None and arg2 is None:
                    ret = func()
                elif arg2 is None:
                    ret = func(arg1)
                else:
                    ret = func(arg1, arg2)
            except ssl_module.SSLWantReadError:
                want_read = True
            except ssl_module.SSLWantWriteError:
                want_read = False  # Defensive: MemoryBIO output grows on demand; retain for alternate TLS backends.

            buf = self.outgoing.read()
            self.socket.sendall(buf)

            if want_read is None:
                should_loop = False
            elif want_read:
                buf = self.socket.recv(DEFAULT_BLOCKSIZE)
                if buf:
                    self.incoming.write(buf)
                else:
                    self.incoming.write_eof()
        return typing.cast(_ReturnValue, ret)
