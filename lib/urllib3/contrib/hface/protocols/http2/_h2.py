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

from collections import deque
from secrets import token_bytes
from typing import Iterator

import jh2.config  # type: ignore
import jh2.connection  # type: ignore
import jh2.errors  # type: ignore
import jh2.events  # type: ignore
import jh2.exceptions  # type: ignore
import jh2.settings  # type: ignore

from jh2 import __version__ as jh2_version  # type: ignore[attr-defined]

from ..._stream_matrix import StreamMatrix
from ..._typing import HeadersType
from ...events import (
    ConnectionTerminated,
    DataReceived,
    EarlyHeadersReceived,
    Event,
    GoawayReceived,
    HandshakeCompleted,
    HeadersReceived,
    StreamResetReceived,
)
from .._protocols import HTTP2Protocol


# h2 state machine had a couple of issues
# we were locked in on some settings and
# attempting to change them resulted in weird
# issues. see https://github.com/jawah/h2/releases/tag/v5.0.12
JH2_NOT_RFC_COMPLIANT_SETTINGS: bool = tuple(
    int(p) for p in jh2_version.split(".", maxsplit=3)[:3]
) <= (5, 0, 11)
HTTP2_INITIAL_CONNECTION_WINDOW_SIZE = 2**16 - 1


class _PatchedH2Connection(jh2.connection.H2Connection):  # type: ignore[misc]
    """
    This is a performance hotfix class. We internally, already keep
    track of the open stream count.
    """

    def __init__(
        self,
        config: jh2.config.H2Configuration | None = None,
        observable_impl: HTTP2ProtocolHyperImpl | None = None,
    ) -> None:
        super().__init__(config=config)
        # by default CONNECT is disabled
        # we need it to support natively WebSocket over HTTP/2 for example.
        if not JH2_NOT_RFC_COMPLIANT_SETTINGS:
            initial_settings = {
                jh2.settings.SettingCodes.HEADER_TABLE_SIZE: 65536,
                jh2.settings.SettingCodes.ENABLE_PUSH: 0,  # we don't support it anyway for now.
                jh2.settings.SettingCodes.INITIAL_WINDOW_SIZE: 6291456,
                jh2.settings.SettingCodes.MAX_HEADER_LIST_SIZE: 262144,
            }
        else:  # Defensive: legacy, non-RFC-compliant settings in jh2 <= 5.0.11.
            initial_settings = {
                jh2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 100,
                jh2.settings.SettingCodes.MAX_HEADER_LIST_SIZE: self.DEFAULT_MAX_HEADER_LIST_SIZE,
            }
        self.local_settings = jh2.settings.Settings(
            client=True,
            initial_values=initial_settings,
        )
        self._observable_impl = observable_impl

    def _open_streams(self, *args, **kwargs) -> int:  # type: ignore[no-untyped-def]
        if self._observable_impl is not None:
            return len(self._observable_impl._open_streams)
        return super()._open_streams(*args, **kwargs)  # type: ignore[no-any-return]  # Defensive: unreachable

    def _receive_goaway_frame(self, frame):  # type: ignore[no-untyped-def]
        """
        Receive a GOAWAY frame on the connection.
        We purposely override this method to work around a known bug of jh2.
        """
        events = self.state_machine.process_input(
            jh2.connection.ConnectionInputs.RECV_GOAWAY
        )

        err_code = jh2.errors._error_code_from_int(frame.error_code)

        # GOAWAY allows an
        # endpoint to gracefully stop accepting new streams while still
        # finishing processing of previously established streams.
        # see https://tools.ietf.org/html/rfc7540#section-6.8
        # hyper/h2 does not allow such a thing for now. let's work around this.
        if (
            err_code == 0
            and self._observable_impl is not None
            and self._observable_impl._open_streams
        ):
            self.state_machine.state = jh2.connection.ConnectionState.CLIENT_OPEN

        # Clear the outbound data buffer: we cannot send further data now.
        self.clear_outbound_data_buffer()

        # Fire an appropriate ConnectionTerminated event.
        new_event = jh2.events.ConnectionTerminated()
        new_event.error_code = err_code
        new_event.last_stream_id = frame.last_stream_id
        new_event.additional_data = (
            frame.additional_data if frame.additional_data else None
        )
        events.append(new_event)

        return [], events


HEADER_OR_TRAILER_TYPE_SET = {
    jh2.events.ResponseReceived,
    jh2.events.TrailersReceived,
}

SETTINGS_EVENT_SET = {
    jh2.events.SettingsAcknowledged,
    jh2.events.RemoteSettingsChanged,
}


