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

from functools import lru_cache

import h11
from h11._receivebuffer import ReceiveBuffer
from h11._state import _SWITCH_UPGRADE, ConnectionState

from ..._stream_matrix import StreamMatrix
from ..._typing import HeadersType
from ...events import (
    ConnectionTerminated,
    DataReceived,
    EarlyHeadersReceived,
    Event,
    HeadersReceived,
)
from .._protocols import HTTP1Protocol

_IDLE_STATES = frozenset({h11.IDLE, h11.MUST_CLOSE})


class _H11ReceiveBuffer(ReceiveBuffer):
    """Hand off complete body buffers without copying them."""

    def maybe_extract_at_most(  # type: ignore[override]
        self, count: int
    ) -> bytes | memoryview | None:
        if count <= 0 or not self._data:
            return None

        current = self._data
        data: bytes | memoryview
        if count >= len(current):
            self._data = bytearray()
            data = memoryview(current)
        else:
            view = memoryview(current)
            chunk = view[:count]
            data = chunk.tobytes()
            chunk.release()
            view.release()
            del current[:count]

        self._next_line_search = 0
        self._multiple_lines_search = 0

        return data


@lru_cache(maxsize=64)
def capitalize_header_name(name: bytes) -> bytes:
    """
    Take a header name and capitalize it.
    >>> capitalize_header_name(b"x-hEllo-wORLD")
    'X-Hello-World'
    >>> capitalize_header_name(b"server")
    'Server'
    >>> capitalize_header_name(b"contEnt-TYPE")
    'Content-Type'
    >>> capitalize_header_name(b"content_type")
    'Content-Type'
    """
    return b"-".join(el.capitalize() for el in name.split(b"-"))


def headers_to_request(headers: HeadersType) -> h11.Event:
    method = authority = path = host = None
    regular_headers = []

    for name, value in headers:
        if name.startswith(b":"):
            if name == b":method":
                method = value
            elif name == b":scheme":
                pass
            elif name == b":authority":
                authority = value
            elif name == b":path":
                path = value
            else:  # Defensive: unreachable, upper stack filter it early.
                raise ValueError("Unexpected request header: " + name.decode())
        else:
            if host is None and name == b"host":
                host = value

            # We found that many projects... actually expect the header name to be sent capitalized... hardcoded
            # within their tests. Bad news, we have to keep doing this nonsense (namely capitalize_header_name)
            regular_headers.append((capitalize_header_name(name), value))

    if authority is None:
        raise ValueError(  # Defensive: raise an error higher in stack
            "Missing request header: :authority"
        )

    if method == b"CONNECT" and path is None:
        # CONNECT requests are a special case.
        target = authority
    else:
        target = path  # type: ignore[assignment]

    if host is None:
        regular_headers.insert(0, (b"Host", authority))
    elif host != authority:
        raise ValueError("Host header does not match :authority.")

    return h11.Request(
        method=method,  # type: ignore[arg-type]
        headers=regular_headers,
        target=target,
    )


def headers_from_response(
    response: h11.InformationalResponse | h11.Response,
) -> HeadersType:
    """
    Converts an HTTP/1.0 or HTTP/1.1 response to HTTP/2-like headers.

    Generates from pseudo (colon) headers from a response line.
    """
    return [
        (b":status", str(response.status_code).encode("ascii")),
        *response.headers.raw_items(),
    ]


class RelaxConnectionState(ConnectionState):
    def process_event(  # type: ignore[no-untyped-def]
        self,
        role,
        event_type,
        server_switch_event=None,
    ) -> None:
        if server_switch_event is not None:
            if server_switch_event not in self.pending_switch_proposals:
                if (  # Defensive: http.client old behavior kept
                    server_switch_event is _SWITCH_UPGRADE
                ):
                    # Received server _SWITCH_UPGRADE event without a pending proposal.
                    # kept for backward compatibility with stdlib http.client
                    self.pending_switch_proposals.add(_SWITCH_UPGRADE)

        return super().process_event(role, event_type, server_switch_event)


