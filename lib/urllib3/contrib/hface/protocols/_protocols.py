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

import typing
from abc import ABCMeta, abstractmethod
from typing import Any

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

from .._typing import HeadersType
from ..events import Event


class BaseProtocol(metaclass=ABCMeta):
    """Sans-IO common methods whenever it is TCP, UDP or QUIC."""

    @abstractmethod
    def bytes_received(self, data: bytes) -> None:
        """
        Called when some data is received.
        """
        raise NotImplementedError

    # Sending direction

    @abstractmethod
    def bytes_to_send(self) -> bytes:
        """
        Returns data for sending out of the internal data buffer.
        """
        raise NotImplementedError

    @abstractmethod
    def connection_lost(self) -> None:
        """
        Called when the connection is lost or closed.
        """
        raise NotImplementedError

    def should_wait_remote_flow_control(
        self, stream_id: int, amt: int | None = None
    ) -> bool | None:
        """
        Verify if the client should listen network incoming data for
        the flow control update purposes.
        """
        raise NotImplementedError

    def max_frame_size(self) -> int:
        """
        Determine if the remote set a limited size for each data frame.
        """
        raise NotImplementedError


class OverTCPProtocol(BaseProtocol, metaclass=ABCMeta):
    """
    Interface for sans-IO protocols on top TCP.
    """

    @abstractmethod
    def eof_received(self) -> None:
        """
        Called when the other end signals it won’t send any more data.
        """
        raise NotImplementedError


class OverUDPProtocol(BaseProtocol, metaclass=ABCMeta):
    """
    Interface for sans-IO protocols on top UDP.
    """


