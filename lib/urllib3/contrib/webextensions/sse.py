from __future__ import annotations

import codecs
import json
import typing
from threading import RLock

if typing.TYPE_CHECKING:
    from ...response import HTTPResponse

from ...backend import HttpVersion
from .protocol import ExtensionFromHTTP


class ServerSentEvent:
    """A parsed SSE block with text data, event type, ID, and retry metadata."""

    def __init__(
        self,
        event: str | None = None,
        data: str | None = None,
        id: str | None = None,
        retry: int | None = None,
    ) -> None:
        if not event:
            event = "message"

        if data is None:
            data = ""

        if id is None:
            id = ""

        self._event = event
        self._data = data
        self._id = id
        self._retry = retry

    @property
    def event(self) -> str:
        """Event type, defaulting to ``message``."""
        return self._event

    @property
    def data(self) -> str:
        """Text payload, with multiple data fields joined by newlines."""
        return self._data

    @property
    def id(self) -> str:
        """Current event ID; an empty string clears the resumption cursor."""
        return self._id

    @property
    def retry(self) -> int | None:
        """Retry delay in milliseconds from this block, or ``None`` if absent."""
        return self._retry

    def json(self) -> typing.Any:
        """Parse the text payload as JSON, propagating JSON decoding errors."""
        return json.loads(self.data)

    def __repr__(self) -> str:
        pieces = [f"event={self.event!r}"]
        if self.data != "":
            pieces.append(f"data={self.data!r}")
        if self.id != "":
            pieces.append(f"id={self.id!r}")
        if self.retry is not None:
            pieces.append(f"retry={self.retry!r}")
        return f"ServerSentEvent({', '.join(pieces)})"


# Views avoid large temporary copies; smaller events decode faster from bytes.
_VIEW_THRESHOLD = 64 * 1024


def _cr_boundary(
    buffer: bytes, start: int, *, raw: bool, final: bool
) -> tuple[int, int] | None:
    """Expand an LF/CR or CR/CR marker to include adjacent CRLF bytes."""
    end = start + 2
    if end == len(buffer):
        if raw and not final:
            return None
    elif buffer[end] == 10:
        end += 1
    if start and buffer[start] == 10 and buffer[start - 1] == 13:
        start -= 1
    return start, end


def _parse_event(event_text: str, last_event_id: str | None) -> ServerSentEvent | None:
    event_type = event_id = data = None
    retry = None
    data_lines: list[str] | None = None
    if "\r" in event_text:
        event_text = event_text.replace("\r\n", "\n").replace("\r", "\n")
    # Split only at SSE line endings, preserving Unicode separators as data.
    for line in event_text.split("\n"):
        if not line or line[0] == ":":
            continue
        # The usual ": " delimiter strips its single space without copying
        # the value twice. Fall back when the first colon has no following space.
        key, separator, value = line.partition(": ")
        if not separator or ":" in key:
            key, _, value = line.partition(":")
        if key == "data":
            if data is None:
                data = value
            elif data_lines is None:
                data_lines = [data, value]
            else:
                data_lines.append(value)
        elif key == "event":
            event_type = value
        elif key == "id":
            if "\x00" not in value:
                event_id = value
        elif key == "retry":
            try:
                # Retain tolerant integer parsing for existing applications.
                retry = int(value)
            except ValueError:
                pass

    if data is None and event_type is None and event_id is None and retry is None:
        return None
    if data_lines is not None:
        data = "\n".join(data_lines)
    return ServerSentEvent(
        event_type, data, event_id if event_id is not None else last_event_id, retry
    )


