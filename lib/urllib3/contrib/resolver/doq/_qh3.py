from __future__ import annotations

import socket
import typing

from ...anytls import ssl
from time import time as monotonic

from qh3.quic.configuration import QuicConfiguration
from qh3.quic.connection import QuicConnection
from qh3.quic.events import (
    ConnectionTerminated,
    HandshakeCompleted,
    QuicEvent,
    StopSendingReceived,
    StreamDataReceived,
    StreamReset,
)

from ....util.ssl_ import (
    IS_FIPS,
    _get_ca_certs,
    _load_default_certs_eagerly,
    resolve_cert_reqs,
)
from ....util.sub_timeout import SubTimeout
from ...ssa._gro import (
    GenericSegmentOffloadUnsupported,
    _sock_has_gro,
    _sock_has_gso,
    sync_recv_gro,
    sync_send_dgram,
    sync_sendmsg_gso,
)
from .._cache import ResolutionResult, cache_resolution, calculate_effective_ttl
from ..dou import PlainResolver
from ..protocols import (
    COMMON_RCODE_LABEL,
    DomainNameServerQuery,
    DomainNameServerParseException,
    DomainNameServerReturn,
    ProtocolResolver,
    SupportedQueryType,
)
from ..utils import (
    is_ipv4,
    is_ipv6,
    rfc1035_pack,
    validate_length_of,
)

SSLError = ssl.SSLError

if IS_FIPS:
    raise ImportError(
        "DNS-over-QUIC disabled when Python is built with FIPS-compliant ssl module"
    )