class HTTP2ProtocolHyperImpl(HTTP2Protocol):
    implementation: str = "h2"

    def __init__(
        self,
        *,
        validate_outbound_headers: bool = False,
        validate_inbound_headers: bool = False,
        normalize_outbound_headers: bool = False,
        normalize_inbound_headers: bool = True,
    ) -> None:
        self._connection: jh2.connection.H2Connection = _PatchedH2Connection(
            jh2.config.H2Configuration(
                client_side=True,
                validate_outbound_headers=validate_outbound_headers,
                normalize_outbound_headers=normalize_outbound_headers,
                validate_inbound_headers=validate_inbound_headers,
                normalize_inbound_headers=normalize_inbound_headers,
            ),
            observable_impl=self,
        )
        self._open_streams: set[int] = set()
        self._connection.initiate_connection()
        if JH2_NOT_RFC_COMPLIANT_SETTINGS:  # Defensive: legacy jh2 flow-control setup.
            self._connection.increment_flow_control_window(2**24)
        else:
            self._connection.increment_flow_control_window(15663105)
        self._events: StreamMatrix = StreamMatrix()
        self._terminated: bool = False
        self._goaway_to_honor: bool = False
        self._max_stream_count: int = (
            self._connection.remote_settings.max_concurrent_streams
        )
        self._max_frame_size: int = self._connection.remote_settings.max_frame_size

        self._pending_ping_ack: deque[bytes] = deque()

    def max_frame_size(self) -> int:
        initial_window_size: int = self._connection.remote_settings.initial_window_size
        if initial_window_size == 0:
            # body_to_chunks() requires a positive block size. Flow control
            # still prevents this byte from being sent before WINDOW_UPDATE.
            return 1

        return min(
            self._max_frame_size,
            initial_window_size,
            HTTP2_INITIAL_CONNECTION_WINDOW_SIZE,
        )

    @staticmethod
    def exceptions() -> tuple[type[BaseException], ...]:
        return jh2.exceptions.ProtocolError, jh2.exceptions.H2Error

    def is_available(self) -> bool:
        if self._terminated or self._goaway_to_honor:
            return False
        return self._max_stream_count > len(self._open_streams)

    @property
    def max_stream_count(self) -> int:
        return (
            self._max_stream_count
        )  # Defensive: protocol contract; backend uses is_available().

    def is_idle(self) -> bool:
        if self._events.stream_count:
            return False
        return not self._terminated and not self._open_streams

    def has_expired(self) -> bool:
        if len(self._pending_ping_ack) >= 2:
            self._connection.close_connection()
            self._terminated = True
        return (
            self._terminated or self._goaway_to_honor
        ) and not self._events.stream_count

    def get_available_stream_id(self) -> int:
        return self._connection.get_next_available_stream_id()  # type: ignore[no-any-return]

    def submit_close(self, error_code: int = 0) -> None:
        self._connection.close_connection(error_code)

    def submit_headers(
        self, stream_id: int, headers: HeadersType, end_stream: bool = False
    ) -> None:
        self._connection.send_headers(stream_id, headers, end_stream)
        self._open_streams.add(stream_id)

    def submit_data(
        self, stream_id: int, data: bytes, end_stream: bool = False
    ) -> None:
        self._connection.send_data(stream_id, data, end_stream)

    def submit_stream_reset(self, stream_id: int, error_code: int = 8) -> None:
        """Discard local events and cancel an unfinished stream (CANCEL)."""
        self._events.discard(stream_id)
        self._open_streams.discard(stream_id)
        stream = self._connection.streams.get(stream_id)
        if stream is None or stream.closed:
            return
        try:
            self._connection.reset_stream(stream_id, error_code)
        except (
            jh2.exceptions.StreamClosedError
        ):  # Defensive: closed streams are checked before reset.
            pass

    def next_event(self, stream_id: int | None = None) -> Event | None:
        return self._events.popleft(stream_id)

    def has_pending_event(
        self,
        *,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> bool:
        return self._events.has(stream_id=stream_id, excl_event=excl_event)

    def _map_events(self, h2_events: list[jh2.events.Event]) -> Iterator[Event]:
        conn = self._connection
        for e in h2_events:
            ev_type = e.__class__

            if ev_type is jh2.events.DataReceived:
                stream_id = e.stream_id
                conn.acknowledge_received_data(e.flow_controlled_length, stream_id)
                if stream_id not in self._open_streams:
                    continue  # Defensive: jh2 filters unsolicited or closed-stream DATA.
                end_stream = e.stream_ended is not None
                if end_stream:
                    self._open_streams.discard(stream_id)
                    stream = conn.streams[stream_id]
                    if stream.closed:
                        del conn.streams[stream_id]
                        conn._closed_streams[stream_id] = stream.closed_by
                yield DataReceived(stream_id, e.data, end_stream=end_stream)
            elif ev_type in HEADER_OR_TRAILER_TYPE_SET:
                stream_id = e.stream_id
                if stream_id not in self._open_streams:
                    continue  # Defensive: jh2 filters unsolicited or closed-stream HEADERS.
                end_stream = e.stream_ended is not None
                if end_stream:
                    self._open_streams.discard(stream_id)
                    stream = conn.streams[stream_id]
                    if stream.closed:
                        del conn.streams[stream_id]
                        conn._closed_streams[stream_id] = stream.closed_by
                yield HeadersReceived(stream_id, e.headers, end_stream=end_stream)
            elif ev_type is jh2.events.InformationalResponseReceived:
                if e.stream_id not in self._open_streams:
                    continue  # Defensive: jh2 validates the stream before emitting informational headers.
                yield EarlyHeadersReceived(
                    e.stream_id,
                    e.headers,
                )
            elif ev_type is jh2.events.StreamReset:
                # END_STREAM may precede a reset stopping an unfinished upload.
                stream_id = e.stream_id
                if stream_id not in self._open_streams:
                    continue
                self._open_streams.discard(stream_id)
                if stream_id in conn.streams:
                    stream = conn.streams.pop(stream_id)
                    conn._closed_streams[stream_id] = stream.closed_by
                yield StreamResetReceived(stream_id, e.error_code)
            elif ev_type is jh2.events.ConnectionTerminated:
                # ConnectionTerminated from h2 means that GOAWAY was received.
                # A server can send GOAWAY for graceful shutdown, where clients
                # do not open new streams, but inflight requests can be completed.
                #
                # Saying "connection was terminated" can be confusing,
                # so we emit an event called "GoawayReceived".
                if e.error_code == 0:
                    self._goaway_to_honor = True
                    yield GoawayReceived(e.last_stream_id, e.error_code)
                else:
                    self._terminated = True
                    error_name = getattr(e.error_code, "name", "UNKNOWN_ERROR")
                    yield ConnectionTerminated(
                        e.error_code,
                        f"HTTP/2 peer sent GOAWAY with error {error_name} ({e.error_code:#x}).",
                    )
            elif ev_type in SETTINGS_EVENT_SET:
                yield HandshakeCompleted(alpn_protocol="h2")
            elif ev_type is jh2.events.PingAckReceived:
                uid = e.ping_data

                if uid in self._pending_ping_ack:
                    self._pending_ping_ack.remove(uid)

    def connection_lost(self) -> None:
        self._connection_terminated()

    def eof_received(self) -> None:
        # A clean TLS shutdown does not complete an HTTP/2 stream without END_STREAM.
        incomplete = bool(self._open_streams)
        self._connection_terminated(
            int(jh2.errors.ErrorCodes.PROTOCOL_ERROR) if incomplete else 0,
            "HTTP/2 connection closed before END_STREAM" if incomplete else None,
        )

    def bytes_received(self, data: bytes) -> None:
        if not data:
            return  # Defensive: backends handle TCP EOF before forwarding bytes.

        try:
            h2_events = self._connection.receive_data(data)
        except jh2.exceptions.ProtocolError as e:
            self._connection_terminated(e.error_code, str(e))
        else:
            self._events.extend(self._map_events(h2_events))

        # we want to perpetually mark the connection as "saturated"
        if self._goaway_to_honor:
            self._max_stream_count = len(self._open_streams)

        if self._connection.remote_settings.has_update:
            if not self._goaway_to_honor:
                self._max_stream_count = (
                    self._connection.remote_settings.max_concurrent_streams
                )
            self._max_frame_size = self._connection.remote_settings.max_frame_size

    def bytes_to_send(self) -> bytes:
        return self._connection.data_to_send()  # type: ignore[no-any-return]

    def _connection_terminated(
        self, error_code: int = 0, message: str | None = None
    ) -> None:
        if self._terminated:
            return  # Defensive: tolerate repeated termination notifications.
        error_code = int(error_code)  # Convert h2 IntEnum to an actual int
        self._terminated = True
        self._events.append(ConnectionTerminated(error_code, message))

    def should_wait_remote_flow_control(
        self, stream_id: int, amt: int | None = None
    ) -> bool | None:
        flow_remaining_bytes: int = self._connection.local_flow_control_window(
            stream_id
        )

        if amt is None:
            return (
                flow_remaining_bytes == 0
            )  # Defensive: backend callers always supply a byte count.

        return amt > flow_remaining_bytes

    def reshelve(self, *events: Event) -> None:
        for ev in reversed(events):
            self._events.appendleft(ev)

    def ping(self) -> None:
        uid = token_bytes(8)
        self._pending_ping_ack.append(uid)
        self._connection.ping(uid)

    def expect_pong(self) -> bool:
        return bool(self._pending_ping_ack)
