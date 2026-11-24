from __future__ import annotations

import asyncio
import platform
import socket
import sys
import typing
import warnings

from ._timeout import timeout
from ._gro import open_dgram_connection, DatagramReader, DatagramWriter

StandardTimeoutError = socket.timeout

try:
    from concurrent.futures import TimeoutError as FutureTimeoutError
except ImportError:
    FutureTimeoutError = TimeoutError  # type: ignore[misc]

try:
    AsyncioTimeoutError = asyncio.exceptions.TimeoutError
except AttributeError:
    AsyncioTimeoutError = TimeoutError  # type: ignore[misc]

if typing.TYPE_CHECKING:
    import ssl

    from typing_extensions import Literal

    from ..._typing import _TYPE_PEER_CERT_RET, _TYPE_PEER_CERT_RET_DICT


def _can_shutdown_and_close_selector_loop_bug() -> bool:
    import platform

    if platform.system() == "Windows" and platform.python_version_tuple()[:2] == (
        "3",
        "7",
    ):
        return int(platform.python_version_tuple()[-1]) >= 17

    return True


# Windows + asyncio bug where doing our shutdown procedure induce a crash
# in SelectorLoop
# File "C:\hostedtoolcache\windows\Python\3.7.9\x64\lib\selectors.py", line 314, in _select
#     r, w, x = select.select(r, w, w, timeout)
# [WinError 10038] An operation was attempted on something that is not a socket
_CPYTHON_SELECTOR_CLOSE_BUG_EXIST = _can_shutdown_and_close_selector_loop_bug() is False


