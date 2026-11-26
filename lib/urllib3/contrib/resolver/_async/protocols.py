from __future__ import annotations

import contextlib
import asyncio
import ipaddress
import socket
import struct
import sys
import typing
from abc import ABCMeta, abstractmethod
from datetime import datetime, timedelta, timezone

from ...._constant import UDP_LINUX_GRO
from ...._typing import _TYPE_SOCKET_OPTIONS, _TYPE_TIMEOUT_INTERNAL
from ....exceptions import LocationParseError
from ....util.connection import _set_socket_options, allowed_gai_family
from ....util.timeout import _DEFAULT_TIMEOUT
from ...ssa import AsyncSocket
from ...ssa._timeout import timeout as timeout_
from ..protocols import BaseResolver

_HAS_WASI_SOCKET_BINDINGS = sys.platform != "wasi"

if sys.platform == "wasi":
    try:
        from ...wasi._async.socket import AsyncSocket
    except ImportError:
        pass
    else:
        _HAS_WASI_SOCKET_BINDINGS = True


class AsyncBaseResolver(BaseResolver, metaclass=ABCMeta):
    def recycle(self) -> AsyncBaseResolver:
        return super().recycle()  # type: ignore[return-value]

    @abstractmethod
    async def close(self) -> None:  # type: ignore[override]
        """Terminate the given resolver instance. This should render it unusable. Further inquiries should raise an exception."""
        raise NotImplementedError

    @abstractmethod
    async def getaddrinfo(  # type: ignore[override]
        self,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str | bytes,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        """This method align itself on the standard library socket.getaddrinfo(). It must be implemented as-is on your Resolver."""
        raise NotImplementedError

    # This function is copied from socket.py in the Python 2.7 standard
    # library test suite. Added to its signature is only `socket_options`.
    # One additional modification is that we avoid binding to IPv6 servers
    # discovered in DNS if the system doesn't have IPv6 functionality.
    async def create_connection(  # type: ignore[override]
        self,
        address: tuple[str, int],
        timeout: _TYPE_TIMEOUT_INTERNAL = _DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        socket_options: _TYPE_SOCKET_OPTIONS | None = None,
        socket_kind: socket.SocketKind = socket.SOCK_STREAM,
        *,
        quic_upgrade_via_dns_rr: bool = False,
        timing_hook: typing.Callable[[tuple[timedelta, timedelta, datetime]], None]
        | None = None,
        ech_config_hook: typing.Callable[[bytes], None] | None = None,
        default_socket_family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> AsyncSocket:
        """Connect to *address* and return the socket object.

        Convenience function.  Connect to *address* (a 2-tuple ``(host,
        port)``) and return the socket object.  Passing the optional
        *timeout* parameter will set the timeout on the socket instance
        before attempting to connect.  If no *timeout* is supplied, the
        global default timeout setting returned by :func:`socket.getdefaulttimeout`
        is used.  If *source_address* is set it must be a tuple of (host, port)
        for the socket to bind as a source address before making the connection.
        An host of '' or port 0 tells the OS to use the default.
        """

        if not _HAS_WASI_SOCKET_BINDINGS:
            raise RuntimeError(  # Defensive: component built without the required WASI socket interfaces.
                "Async networking on WASI requires the Preview 3 socket "
                "interfaces. Componentize with "
                "'-w wasi:cli/command@0.3.0', or import "
                "'wasi:sockets/types@0.3.0' and "
                "'wasi:sockets/ip-name-lookup@0.3.0' in the component world."
            )

        host, port = address
        if host.startswith("["):
            host = host.strip("[]")
        err = None

        # Using the value from allowed_gai_family() in the context of getaddrinfo lets
        # us select whether to work with IPv4 DNS records, IPv6 records, or both.
        # The original create_connection function always returns all records.
        family = allowed_gai_family()

        if family != socket.AF_UNSPEC:
            default_socket_family = family

        if source_address is not None:
            if isinstance(
                ipaddress.ip_address(source_address[0]), ipaddress.IPv4Address
            ):
                default_socket_family = socket.AF_INET
            else:
                default_socket_family = socket.AF_INET6

        try:
            host.encode("idna")
        except UnicodeError:
            raise LocationParseError(f"'{host}', label empty or too long") from None

        dt_pre_resolve = datetime.now(tz=timezone.utc)
        if timeout is not _DEFAULT_TIMEOUT and timeout is not None:
            # we can hang here in case of bad networking conditions
            # the DNS may never answer or the packets can be lost.
            # this isn't possible in sync mode. unfortunately.
            # found by user at https://github.com/jawah/niquests/issues/183
            # todo: find a way to limit getaddrinfo delays in sync mode.
            try:
                async with timeout_(timeout):
                    records = await self.getaddrinfo(
                        host,
                        port,
                        default_socket_family,
                        socket_kind,
                        quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
                    )
            except TimeoutError:
                raise socket.gaierror(
                    f"unable to resolve '{host}' within timeout. the DNS server may be unresponsive."
                )
        else:
            records = await self.getaddrinfo(
                host,
                port,
                default_socket_family,
                socket_kind,
                quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
            )
        delta_post_resolve = datetime.now(tz=timezone.utc) - dt_pre_resolve

        dt_pre_established = datetime.now(tz=timezone.utc)
        for res in records:
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = AsyncSocket(af, socktype, proto)

                # we need to add this or reusing the same origin port will likely fail within
                # short period of time. kernel put port on wait shut.
                if source_address:
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except (OSError, AttributeError):  # Defensive: very old OS?
                        try:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        except (
                            OSError,
                            AttributeError,
                        ):  # Defensive: we can't do anything better than this.
                            pass

                    try:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                        )
                    except (
                        OSError,
                        AttributeError,
                    ):  # Defensive: the platform may not support SO_LINGER.
                        pass

                # attempt to leverage GRO when under Linux
                if socktype == socket.SOCK_DGRAM and sys.platform == "linux":
                    try:
                        sock.setsockopt(socket.SOL_UDP, UDP_LINUX_GRO, 1)
                    except OSError:  # Defensive: oh, well(...) anyway!
                        pass

                # If provided, set socket level options before connecting.
                _set_socket_options(sock, socket_options)

                if timeout is not _DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                if source_address:
                    sock.bind(source_address)

                try:
                    await sock.connect(sa)
                except asyncio.CancelledError:
                    sock.close()
                    raise

                # Break explicitly a reference cycle
                err = None

                delta_post_established = (
                    datetime.now(tz=timezone.utc) - dt_pre_established
                )

                if timing_hook is not None:
                    timing_hook(
                        (
                            delta_post_resolve,
                            delta_post_established,
                            datetime.now(tz=timezone.utc),
                        )
                    )

                if isinstance(canonname, bytes) and canonname:
                    if ech_config_hook is not None:
                        ech_config_hook(canonname)

                return sock
            except (OSError, OverflowError) as _:
                err = _
                if sock is not None:
                    sock.close()
                if isinstance(_, OverflowError):
                    break

        if err is not None:
            try:
                raise err
            finally:
                # Break explicitly a reference cycle
                err = None
        else:
            raise OSError("getaddrinfo returns an empty list")


class AsyncManyResolver(AsyncBaseResolver):
    """
    Special resolver that use many child resolver. Priorities
    are based on given order (list of BaseResolver).
    """

    def __init__(self, *resolvers: AsyncBaseResolver) -> None:
        super().__init__(None, None)

        self._size = len(resolvers)

        self._unconstrained: list[AsyncBaseResolver] = [
            _ for _ in resolvers if not _.have_constraints()
        ]
        self._constrained: list[AsyncBaseResolver] = [
            _ for _ in resolvers if _.have_constraints()
        ]

        self._concurrent: int = 0
        self._terminated: bool = False

    def recycle(self) -> AsyncBaseResolver:
        resolvers = []

        for resolver in self._unconstrained + self._constrained:
            resolvers.append(resolver.recycle())

        return AsyncManyResolver(*resolvers)

    async def close(self) -> None:  # type: ignore[override]
        for resolver in self._unconstrained + self._constrained:
            await resolver.close()

        self._terminated = True

    def is_available(self) -> bool:
        return not self._terminated

    def __resolvers(
        self, constrained: bool = False
    ) -> typing.Generator[AsyncBaseResolver, None, None]:
        resolvers = self._unconstrained if not constrained else self._constrained

        if not resolvers:
            return

        with self._lock:
            self._concurrent += 1

        try:
            resolver_count = len(resolvers)
            start_idx = (self._concurrent - 1) % resolver_count

            for idx in range(start_idx, resolver_count):
                if not resolvers[idx].is_available():
                    with self._lock:
                        resolvers[idx] = resolvers[idx].recycle()
                yield resolvers[idx]

            if start_idx > 0:
                for idx in range(0, start_idx):
                    if not resolvers[idx].is_available():
                        with self._lock:
                            resolvers[idx] = resolvers[idx].recycle()
                    yield resolvers[idx]
        finally:
            with self._lock:
                self._concurrent -= 1

    async def getaddrinfo(  # type: ignore[override]
        self,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str | bytes,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if host is None:
            host = "localhost"

        tested_resolvers = []

        any_constrained_tried: bool = False

        with contextlib.closing(self.__resolvers(True)) as candidates:
            for resolver in candidates:
                can_resolve = resolver.support(host)

                if can_resolve is True:
                    any_constrained_tried = True

                    try:
                        results = await resolver.getaddrinfo(
                            host,
                            port,
                            family,
                            type,
                            proto,
                            flags,
                            quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
                        )

                        if results:
                            return results
                    except socket.gaierror as exc:
                        if isinstance(exc.args[0], str) and (
                            "DNSSEC" in exc.args[0] or "DNSKEY" in exc.args[0]
                        ):
                            raise
                        continue
                elif can_resolve is False:
                    tested_resolvers.append(resolver)

        if any_constrained_tried:
            raise socket.gaierror(
                f"Name or service not known: {host} using {self._size - len(self._unconstrained)} resolver(s)"
            )

        with contextlib.closing(self.__resolvers()) as candidates:
            for resolver in candidates:
                try:
                    results = await resolver.getaddrinfo(
                        host,
                        port,
                        family,
                        type,
                        proto,
                        flags,
                        quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
                    )

                    if results:
                        return results
                except socket.gaierror as exc:
                    if isinstance(exc.args[0], str) and (
                        "DNSSEC" in exc.args[0] or "DNSKEY" in exc.args[0]
                    ):
                        raise
                    continue

        raise socket.gaierror(
            f"Name or service not known: {host} using {self._size - len(self._constrained)} resolver(s)"
        )
