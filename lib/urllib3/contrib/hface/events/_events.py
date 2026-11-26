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

from dataclasses import dataclass, field

from .._typing import HeadersType


class Event:
    """
    Base class for HTTP events.

    This is an abstract base class that should not be initialized.
    """

    _id: int


#
# Connection events
#


@dataclass
class ConnectionTerminated(Event):
    """
    Connection was terminated.

    Extends :class:`.Event`.
    """

    #: Reason for closing the connection.
    error_code: int = 0

    #: Optional message with more information
    message: str | None = field(default=None, compare=False)

    #: TLS failures must remain distinguishable from HTTP application errors.
    is_tls_error: bool = False

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return f"{cls}(error_code={self.error_code!r}, message={self.message!r})"


@dataclass
class GoawayReceived(Event):
    """
    GOAWAY frame was received

    Extends :class:`.Event`.
    """

    #: Highest stream ID that could be processed.
    last_stream_id: int

    #: Reason for closing the connection.
    error_code: int = 0

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return (
            f"{cls}(last_stream_id={self.last_stream_id!r}, "
            f"error_code={self.error_code!r})"
        )


#
# Stream events
#


@dataclass
class StreamEvent(Event):
    """
    Event on one HTTP stream.

    This is an abstract base class that should not be used directly.

    Extends :class:`.Event`.
    """

    #: Stream ID
    stream_id: int


@dataclass
class StreamReset(StreamEvent):
    """
    One stream of an HTTP connection was reset.

    When a stream is reset, it must no longer be used, but the parent
    connection and other streams are unaffected.

    This is an abstract base class that should not be used directly.
    More specific subclasses (StreamResetSent or StreamResetReceived)
    should be emitted.

    Extends :class:`.StreamEvent`.
    """

    #: Reason for closing the stream.
    error_code: int = 0
    end_stream: bool = True

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return f"{cls}(stream_id={self.stream_id!r}, error_code={self.error_code!r})"


@dataclass
class StreamResetReceived(StreamReset):
    """
    One stream of an HTTP connection was reset by the peer.

    This probably means that we did something that the peer does not like.

    Extends :class:`.StreamReset`.
    """


@dataclass
class StreamStopSendingReceived(StreamEvent):
    """The peer stopped our sending direction; its response can still arrive."""

    error_code: int = 0


@dataclass
class HandshakeCompleted(Event):
    alpn_protocol: str | None

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return f"{cls}(alpn={self.alpn_protocol})"


@dataclass
class HeadersReceived(StreamEvent):
    """
    A frame with HTTP headers was received.

    Extends :class:`.StreamEvent`.
    """

    #: The received HTTP headers
    headers: HeadersType

    #: Signals that data will not be sent by the peer over the stream.
    end_stream: bool = False

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return (
            f"{cls}(stream_id={self.stream_id!r}, "
            f"len(headers)={len(self.headers)}, end_stream={self.end_stream!r})"
        )


@dataclass
class DataReceived(StreamEvent):
    """
    A frame with HTTP data was received.

    Extends :class:`.StreamEvent`.
    """

    #: The received data.
    data: bytes

    #: Signals that no more data will be sent by the peer over the stream.
    end_stream: bool = False

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return (
            f"{cls}(stream_id={self.stream_id!r}, "
            f"len(data)={len(self.data)}, end_stream={self.end_stream!r})"
        )


@dataclass
class EarlyHeadersReceived(StreamEvent):
    #: The received HTTP headers
    headers: HeadersType

    #: Early headers never signal end of stream.
    end_stream: bool = False

    def __repr__(self) -> str:  # Defensive: debug purposes only
        cls = type(self).__name__
        return (
            f"{cls}(stream_id={self.stream_id!r}, "
            f"len(headers)={len(self.headers)}, end_stream=False)"
        )