class ServerSideEventExtensionFromHTTP(ExtensionFromHTTP):
    def __init__(self) -> None:
        super().__init__()

        self._last_event_id: str | None = None
        self._buffer: bytes = b""
        self._buffer_start = 0
        self._at_start = True
        self._lock = RLock()
        self._stream: typing.Generator[bytes, None, None] | None = None

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11, HttpVersion.h2, HttpVersion.h3}

    @staticmethod
    def implementation() -> str:
        return "native"

    @property
    def urlopen_kwargs(self) -> dict[str, typing.Any]:
        return {"preload_content": False}

    @property
    def closed(self) -> bool:
        return self._stream is None

    def close(self) -> None:
        if self._stream is not None and self._response is not None:
            self._stream.close()
            if (
                self._response._fp is not None
                and self._police_officer is not None
                and hasattr(self._response._fp, "abort")
            ):
                with self._police_officer.borrow(self._response):
                    self._response._fp.abort()
            self._stream = None
            self._response = None
            self._police_officer = None
            self._buffer = b""
            self._buffer_start = 0

    def start(self, response: HTTPResponse) -> None:
        super().start(response)

        self._buffer = b""
        self._buffer_start = 0
        self._at_start = True
        self._stream = response.stream(-1, decode_content=True)

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        return {"accept": "text/event-stream", "cache-control": "no-store"}

    @typing.overload
    def next_payload(self, *, raw: typing.Literal[True] = True) -> str | None: ...

    @typing.overload
    def next_payload(
        self, *, raw: typing.Literal[False] = False
    ) -> ServerSentEvent | None: ...

    def next_payload(self, *, raw: bool = False) -> ServerSentEvent | str | None:
        """Unpack the next received message/payload from remote."""
        if self._response is None or self._stream is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        with self._lock:
            # Frame ASCII CR/LF bytes before UTF-8 decoding. Searches overlap by
            # two bytes when new input arrives, including an unresolved final CR.
            buffer = self._buffer
            offset = self._buffer_start
            buffer_end = len(buffer)
            stream_ended = False
            search_from = offset
            while True:
                boundary = None
                if offset < buffer_end:
                    if buffer[offset] == 10:
                        boundary = offset, offset + 1
                    elif buffer[offset] == 13:
                        if buffer_end - offset > 1 or not raw or stream_ended:
                            boundary = (
                                offset,
                                offset
                                + (
                                    2 if buffer[offset + 1 : offset + 2] == b"\n" else 1
                                ),
                            )
                    else:
                        lf = buffer.find(b"\n\n", search_from)
                        cr = buffer.find(b"\r", search_from)
                        if cr < 0 or (lf >= 0 and lf < cr):
                            if lf >= 0:
                                start = (
                                    lf - 1
                                    if lf > offset and buffer[lf - 1] == 13
                                    else lf
                                )
                                boundary = start, lf + 2
                        else:
                            candidate = buffer.find(b"\n\r", search_from)
                            bare = buffer.find(b"\r\r", cr)
                            if candidate < 0 or 0 <= bare < candidate:
                                candidate = bare
                            if candidate >= 0 and (lf < 0 or candidate < lf):
                                boundary = _cr_boundary(
                                    buffer, candidate, raw=raw, final=stream_ended
                                )
                            elif lf >= 0:
                                boundary = lf, lf + 2
                if boundary is None:
                    if stream_ended:
                        self._stream = None
                        self._buffer = b""
                        self._buffer_start = 0
                        return None
                    try:
                        search_from = buffer_end - offset - 2
                        if search_from < 0:
                            search_from = 0
                        chunk = next(self._stream)
                        if offset:
                            buffer = b"".join((memoryview(buffer)[offset:], chunk))
                            offset = 0
                            self._buffer_start = 0
                        else:
                            buffer += chunk
                        if self._at_start and buffer.startswith(codecs.BOM_UTF8):
                            offset = 3
                            self._buffer_start = offset
                            search_from = offset
                            self._at_start = False
                        self._buffer = buffer
                        buffer_end = len(buffer)
                    except StopIteration:
                        search_from = offset
                        stream_ended = True
                    continue

                start, end = boundary
                payload_end = end if raw else start
                if payload_end - offset >= _VIEW_THRESHOLD and (
                    offset or payload_end != buffer_end
                ):
                    event_text = codecs.utf_8_decode(
                        memoryview(buffer)[offset:payload_end], "replace", True
                    )[0]
                else:
                    event_text = buffer[offset:payload_end].decode("utf-8", "replace")
                if end == buffer_end:
                    buffer = b""
                    self._buffer = buffer
                    buffer_end = offset = 0
                else:
                    offset = end
                self._buffer_start = offset
                search_from = offset
                if self._at_start:
                    self._at_start = False
                event = _parse_event(event_text, self._last_event_id)
                if event is None:
                    continue
                self._last_event_id = event.id

                if raw is True:
                    return event_text

                return event

    def send_payload(self, buf: str | bytes) -> None:
        """Dispatch a buffer to remote."""
        raise NotImplementedError("SSE is only one-way. Sending is forbidden.")

    @staticmethod
    def supported_schemes() -> set[str]:
        return {"sse", "psse"}

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        return {"sse": "https", "psse": "http"}[scheme]
