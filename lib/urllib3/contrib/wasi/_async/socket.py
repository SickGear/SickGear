"""Native asynchronous socket facade for WASI Preview 3."""

from __future__ import annotations

import errno
import ipaddress
import socket as _stdlib_socket
import sys
from typing import Any

if sys.platform == "wasi":
    import asyncio

    import componentize_py_async_support
    import wit_world
    from componentize_py_types import Err
    from wit_world.imports import wasi_sockets_types as _wasi_sockets

    from ...anytls import ssl as _tls

    try:
        from wit_world.imports import (
            wasi_sockets_ip_name_lookup_0_3_0 as _wasi_ip_name_lookup,
        )
    except ImportError:
        from wit_world.imports import ip_name_lookup as _wasi_ip_name_lookup

        if not hasattr(_wasi_ip_name_lookup, "ErrorCode_NameUnresolvable"):
            raise ImportError("wasi:sockets/ip-name-lookup@0.3.0 is required")

    def _gaierror(error: Any) -> OSError:
        if isinstance(error, _wasi_ip_name_lookup.ErrorCode_NameUnresolvable):
            code = _stdlib_socket.EAI_NONAME
        elif isinstance(error, _wasi_ip_name_lookup.ErrorCode_TemporaryResolverFailure):
            # Wasmtime 47 collapses lookup failures to name-unresolvable.
            code = _stdlib_socket.EAI_AGAIN  # Defensive: WASI spec compatibility.
        else:
            code = _stdlib_socket.EAI_FAIL
        return _stdlib_socket.gaierror(code, type(error).__name__)

    def _socket_error(error: Any) -> OSError:
        if isinstance(error, _wasi_sockets.ErrorCode_ConnectionRefused):
            return ConnectionRefusedError(errno.ECONNREFUSED, "connection refused")
        if isinstance(error, _wasi_sockets.ErrorCode_ConnectionReset):
            return ConnectionResetError(
                errno.ECONNRESET, "connection reset"
            )  # Defensive: WASI host-specific error mapping.
        if isinstance(error, _wasi_sockets.ErrorCode_ConnectionAborted):
            return ConnectionAbortedError(
                errno.ECONNABORTED, "connection aborted"
            )  # Defensive: WASI host-specific error mapping.
        if isinstance(error, _wasi_sockets.ErrorCode_Timeout):
            return TimeoutError(
                "operation timed out"
            )  # Defensive: WASI host-specific error mapping.
        if isinstance(error, _wasi_sockets.ErrorCode_AccessDenied):
            return PermissionError(errno.EACCES, "network access denied")
        return OSError(errno.EIO, type(error).__name__)

    def _wasi_socket_address(address: tuple[Any, ...]) -> _wasi_sockets.IpSocketAddress:
        ip = ipaddress.ip_address(address[0])
        port = int(address[1])
        if isinstance(ip, ipaddress.IPv4Address):
            return _wasi_sockets.IpSocketAddress_Ipv4(
                _wasi_sockets.Ipv4SocketAddress(port=port, address=tuple(ip.packed))
            )
        packed = ip.packed
        return _wasi_sockets.IpSocketAddress_Ipv6(
            _wasi_sockets.Ipv6SocketAddress(
                port=port,
                flow_info=int(address[2]) if len(address) > 2 else 0,
                address=tuple(
                    int.from_bytes(packed[index : index + 2], "big")
                    for index in range(0, 16, 2)
                ),
                scope_id=int(address[3]) if len(address) > 3 else 0,
            )
        )

    def _python_socket_address(
        address: _wasi_sockets.IpSocketAddress,
    ) -> tuple[str, int] | tuple[str, int, int, int]:
        if isinstance(address, _wasi_sockets.IpSocketAddress_Ipv4):
            value = address.value
            return str(ipaddress.IPv4Address(bytes(value.address))), value.port
        value = address.value
        packed = b"".join(part.to_bytes(2, "big") for part in value.address)
        return (
            str(ipaddress.IPv6Address(packed)),
            value.port,
            value.flow_info,
            value.scope_id,
        )

    async def _resolve_host(
        host: str,
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass

        try:
            resolved = await _wasi_ip_name_lookup.resolve_addresses(host)
        except Err as error:
            raise _gaierror(error.value) from None

        addresses = []
        for address in resolved:
            if isinstance(address, _wasi_sockets.IpAddress_Ipv4):
                addresses.append(ipaddress.IPv4Address(bytes(address.value)))
            else:
                packed = b"".join(part.to_bytes(2, "big") for part in address.value)
                addresses.append(ipaddress.IPv6Address(packed))
        return addresses

    def _coerce_port(port: bytes | str | int | None, socket_type: int) -> int:
        if port is None:
            return 0
        if isinstance(port, bytes):
            port = port.decode("ascii")
        if isinstance(port, str):
            if port.isdigit():
                return int(port)
            protocol = "udp" if socket_type == _stdlib_socket.SOCK_DGRAM else "tcp"
            return _stdlib_socket.getservbyname(port, protocol)
        return int(port)

    async def getaddrinfo(
        host: bytes | str | None,
        port: bytes | str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[
        tuple[
            _stdlib_socket.AddressFamily,
            _stdlib_socket.SocketKind,
            int,
            str,
            tuple[Any, ...],
        ]
    ]:
        if isinstance(host, bytes):
            host = host.decode("ascii")

        if host is None:
            addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            if family in (0, _stdlib_socket.AF_UNSPEC, _stdlib_socket.AF_INET6):
                addresses.append(
                    ipaddress.IPv6Address(
                        "::" if flags & _stdlib_socket.AI_PASSIVE else "::1"
                    )
                )
            if family in (0, _stdlib_socket.AF_UNSPEC, _stdlib_socket.AF_INET):
                addresses.append(
                    ipaddress.IPv4Address(
                        "0.0.0.0" if flags & _stdlib_socket.AI_PASSIVE else "127.0.0.1"
                    )
                )
            hostname = ""
        else:
            hostname = host
            if flags & _stdlib_socket.AI_NUMERICHOST:
                try:
                    addresses = [ipaddress.ip_address(host)]
                except ValueError:
                    raise _stdlib_socket.gaierror(
                        _stdlib_socket.EAI_NONAME, "name or service not known"
                    ) from None
            else:
                addresses = await _resolve_host(host)

        socket_types: list[tuple[int, int]]
        if type == 0:
            socket_types = [
                (_stdlib_socket.SOCK_STREAM, _stdlib_socket.IPPROTO_TCP),
                (_stdlib_socket.SOCK_DGRAM, _stdlib_socket.IPPROTO_UDP),
            ]
        elif type == _stdlib_socket.SOCK_STREAM:
            socket_types = [
                (_stdlib_socket.SOCK_STREAM, proto or _stdlib_socket.IPPROTO_TCP)
            ]
        elif type == _stdlib_socket.SOCK_DGRAM:
            socket_types = [
                (_stdlib_socket.SOCK_DGRAM, proto or _stdlib_socket.IPPROTO_UDP)
            ]
        else:
            socket_types = [(type, proto)]

        results = []
        for address in addresses:
            address_family = (
                _stdlib_socket.AF_INET
                if address.version == 4
                else _stdlib_socket.AF_INET6
            )
            if family not in (0, _stdlib_socket.AF_UNSPEC, address_family):
                continue
            for socket_type, socket_proto in socket_types:
                resolved_port = _coerce_port(port, socket_type)
                sockaddr: tuple[Any, ...]
                if address_family == _stdlib_socket.AF_INET:
                    sockaddr = (str(address), resolved_port)
                else:
                    sockaddr = (str(address), resolved_port, 0, 0)
                canonname = (
                    hostname
                    if flags & _stdlib_socket.AI_CANONNAME and not results
                    else ""
                )
                results.append(
                    (
                        _stdlib_socket.AddressFamily(address_family),
                        _stdlib_socket.SocketKind(socket_type),
                        socket_proto,
                        canonname,
                        sockaddr,
                    )
                )

        if not results:
            raise _stdlib_socket.gaierror(
                _stdlib_socket.EAI_NONAME, "name or service not known"
            )
        return results

    class AsyncSocket:
        """TCP socket backed by native WASI Preview 3 async resources."""

        def __init__(
            self,
            family: _stdlib_socket.AddressFamily = _stdlib_socket.AF_INET,
            type: _stdlib_socket.SocketKind = _stdlib_socket.SOCK_STREAM,
            proto: int = -1,
            fileno: int | None = None,
        ) -> None:
            if fileno is not None:
                raise NotImplementedError("WASI sockets do not expose file descriptors")
            if type != _stdlib_socket.SOCK_STREAM:
                raise OSError(errno.EPROTONOSUPPORT, "only TCP sockets are supported")
            if family not in (_stdlib_socket.AF_INET, _stdlib_socket.AF_INET6):
                raise OSError(errno.EAFNOSUPPORT, "address family not supported")

            address_family = (
                _wasi_sockets.IpAddressFamily.IPV4
                if family == _stdlib_socket.AF_INET
                else _wasi_sockets.IpAddressFamily.IPV6
            )
            try:
                self._socket = _wasi_sockets.TcpSocket.create(address_family)
            except Err as error:  # Defensive: WASI host socket-allocation failure.
                raise _socket_error(error.value) from None

            self.family = family
            self.type = type
            self.proto = proto if proto >= 0 else _stdlib_socket.IPPROTO_TCP
            self._reader: Any | None = None
            self._writer: Any | None = None
            self._read_buffer = b""
            self._send_error: OSError | None = None
            self._receive_error: OSError | None = None
            self._connected = False
            self._closed = False
            self._timeout: float | int | None = None

        async def _watch_send(self, future: Any) -> None:
            result = await future.read()
            if isinstance(
                result, Err
            ):  # Defensive: host stream failures depend on component-runtime scheduling.
                self._send_error = _socket_error(result.value)

        async def _watch_receive(self, future: Any) -> None:
            result = await future.read()
            if isinstance(
                result, Err
            ):  # Defensive: host stream failures depend on component-runtime scheduling.
                self._receive_error = _socket_error(result.value)

        async def connect(self, address: tuple[Any, ...]) -> None:
            if self._connected:
                raise OSError(
                    errno.EISCONN, "socket is already connected"
                )  # Defensive: direct socket callers may attempt to connect twice.
            try:
                await self._socket.connect(_wasi_socket_address(address))
            except Err as error:
                raise _socket_error(error.value) from None

            self._reader, receive_future = self._socket.receive()
            self._writer, send_reader = wit_world.byte_stream()
            send_future = self._socket.send(send_reader)
            componentize_py_async_support.spawn(self._watch_receive(receive_future))
            componentize_py_async_support.spawn(self._watch_send(send_future))
            self._connected = True

        async def send(self, data: bytes) -> int:
            if self._send_error is not None:
                raise self._send_error  # Defensive: propagate a host stream failure to direct socket callers.
            if self._writer is None:
                raise OSError(errno.ENOTCONN, "socket is not connected")
            return await self._writer.write(
                data
            )  # Defensive: direct WASI socket API; internal callers use sendall.

        async def sendall(self, data: bytes) -> None:
            if self._send_error is not None:
                raise self._send_error  # Defensive: host stream failure may arrive before the next write.
            if self._writer is None:
                raise OSError(
                    errno.ENOTCONN, "socket is not connected"
                )  # Defensive: direct socket callers may write before connecting.
            written = await self._writer.write_all(data)
            if written != len(data):
                raise BrokenPipeError(errno.EPIPE, "connection closed during write")

        async def write_all(self, data: bytes) -> None:
            await self.sendall(data)

        def read_ready(self) -> bool:
            if self._reader is None:
                raise OSError(
                    errno.ENOTCONN, "socket is not connected"
                )  # Defensive: direct socket callers may inspect readiness before connecting.
            return bool(
                self._read_buffer
                or self._receive_error is not None
                or self._reader.writer_dropped
            )

        async def until_data_available(self, remaining: float | None = None) -> None:
            # Preview 3 streams have no peek operation. Retain a bounded read
            # for recv(); cancellation/timeouts are not supported by the runtime.
            if not self.read_ready():
                self._read_buffer = await self.recv(65536)

        async def recv(self, bufsize: int) -> bytes:
            # Zero-length component-stream reads wait for readiness.
            if bufsize == 0:
                return b""
            if self._receive_error is not None:
                raise self._receive_error  # Defensive: host stream failure may arrive before the next read.
            if self._reader is None:
                raise OSError(errno.ENOTCONN, "socket is not connected")
            if self._read_buffer:
                data = self._read_buffer[:bufsize]
                self._read_buffer = self._read_buffer[bufsize:]
                return data
            return await self._reader.read(bufsize)

        async def read_exact(self, size: int) -> bytes:
            chunks = []
            remaining = size
            while remaining:
                chunk = await self.recv(remaining)
                if not chunk:
                    raise EOFError("connection closed before enough data was received")
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)

        async def recv_into(self, buffer: Any, nbytes: int = 0) -> int:
            if nbytes <= 0:
                nbytes = len(buffer)
            data = await self.recv(nbytes)
            buffer[: len(data)] = data
            return len(data)

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            for resource_name in ("_writer", "_reader", "_socket"):
                resource = getattr(self, resource_name, None)
                if resource is not None:
                    resource.__exit__(None, None, None)
                    setattr(self, resource_name, None)

        async def wait_for_close(self) -> None:
            return None

        async def wait_for_readiness(
            self,
        ) -> (
            None
        ):  # Defensive: socket compatibility stub; native connect completes readiness.
            return None

        def should_connect(self) -> bool:
            return not self._connected

        def fileno(self) -> int:
            return -1 if self._closed else 0

        def settimeout(self, value: float | int | None = None) -> None:
            if value is not None and value < 0:
                raise ValueError("Timeout value out of range")
            self._timeout = value

        def gettimeout(self) -> float | int | None:
            return self._timeout

        def getsockopt(
            self, level: int, optname: int, buflen: int | None = None
        ) -> int:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                if level == _stdlib_socket.SOL_SOCKET:
                    if optname == _stdlib_socket.SO_ERROR:
                        error = self._send_error or self._receive_error
                        return error.errno or errno.EIO if error is not None else 0
                    if optname == _stdlib_socket.SO_KEEPALIVE:
                        return int(self._socket.get_keep_alive_enabled())
                    if optname == _stdlib_socket.SO_RCVBUF:
                        return self._socket.get_receive_buffer_size()
                    if optname == _stdlib_socket.SO_SNDBUF:
                        return self._socket.get_send_buffer_size()
                elif level == _stdlib_socket.IPPROTO_TCP:
                    if optname in (
                        getattr(_stdlib_socket, "TCP_KEEPIDLE", -1),
                        getattr(_stdlib_socket, "TCP_KEEPALIVE", -1),
                    ):
                        return self._socket.get_keep_alive_idle_time() // 1_000_000_000
                    if optname == getattr(_stdlib_socket, "TCP_KEEPINTVL", -1):
                        return self._socket.get_keep_alive_interval() // 1_000_000_000
                    if optname == getattr(_stdlib_socket, "TCP_KEEPCNT", -1):
                        return self._socket.get_keep_alive_count()
            except Err as error:  # Defensive: host-specific failure querying an otherwise supported socket option.
                raise _socket_error(error.value) from None
            raise OSError(errno.ENOPROTOOPT, "protocol option not available")

        def setsockopt(self, level: int, optname: int, value: Any) -> None:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                if level == _stdlib_socket.SOL_SOCKET:
                    if optname == _stdlib_socket.SO_KEEPALIVE:
                        self._socket.set_keep_alive_enabled(bool(value))
                        return
                    if optname == _stdlib_socket.SO_RCVBUF:
                        self._socket.set_receive_buffer_size(int(value))
                        return
                    if optname == _stdlib_socket.SO_SNDBUF:
                        self._socket.set_send_buffer_size(int(value))
                        return
                elif level == _stdlib_socket.IPPROTO_TCP:
                    if optname == _stdlib_socket.TCP_NODELAY:
                        return
                    if optname in (
                        getattr(_stdlib_socket, "TCP_KEEPIDLE", -1),
                        getattr(_stdlib_socket, "TCP_KEEPALIVE", -1),
                    ):
                        self._socket.set_keep_alive_idle_time(
                            int(value) * 1_000_000_000
                        )
                        return
                    if optname == getattr(_stdlib_socket, "TCP_KEEPINTVL", -1):
                        self._socket.set_keep_alive_interval(int(value) * 1_000_000_000)
                        return
                    if optname == getattr(_stdlib_socket, "TCP_KEEPCNT", -1):
                        self._socket.set_keep_alive_count(int(value))
                        return
            except Err as error:
                raise _socket_error(error.value) from None
            raise OSError(errno.ENOPROTOOPT, "protocol option not available")

        def getsockname(self) -> tuple[str, int] | tuple[str, int, int, int]:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                return _python_socket_address(self._socket.get_local_address())
            except Err as error:
                raise _socket_error(error.value) from None

        def getpeername(self) -> tuple[str, int] | tuple[str, int, int, int]:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                return _python_socket_address(self._socket.get_remote_address())
            except Err as error:
                raise _socket_error(error.value) from None

        async def wrap_socket(
            self,
            context: Any,
            *,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> SSLAsyncSocket:
            tls_socket = SSLAsyncSocket(self, context, server_hostname)
            await tls_socket.do_handshake()
            return tls_socket

        def __enter__(self) -> AsyncSocket:
            return self

        def __exit__(self, *args: Any) -> None:
            self.close()

    class SSLAsyncSocket:
        """TLS over a native WASI Preview 3 byte stream."""

        def __init__(
            self,
            transport: AsyncSocket,
            context: Any,
            server_hostname: str | None,
        ) -> None:
            if _tls is None:
                raise RuntimeError(
                    "TLS support is unavailable"
                )  # Defensive: TLS wrapper used without an installed TLS engine.

            self._transport = transport
            self.family = transport.family
            self.type = transport.type
            self.proto = transport.proto
            self._timeout = transport.gettimeout()
            self._incoming = _tls.MemoryBIO()
            self._outgoing = _tls.MemoryBIO()
            self._sslobj_internal = context.wrap_bio(
                self._incoming,
                self._outgoing,
                server_side=False,
                server_hostname=server_hostname,
            )
            self._plaintext_writer, self._plaintext_reader = wit_world.byte_stream()
            self._read_buffer = b""
            self._write_lock = asyncio.Lock()
            self._error: BaseException | None = None
            self._closed = False
            self._closing = False

        @property
        def sslobj(self) -> Any:
            return self._sslobj_internal

        @property
        def _sslobj(
            self,
        ) -> Any:  # Defensive: SSL socket compatibility alias; native paths use sslobj.
            return self._sslobj_internal

        @property
        def context(self) -> Any:
            return self._sslobj_internal.context

        async def _flush_outgoing(self) -> None:
            async with self._write_lock:
                while self._outgoing.pending:
                    await self._transport.sendall(self._outgoing.read())

        async def do_handshake(self) -> None:
            while True:
                try:
                    self._sslobj_internal.do_handshake()
                except _tls.SSLWantReadError:
                    await self._flush_outgoing()
                    ciphertext = await self._transport.recv(65536)
                    if not ciphertext:
                        raise _tls.SSLEOFError("EOF occurred during the TLS handshake")
                    self._incoming.write(ciphertext)
                except _tls.SSLWantWriteError:  # Defensive: unbounded MemoryBIO.
                    # Retained for TLS-engine compatibility.
                    await self._flush_outgoing()
                else:
                    await self._flush_outgoing()
                    break

            componentize_py_async_support.spawn(self._receive_pump())

        async def _receive_pump(self) -> None:
            try:
                while not self._closing:
                    ciphertext = await self._transport.recv(65536)
                    if not ciphertext:
                        self._incoming.write_eof()
                        break
                    self._incoming.write(ciphertext)

                    while True:
                        try:
                            plaintext = self._sslobj_internal.read(65536)
                        except _tls.SSLWantReadError:
                            break
                        except _tls.SSLZeroReturnError:
                            self._closing = True
                            break
                        if not plaintext:
                            break
                        written = await self._plaintext_writer.write_all(plaintext)
                        if (
                            written != len(plaintext)
                        ):  # Defensive: component consumer may close during a plaintext write.
                            self._closing = True
                            break

                    await self._flush_outgoing()
            except BaseException as error:
                self._error = error
            finally:
                self._plaintext_writer.__exit__(None, None, None)

        async def send(self, data: bytes) -> int:
            if self._error is not None:
                raise self._error
            if self._closing:
                raise BrokenPipeError(
                    errno.EPIPE, "TLS connection is closed"
                )  # Defensive: direct socket callers may write after TLS shutdown.
            written = self._sslobj_internal.write(data)
            await self._flush_outgoing()
            return written

        async def sendall(self, data: bytes) -> None:
            view = memoryview(data)
            sent = 0
            while sent < len(view):
                sent += await self.send(bytes(view[sent:]))

        async def write_all(self, data: bytes) -> None:
            await self.sendall(data)

        def read_ready(self) -> bool:
            return bool(
                self._read_buffer
                or self._error is not None
                or self._plaintext_reader.writer_dropped
            )

        async def until_data_available(self, remaining: float | None = None) -> None:
            # Wait for plaintext from the TLS pump, not ciphertext readiness.
            if not self.read_ready():
                self._read_buffer = await self.recv(65536)

        async def recv(self, bufsize: int) -> bytes:
            # Zero-length component-stream reads wait for readiness.
            if bufsize == 0:
                return b""
            if self._read_buffer:
                data = self._read_buffer[:bufsize]
                self._read_buffer = self._read_buffer[bufsize:]
                return data
            data = await self._plaintext_reader.read(bufsize)
            if not data and self._error is not None:
                raise self._error
            return data

        async def read_exact(self, size: int) -> bytes:
            chunks = []
            remaining = size
            while remaining:
                chunk = await self.recv(remaining)
                if not chunk:
                    raise EOFError("connection closed before enough data was received")
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)

        async def recv_into(self, buffer: Any, nbytes: int = 0) -> int:
            if nbytes <= 0:
                nbytes = len(buffer)
            data = await self.recv(nbytes)
            buffer[: len(data)] = data
            return len(data)

        def selected_alpn_protocol(self) -> str | None:
            return self._sslobj_internal.selected_alpn_protocol()

        def getpeercert(self, binary_form: bool = False) -> Any:
            return self._sslobj_internal.getpeercert(binary_form=binary_form)

        def cipher(self) -> tuple[str, str, int] | None:
            return self._sslobj_internal.cipher()

        def version(self) -> str | None:
            return self._sslobj_internal.version()

        def close(self) -> None:
            if self._closed or self._closing:
                return
            self._closing = True
            try:
                self._sslobj_internal.unwrap()
            except (
                _tls.SSLError
            ):  # Defensive: best-effort TLS shutdown across WASI TLS engines.
                pass

        async def wait_for_close(self) -> None:
            if self._closed:
                return
            self._closed = True
            try:
                await self._flush_outgoing()
            finally:
                self._plaintext_writer.__exit__(None, None, None)
                self._plaintext_reader.__exit__(None, None, None)
                self._transport.close()
                await self._transport.wait_for_close()

        async def wait_for_readiness(self) -> None:
            return None

        def should_connect(self) -> bool:
            return False

        def fileno(self) -> int:
            return -1 if self._closed else self._transport.fileno()

        def settimeout(self, value: float | int | None = None) -> None:
            self._timeout = value
            self._transport.settimeout(value)

        def gettimeout(self) -> float | int | None:
            return self._timeout

        def getsockopt(
            self, level: int, optname: int, buflen: int | None = None
        ) -> int:
            return self._transport.getsockopt(level, optname, buflen)

        def setsockopt(self, level: int, optname: int, value: Any) -> None:
            self._transport.setsockopt(level, optname, value)

        def getsockname(self) -> tuple[str, int] | tuple[str, int, int, int]:
            return self._transport.getsockname()

        def getpeername(self) -> tuple[str, int] | tuple[str, int, int, int]:
            return self._transport.getpeername()

        async def wrap_socket(
            self,
            context: Any,
            *,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> SSLAsyncSocket:
            tls_socket = SSLAsyncSocket(self, context, server_hostname)
            await tls_socket.do_handshake()
            return tls_socket

        def __enter__(self) -> SSLAsyncSocket:
            return self

        def __exit__(self, *args: Any) -> None:
            self.close()

    socket = AsyncSocket

    async def create_connection(
        address: tuple[str, int],
        *,
        family: _stdlib_socket.AddressFamily = _stdlib_socket.AF_UNSPEC,
    ) -> AsyncSocket:
        host, port = address
        errors = []
        for address_family, _, proto, _, socket_address in await getaddrinfo(
            host, port, family, _stdlib_socket.SOCK_STREAM
        ):
            sock = AsyncSocket(address_family, _stdlib_socket.SOCK_STREAM, proto)
            try:
                await sock.connect(socket_address)
                return sock
            except OSError as error:
                errors.append(error)
                sock.close()
        if not errors:
            raise OSError(
                "getaddrinfo returns an empty list"
            )  # Defensive: native resolution already rejects an empty address list.
        raise errors[-1]
else:
    from urllib3.contrib.ssa import AsyncSocket, SSLAsyncSocket

    socket = AsyncSocket

    async def getaddrinfo(
        host: bytes | str | None,
        port: bytes | str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[Any]:
        import asyncio

        return await asyncio.get_running_loop().getaddrinfo(
            host, port, family=family, type=type, proto=proto, flags=flags
        )

    async def create_connection(
        address: tuple[str, int],
        *,
        family: _stdlib_socket.AddressFamily = _stdlib_socket.AF_UNSPEC,
    ) -> AsyncSocket:
        records = await getaddrinfo(
            address[0], address[1], family, _stdlib_socket.SOCK_STREAM
        )
        last_error = None
        for address_family, socket_type, proto, _, socket_address in records:
            sock = AsyncSocket(address_family, socket_type, proto)
            try:
                await sock.connect(socket_address)
                return sock
            except OSError as error:
                last_error = error
                sock.close()
        if last_error is not None:
            raise last_error
        raise OSError(
            "getaddrinfo returns an empty list"
        )  # Defensive: system getaddrinfo normally returns addresses or raises.


__all__ = [
    "AsyncSocket",
    "SSLAsyncSocket",
    "create_connection",
    "getaddrinfo",
    "socket",
]
