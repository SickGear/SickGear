"""Compatibility facade for the CPython socket module under WASI."""

from __future__ import annotations

import builtins
import errno
import ipaddress
import socket as _stdlib_socket
import sys
from typing import Any

__all__ = _stdlib_socket.__all__

# Keep these assignments explicit for static analyzers. The values are also
# used by the WASI implementation as module globals.
AddressFamily = _stdlib_socket.AddressFamily
SocketKind = _stdlib_socket.SocketKind
gaierror = _stdlib_socket.gaierror
getservbyname = _stdlib_socket.getservbyname
AF_UNSPEC = _stdlib_socket.AF_UNSPEC
AF_INET = _stdlib_socket.AF_INET
AF_INET6 = _stdlib_socket.AF_INET6
SOCK_STREAM = _stdlib_socket.SOCK_STREAM
SOCK_DGRAM = _stdlib_socket.SOCK_DGRAM
SHUT_RD = _stdlib_socket.SHUT_RD
SHUT_WR = _stdlib_socket.SHUT_WR
IPPROTO_TCP = _stdlib_socket.IPPROTO_TCP
IPPROTO_UDP = _stdlib_socket.IPPROTO_UDP
AI_PASSIVE = _stdlib_socket.AI_PASSIVE
AI_CANONNAME = _stdlib_socket.AI_CANONNAME
AI_NUMERICHOST = _stdlib_socket.AI_NUMERICHOST
EAI_AGAIN = _stdlib_socket.EAI_AGAIN
EAI_FAIL = _stdlib_socket.EAI_FAIL
EAI_NONAME = _stdlib_socket.EAI_NONAME
_GLOBAL_DEFAULT_TIMEOUT = getattr(_stdlib_socket, "_GLOBAL_DEFAULT_TIMEOUT")