class AsyncSocket:
    """
    This class is brought to add a level of abstraction to an asyncio transport (reader, or writer)
    We don't want to have two distinct code (async/sync) but rather a unified and easily verifiable
    code base.

    'ssa' stands for Simplified - Socket - Asynchronous.
    """

    def __init__(
        self,
        family: socket.AddressFamily = socket.AF_INET,
        type: socket.SocketKind = socket.SOCK_STREAM,
        proto: int = -1,
        fileno: int | None = None,
    ) -> None:
        self.family: socket.AddressFamily = family
        self.type: socket.SocketKind = type
        self.proto: int = proto
        self._fileno: int | None = fileno

        self._connect_called: bool = False
        self._established: asyncio.Event = asyncio.Event()

        # we do that every time to forward properly options / advanced settings
        self._sock: socket.socket = socket.socket(
            family=self.family, type=self.type, proto=self.proto, fileno=fileno
        )
        # set nonblocking / or cause the loop to block with dgram socket...
        self._sock.settimeout(0)

        self._writer: asyncio.StreamWriter | DatagramWriter | None = None
        self._reader: asyncio.StreamReader | DatagramReader | None = None

        self._writer_semaphore: asyncio.Semaphore = asyncio.Semaphore()
        self._reader_semaphore: asyncio.Semaphore = asyncio.Semaphore()

        self._addr: tuple[str, int] | tuple[str, int, int, int] | None = None

        self._external_timeout: float | int | None = None
        self._read_ready_hint = False
        self._tls_in_tls = False

    def fileno(self) -> int:
        return self._fileno if self._fileno is not None else self._sock.fileno()

    async def wait_for_close(self) -> None:
        if self._connect_called:
            return

        if self._writer is None:
            return

        try:
            # wait_closed can hang indefinitely!
            # on Python 3.8 and 3.9
            # there's some case where Python want an explicit EOT
            # (spoiler: it was a CPython bug) fixed in recent interpreters.
            # to circumvent this and still have a proper close
            # we enforce a maximum delay (1000ms).
            async with timeout(1):
                await self._writer.wait_closed()
        except OSError:
            pass

    def close(self) -> None:
        """The closing procedure is a real challenge. There's a ton of edge cases. Act carefully around this method."""
        if self._writer is not None:
            try:
                self._writer.close()
                try:
                    is_ssl = self._writer.get_extra_info("ssl_object") is not None
                except AttributeError:
                    is_ssl = False
                if is_ssl:
                    # TLS close() defers transport shutdown. Abort before the
                    # raw fd is released below, so another connection can reuse
                    # it without conflicting with an active asyncio transport.
                    self._writer.transport.abort()
            except AttributeError:  # Defensive: rare racing condition where transport is freed but writer isn't fully freed yet.
                self._connect_called = False
                self._established.clear()
                self._writer = None
                self._reader = None
                return  # see https://github.com/jawah/niquests/issues/368 to learn more

        edge_case_close_bug_exist = _CPYTHON_SELECTOR_CLOSE_BUG_EXIST

        # Windows + asyncio + asyncio.SelectorEventLoop limits us on how far
        # we can safely shutdown the socket.
        if not edge_case_close_bug_exist and platform.system() == "Windows":
            if hasattr(asyncio, "SelectorEventLoop") and isinstance(
                asyncio.get_running_loop(), asyncio.SelectorEventLoop
            ):
                edge_case_close_bug_exist = (
                    True  # Defensive: Windows SelectorEventLoop shutdown compatibility.
                )

        try:
            # see https://github.com/MagicStack/uvloop/issues/241
            # and https://github.com/jawah/niquests/issues/166
            # probably not just uvloop.
            uvloop_edge_case_bug = False

            # keep track of our clean exit procedure
            shutdown_called = False
            close_called = False

            if hasattr(self._sock, "shutdown"):
                try:
                    self._sock.shutdown(socket.SHUT_RD)
                    shutdown_called = True
                except TypeError:  # Defensive: we're not testing uvloop in CI
                    uvloop_edge_case_bug = True
                    # uvloop don't support shutdown! and sometime does not support close()...
                    # see https://github.com/jawah/niquests/issues/166 for ctx.
                    try:
                        self._sock.close()
                        close_called = True
                    except TypeError:
                        # last chance of releasing properly the underlying fd!
                        try:
                            direct_sock = socket.socket(fileno=self._sock.fileno())
                        except (OSError, ValueError):
                            pass
                        else:
                            try:
                                direct_sock.shutdown(socket.SHUT_RD)
                                shutdown_called = True
                            except OSError:
                                warnings.warn(
                                    (
                                        "urllib3-future is unable to properly close your async socket. "
                                        "This mean that you are probably using an asyncio implementation like uvloop "
                                        "that does not support shutdown() or/and close() on the socket transport. "
                                        "This will lead to unclosed socket (fd)."
                                    ),
                                    ResourceWarning,
                                )
                            finally:
                                direct_sock.detach()
            # we have to force call close() on our sock object (even after shutdown).
            # or we'll get a resource warning for sure!
            if isinstance(self._sock, socket.socket) and hasattr(self._sock, "close"):
                if not uvloop_edge_case_bug and not edge_case_close_bug_exist:
                    try:
                        self._sock.close()
                        close_called = True
                    except (
                        OSError,
                        TypeError,
                    ):  # Defensive: closing procedure full of surprises
                        pass

            if not close_called or not shutdown_called:
                # this branch detect whether we have an asyncio.TransportSocket instead of socket.socket.
                if hasattr(self._sock, "_sock") and not edge_case_close_bug_exist:
                    try:
                        self._sock._sock.close()
                    except (
                        AttributeError,
                        OSError,
                        TypeError,
                    ):  # Defensive: closing procedure full of surprises
                        pass

        except (
            OSError
        ):  # branch where we failed to connect and still try to release resource
            if isinstance(self._sock, socket.socket):
                try:
                    self._sock.close()  # don't call close on asyncio.TransportSocket
                except (
                    OSError,
                    TypeError,
                    AttributeError,
                ):  # Defensive: closing procedure full of surprises
                    pass
            elif hasattr(self._sock, "_sock") and not edge_case_close_bug_exist:
                try:
                    self._sock._sock.detach()
                except (
                    AttributeError,
                    OSError,
                    TypeError,
                ):  # Defensive: closing procedure full of surprises
                    pass

        self._connect_called = False
        self._established.clear()

    async def wait_for_readiness(self) -> None:
        await self._established.wait()

    if sys.platform == "win32":

        def ioctl(
            self, control: int, option: int | tuple[int, int, int] | bool
        ) -> None:
            return self._sock.ioctl(
                control, option
            )  # Defensive: platform-specific ioctl forwarding for direct socket consumers.

    def setsockopt(self, __level: int, __optname: int, __value: int | bytes) -> None:
        self._sock.setsockopt(__level, __optname, __value)

    @typing.overload
    def getsockopt(self, __level: int, __optname: int) -> int: ...

    @typing.overload
    def getsockopt(self, __level: int, __optname: int, buflen: int) -> bytes: ...

    def getsockopt(
        self, __level: int, __optname: int, buflen: int | None = None
    ) -> int | bytes:
        if buflen is None:
            return self._sock.getsockopt(__level, __optname)
        return self._sock.getsockopt(__level, __optname, buflen)

    def should_connect(self) -> bool:
        return self._connect_called is False

    async def connect(self, addr: tuple[str, int] | tuple[str, int, int, int]) -> None:
        if self._connect_called:
            raise OSError(
                "attempted to connect twice on a already established connection"
            )

        self._connect_called = True

        # there's a particularity on Windows
        # we must not forward non-IP in addr due to
        # a limitation in the network bridge used in asyncio
        if platform.system() == "Windows":
            from ..resolver.utils import is_ipv4, is_ipv6

            host, port = addr[:2]

            if not is_ipv4(host) and not is_ipv6(host):
                res = await asyncio.get_running_loop().getaddrinfo(
                    host,
                    port,
                    family=self.family,
                    type=self.type,
                )

                if (
                    not res
                ):  # Defensive: system resolution normally returns addresses or raises.
                    raise socket.gaierror(f"unable to resolve hostname {host}")

                addr = res[0][-1]

        if self._external_timeout is not None:
            try:
                async with timeout(self._external_timeout):
                    await asyncio.get_running_loop().sock_connect(self._sock, addr)
            except (FutureTimeoutError, AsyncioTimeoutError, TimeoutError) as e:
                self._connect_called = False
                raise StandardTimeoutError from e
            except RuntimeError:  # Defensive: FD allocation errors in alternate event-loop implementations.
                raise ConnectionError(
                    "Likely FD Kernel/Loop Racing Allocation Error. You should retry."
                )
        else:
            try:
                await asyncio.get_running_loop().sock_connect(self._sock, addr)
            except RuntimeError:  # Defensive: CPython might raise RuntimeError if there is a FD allocation error.
                raise ConnectionError(
                    "Likely FD Kernel/Loop Racing Allocation Error. You should retry."
                )

        if self.type == socket.SOCK_STREAM or self.type == -1:  # type: ignore[comparison-overlap]
            self._reader, self._writer = await asyncio.open_connection(sock=self._sock)
        elif self.type == socket.SOCK_DGRAM:
            self._reader, self._writer = await open_dgram_connection(sock=self._sock)

        # can become an asyncio.TransportSocket
        assert self._writer is not None
        self._sock = self._writer.get_extra_info("socket", self._sock)

        self._addr = addr
        self._established.set()

    async def wrap_socket(
        self,
        ctx: ssl.SSLContext,
        *,
        server_hostname: str | None = None,
        ssl_handshake_timeout: float | None = None,
    ) -> SSLAsyncSocket:
        await self._established.wait()
        self._established.clear()

        # only if Python <= 3.10
        try:
            setattr(
                asyncio.sslproto._SSLProtocolTransport,  # type: ignore[attr-defined]
                "_start_tls_compatible",
                True,
            )
        except AttributeError:  # Defensive: nonstandard asyncio implementations may omit the private TLS transport.
            pass

        # CPython < 3.11 bug: _SSLProtocolTransport lacks _force_close(),
        # but SSLProtocol._fatal_error() calls it during TLS-in-TLS
        # handshake failures. Backport the 3.11+ implementation.
        try:
            _ssl_tp = asyncio.sslproto._SSLProtocolTransport  # type: ignore[attr-defined]
            if not hasattr(_ssl_tp, "_force_close"):

                def _force_close(self, exc):  # type: ignore[no-untyped-def]
                    self._closed = True
                    if self._ssl_protocol is not None:
                        try:
                            self._ssl_protocol._abort(exc)
                        except TypeError:
                            # Python < 3.11: _abort() takes no arguments
                            self._ssl_protocol._abort()

                _ssl_tp._force_close = _force_close
        except AttributeError:  # Defensive: nonstandard asyncio implementations may omit the private TLS transport.
            pass

        if self.type == socket.SOCK_STREAM:
            assert self._writer is not None
            assert isinstance(self._writer, asyncio.StreamWriter)

            # below is hard to maintain. Starting with 3.11+, it is useless.
            protocol = self._writer._protocol  # type: ignore[attr-defined]
            await self._writer.drain()

            new_transport = await self._writer._loop.start_tls(  # type: ignore[attr-defined]
                self._writer._transport,  # type: ignore[attr-defined]
                protocol,
                ctx,
                server_side=False,
                server_hostname=server_hostname,
                ssl_handshake_timeout=ssl_handshake_timeout,
            )

            if new_transport is None:
                # Most likely Python < 3.11 only.
                # https://github.com/jawah/niquests/issues/383
                if self._tls_in_tls:
                    raise OSError(
                        "Asyncio TLS-in-TLS failed. The transport failed silently during inner TLS handshake."
                    )
                raise OSError(
                    "Asyncio start TLS failed. The transport failed silently during TLS handshake."
                )

            self._writer._transport = new_transport  # type: ignore[attr-defined]

            transport = self._writer.transport
            protocol._stream_writer = self._writer
            protocol._transport = transport
            protocol._over_ssl = transport.get_extra_info("sslcontext") is not None

            self._tls_ctx = ctx
        else:
            raise RuntimeError("Unsupported socket type")  # Defensive: unreachable

        self._established.set()
        self.__class__ = SSLAsyncSocket

        return self  # type: ignore[return-value]

    def read_ready(self) -> bool:
        reader = self._reader
        if isinstance(reader, DatagramReader):
            return bool(reader._buffer or reader._exception or reader.at_eof())
        if not isinstance(reader, asyncio.StreamReader):
            raise OSError("Readiness requires a connected stream")
        ready = bool(
            getattr(reader, "_buffer") or reader.exception() or reader.at_eof()
        )
        self._read_ready_hint = ready
        return ready

    async def until_data_available(self, remaining: float | None = None) -> None:
        if remaining is None:
            remaining = self._external_timeout
        reader = self._reader
        if not isinstance(reader, asyncio.StreamReader):
            raise OSError("Readiness requires a connected stream")
        async with self._reader_semaphore:
            if reader.exception() is not None:
                raise reader.exception()
            if getattr(reader, "_buffer") or reader.at_eof():
                self._read_ready_hint = True
                return
            try:
                async with timeout(remaining):
                    await getattr(reader, "_wait_for_data")("until_data_available")
            except (FutureTimeoutError, AsyncioTimeoutError, TimeoutError) as exc:
                raise StandardTimeoutError from exc
            self._read_ready_hint = True

    async def recv(self, size: int = -1) -> bytes | list[bytes]:
        """Receive data from the socket.

        Returns ``bytes`` for a single datagram (or stream chunk), or
        ``list[bytes]`` when GRO / batch-receive delivered multiple
        coalesced datagrams in one syscall.  The caller can then feed
        all segments to the QUIC state-machine in a tight loop before
        probing, avoiding per-datagram overhead."""
        if size == -1:
            size = 65536
        assert self._reader is not None

        if not self._established.is_set():
            await self._established.wait()
        await self._reader_semaphore.acquire()

        try:
            if self._external_timeout is not None:
                try:
                    if self._read_ready_hint:
                        self._read_ready_hint = False
                        # Only readiness users opt into this path. Recheck after
                        # acquiring the semaphore; an earlier reader may have
                        # consumed the bytes. A positive read on the standard
                        # StreamReader cannot suspend when it has bytes or EOF.
                        if (
                            type(self._reader) is asyncio.StreamReader
                            and size > 0
                            and (
                                getattr(self._reader, "_buffer")
                                or self._reader.at_eof()
                            )
                        ):
                            return await self._reader.read(n=size)
                    async with timeout(self._external_timeout):
                        return await self._reader.read(n=size)
                except (FutureTimeoutError, AsyncioTimeoutError, TimeoutError) as e:
                    raise StandardTimeoutError from e
                except OSError as e:  # Defensive: treat any OSError as ConnReset!
                    raise ConnectionResetError() from e
            return await self._reader.read(n=size)
        finally:
            self._reader_semaphore.release()

    async def read_exact(self, size: int = -1) -> bytes | list[bytes]:
        """Just an alias for recv(), it is needed due to our custom AsyncSocks override."""
        return await self.recv(size=size)

    async def read(self) -> bytes | list[bytes]:
        """Just an alias for recv(), it is needed due to our custom AsyncSocks override."""
        return await self.recv()

    async def sendall(self, data: bytes | bytearray | memoryview | list[bytes]) -> None:
        assert self._writer is not None
        await self._established.wait()
        await self._writer_semaphore.acquire()
        try:
            self._writer.write(data)  # type: ignore[arg-type]
            await self._writer.drain()
        finally:
            self._writer_semaphore.release()

    async def write_all(
        self, data: bytes | bytearray | memoryview | list[bytes]
    ) -> None:
        """Just an alias for sendall(), it is needed due to our custom AsyncSocks override."""
        await self.sendall(data)

    async def send(self, data: bytes | bytearray | memoryview | list[bytes]) -> None:
        await self.sendall(data)

    def settimeout(self, __value: float | None = None) -> None:
        self._external_timeout = __value

    def gettimeout(self) -> float | None:
        return self._external_timeout

    def getpeername(self) -> tuple[str, int]:
        return self._sock.getpeername()  # type: ignore[no-any-return]

    def bind(self, addr: tuple[str, int]) -> None:
        self._sock.bind(addr)