class HTTP1ProtocolHyperImpl(HTTP1Protocol):
    implementation: str = "h11"

    def __init__(self) -> None:
        self._connection: h11.Connection = h11.Connection(h11.CLIENT)
        self._connection._receive_buffer = _H11ReceiveBuffer()
        self._connection._cstate = RelaxConnectionState()

        self._data_buffer: list[bytes] = []
        self._events: StreamMatrix = StreamMatrix()
        self._terminated: bool = False
        self._switched: bool = False

        self._current_stream_id: int = 1

    @staticmethod
    def exceptions() -> tuple[type[BaseException], ...]:
        return h11.LocalProtocolError, h11.ProtocolError, h11.RemoteProtocolError

    def is_available(self) -> bool:
        # there is a case where we could genuinely receive the whole response
        # and the h11 state machine would be marked as idle, when the
        # stream matrix still have ready data to unpack.
        # we first saw that behavior at https://github.com/jawah/urllib3.future/issues/323
        # below will prevent sending any requests until the stream matrix
        # have been entirely consumed.
        if self._events.stream_count:
            return False
        return self._connection.our_state == self._connection.their_state == h11.IDLE

    @property
    def max_stream_count(self) -> int:
        return 1  # Defensive: protocol contract; HTTP/1 does not multiplex streams.

    def is_idle(self) -> bool:
        return self._connection.their_state in _IDLE_STATES

    def has_expired(self) -> bool:
        return self._terminated and not self._events.stream_count

    def get_available_stream_id(self) -> int:
        if not self.is_available():
            raise RuntimeError(  # Defensive: should be unreachable in current state.
                "Cannot generate a new stream ID because the connection is not idle. "
                "HTTP/1.1 is not multiplexed and we do not support HTTP pipelining."
            )
        return self._current_stream_id

    def submit_close(self, error_code: int = 0) -> None:
        pass  # no-op

    def submit_headers(
        self, stream_id: int, headers: HeadersType, end_stream: bool = False
    ) -> None:
        if stream_id != self._current_stream_id:
            raise ValueError("Invalid stream ID.")  # Defensive: overly protective

        self._h11_submit(headers_to_request(headers))

        if end_stream:
            self._h11_submit(h11.EndOfMessage())

    def submit_data(
        self, stream_id: int, data: bytes, end_stream: bool = False
    ) -> None:
        if stream_id != self._current_stream_id:
            raise ValueError("Invalid stream ID.")  # Defensive: overly protective
        if self._connection.their_state == h11.SWITCHED_PROTOCOL:
            self._data_buffer.append(data)
            if end_stream:
                self._events.append(self._connection_terminated())
            return
        self._h11_submit(h11.Data(data))
        if end_stream:
            self._h11_submit(h11.EndOfMessage())

    def submit_stream_reset(self, stream_id: int, error_code: int = 0) -> None:
        self._events.discard(stream_id)
        # HTTP/1 cannot submit a stream (it does not have real streams).
        # But if there are no other streams, we can close the connection instead.
        self.connection_lost()

    def connection_lost(self) -> None:
        if self._connection.their_state == h11.SWITCHED_PROTOCOL:
            self._events.append(self._connection_terminated())
            return
        # This method is called when the connection is closed without an EOF.
        # But not all connections support EOF, so being here does not
        # necessarily mean that something when wrong.
        #
        # The tricky part is that HTTP/1.0 server can send responses
        # without Content-Length or Transfer-Encoding headers,
        # meaning that a response body is closed with the connection.
        # In such cases, we require a proper EOF to distinguish complete
        # messages from partial messages interrupted by network failure.
        if not self._terminated:
            self._connection.send_failed()
            self._events.append(self._connection_terminated())

    def eof_received(self) -> None:
        if self._connection.their_state == h11.SWITCHED_PROTOCOL:
            self._events.append(self._connection_terminated())
            return
        self._h11_data_received(b"")

    def bytes_received(self, data: bytes) -> None:
        if not data:
            return  # Defensive: backends route EOF through eof_received() or connection_lost().
        if self._connection.their_state == h11.SWITCHED_PROTOCOL:
            self._events.append(DataReceived(self._current_stream_id, data))
            return
        else:
            self._h11_data_received(data)

    def bytes_to_send(self) -> bytes:
        data = b"".join(self._data_buffer)
        self._data_buffer.clear()
        self._maybe_start_next_cycle()
        return data

    def next_event(self, stream_id: int | None = None) -> Event | None:
        return self._events.popleft(stream_id)

    def has_pending_event(
        self,
        *,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> bool:
        return self._events.has(stream_id=stream_id, excl_event=excl_event)

    def _h11_submit(self, h11_event: h11.Event) -> None:
        chunks = self._connection.send_with_data_passthrough(h11_event)
        if chunks:
            self._data_buffer.extend(chunks)

    def _h11_data_received(self, data: bytes) -> None:
        self._connection.receive_data(data)
        self._fetch_events()

    def _fetch_events(self) -> None:
        a = self._events.append
        conn = self._connection
        while not self._terminated:
            try:
                h11_event = conn.next_event()
            except h11.RemoteProtocolError as e:
                a(self._connection_terminated(e.error_status_hint, str(e)))
                break

            ev_type = h11_event.__class__

            if ev_type is h11.Data:
                # officially h11 typed data as "bytes"
                # but we... found that it store bytearray sometime.
                payload = h11_event.data  # type: ignore[union-attr]
                a(
                    DataReceived(
                        self._current_stream_id,
                        bytes(payload) if payload.__class__ is bytearray else payload,
                    )
                )
            elif h11_event is h11.NEED_DATA or h11_event is h11.PAUSED:
                if h11.MUST_CLOSE == conn.their_state:
                    a(self._connection_terminated())
                else:
                    break
            elif ev_type is h11.Response:
                a(
                    HeadersReceived(
                        self._current_stream_id,
                        headers_from_response(h11_event),  # type: ignore[arg-type]
                    )
                )
            elif ev_type is h11.InformationalResponse:
                a(
                    EarlyHeadersReceived(
                        stream_id=self._current_stream_id,
                        headers=headers_from_response(h11_event),  # type: ignore[arg-type]
                    )
                )
            elif ev_type is h11.EndOfMessage:
                # HTTP/2 and HTTP/3 send END_STREAM flag with HEADERS and DATA frames.
                # We emulate similar behavior for HTTP/1.
                if h11_event.headers:  # type: ignore[union-attr]
                    last_event: HeadersReceived | DataReceived = HeadersReceived(
                        self._current_stream_id,
                        h11_event.headers,  # type: ignore[union-attr]
                        conn.their_state != h11.MIGHT_SWITCH_PROTOCOL,  # type: ignore[attr-defined]
                    )
                else:
                    last_event = DataReceived(
                        self._current_stream_id,
                        b"",
                        conn.their_state != h11.MIGHT_SWITCH_PROTOCOL,  # type: ignore[attr-defined]
                    )
                a(last_event)
                self._maybe_start_next_cycle()
            elif ev_type is h11.ConnectionClosed:
                a(self._connection_terminated())

    def _connection_terminated(
        self, error_code: int = 0, message: str | None = None
    ) -> Event:
        self._terminated = True
        return ConnectionTerminated(error_code, message)

    def _maybe_start_next_cycle(self) -> None:
        if h11.DONE == self._connection.our_state == self._connection.their_state:
            self._connection.start_next_cycle()
            self._current_stream_id += 1
        if h11.SWITCHED_PROTOCOL == self._connection.their_state and not self._switched:
            data, closed = self._connection.trailing_data
            if data:
                self._events.append(DataReceived(self._current_stream_id, data))
            self._switched = True

    def reshelve(self, *events: Event) -> None:  # Defensive: protocol contract.
        # Current HTTP/1 exchanges collect all supported events.
        for ev in reversed(events):
            self._events.appendleft(ev)

    def ping(self) -> None:
        raise NotImplementedError("http1 does not support PING")

    def expect_pong(self) -> bool:
        return False