if sys.platform == "wasi":
    from componentize_py_types import Err
    from wit_world.imports import instance_network as _wasi_instance_network
    from wit_world.imports import network as _wasi_network
    from wit_world.imports import streams as _wasi_streams
    from wit_world.imports import tcp as _wasi_tcp
    from wit_world.imports import tcp_create_socket as _wasi_tcp_create_socket

    try:
        from wit_world.imports import (
            wasi_sockets_ip_name_lookup_0_2_0 as _wasi_ip_name_lookup,
        )
    except ImportError:
        from wit_world.imports import ip_name_lookup as _wasi_ip_name_lookup

        if not hasattr(_wasi_ip_name_lookup, "ResolveAddressStream"):
            raise ImportError("wasi:sockets/ip-name-lookup@0.2.0 is required")

    def _gaierror(error: _wasi_network.ErrorCode) -> OSError:
        if error is _wasi_network.ErrorCode.NAME_UNRESOLVABLE:
            code = EAI_NONAME
        elif error is _wasi_network.ErrorCode.TEMPORARY_RESOLVER_FAILURE:
            # Wasmtime 47 collapses lookup failures to name-unresolvable.
            code = EAI_AGAIN  # Defensive: WASI spec compatibility.
        else:
            code = EAI_FAIL
        return gaierror(code, error.name.lower().replace("_", " "))

    def _resolve_host(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass

        addresses = []
        try:
            with _wasi_instance_network.instance_network() as network:
                with _wasi_ip_name_lookup.resolve_addresses(network, host) as stream:
                    while True:
                        with stream.subscribe() as pollable:
                            pollable.block()
                        address = stream.resolve_next_address()
                        if address is None:
                            break
                        if isinstance(address, _wasi_network.IpAddress_Ipv4):
                            addresses.append(
                                ipaddress.IPv4Address(bytes(address.value))
                            )
                        else:
                            packed = b"".join(
                                part.to_bytes(2, "big") for part in address.value
                            )
                            addresses.append(ipaddress.IPv6Address(packed))
        except Err as error:
            raise _gaierror(error.value) from None

        if not addresses:
            raise gaierror(
                EAI_NONAME, "name or service not known"
            )  # Defensive: WASI hosts may return a successful but empty address stream.
        return addresses

    def _coerce_port(port: bytes | str | int | None, sock_type: int) -> int:
        if port is None:
            return 0
        if isinstance(port, bytes):
            port = port.decode("ascii")
        if isinstance(port, str):
            if port.isdigit():
                return int(port)
            protocol = "udp" if sock_type == SOCK_DGRAM else "tcp"
            return getservbyname(port, protocol)
        return int(port)

    def getaddrinfo(
        host: bytes | str | None,
        port: bytes | str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[AddressFamily, SocketKind, int, str, tuple[Any, ...]]]:
        if isinstance(host, bytes):
            host = host.decode("ascii")

        if host is None:
            addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            if family in (0, AF_UNSPEC, AF_INET6):
                addresses.append(
                    ipaddress.IPv6Address("::" if flags & AI_PASSIVE else "::1")
                )
            if family in (0, AF_UNSPEC, AF_INET):
                addresses.append(
                    ipaddress.IPv4Address(
                        "0.0.0.0" if flags & AI_PASSIVE else "127.0.0.1"
                    )
                )
            hostname = ""
        else:
            hostname = host
            if flags & AI_NUMERICHOST:
                try:
                    addresses = [ipaddress.ip_address(host)]
                except ValueError:
                    raise gaierror(EAI_NONAME, "name or service not known") from None
            else:
                addresses = _resolve_host(host)

        socket_types: list[tuple[int, int]]
        if type == 0:
            socket_types = [(SOCK_STREAM, IPPROTO_TCP), (SOCK_DGRAM, IPPROTO_UDP)]
        elif type == SOCK_STREAM:
            socket_types = [(SOCK_STREAM, proto or IPPROTO_TCP)]
        elif type == SOCK_DGRAM:
            socket_types = [(SOCK_DGRAM, proto or IPPROTO_UDP)]
        else:
            socket_types = [(type, proto)]

        results = []
        for address in addresses:
            address_family = AF_INET if address.version == 4 else AF_INET6
            if family not in (0, AF_UNSPEC, address_family):
                continue
            for socket_type, socket_proto in socket_types:
                resolved_port = _coerce_port(port, socket_type)
                sockaddr: tuple[Any, ...]
                if address_family == AF_INET:
                    sockaddr = (str(address), resolved_port)
                else:
                    sockaddr = (str(address), resolved_port, 0, 0)
                canonname = hostname if flags & AI_CANONNAME and not results else ""
                results.append(
                    (
                        AddressFamily(address_family),
                        SocketKind(socket_type),
                        socket_proto,
                        canonname,
                        sockaddr,
                    )
                )

        if not results:
            raise gaierror(EAI_NONAME, "name or service not known")
        return results

    def gethostbyname(hostname: str) -> str:
        results = getaddrinfo(hostname, 0, AF_INET, SOCK_STREAM)
        return results[0][4][0]

    def gethostbyname_ex(hostname: str) -> tuple[str, list[str], list[str]]:
        addresses = [
            result[4][0] for result in getaddrinfo(hostname, 0, AF_INET, SOCK_STREAM)
        ]
        return hostname, [], list(dict.fromkeys(addresses))

    def _wasi_socket_address(address: tuple[Any, ...]) -> _wasi_network.IpSocketAddress:
        ip = ipaddress.ip_address(address[0])
        port = int(address[1])
        if isinstance(ip, ipaddress.IPv4Address):
            return _wasi_network.IpSocketAddress_Ipv4(
                _wasi_network.Ipv4SocketAddress(port=port, address=tuple(ip.packed))
            )
        packed = ip.packed
        return _wasi_network.IpSocketAddress_Ipv6(
            _wasi_network.Ipv6SocketAddress(
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
        address: _wasi_network.IpSocketAddress,
    ) -> tuple[str, int] | tuple[str, int, int, int]:
        if isinstance(address, _wasi_network.IpSocketAddress_Ipv4):
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

    def _socket_error(error_code: Any) -> OSError:
        name = getattr(error_code, "name", "UNKNOWN").lower().replace("_", " ")
        if error_code is _wasi_network.ErrorCode.CONNECTION_REFUSED:
            code = errno.ECONNREFUSED
        elif error_code is _wasi_network.ErrorCode.CONNECTION_RESET:
            code = errno.ECONNRESET  # Defensive: WASI host-specific error mapping.
        elif error_code is _wasi_network.ErrorCode.CONNECTION_ABORTED:
            code = errno.ECONNABORTED  # Defensive: WASI host-specific error mapping.
        elif error_code is _wasi_network.ErrorCode.TIMEOUT:
            return _stdlib_socket.timeout(
                name
            )  # Defensive: WASI host-specific error mapping.
        elif error_code is _wasi_network.ErrorCode.ACCESS_DENIED:
            code = errno.EACCES
        else:
            code = errno.EIO
        return OSError(code, name)

    class socket:
        """Blocking TCP socket backed by WASI Preview 2 resources."""

        def __init__(
            self,
            family: int = AF_INET,
            type: int = SOCK_STREAM,
            proto: int = 0,
            fileno: int | None = None,
        ) -> None:
            if fileno is not None:
                raise NotImplementedError(
                    "WASI sockets cannot be created from file descriptors"
                )
            if type != SOCK_STREAM:
                raise OSError(errno.EPROTONOSUPPORT, "only TCP sockets are supported")
            if family not in (AF_INET, AF_INET6):
                raise OSError(errno.EAFNOSUPPORT, "address family not supported")

            address_family = (
                _wasi_network.IpAddressFamily.IPV4
                if family == AF_INET
                else _wasi_network.IpAddressFamily.IPV6
            )
            try:
                self._socket = _wasi_tcp_create_socket.create_tcp_socket(address_family)
            except Err as error:  # Defensive: WASI host socket-allocation failure.
                raise _socket_error(error.value) from None

            self.family = AddressFamily(family)
            self.type = SocketKind(type)
            self.proto = proto or IPPROTO_TCP
            self._reader: _wasi_streams.InputStream | None = None
            self._writer: _wasi_streams.OutputStream | None = None
            self._timeout: float | None = None
            self._closed = False

        def connect(self, address: tuple[Any, ...]) -> None:
            try:
                with _wasi_instance_network.instance_network() as network:
                    self._socket.start_connect(network, _wasi_socket_address(address))
                    with self._socket.subscribe() as pollable:
                        pollable.block()
                    self._reader, self._writer = self._socket.finish_connect()
            except Err as error:
                raise _socket_error(error.value) from None

        def connect_ex(self, address: tuple[Any, ...]) -> int:
            try:
                self.connect(address)
            except OSError as error:
                return error.errno or errno.EIO
            return 0

        def recv(self, bufsize: int, flags: int = 0) -> bytes:
            if flags:
                raise NotImplementedError("WASI TCP recv flags are not supported")
            if bufsize == 0:
                return b""
            if self._reader is None:
                raise OSError(errno.ENOTCONN, "socket is not connected")
            try:
                return self._reader.blocking_read(bufsize)
            except Err as error:
                if isinstance(error.value, _wasi_streams.StreamError_Closed):
                    return b""
                raise OSError(errno.EIO, "WASI stream read failed") from None

        def recv_into(self, buffer: Any, nbytes: int = 0, flags: int = 0) -> int:
            if nbytes <= 0:
                nbytes = len(buffer)
            data = self.recv(nbytes, flags)
            buffer[: len(data)] = data
            return len(data)

        def send(self, data: bytes, flags: int = 0) -> int:
            if flags:
                raise NotImplementedError("WASI TCP send flags are not supported")
            if self._writer is None:
                raise OSError(errno.ENOTCONN, "socket is not connected")
            if not data:
                return 0
            chunk = data[:4096]
            try:
                self._writer.blocking_write_and_flush(chunk)
            except Err as error:
                raise OSError(errno.EIO, "WASI stream write failed") from error
            return len(chunk)

        def sendall(self, data: bytes, flags: int = 0) -> None:
            view = memoryview(data)
            sent = 0
            while sent < len(view):
                sent += self.send(bytes(view[sent:]), flags)

        def shutdown(self, how: int) -> None:
            if how == SHUT_RD:
                shutdown_type = _wasi_tcp.ShutdownType.RECEIVE
            elif how == SHUT_WR:
                shutdown_type = _wasi_tcp.ShutdownType.SEND
            else:
                shutdown_type = _wasi_tcp.ShutdownType.BOTH
            try:
                self._socket.shutdown(shutdown_type)
            except Err as error:  # Defensive: WASI host-specific shutdown failure.
                raise _socket_error(error.value) from None

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            for resource_name in ("_reader", "_writer", "_socket"):
                resource = getattr(self, resource_name, None)
                if resource is not None:
                    resource.__exit__(None, None, None)
                    setattr(self, resource_name, None)

        def fileno(self) -> int:
            return -1 if self._closed else 0

        def settimeout(self, value: float | None) -> None:
            if value is not None and value < 0:
                raise ValueError("Timeout value out of range")
            self._timeout = value

        def gettimeout(self) -> float | None:
            return self._timeout

        def setblocking(self, flag: bool) -> None:
            self._timeout = None if flag else 0.0

        def getblocking(self) -> bool:
            return self._timeout != 0.0

        def getsockopt(
            self, level: int, optname: int, buflen: int | None = None
        ) -> int:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                if level == _stdlib_socket.SOL_SOCKET:
                    if optname == _stdlib_socket.SO_ERROR:
                        return 0
                    if optname == _stdlib_socket.SO_KEEPALIVE:
                        return int(self._socket.keep_alive_enabled())
                    if optname == _stdlib_socket.SO_RCVBUF:
                        return self._socket.receive_buffer_size()
                    if optname == _stdlib_socket.SO_SNDBUF:
                        return self._socket.send_buffer_size()
                elif level == _stdlib_socket.IPPROTO_TCP:
                    if optname in (
                        getattr(_stdlib_socket, "TCP_KEEPIDLE", -1),
                        getattr(_stdlib_socket, "TCP_KEEPALIVE", -1),
                    ):
                        return self._socket.keep_alive_idle_time() // 1_000_000_000
                    if optname == getattr(_stdlib_socket, "TCP_KEEPINTVL", -1):
                        return self._socket.keep_alive_interval() // 1_000_000_000
                    if optname == getattr(_stdlib_socket, "TCP_KEEPCNT", -1):
                        return self._socket.keep_alive_count()
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
                return _python_socket_address(self._socket.local_address())
            except Err as error:
                raise _socket_error(error.value) from None

        def getpeername(self) -> tuple[str, int] | tuple[str, int, int, int]:
            if self._closed:
                raise OSError(errno.EBADF, "bad file descriptor")
            try:
                return _python_socket_address(self._socket.remote_address())
            except Err as error:
                raise _socket_error(error.value) from None

        def __enter__(self) -> socket:
            return self

        def __exit__(self, *args: Any) -> None:
            self.close()

    def create_connection(
        address: tuple[str, int],
        timeout: object = _GLOBAL_DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        *,
        all_errors: bool = False,
    ) -> socket:
        if source_address is not None:
            raise OSError("bind unsupported")

        host, port = address
        errors = []
        for family, socket_type, proto, _, socket_address in getaddrinfo(
            host, port, 0, SOCK_STREAM
        ):
            sock = None
            try:
                sock = socket(family, socket_type, proto)
                if timeout is not _GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)  # type: ignore[arg-type]
                sock.connect(socket_address)
                return sock
            except OSError as error:
                errors.append(error)
                if sock is not None:
                    sock.close()

        if not errors:
            raise OSError(
                "getaddrinfo returns an empty list"
            )  # Defensive: native resolution already rejects an empty address list.
        if all_errors:
            exception_group = getattr(builtins, "ExceptionGroup")
            raise exception_group("create_connection failed", errors)
        raise errors[-1]
else:
    socket = _stdlib_socket.socket  # Defensive: non-WASI socket compatibility alias.


def __getattr__(name: str) -> Any:
    return getattr(_stdlib_socket, name)


def __dir__() -> list[str]:  # Defensive: stdlib socket introspection compatibility.
    return sorted(set(globals()) | set(dir(_stdlib_socket)))