class SSLAsyncSocket(AsyncSocket):
    _tls_ctx: ssl.SSLContext
    _tls_in_tls: bool

    @typing.overload
    def getpeercert(
        self, binary_form: Literal[False] = ...
    ) -> _TYPE_PEER_CERT_RET_DICT | None: ...

    @typing.overload
    def getpeercert(self, binary_form: Literal[True]) -> bytes | None: ...

    def getpeercert(self, binary_form: bool = False) -> _TYPE_PEER_CERT_RET:
        return self.sslobj.getpeercert(binary_form=binary_form)  # type: ignore[return-value]

    def selected_alpn_protocol(self) -> str | None:
        return self.sslobj.selected_alpn_protocol()

    @property
    def sslobj(self) -> ssl.SSLSocket | ssl.SSLObject:
        if self._writer is not None:
            sslobj: ssl.SSLSocket | ssl.SSLObject | None = self._writer.get_extra_info(
                "ssl_object"
            )

            if sslobj is not None:
                return sslobj

        raise RuntimeError(  # Defensive: unreachable
            '"ssl_object" could not be extracted from this SslAsyncSock instance'
        )

    def version(self) -> str | None:
        return self.sslobj.version()

    @property
    def context(self) -> ssl.SSLContext:
        return self.sslobj.context

    @property
    def _sslobj(self) -> ssl.SSLSocket | ssl.SSLObject:
        return self.sslobj

    def cipher(self) -> tuple[str, str, int] | None:
        return self.sslobj.cipher()

    async def wrap_socket(
        self,
        ctx: ssl.SSLContext,
        *,
        server_hostname: str | None = None,
        ssl_handshake_timeout: float | None = None,
    ) -> SSLAsyncSocket:
        self._tls_in_tls = True

        return await super().wrap_socket(
            ctx,
            server_hostname=server_hostname,
            ssl_handshake_timeout=ssl_handshake_timeout,
        )


def _has_complete_support_dgram() -> bool:
    """A bug exist in PyPy asyncio implementation that prevent us to use a DGRAM socket.
    This piece of code inform us, potentially, if PyPy has fixed the winapi implementation.
    See https://github.com/pypy/pypy/issues/4008 and https://github.com/jawah/niquests/pull/87

    The stacktrace look as follows:
    File "C:\\hostedtoolcache\\windows\\PyPy\3.10.13\x86\\Lib\asyncio\\windows_events.py", line 594, in connect
    _overlapped.WSAConnect(conn.fileno(), address)
        AttributeError: module '_overlapped' has no attribute 'WSAConnect'
    """
    import platform

    if (
        platform.system() == "Windows" and platform.python_implementation() == "PyPy"
    ):  # Defensive: Windows PyPy winapi capability compatibility.
        try:
            import _overlapped  # type: ignore[import-not-found]
        except ImportError:  # Defensive:
            return False

        if hasattr(_overlapped, "WSAConnect"):
            return True

        return False

    return True


__all__ = (
    "AsyncSocket",
    "SSLAsyncSocket",
    "_has_complete_support_dgram",
)
