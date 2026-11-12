from __future__ import annotations

import asyncio
import codecs
import typing

if typing.TYPE_CHECKING:
    from ...._async.response import AsyncHTTPResponse

from ....backend import HttpVersion
from ..sse import ServerSentEvent, _VIEW_THRESHOLD, _cr_boundary, _parse_event
from .protocol import AsyncExtensionFromHTTP


class AsyncServerSideEventExtensionFromHTTP(AsyncExtensionFromHTTP):
    def __init__(self) -> None:
        super().__init__()

        self._next_value_task: asyncio.Task[bytes] | None = None
        self._last_event_id: str | None = None
        self._buffer: bytes = b""
        self._buffer_start = 0
        self._at_start = True
        self._stream: typing.AsyncGenerator[bytes, None] | None = None

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11, HttpVersion.h2, HttpVersion.h3}

    @staticmethod
    def implementation() -> str:
        return "native"

    @property
    def urlopen_kwargs(self) -> dict[str, typing.Any]:
        return {"preload_content": False}

    async def close(self) -> None:
        if self._stream is not None and self._response is not None:
            stream = self._stream
            if self._next_value_task is not None:
                task = self._next_value_task
                task.cancel()
                # Consume our read cancellation without suppressing caller cancellation.
                await asyncio.wait([task])
                if not task.cancelled():
                    task.result()

            await stream.aclose()
            if (
                self._response._fp is not None
                # Cancelling the read may already have closed the response.
                and not self._response._fp.closed
                and self._police_officer is not None
                and hasattr(self._response._fp, "abort")
            ):
                async with self._police_officer.borrow(self._response):
                    await self._response._fp.abort()
            self._stream = None
            self._response = None
            self._police_officer = None
            self._buffer = b""
            self._buffer_start = 0

    @property
    def closed(self) -> bool:
        return self._stream is None

    async def start(self, response: AsyncHTTPResponse) -> None:
        await super().start(response)

        self._buffer = b""
        self._buffer_start = 0
        self._at_start = True
        self._stream = response.stream(-1, decode_content=True)

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        return {"accept": "text/event-stream", "cache-control": "no-store"}

    @typing.overload
    async def next_payload(self, *, raw: typing.Literal[True] = True) -> str | None: ...

    @typing.overload
    async def next_payload(
        self, *, raw: typing.Literal[False] = False
    ) -> ServerSentEvent | None: ...

    async def next_payload(self, *, raw: bool = False) -> ServerSentEvent | str | None:
        """Unpack the next received message/payload from remote."""
        if self._response is None or self._stream is None:
            raise OSError("The HTTP extension is closed or uninitialized")

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
                            + (2 if buffer[offset + 1 : offset + 2] == b"\n" else 1),
                        )
                else:
                    lf = buffer.find(b"\n\n", search_from)
                    cr = buffer.find(b"\r", search_from)
                    if cr < 0 or (lf >= 0 and lf < cr):
                        if lf >= 0:
                            start = (
                                lf - 1 if lf > offset and buffer[lf - 1] == 13 else lf
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
                    self._next_value_task = asyncio.create_task(
                        self._stream.__anext__()
                    )
                    chunk = await self._next_value_task
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
                except asyncio.CancelledError:
                    return None
                except StopAsyncIteration:
                    search_from = offset
                    stream_ended = True
                finally:
                    self._next_value_task = None
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

    async def send_payload(self, buf: str | bytes) -> None:
        """Dispatch a buffer to remote."""
        raise NotImplementedError("SSE is only one-way. Sending is forbidden.")

    @staticmethod
    def supported_schemes() -> set[str]:
        return {"sse", "psse"}

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        return {"sse": "https", "psse": "http"}[scheme]
