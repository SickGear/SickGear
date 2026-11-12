from __future__ import annotations

import socket
import secrets
import typing
from threading import Lock
from time import monotonic

from ....util.wait import wait_for_read, wait_for_write
from ...ssa._gro import _sock_has_gro, sync_recv_gro
from .._cache import (
    ResolutionResult,
    ResolverCache,
    cache_resolution,
    calculate_effective_ttl,
)
from ..protocols import (
    COMMON_RCODE_LABEL,
    BaseResolver,
    DomainNameServerQuery,
    DomainNameServerParseException,
    DomainNameServerReturn,
    ProtocolResolver,
    SupportedQueryType,
)
from ..system import SystemResolver
from ..utils import (
    _UDP_DEFAULT_TIMEOUT,
    _udp_retry_deadlines,
    is_ipv4,
    is_ipv6,
    validate_length_of,
)


class PlainResolver(BaseResolver):
    """
    Minimalist DNS resolver over UDP
    Comply with RFC 1035: https://datatracker.ietf.org/doc/html/rfc1035

    EDNS is not supported, yet. But we plan to. Willing to contribute?
    """

    protocol = ProtocolResolver.DOU
    implementation = "socket"

    def __init__(
        self,
        server: str,
        port: int | None = None,
        *patterns: str,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(server, port, *patterns, **kwargs)
        self._resolver_cache = ResolverCache(
            int(kwargs.pop("cache_maxsize", 1024)),
            int(kwargs.pop("cache_max_ttl", 60)),
        )

        if not hasattr(self, "_socket"):
            if "timeout" in kwargs and isinstance(
                kwargs["timeout"],
                (
                    float,
                    int,
                ),
            ):
                timeout = kwargs["timeout"]
            else:
                timeout = None

            if "source_address" in kwargs and isinstance(kwargs["source_address"], str):
                bind_ip, bind_port = kwargs["source_address"].split(":", 1)
            else:
                bind_ip, bind_port = "0.0.0.0", "0"

            self._socket = SystemResolver().create_connection(
                (server, port or 53),
                timeout=timeout,
                source_address=(
                    (bind_ip, int(bind_port))
                    if bind_ip != "0.0.0.0" or bind_port != "0"
                    else None
                ),
                socket_options=None,
                socket_kind=socket.SOCK_DGRAM,
            )

        #: Only useful for inheritance, e.g. DNS over TLS support dns-message but require a prefix.
        self._rfc1035_prefix_mandated: bool = False

        self._gro_enabled: bool = _sock_has_gro(self._socket)
        if self.protocol is ProtocolResolver.DOU:
            self._timeout = self._socket.gettimeout()
            self._read_lock = Lock()
            # UDP waits use per-lookup deadlines without changing a shared
            # socket timeout while other threads send queries.
            self._socket.setblocking(False)

        self._pending: dict[int, DomainNameServerQuery] = {}
        self._completed: dict[int, DomainNameServerReturn] = {}

        self._terminated: bool = False

    def close(self) -> None:
        if not self._terminated:
            with self._lock:
                if self._socket is not None:
                    self._socket.shutdown(0)
                    self._socket.close()
                self._terminated = True

    def is_available(self) -> bool:
        return not self._terminated

    def _reserve_queries(
        self, host: str, query_types: list[SupportedQueryType]
    ) -> list[DomainNameServerQuery]:
        with self._lock:
            if len(query_types) > 0x10000 - len(self._pending):
                raise socket.gaierror("DNS transaction ID space exhausted")

            queries = []
            for query_type in query_types:
                start = secrets.randbits(16)
                for offset in range(0x10000):
                    query_id = (start + offset) & 0xFFFF
                    if query_id not in self._pending:
                        query = DomainNameServerQuery(host, query_type, query_id)
                        self._pending[query_id] = query
                        queries.append(query)
                        break
                else:  # Defensive: the capacity check under this lock guarantees a free transaction ID.
                    raise socket.gaierror("DNS transaction ID space exhausted")
            return queries

    def _release_queries(self, queries: list[DomainNameServerQuery]) -> None:
        with self._lock:
            for query in queries:
                self._pending.pop(query.id, None)
                self._completed.pop(query.id, None)

    def _exchange(
        self, queries: list[DomainNameServerQuery]
    ) -> list[DomainNameServerReturn]:
        deadline = monotonic() + (
            self._timeout if self._timeout is not None else _UDP_DEFAULT_TIMEOUT
        )
        try:
            for attempt_deadline in _udp_retry_deadlines(deadline):
                with self._lock:
                    missing = [q for q in queries if q.id not in self._completed]
                for query in missing:
                    while monotonic() < attempt_deadline:
                        try:
                            self._socket.sendall(bytes(query))
                            break
                        except BlockingIOError:
                            if not wait_for_write(
                                self._socket, max(0, attempt_deadline - monotonic())
                            ):
                                break

                while monotonic() < attempt_deadline:
                    with self._lock:
                        if self._terminated:
                            raise OSError("DNS resolver is closed")
                        if all(q.id in self._completed for q in queries):
                            return [self._completed[q.id] for q in queries]
                    if not self._read_lock.acquire(
                        timeout=max(0, attempt_deadline - monotonic())
                    ):
                        break
                    try:
                        with self._lock:
                            if self._terminated:
                                raise OSError("DNS resolver is closed")
                            if all(q.id in self._completed for q in queries):
                                return [self._completed[q.id] for q in queries]
                        if not wait_for_read(
                            self._socket, max(0, attempt_deadline - monotonic())
                        ):
                            break
                        try:
                            data = (
                                sync_recv_gro(self._socket, 65535)
                                if self._gro_enabled
                                else self._socket.recv(1500)
                            )
                        except BlockingIOError:
                            continue
                        with self._lock:
                            for payload in data if isinstance(data, list) else (data,):
                                try:
                                    response = DomainNameServerReturn(
                                        payload, ignore_truncated_https=True
                                    )
                                except DomainNameServerParseException:
                                    continue
                                pending_query = self._pending.get(response.id)
                                if pending_query is not None and response.matches(
                                    pending_query
                                ):
                                    self._completed.setdefault(response.id, response)
                    finally:
                        self._read_lock.release()
            # Another reader may have collected our answers while we waited
            # for read ownership, including during the final attempt.
            with self._lock:
                if self._terminated:
                    raise OSError("DNS resolver is closed")
                if all(q.id in self._completed for q in queries):
                    return [self._completed[q.id] for q in queries]
        except (OSError, ValueError) as e:
            raise socket.gaierror(
                "Got unexpectedly disconnected while waiting for name resolution"
            ) from e
        raise socket.gaierror(socket.EAI_AGAIN, "DNS resolution timed out")

    @cache_resolution
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
            raise socket.gaierror(  # Defensive: stdlib cpy behavior
                "Tried to resolve 'localhost' from a PlainResolver"
            )

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

        validate_length_of(host)

        remote_preemptive_quic_rr = False
        ech_config_list: bytes | None = None

        if quic_upgrade_via_dns_rr and type == socket.SOCK_DGRAM:
            quic_upgrade_via_dns_rr = False

        tbq = []

        if family in [socket.AF_UNSPEC, socket.AF_INET]:
            tbq.append(SupportedQueryType.A)

        if family in [socket.AF_UNSPEC, socket.AF_INET6]:
            tbq.append(SupportedQueryType.AAAA)

        tbq.append(SupportedQueryType.HTTPS)

        queries = self._reserve_queries(host, tbq)
        try:
            responses = self._exchange(queries)
        finally:
            self._release_queries(queries)

        results: list[
            tuple[
                socket.AddressFamily,
                socket.SocketKind,
                int,
                str | bytes,
                tuple[str, int] | tuple[str, int, int, int],
            ]
        ] = []

        for response in responses:
            if not response.is_ok:
                if response.rcode == 2:
                    raise socket.gaierror(
                        f"DNSSEC validation failure. Check http://dnsviz.net/d/{host}/dnssec/ and http://dnssec-debugger.verisignlabs.com/{host} for errors"
                    )
                raise socket.gaierror(
                    f"DNS returned an error: {COMMON_RCODE_LABEL[response.rcode] if response.rcode in COMMON_RCODE_LABEL else f'code {response.rcode}'}"
                )

            for record in response.records:
                if record[0] == SupportedQueryType.HTTPS:
                    assert isinstance(record[-1], dict)
                    if record[-1]["echconfig"]:
                        ech_config_list = record[-1]["echconfig"]
                    if "h3" in record[-1]["alpn"] and quic_upgrade_via_dns_rr:
                        remote_preemptive_quic_rr = True
                    continue

                assert not isinstance(record[-1], dict)

                inet_type = (
                    socket.AF_INET
                    if record[0] == SupportedQueryType.A
                    else socket.AF_INET6
                )
                dst_addr: tuple[str, int] | tuple[str, int, int, int] = (
                    (
                        record[-1],
                        port,
                    )
                    if inet_type == socket.AF_INET
                    else (
                        record[-1],
                        port,
                        0,
                        0,
                    )
                )

                results.append(
                    (
                        inet_type,
                        type,
                        6 if type == socket.SOCK_STREAM else 17,
                        "",
                        dst_addr,
                    )
                )

        quic_results: list[
            tuple[
                socket.AddressFamily,
                socket.SocketKind,
                int,
                str | bytes,
                tuple[str, int] | tuple[str, int, int, int],
            ]
        ] = []

        if remote_preemptive_quic_rr:
            any_specified = False

            for result in results:
                if result[1] == socket.SOCK_STREAM:
                    quic_results.append(
                        (result[0], socket.SOCK_DGRAM, 17, "", result[4])
                    )
                else:
                    any_specified = True
                    break

            if any_specified:
                quic_results = []

        if ech_config_list is not None:
            results = [(r[0], r[1], r[2], ech_config_list, r[4]) for r in results]
            quic_results = [
                (r[0], r[1], r[2], ech_config_list, r[4]) for r in quic_results
            ]

        if not results and not quic_results:
            raise socket.gaierror(f"Name or service not known: '{host}'")

        ttl = calculate_effective_ttl(
            ttl for response in responses for ttl in response.answer_ttls
        )
        return ResolutionResult(
            sorted(quic_results + results, key=lambda _: _[0] + _[1], reverse=True),
            ttl,
        )


class CloudflareResolver(
    PlainResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "cloudflare"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("1.1.1.1", port, *patterns, **kwargs)


class GoogleResolver(
    PlainResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "google"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("8.8.8.8", port, *patterns, **kwargs)


class Quad9Resolver(
    PlainResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "quad9"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("9.9.9.9", port, *patterns, **kwargs)


class AdGuardResolver(
    PlainResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "adguard"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("94.140.14.140", port, *patterns, **kwargs)
