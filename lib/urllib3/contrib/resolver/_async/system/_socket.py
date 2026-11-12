from __future__ import annotations

import asyncio
import socket
import sys
import typing

from ...protocols import ProtocolResolver
from ..protocols import AsyncBaseResolver

if sys.platform == "wasi":
    try:
        from ....wasi._async.socket import getaddrinfo as wasi_getaddrinfo
    except ImportError:
        wasi_getaddrinfo = None
else:
    wasi_getaddrinfo = None


class SystemResolver(AsyncBaseResolver):
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

    def recycle(self) -> AsyncBaseResolver:
        return self

    async def close(self) -> None:  # type: ignore[override]
        pass  # no-op!

    def is_available(self) -> bool:
        return True

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
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        if wasi_getaddrinfo is not None:
            return await wasi_getaddrinfo(
                host=host,
                port=port,
                family=family,
                type=type,
                proto=proto,
                flags=flags,
            )

        return await asyncio.get_running_loop().getaddrinfo(
            host=host,
            port=port,
            family=family,
            type=type,
            proto=proto,
            flags=flags,
        )