class OverQUICProtocol(OverUDPProtocol):
    def next_timer(self) -> float | None:
        """Return the absolute monotonic time of the next QUIC timer event.
        Returns None when no timer is currently scheduled.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def session_ticket(self) -> Any | None:
        raise NotImplementedError

    @typing.overload
    def getpeercert(self, *, binary_form: Literal[True]) -> bytes: ...

    @typing.overload
    def getpeercert(self, *, binary_form: Literal[False] = ...) -> dict[str, Any]: ...

    @abstractmethod
    def getpeercert(self, *, binary_form: bool = False) -> bytes | dict[str, Any]:
        raise NotImplementedError

    @typing.overload
    def getissuercert(self, *, binary_form: Literal[True]) -> bytes | None: ...

    @typing.overload
    def getissuercert(
        self, *, binary_form: Literal[False] = ...
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def getissuercert(
        self, *, binary_form: bool = False
    ) -> bytes | dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def cipher(self) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def ech_accepted(self) -> bool:
        raise NotImplementedError


class HTTPProtocol(metaclass=ABCMeta):
    """
    Sans-IO representation of an HTTP connection
    """

    implementation: str

    @staticmethod
    @abstractmethod
    def exceptions() -> tuple[type[BaseException], ...]:
        """Return exception types that should be handled in your application."""
        raise NotImplementedError

    @property
    @abstractmethod
    def multiplexed(self) -> bool:
        """
        Whether this connection supports multiple parallel streams.

        Returns ``True`` for HTTP/2 and HTTP/3 connections.
        """
        raise NotImplementedError

    @abstractmethod
    def is_idle(self) -> bool:
        """
        Return True if this connection is BOTH available and not doing anything.
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return whether this connection is capable to open new streams.
        """
        raise NotImplementedError

    @abstractmethod
    def has_expired(self) -> bool:
        """
        Return whether this connection is closed or should be closed.
        """
        raise NotImplementedError

    @abstractmethod
    def get_available_stream_id(self) -> int:
        """
        Return an ID that can be used to create a new stream.

        Use the returned ID with :meth:`.submit_headers` to create the stream.
        This method may or may not return one value until that method is called.

        :return: stream ID
        """
        raise NotImplementedError

    @abstractmethod
    def submit_headers(
        self, stream_id: int, headers: HeadersType, end_stream: bool = False
    ) -> None:
        """
        Submit a frame with HTTP headers.

        If this is a client connection, this method starts an HTTP request.
        If this is a server connection, it starts an HTTP response.

        :param stream_id: stream ID
        :param headers: HTTP headers
        :param end_stream: whether to close the stream for sending
        """
        raise NotImplementedError

    @abstractmethod
    def submit_data(
        self, stream_id: int, data: bytes, end_stream: bool = False
    ) -> None:
        """
        Submit a frame with HTTP data.

        :param stream_id: stream ID
        :param data: payload
        :param end_stream: whether to close the stream for sending
        """
        raise NotImplementedError

    @abstractmethod
    def submit_stream_reset(self, stream_id: int, error_code: int = 0) -> None:
        """
        Immediate terminate a stream.

        Stream reset is used to request cancellation of a stream
        or to indicate that an error condition has occurred.

        Use :attr:`.error_codes` to obtain error codes for common problems.

        :param stream_id: stream ID
        :param error_code:  indicates why the stream is being terminated
        """
        raise NotImplementedError

    @abstractmethod
    def submit_close(self, error_code: int = 0) -> None:
        """
        Submit graceful close the connection.

        Use :attr:`.error_codes` to obtain error codes for common problems.

        :param error_code:  indicates why the connections is being closed
        """
        raise NotImplementedError

    @abstractmethod
    def next_event(self, stream_id: int | None = None) -> Event | None:
        """
        Consume next HTTP event.

        :return: an event instance
        """
        raise NotImplementedError

    def events(self, stream_id: int | None = None) -> typing.Iterator[Event]:
        """
        Consume available HTTP events.

        :return: an iterator that unpack "next_event" until exhausted.
        """
        next_event = self.next_event

        while True:
            ev = next_event(stream_id)

            if ev is None:
                break

            yield ev

    @abstractmethod
    def has_pending_event(
        self,
        *,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> bool:
        """Verify if there is queued event waiting to be consumed."""
        raise NotImplementedError

    @abstractmethod
    def reshelve(self, *events: Event) -> None:
        """Put back events into the deque."""
        raise NotImplementedError

    @abstractmethod
    def ping(self) -> None:
        """Send a PING frame to the remote peer. Thus keeping the connection alive."""
        raise NotImplementedError

    @abstractmethod
    def expect_pong(self) -> bool:
        """Tell if we should expect a ping ack frame to confirm connection liveness."""
        raise NotImplementedError


class HTTPOverTCPProtocol(HTTPProtocol, OverTCPProtocol, metaclass=ABCMeta):
    """
    :class:`HTTPProtocol` over a TCP connection

    An interface for HTTP/1 and HTTP/2 protocols.
    Extends :class:`.HTTPProtocol`.
    """


class HTTPOverQUICProtocol(HTTPProtocol, OverQUICProtocol, metaclass=ABCMeta):
    """
    :class:`HTTPProtocol` over a QUIC connection

    Abstract base class for HTTP/3 protocols.
    Extends :class:`.HTTPProtocol`.
    """

    @abstractmethod
    def many_bytes_received(self, data: list[bytes]) -> None:
        """Process a batch of datagrams received by a single socket read."""
        raise NotImplementedError


class HTTP1Protocol(HTTPOverTCPProtocol, metaclass=ABCMeta):
    """
    Sans-IO representation of an HTTP/1 connection

    An interface for HTTP/1 implementations.
    Extends :class:`.HTTPOverTCPProtocol`.
    """

    @property
    def multiplexed(self) -> bool:
        return False

    def should_wait_remote_flow_control(
        self, stream_id: int, amt: int | None = None
    ) -> bool | None:
        return NotImplemented  # type: ignore[no-any-return]


class HTTP2Protocol(HTTPOverTCPProtocol, metaclass=ABCMeta):
    """
    Sans-IO representation of an HTTP/2 connection

    An abstract base class for HTTP/2 implementations.
    Extends :class:`.HTTPOverTCPProtocol`.
    """

    @property
    def multiplexed(self) -> bool:
        return True


class HTTP3Protocol(HTTPOverQUICProtocol, metaclass=ABCMeta):
    """
    Sans-IO representation of an HTTP/2 connection

    An abstract base class for HTTP/3 implementations.
    Extends :class:`.HTTPOverQUICProtocol`
    """

    @property
    def multiplexed(self) -> bool:
        return True
