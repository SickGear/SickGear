from __future__ import annotations

import socket
import sys
import typing

if sys.platform == "wasi":
    try:
        from ...wasi import socket
    except ImportError:
        pass

from ..protocols import BaseResolver, ProtocolResolver


class SystemResolver(BaseResolver):
    implementation = "socket"
    protocol = ProtocolResolver.SYSTEM

    def __init__(self, *patterns: str, **kwargs: typing.Any):
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            kwargs.pop("port")
        super().__init__(None, None, *patterns, **kwargs)

    def support(self, hostname: str | bytes | None) -> bool | None:
        if hostname is None:
            return True
        if isinstance(hostname, bytes):
            hostname = hostname.decode("ascii")
        if hostname == "localhost":
            return True
        return super().support(hostname)

    def recycle(self) -> BaseResolver:
        return self

    def close(self) -> None:
        pass  # no-op!

    def is_available(self) -> bool:
        return True

    def getaddrinfo(
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
        # the | tuple[int, bytes] is silently ignored, can't happen with our cases.
        return socket.getaddrinfo(  # type: ignore[return-value]
            host,
            port,
            family,
            type,
            proto,
            flags,
        )
