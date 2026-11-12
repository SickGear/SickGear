from __future__ import annotations

import socket
import typing

from ....util.url import _IPV6_ADDRZ_RE
from ..protocols import BaseResolver, ProtocolResolver
from ..utils import is_ipv4, is_ipv6


class InMemoryResolver(BaseResolver):
    protocol = ProtocolResolver.MANUAL
    implementation = "dict"

    def __init__(self, *patterns: str, **kwargs: typing.Any):
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            kwargs.pop("port")

        ech_config = kwargs.pop("ech_config", None)

        super().__init__(None, None, *patterns, **kwargs)

        self._maxsize = 65535 if "maxsize" not in kwargs else int(kwargs["maxsize"])
        self._hosts: dict[str, list[tuple[socket.AddressFamily, str]]] = {}

        self._ech_config_list: bytes | None = None
        if isinstance(ech_config, str) and ech_config:
            self._ech_config_list = bytes.fromhex(ech_config)
        elif isinstance(ech_config, bytes) and ech_config:
            self._ech_config_list = ech_config

        if self._host_patterns:
            for record in self._host_patterns:
                if ":" not in record:
                    continue
                hostname, addr = record.split(":", 1)
                self.register(hostname, addr)
            self._host_patterns = tuple([])

        # probably about our happy eyeballs impl (sync only)
        if len(self._hosts) == 1 and len(self._hosts[list(self._hosts.keys())[0]]) == 1:
            self._unsafe_expose = True

    def recycle(self) -> BaseResolver:
        return self

    def close(self) -> None:
        pass  # no-op

    def is_available(self) -> bool:
        return True

    def have_constraints(self) -> bool:
        return True

    def support(self, hostname: str | bytes | None) -> bool | None:
        if hostname is None:
            hostname = "localhost"
        if isinstance(hostname, bytes):
            hostname = hostname.decode("ascii")
        return hostname.lower() in self._hosts

    def register(self, hostname: str, ipaddr: str) -> None:
        # Normalize DNS names without altering addresses or their IPv6 zone IDs.
        hostname = hostname.lower()
        with self._lock:
            if hostname not in self._hosts:
                self._hosts[hostname] = []
            else:
                for e in self._hosts[hostname]:
                    t, addr = e
                    # Compare complete addresses, allowing bracketed IPv6 input.
                    if addr == ipaddr or f"[{addr}]" == ipaddr:
                        return

            if _IPV6_ADDRZ_RE.match(ipaddr):
                self._hosts[hostname].append((socket.AF_INET6, ipaddr[1:-1]))
            elif is_ipv6(ipaddr):
                self._hosts[hostname].append((socket.AF_INET6, ipaddr))
            else:
                self._hosts[hostname].append((socket.AF_INET, ipaddr))

            if len(self._hosts) > self._maxsize:
                k = None
                for k in self._hosts.keys():
                    break
                if k:
                    self._hosts.pop(k)

    def clear(self, hostname: str) -> None:
        hostname = hostname.lower()
        with self._lock:
            if hostname in self._hosts:
                del self._hosts[hostname]

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
        if host is None:
            host = "localhost"  # Defensive: stdlib cpy behavior

        if port is None:
            port = 0  # Defensive: stdlib cpy behavior
        if isinstance(port, str):
            port = int(port)  # Defensive: stdlib cpy behavior
        if port < 0:
            raise socket.gaierror(  # Defensive: stdlib cpy behavior
                "Servname not supported for ai_socktype"
            )

        if isinstance(host, bytes):
            host = host.decode("ascii")  # Defensive: stdlib cpy behavior

        if is_ipv4(host):
            if family == socket.AF_INET6:
                raise socket.gaierror(  # Defensive: stdlib cpy behavior
                    "Address family for hostname not supported"
                )
            return [
                (
                    socket.AF_INET,
                    type,
                    6,
                    "",
                    (
                        host,
                        port,
                    ),
                )
            ]
        elif is_ipv6(host):
            if family == socket.AF_INET:
                raise socket.gaierror(  # Defensive: stdlib cpy behavior
                    "Address family for hostname not supported"
                )
            return [
                (
                    socket.AF_INET6,
                    type,
                    17,
                    "",
                    (
                        host,
                        port,
                        0,
                        0,
                    ),
                )
            ]

        host = host.lower()

        results: list[
            tuple[
                socket.AddressFamily,
                socket.SocketKind,
                int,
                str | bytes,
                tuple[str, int] | tuple[str, int, int, int],
            ]
        ] = []

        canonname: str | bytes = (
            self._ech_config_list if self._ech_config_list is not None else ""
        )

        with self._lock:
            if host not in self._hosts:
                raise socket.gaierror(f"no records found for hostname {host} in-memory")

            for entry in self._hosts[host]:
                addr_type, addr_target = entry

                if family != socket.AF_UNSPEC:
                    if family != addr_type:
                        continue

                results.append(
                    (
                        addr_type,
                        type,
                        6 if type == socket.SOCK_STREAM else 17,
                        canonname,
                        (addr_target, port)
                        if addr_type == socket.AF_INET
                        else (addr_target, port, 0, 0),
                    )
                )

        if not results:
            raise socket.gaierror(f"Name or service not known: '{host}'")

        return results