class QUICResolver(PlainResolver):
    protocol = ProtocolResolver.DOQ
    implementation = "qh3"

    def __init__(
        self,
        server: str,
        port: int | None = None,
        *patterns: str,
        **kwargs: typing.Any,
    ):
        super().__init__(server, port or 853, *patterns, **kwargs)

        # Export default trust for qh3; OpenSSL CA directories may still be lazy.
        if "ca_cert_data" not in kwargs and "ca_certs" not in kwargs:
            kwargs["ca_cert_data"] = []

            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

            try:
                ctx.load_default_certs()

                certificates = _get_ca_certs(ctx)
                if (
                    not certificates
                    and "ca_cert_dir" not in kwargs
                    and resolve_cert_reqs(kwargs.get("cert_reqs")) != ssl.CERT_NONE
                ):
                    _load_default_certs_eagerly(ctx)
                    certificates = _get_ca_certs(ctx)

                for der in certificates:
                    assert isinstance(der, bytes)
                    kwargs["ca_cert_data"].append(ssl.DER_cert_to_PEM_cert(der))

                if kwargs["ca_cert_data"]:
                    kwargs["ca_cert_data"] = "".join(kwargs["ca_cert_data"])
                else:
                    del kwargs["ca_cert_data"]
            except (AttributeError, ValueError, OSError):
                del kwargs["ca_cert_data"]

        if "ca_cert_data" not in kwargs and "ca_certs" not in kwargs:
            if (
                "cert_reqs" not in kwargs
                or resolve_cert_reqs(kwargs["cert_reqs"]) == ssl.CERT_REQUIRED
            ):
                # Construction fails before the caller can close the resolver.
                self._socket.close()
                raise ssl.SSLError(
                    "DoQ requires at least one CA loaded in order to verify the remote peer certificate. "
                    "Add ?cert_reqs=0 to disable certificate checks."
                )

        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=["doq"],
            server_name=(
                self._server
                if "server_hostname" not in kwargs
                else kwargs["server_hostname"]
            ),
            verify_mode=(
                resolve_cert_reqs(kwargs["cert_reqs"])
                if "cert_reqs" in kwargs
                else ssl.CERT_REQUIRED
            ),
            cadata=(
                kwargs["ca_cert_data"].encode() if "ca_cert_data" in kwargs else None
            ),
            cafile=kwargs["ca_certs"] if "ca_certs" in kwargs else None,
            idle_timeout=300.0,
        )

        if "cert_file" in kwargs:
            configuration.load_cert_chain(
                kwargs["cert_file"],
                kwargs["key_file"] if "key_file" in kwargs else None,
                kwargs["key_password"] if "key_password" in kwargs else None,
            )
        elif "cert_data" in kwargs:
            configuration.load_cert_chain(
                kwargs["cert_data"],
                kwargs["key_data"] if "key_data" in kwargs else None,
                kwargs["key_password"] if "key_password" in kwargs else None,
            )

        self._quic = QuicConnection(configuration=configuration)

        self._dgram_gro_enabled: bool = _sock_has_gro(self._socket)
        self._dgram_gso_enabled: bool = _sock_has_gso(self._socket)

        self._peer_addr = self._socket.getpeername()

        self._quic.connect(self._peer_addr, monotonic())
        try:
            self.__exchange_until(HandshakeCompleted, receive_first=False)
        except BaseException:
            # A failed constructor leaves the caller no resolver to close.
            self._socket.close()
            raise

        self._terminated: bool = False
        self._should_disconnect: bool = False

        # DNS over QUIC mandate the size-prefix (unsigned int, 2b)
        self._rfc1035_prefix_mandated = True

        # DoQ transactions are correlated by QUIC stream, never by DNS ID.
        self._pending: dict[int, DomainNameServerQuery] = {}
        self._completed: dict[int, DomainNameServerReturn] = {}
        self._response_buffers: dict[int, bytes] = {}
        self._stream_failures: dict[int, str] = {}

    def close(self) -> None:
        with self._lock:
            if not self._terminated:
                self._quic.close()

                while True:
                    datagrams = self._quic.datagrams_to_send(monotonic())

                    if not datagrams:
                        break

                    if (
                        self._dgram_gso_enabled and len(datagrams) > 1
                    ):  # Defensive: legacy qh3 may emit multiple close datagrams.
                        try:
                            sync_sendmsg_gso(self._socket, [d[0] for d in datagrams])
                        except GenericSegmentOffloadUnsupported:
                            self._dgram_gso_enabled = False
                            for datagram in datagrams:
                                sync_send_dgram(self._socket, datagram[0])
                    else:
                        for datagram in datagrams:
                            sync_send_dgram(self._socket, datagram[0])

            # Protocol termination does not close the underlying UDP socket.
            self._socket.close()
            self._terminated = True

    def is_available(self) -> bool:
        self._quic.handle_timer(monotonic())
        if hasattr(self._quic, "_close_event") and self._quic._close_event is not None:
            self._terminated = True
        return not self._terminated

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
                "Tried to resolve 'localhost' using the QUICResolver"
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

        queries = [DomainNameServerQuery(host, query_type, 0) for query_type in tbq]
        owned_streams: set[int] = set()
        responses: list[DomainNameServerReturn] = []
        try:
            with self._lock:
                for query in queries:
                    payload = rfc1035_pack(bytes(query))
                    stream_id = self._quic.get_next_available_stream_id()
                    self._pending[stream_id] = query
                    self._response_buffers[stream_id] = b""
                    owned_streams.add(stream_id)
                    self._quic.send_stream_data(stream_id, payload, True)

                    datagrams = self._quic.datagrams_to_send(monotonic())
                    if self._dgram_gso_enabled and len(datagrams) > 1:
                        try:
                            sync_sendmsg_gso(self._socket, [d[0] for d in datagrams])
                        except GenericSegmentOffloadUnsupported:
                            self._dgram_gso_enabled = False
                            for dg in datagrams:
                                sync_send_dgram(self._socket, dg[0])
                    else:
                        for dg in datagrams:
                            sync_send_dgram(self._socket, dg[0])

            while len(responses) < len(tbq):
                with self._lock:
                    responses = [
                        self._completed[stream_id]
                        for stream_id in owned_streams
                        if stream_id in self._completed
                    ]
                    failures = [
                        self._stream_failures[stream_id]
                        for stream_id in owned_streams
                        if stream_id in self._stream_failures
                    ]
                    if failures:
                        raise socket.gaierror(failures[0])
                    if len(responses) == len(tbq):
                        continue

                    try:
                        events: list[StreamDataReceived] = self.__exchange_until(  # type: ignore[assignment]
                            StreamDataReceived,
                            receive_first=True,
                            event_type_collectable=(StreamDataReceived,),
                            respect_end_stream_signal=False,
                        )
                    except (
                        TimeoutError,
                        OSError,
                        socket.timeout,
                        ConnectionError,
                    ) as e:
                        raise socket.gaierror(
                            "Got unexpectedly disconnected while waiting for name resolution"
                        ) from e

                    for event in events:
                        stream_id = event.stream_id
                        pending_query = self._pending.get(stream_id)
                        if pending_query is None or stream_id in self._completed:
                            continue

                        payload = (
                            self._response_buffers.get(stream_id, b"") + event.data
                        )
                        if len(payload) < 2:
                            if event.end_stream:
                                self._pending.pop(stream_id, None)
                                self._response_buffers.pop(stream_id, None)
                                self._stream_failures[stream_id] = (
                                    "DoQ stream ended before its response length was received"
                                )
                            else:
                                self._response_buffers[stream_id] = payload
                            continue

                        message_size = int.from_bytes(payload[:2], "big")
                        if len(payload) < message_size + 2:
                            if event.end_stream:
                                self._pending.pop(stream_id, None)
                                self._response_buffers.pop(stream_id, None)
                                self._stream_failures[stream_id] = (
                                    "DoQ stream ended with an incomplete DNS response"
                                )
                            else:
                                self._response_buffers[stream_id] = payload
                            continue

                        # RFC 9250 permits exactly one DNS message per stream.
                        self._response_buffers.pop(stream_id, None)
                        if len(payload) != message_size + 2:
                            self._pending.pop(stream_id, None)
                            self._stream_failures[stream_id] = (
                                "DoQ stream contained more than one DNS response"
                            )
                            continue
                        try:
                            dns_resp = DomainNameServerReturn(
                                payload[2 : message_size + 2]
                            )
                        except DomainNameServerParseException:
                            self._pending.pop(stream_id, None)
                            self._stream_failures[stream_id] = (
                                "DoQ stream contained a malformed DNS response"
                            )
                            continue

                        if (
                            dns_resp.id == 0
                            and dns_resp.matches(pending_query)
                            and stream_id not in self._completed
                        ):
                            self._completed[stream_id] = dns_resp
                        else:
                            self._pending.pop(stream_id, None)
                            self._stream_failures[stream_id] = (
                                "DoQ response did not match its query"
                            )
        finally:
            with self._lock:
                for stream_id in owned_streams:
                    self._pending.pop(stream_id, None)
                    self._completed.pop(stream_id, None)
                    self._response_buffers.pop(stream_id, None)
                    self._stream_failures.pop(stream_id, None)

        if self._should_disconnect:
            self.close()
            self._should_disconnect = False
            self._terminated = True

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

    def __exchange_until(
        self,
        event_type: type[QuicEvent] | tuple[type[QuicEvent], ...],
        *,
        receive_first: bool = False,
        event_type_collectable: (
            type[QuicEvent] | tuple[type[QuicEvent], ...] | None
        ) = None,
        respect_end_stream_signal: bool = True,
    ) -> list[QuicEvent]:
        quic = self._quic
        sock = self._socket
        gso_enabled = self._dgram_gso_enabled
        gro_enabled = self._dgram_gro_enabled

        def send_pending() -> None:
            nonlocal gso_enabled
            now = monotonic()
            quic.handle_timer(now)
            while True:
                datagrams = quic.datagrams_to_send(now)
                if not datagrams:
                    break
                if gso_enabled and len(datagrams) > 1:
                    try:
                        sync_sendmsg_gso(sock, [d[0] for d in datagrams])
                    except GenericSegmentOffloadUnsupported:
                        self._dgram_gso_enabled = gso_enabled = False
                        for datagram in datagrams:
                            sync_send_dgram(sock, datagram[0])
                else:
                    for datagram in datagrams:
                        sync_send_dgram(sock, datagram[0])

        while True:
            if receive_first is False:
                now = monotonic()
                while True:
                    datagrams = quic.datagrams_to_send(now)

                    if not datagrams:
                        break

                    if gso_enabled and len(datagrams) > 1:
                        try:
                            sync_sendmsg_gso(sock, [d[0] for d in datagrams])
                        except GenericSegmentOffloadUnsupported:
                            self._dgram_gso_enabled = gso_enabled = False
                            for datagram in datagrams:
                                sync_send_dgram(sock, datagram[0])
                    else:
                        for datagram in datagrams:
                            sync_send_dgram(sock, datagram[0])

            events = []

            while True:
                # qh3 records a close reason before its closing timer publishes an event.
                if not quic._events and getattr(quic, "_close_event", None) is None:
                    sub = SubTimeout(
                        sock,
                        quic.get_timer(),
                        send_pending,
                    )
                    with sub:
                        if gro_enabled:
                            data_in = sync_recv_gro(sock, 65535)
                        else:
                            data_in = sock.recv(1500)
                    if sub.timer_fired:
                        continue

                    if not data_in:
                        break

                    now = monotonic()

                    if isinstance(data_in, list):
                        for gro_segment in data_in:
                            quic.receive_datagram(gro_segment, self._peer_addr, now)
                    else:
                        quic.receive_datagram(data_in, self._peer_addr, now)

                    while True:
                        now = monotonic()
                        datagrams = quic.datagrams_to_send(now)

                        if not datagrams:
                            break

                        if gso_enabled and len(datagrams) > 1:
                            try:
                                sync_sendmsg_gso(sock, [d[0] for d in datagrams])
                            except GenericSegmentOffloadUnsupported:
                                self._dgram_gso_enabled = gso_enabled = False
                                for datagram in datagrams:
                                    sync_send_dgram(sock, datagram[0])
                        else:
                            for datagram in datagrams:
                                sync_send_dgram(sock, datagram[0])

                while True:
                    ev = quic.next_event()
                    if ev is None:
                        ev = getattr(quic, "_close_event", None)
                    if ev is None:
                        break
                    if isinstance(ev, ConnectionTerminated):
                        if ev.error_code == 298:
                            raise SSLError(
                                "DNS over QUIC did not succeed (Error 298). Chain certificate verification failed."
                            )
                        raise socket.gaierror(
                            f"DNS over QUIC encountered a unrecoverable failure (error {ev.error_code} {ev.reason_phrase})"
                        )
                    elif isinstance(ev, StreamReset):
                        self._terminated = True
                        raise socket.gaierror(
                            "DNS over QUIC server submitted a StreamReset. A request was rejected."
                        )
                    elif isinstance(ev, StopSendingReceived):
                        self._should_disconnect = True
                        continue

                    if event_type_collectable:
                        if isinstance(ev, event_type_collectable):
                            events.append(ev)
                    else:
                        events.append(ev)

                    if isinstance(ev, event_type):
                        if not respect_end_stream_signal:
                            return events
                        if (
                            hasattr(ev, "stream_ended") and ev.stream_ended
                        ):  # Defensive: current stream-data callers do not wait for end-of-stream here.
                            return events
                        elif hasattr(ev, "stream_ended") is False:
                            return events

            return events


class AdGuardResolver(
    QUICResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "adguard"

    def __init__(self, *patterns: str, **kwargs: typing.Any):
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None
        super().__init__("unfiltered.adguard-dns.com", port, *patterns, **kwargs)


class NextDNSResolver(
    QUICResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "nextdns"

    def __init__(self, *patterns: str, **kwargs: typing.Any):
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None
        super().__init__("dns.nextdns.io", port, *patterns, **kwargs)
