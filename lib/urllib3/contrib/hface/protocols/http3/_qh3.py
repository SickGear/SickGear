# Copyright 2022 Akamai Technologies, Inc
# Largely rewritten in 2023 for urllib3-future
# Copyright 2024 Ahmed Tahri
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import datetime
import ssl
import typing
from collections import deque
from os import environ
from time import time as monotonic
from typing import Any

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

from qh3 import (
    H3Connection,
    H3Error,
    ProtocolError,
    QuicConfiguration,
    QuicConnection,
    QuicConnectionError,
    QuicFileLogger,
    SessionTicket,
    h3_events,
    quic_events,
)
from qh3.h3.connection import ErrorCode as H3ErrorCode
from qh3.quic.connection import QuicConnectionState
from qh3.quic.packet import QuicErrorCode
from qh3.tls import AlertDescription

from ..._configuration import QuicTLSConfig
from ..._stream_matrix import StreamMatrix
from ..._typing import AddressType, HeadersType
from ...events import (
    ConnectionTerminated,
    DataReceived,
    EarlyHeadersReceived,
    Event,
    GoawayReceived,
)
from ...events import (
    HandshakeCompleted as _HandshakeCompleted,
    HeadersReceived,
    StreamResetReceived,
    StreamStopSendingReceived,
)
from .._protocols import HTTP3Protocol


QUIC_RELEVANT_EVENT_TYPES = {
    quic_events.HandshakeCompleted,
    quic_events.ConnectionTerminated,
    quic_events.StreamReset,
    quic_events.PingAcknowledged,
}

if hasattr(quic_events, "StopSendingReceived"):
    STOP_SENDING_EVENT_AVAILABLE = True
    QUIC_RELEVANT_EVENT_TYPES.add(quic_events.StopSendingReceived)
else:  # Defensive: older qh3 releases do not expose STOP_SENDING events.
    STOP_SENDING_EVENT_AVAILABLE = False

_SHORT_NAME_ASSOC = {
    "CN": "commonName",
    "L": "localityName",
    "ST": "stateOrProvinceName",
    "O": "organizationName",
    "OU": "organizationalUnitName",
    "C": "countryName",
    "STREET": "streetAddress",
    "DC": "domainComponent",
    "E": "email",
}

# v1.8+ introduced H3 Goaway event
_QH3_H3_HAVE_GA_EV: bool = hasattr(h3_events, "GoawayReceived")


class HTTP3ProtocolAioQuicImpl(HTTP3Protocol):
    implementation: str = "qh3"

    def __init__(
        self,
        *,
        remote_address: AddressType,
        server_name: str,
        tls_config: QuicTLSConfig,
    ) -> None:
        keylogfile_path: str | None = environ.get("SSLKEYLOGFILE", None)
        qlogdir_path: str | None = environ.get("QUICLOGDIR", None)

        self._configuration: QuicConfiguration = QuicConfiguration(
            is_client=True,
            verify_mode=ssl.CERT_NONE if tls_config.insecure else ssl.CERT_REQUIRED,
            cafile=tls_config.cafile,
            capath=tls_config.capath,
            cadata=tls_config.cadata,
            alpn_protocols=["h3"],
            session_ticket=tls_config.session_ticket,
            server_name=server_name,
            hostname_checks_common_name=tls_config.cert_use_common_name,
            assert_fingerprint=tls_config.cert_fingerprint,
            verify_hostname=tls_config.verify_hostname,
            secrets_log_file=open(keylogfile_path, "w") if keylogfile_path else None,  # type: ignore[arg-type]
            quic_logger=QuicFileLogger(qlogdir_path) if qlogdir_path else None,
            idle_timeout=tls_config.idle_timeout,
            max_data=15728640,
            max_stream_data=6291456,
        )

        # infer support for encrypted hello!
        # qh3 introduced its support since v1.7.0
        if hasattr(self._configuration, "ech_config_list"):
            self._configuration.ech_config_list = tls_config.ech_config_list

        if tls_config.certfile:
            self._configuration.load_cert_chain(
                tls_config.certfile,
                tls_config.keyfile,
                tls_config.keypassword,
            )

        self._quic: QuicConnection = QuicConnection(configuration=self._configuration)
        self._connection_ids: set[bytes] = set()
        self._remote_address = remote_address
        self._events: StreamMatrix = StreamMatrix()
        self._packets: deque[bytes] = deque()
        self._http: H3Connection | None = None
        self._terminated: bool = False
        self._open_streams: set[int] = set()
        self._sending_streams: set[int] = set()
        self._total_stream_count: int = 0
        self._goaway_to_honor: bool = False
        self._max_frame_size: int | None = None
        self._next_timer: float | None = None

        self._last_ping_uid: int = 0
        self._pending_ping_ack: deque[int] = deque()

    def next_timer(self) -> float | None:
        self._next_timer = self._quic.get_timer()
        return self._next_timer

    @staticmethod
    def exceptions() -> tuple[type[BaseException], ...]:
        return ProtocolError, H3Error, QuicConnectionError, AssertionError

    def is_available(self) -> bool:
        if self._terminated or self._goaway_to_honor:
            return False
        opened = self._quic._local_next_stream_id_bidi // 4
        granted = self._quic.max_concurrent_bidi_streams
        return granted > opened

    def is_idle(self) -> bool:
        if self._events.stream_count:
            return False
        return (
            not self._terminated
            and not self._open_streams
            and not self._sending_streams
        )

    def has_expired(self) -> bool:
        if not self._terminated and not self._goaway_to_honor:
            if len(self._pending_ping_ack) >= 2:
                self._quic.close()
                self._terminated = True
            else:
                now = monotonic()
                try:
                    self._quic.handle_timer(now)
                except TypeError:  # Defensive: old qh3 bug
                    pass
                if self._quic._state in {
                    QuicConnectionState.CLOSING,
                    QuicConnectionState.TERMINATED,
                }:
                    self._terminated = True
                if getattr(self._quic, "_close_event", None) is not None:
                    qe = self._map_quic_event(self._quic._close_event)  # type: ignore[arg-type]
                    assert qe is not None
                    self._events.append(qe)
                    self._terminated = True
        return (
            self._terminated or self._goaway_to_honor
        ) and not self._events.stream_count

    @property
    def session_ticket(self) -> SessionTicket | None:
        return (
            self._quic.tls.session_ticket if self._quic and self._quic.tls else None
        )  # Defensive: unused legacy session-ticket accessor.

    def get_available_stream_id(self) -> int:
        return self._quic.get_next_available_stream_id()

    def submit_close(self, error_code: int = 0) -> None:
        # QUIC has two different frame types for closing the connection.
        # From RFC 9000 (QUIC: A UDP-Based Multiplexed and Secure Transport):
        #
        # > An endpoint sends a CONNECTION_CLOSE frame (type=0x1c or 0x1d)
        # > to notify its peer that the connection is being closed.
        # > The CONNECTION_CLOSE frame with a type of 0x1c is used to signal errors
        # > at only the QUIC layer, or the absence of errors (with the NO_ERROR code).
        # > The CONNECTION_CLOSE frame with a type of 0x1d is used
        # > to signal an error with the application that uses QUIC.
        frame_type = 0x1D if error_code else 0x1C
        self._quic.close(error_code=error_code, frame_type=frame_type)

    def submit_headers(
        self, stream_id: int, headers: HeadersType, end_stream: bool = False
    ) -> None:
        assert self._http is not None
        self._open_streams.add(stream_id)
        if not end_stream:
            self._sending_streams.add(stream_id)
        self._total_stream_count += 1
        self._http.send_headers(stream_id, headers, end_stream)  # type: ignore[arg-type]

    def submit_data(
        self, stream_id: int, data: bytes, end_stream: bool = False
    ) -> None:
        assert self._http is not None
        # STOP_SENDING may finish this direction before extension cleanup sends FIN.
        if end_stream and not data and stream_id not in self._sending_streams:
            return
        self._http.send_data(stream_id, data, end_stream)
        if end_stream:
            self._sending_streams.discard(stream_id)

    def submit_stream_reset(self, stream_id: int, error_code: int = 0x10C) -> None:
        """Discard local events and cancel unfinished directions (H3_REQUEST_CANCELLED)."""
        self._events.discard(stream_id)
        assert self._http is not None
        stream = self._http._stream.get(stream_id)
        if stream_id in self._open_streams:
            self._open_streams.discard(stream_id)
            # FIN may already have arrived while HTTP/3 is decoding trailers.
            if stream is None or not getattr(stream, "receiving_ended", stream.ended):
                self._quic.stop_stream(stream_id, error_code)
        if stream_id in self._sending_streams:
            self._sending_streams.discard(stream_id)
            self._quic.reset_stream(stream_id, error_code)
        if stream is not None and stream.blocked:
            # QPACK may still need this context to finish decoding trailers.
            # Keep its bookkeeping, but release payload and never deliver its events.
            stream.buffer = type(stream.buffer)()
            stream.ended = True
            stream.receiving_ended = True
            stream.sending_ended = True
        else:
            self._http._stream.pop(stream_id, None)

    def next_event(self, stream_id: int | None = None) -> Event | None:
        return self._events.popleft(stream_id)

    def has_pending_event(
        self,
        *,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> bool:
        return self._events.has(stream_id=stream_id, excl_event=excl_event)

    def connection_lost(self) -> None:
        self._terminated = True
        self._events.append(ConnectionTerminated())

    def bytes_received(self, data: bytes) -> None:
        quic = self._quic
        quic.receive_datagram(data, self._remote_address, now=monotonic())
        self._fetch_events()

        remote_max = quic._remote_max_stream_data_bidi_remote

        if remote_max and remote_max != self._max_frame_size:
            self._max_frame_size = remote_max

    def many_bytes_received(self, data: list[bytes]) -> None:
        quic = self._quic
        receive_many_datagrams = getattr(quic, "receive_many_datagrams", None)

        if (
            receive_many_datagrams is None
        ):  # Defensive: older qh3 only exposes single-datagram input.
            for datagram in data:
                self.bytes_received(datagram)
            return

        receive_many_datagrams(data, self._remote_address, now=monotonic())
        self._fetch_events()

        remote_max = quic._remote_max_stream_data_bidi_remote

        if remote_max and remote_max != self._max_frame_size:
            self._max_frame_size = remote_max

    def bytes_to_send(self) -> bytes:
        now = monotonic()

        if self._http is None:
            self._quic.connect(self._remote_address, now=now)
            self._http = H3Connection(self._quic)

        timer_expired = self._next_timer is not None and now >= self._next_timer

        if not self._packets or timer_expired:
            if timer_expired:
                try:
                    self._quic.handle_timer(now)
                except TypeError:  # Defensive: old qh3 bug
                    pass
            # the QUIC state machine returns datagrams (addr, packet)
            # the client never have to worry about the destination
            # unless server yield a preferred address?
            self._packets.extend(e[0] for e in self._quic.datagrams_to_send(now=now))
            self._next_timer = self._quic.get_timer()

        if not self._packets:
            return b""

        # it is absolutely crucial to return one at a time
        # because UDP don't support sending more than
        # MTU (to be more precise, lowest MTU in the network path from A (you) to B (server))
        return self._packets.popleft()

    def _fetch_events(self) -> None:
        assert self._http is not None

        for quic_event in iter(self._quic.next_event, None):
            if (
                isinstance(quic_event, quic_events.StreamDataReceived)
                and quic_event.stream_id % 4 == 0
                and quic_event.stream_id not in self._open_streams
            ):
                # QUIC still processes transport/flow control; abandoned payload
                # must not recreate HTTP/3 stream buffers or application events.
                continue
            qe = self._map_quic_event(quic_event)

            if qe is not None:
                self._events.append(qe)

            try:
                http_events = self._http.handle_event(quic_event)
            except QuicConnectionError:
                close_event = getattr(self._quic, "_close_event", None)
                if close_event is None:
                    raise  # Defensive: unexpected qh3 failure without a recorded close.
                # Responding to queued SETTINGS can fail after TLS already rejected us.
                # Preserve that cause for the backend's event handling.
                qe = self._map_quic_event(close_event)
                assert qe is not None
                self._events.append(qe)
                return
            for h3_event in http_events:
                he = self._map_h3_event(h3_event)

                if he is not None:
                    self._events.append(he)

        if getattr(self._quic, "_close_event", None) is not None:
            qe = self._map_quic_event(self._quic._close_event)  # type: ignore[arg-type]
            assert qe is not None
            self._events.append(qe)

    def _map_quic_event(
        self,
        quic_event: quic_events.QuicEvent,
    ) -> Event | None:
        event_type = quic_event.__class__

        # fastest path execution, most of the time we don't have those
        # 3 event types.
        if event_type not in QUIC_RELEVANT_EVENT_TYPES:
            return None

        if event_type is quic_events.HandshakeCompleted:
            return _HandshakeCompleted(quic_event.alpn_protocol)  # type: ignore[attr-defined]

        if event_type is quic_events.ConnectionTerminated:
            self._terminated = True
            termination = typing.cast(quic_events.ConnectionTerminated, quic_event)
            error_code = termination.error_code
            is_tls_error = (
                termination.frame_type is not None and 0x100 <= error_code < 0x200
            )
            try:
                # Application closes omit the triggering frame type. Transport
                # closes use a separate namespace, including TLS alerts at 0x100.
                if termination.frame_type is None:
                    error_name = H3ErrorCode(error_code).name
                elif is_tls_error:
                    error_name = (
                        f"TLS_{AlertDescription(error_code - 0x100).name.upper()}"
                    )
                else:
                    error_name = QuicErrorCode(error_code).name
            except ValueError:
                error_name = "UNKNOWN_ERROR"
            message = f"HTTP/3 connection terminated with error {error_name} ({error_code:#x})."
            if termination.reason_phrase:
                message += f" {termination.reason_phrase}"
            return ConnectionTerminated(error_code, message, is_tls_error=is_tls_error)

        if event_type is quic_events.StreamReset:
            stream_id = quic_event.stream_id  # type: ignore[attr-defined]
            if stream_id not in self._open_streams:
                return None
            self._open_streams.discard(stream_id)
            return StreamResetReceived(
                quic_event.stream_id,  # type: ignore[attr-defined]
                quic_event.error_code,  # type: ignore[attr-defined]
            )

        if (
            STOP_SENDING_EVENT_AVAILABLE
            and event_type is quic_events.StopSendingReceived
        ):
            stream_id = quic_event.stream_id  # type: ignore[attr-defined]
            if stream_id in self._sending_streams:
                self._sending_streams.discard(stream_id)
                # A completed/discarded response must not regain pending events.
                if stream_id in self._open_streams:
                    return StreamStopSendingReceived(
                        stream_id,
                        quic_event.error_code,  # type: ignore[attr-defined]
                    )
            return None

        if event_type is quic_events.PingAcknowledged:
            try:
                self._pending_ping_ack.remove(quic_event.uid)  # type: ignore[attr-defined]
            except ValueError:  # Defensive: duplicate or untracked acknowledgement.
                pass

        return None

    def _map_h3_event(
        self,
        h3_event: h3_events.H3Event,
    ) -> Event | None:
        event_type = h3_event.__class__

        if event_type is h3_events.DataReceived:
            if h3_event.stream_id not in self._open_streams:  # type: ignore[attr-defined]
                return None  # Defensive: transport events for discarded streams are filtered earlier.
            stream_ended = h3_event.stream_ended  # type: ignore[attr-defined]
            if stream_ended:
                self._open_streams.discard(h3_event.stream_id)  # type: ignore[attr-defined]
            return DataReceived(
                h3_event.stream_id,  # type: ignore[attr-defined]
                h3_event.data,  # type: ignore[attr-defined]
                stream_ended,
            )

        if event_type is h3_events.HeadersReceived:
            if h3_event.stream_id not in self._open_streams:  # type: ignore[attr-defined]
                return None
            stream_ended = h3_event.stream_ended  # type: ignore[attr-defined]
            if stream_ended:
                self._open_streams.discard(h3_event.stream_id)  # type: ignore[attr-defined]
            return HeadersReceived(
                h3_event.stream_id,  # type: ignore[attr-defined]
                h3_event.headers,  # type: ignore[attr-defined]
                stream_ended,
            )

        if event_type is h3_events.InformationalHeadersReceived:
            if h3_event.stream_id not in self._open_streams:  # type: ignore[attr-defined]
                return None  # Defensive: transport events for discarded streams are filtered earlier.
            return EarlyHeadersReceived(
                h3_event.stream_id,  # type: ignore[attr-defined]
                h3_event.headers,  # type: ignore[attr-defined]
            )

        if _QH3_H3_HAVE_GA_EV and event_type is h3_events.GoawayReceived:
            self._goaway_to_honor = True
            return GoawayReceived(h3_event.stream_id)  # type: ignore[attr-defined]

        return None

    def should_wait_remote_flow_control(
        self, stream_id: int, amt: int | None = None
    ) -> bool | None:
        # accessing our QUIC loss detector
        # yes, we now, it's private, and we
        # also maintain qh3, so we're aware.
        if hasattr(
            self._quic, "_loss"
        ):  # Defensive: legacy qh3 loss-detector API, absent from CI versions.
            loss = self._quic._loss

            # At least 2 ack-eliciting packets outstanding.
            # RFC 9000 section 13.2.1
            # - ACK after the peer receives <= 2 ack-eliciting packets.
            # - ACK within the peer's negotiated max_ack_delay (<= 25 ms by default).
            n_outstanding = sum(s.ack_eliciting_in_flight for s in loss.spaces)

            if n_outstanding >= 2:
                return True

            now = monotonic()

            # Or max_ack_delay elapsed since the last ack-eliciting send.
            # Yes, we know, it's approximative, borderline heuristic
            if n_outstanding >= 1:
                deadline = (
                    loss._time_of_last_sent_ack_eliciting_packet + loss.max_ack_delay
                )
                if now >= deadline:
                    return True
        elif hasattr(self._quic, "should_wait_for_ack"):
            return self._quic.should_wait_for_ack(monotonic())

        return False  # Defensive: legacy qh3 without an ACK-wait query.

    @typing.overload
    def getissuercert(self, *, binary_form: Literal[True]) -> bytes | None: ...

    @typing.overload
    def getissuercert(
        self, *, binary_form: Literal[False] = ...
    ) -> dict[str, Any] | None: ...

    def getissuercert(
        self, *, binary_form: bool = False
    ) -> bytes | dict[str, typing.Any] | None:
        x509_certificate = self._quic.get_peercert()

        if x509_certificate is None:
            raise ValueError(  # Defensive: the backend reads certificates only after the handshake.
                "TLS handshake has not been done yet"
            )

        if not self._quic.get_issuercerts():
            return None

        x509_certificate = self._quic.get_issuercerts()[0]

        if binary_form:
            return x509_certificate.public_bytes()

        issuer_info = {
            "version": x509_certificate.version + 1,
            "serialNumber": x509_certificate.serial_number.upper(),
            "subject": [],
            "issuer": [],
            "notBefore": datetime.datetime.fromtimestamp(
                x509_certificate.not_valid_before, tz=datetime.timezone.utc
            ).strftime("%b %d %H:%M:%S %Y")
            + " UTC",
            "notAfter": datetime.datetime.fromtimestamp(
                x509_certificate.not_valid_after, tz=datetime.timezone.utc
            ).strftime("%b %d %H:%M:%S %Y")
            + " UTC",
        }

        for raw_oid, rfc4514_attribute_name, value in x509_certificate.subject:
            if rfc4514_attribute_name not in _SHORT_NAME_ASSOC:
                continue  # Defensive: omit certificate attributes outside the compatibility mapping.
            issuer_info["subject"].append(  # type: ignore[attr-defined]
                (
                    (
                        _SHORT_NAME_ASSOC[rfc4514_attribute_name],
                        value.decode(),
                    ),
                )
            )

        for raw_oid, rfc4514_attribute_name, value in x509_certificate.issuer:
            if rfc4514_attribute_name not in _SHORT_NAME_ASSOC:
                continue  # Defensive: omit certificate attributes outside the compatibility mapping.
            issuer_info["issuer"].append(  # type: ignore[attr-defined]
                (
                    (
                        _SHORT_NAME_ASSOC[rfc4514_attribute_name],
                        value.decode(),
                    ),
                )
            )

        return issuer_info

    @typing.overload
    def getpeercert(self, *, binary_form: Literal[True]) -> bytes: ...

    @typing.overload
    def getpeercert(self, *, binary_form: Literal[False] = ...) -> dict[str, Any]: ...

    def getpeercert(
        self, *, binary_form: bool = False
    ) -> bytes | dict[str, typing.Any]:
        x509_certificate = self._quic.get_peercert()

        if x509_certificate is None:
            raise ValueError(  # Defensive: the backend reads certificates only after the handshake.
                "TLS handshake has not been done yet"
            )

        if binary_form:
            return x509_certificate.public_bytes()

        peer_info = {
            "version": x509_certificate.version + 1,
            "serialNumber": x509_certificate.serial_number.upper(),
            "subject": [],
            "issuer": [],
            "notBefore": datetime.datetime.fromtimestamp(
                x509_certificate.not_valid_before, tz=datetime.timezone.utc
            ).strftime("%b %d %H:%M:%S %Y")
            + " UTC",
            "notAfter": datetime.datetime.fromtimestamp(
                x509_certificate.not_valid_after, tz=datetime.timezone.utc
            ).strftime("%b %d %H:%M:%S %Y")
            + " UTC",
            "subjectAltName": [],
            "OCSP": [],
            "caIssuers": [],
            "crlDistributionPoints": [],
        }

        for raw_oid, rfc4514_attribute_name, value in x509_certificate.subject:
            if rfc4514_attribute_name not in _SHORT_NAME_ASSOC:
                continue  # Defensive: omit certificate attributes outside the compatibility mapping.
            peer_info["subject"].append(  # type: ignore[attr-defined]
                (
                    (
                        _SHORT_NAME_ASSOC[rfc4514_attribute_name],
                        value.decode(),
                    ),
                )
            )

        for raw_oid, rfc4514_attribute_name, value in x509_certificate.issuer:
            if rfc4514_attribute_name not in _SHORT_NAME_ASSOC:
                continue  # Defensive: omit certificate attributes outside the compatibility mapping.
            peer_info["issuer"].append(  # type: ignore[attr-defined]
                (
                    (
                        _SHORT_NAME_ASSOC[rfc4514_attribute_name],
                        value.decode(),
                    ),
                )
            )

        for alt_name in x509_certificate.get_subject_alt_names():
            decoded_alt_name = alt_name.decode()
            in_parenthesis = decoded_alt_name[
                decoded_alt_name.index("(") + 1 : decoded_alt_name.index(")")
            ]
            if decoded_alt_name.startswith("DNS"):
                peer_info["subjectAltName"].append(("DNS", in_parenthesis))  # type: ignore[attr-defined]
            else:
                from ....resolver.utils import inet4_ntoa, inet6_ntoa

                if len(in_parenthesis) == 11:
                    ip_address_decoded = inet4_ntoa(
                        bytes.fromhex(in_parenthesis.replace(":", ""))
                    )
                else:
                    ip_address_decoded = inet6_ntoa(
                        bytes.fromhex(in_parenthesis.replace(":", ""))
                    )
                peer_info["subjectAltName"].append(("IP Address", ip_address_decoded))  # type: ignore[attr-defined]

        for endpoint in x509_certificate.get_ocsp_endpoints():
            decoded_endpoint = endpoint.decode()

            peer_info["OCSP"].append(  # type: ignore[attr-defined]
                decoded_endpoint[decoded_endpoint.index("(") + 1 : -1]
            )

        for endpoint in x509_certificate.get_issuer_endpoints():
            decoded_endpoint = endpoint.decode()
            peer_info["caIssuers"].append(  # type: ignore[attr-defined]
                decoded_endpoint[decoded_endpoint.index("(") + 1 : -1]
            )

        for endpoint in x509_certificate.get_crl_endpoints():
            decoded_endpoint = endpoint.decode()
            peer_info["crlDistributionPoints"].append(  # type: ignore[attr-defined]
                decoded_endpoint[decoded_endpoint.index("(") + 1 : -1]
            )

        pop_keys = []

        for k in peer_info:
            if isinstance(peer_info[k], list):
                peer_info[k] = tuple(peer_info[k])  # type: ignore[arg-type]
                if not peer_info[k]:
                    pop_keys.append(k)

        for k in pop_keys:
            peer_info.pop(k)

        return peer_info

    def cipher(self) -> str | None:
        cipher_suite = self._quic.get_cipher()

        if cipher_suite is None:
            raise ValueError(  # Defensive: backend queries the cipher only after the handshake.
                "TLS handshake has not been done yet"
            )

        return f"TLS_{cipher_suite.name}"

    def ech_accepted(self) -> bool:
        if not hasattr(self._quic, "ech_accepted"):
            return False  # Defensive: older qh3 releases do not report ECH acceptance.
        return self._quic.ech_accepted

    def reshelve(self, *events: Event) -> None:
        for ev in reversed(events):
            self._events.appendleft(ev)

    def ping(self) -> None:
        self._pending_ping_ack.append(self._last_ping_uid)
        self._quic.send_ping(self._last_ping_uid)
        self._last_ping_uid += 1

    def expect_pong(self) -> bool:
        return bool(self._pending_ping_ack)

    def max_frame_size(self) -> int:
        if self._max_frame_size is not None:
            return self._max_frame_size

        raise NotImplementedError
