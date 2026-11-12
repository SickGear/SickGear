from __future__ import annotations

import typing

from ..._collections import HTTPHeaderDict
from ...contrib.ssa import AsyncSocket, SSLAsyncSocket
from .._base import BaseBackend, ResponsePromise

try:
    from jh2._hazmat import _BytesQueueBuffer as BytesQueueBuffer  # type: ignore[import-untyped]
except ImportError:
    from ...util.response import BytesQueueBuffer


class AsyncDirectStreamAccess:
    def __init__(
        self,
        stream_id: int,
        read: typing.Callable[
            [int | None, int | None, bool, bool],
            typing.Awaitable[tuple[list[bytes], bool, HTTPHeaderDict | None]],
        ]
        | None = None,
        write: typing.Callable[[bytes, int, bool], typing.Awaitable[None]]
        | None = None,
    ) -> None:
        self._stream_id = stream_id
        self._read = read
        self._write = write

        self._buffer: BytesQueueBuffer = BytesQueueBuffer()
        self._eot: bool = False

    @property
    def closed(self) -> bool:
        return self._read is None and self._write is None

    async def readinto(
        self, b: bytearray
    ) -> int:  # Defensive: incidental http.client compatibility.
        if self._read is None:
            raise OSError("read operation on a closed stream")

        temp = await self.recv(len(b))

        if len(temp) == 0:
            return 0
        else:
            b[: len(temp)] = temp
            return len(temp)

    def readable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return self._read is not None

    def writable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return self._write is not None

    def seekable(self) -> bool:  # Defensive: incidental http.client compatibility.
        return False

    def fileno(self) -> int:  # Defensive: incidental http.client compatibility.
        return -1

    def name(self) -> int:  # Defensive: incidental http.client compatibility.
        return -1

    async def recv(
        self, __bufsize: int, __flags: int = 0
    ) -> bytes:  # Defensive: incidental http.client compatibility.
        data, _, _ = await self.recv_extended(__bufsize)
        return data

    async def recv_extended(
        self, __bufsize: int | None
    ) -> tuple[bytes, bool, HTTPHeaderDict | None]:
        if self._read is None:
            raise OSError("stream closed error")

        trailers = None

        # Only hit the wire when we have nothing buffered to satisfy the
        # caller; otherwise serve leftover frames first.
        if not self._eot and not self._buffer:
            chunks, self._eot, trailers = await self._read(
                __bufsize,
                self._stream_id,
                __bufsize is not None,
                False,
            )
            # An unbounded extension read can return a single protocol chunk
            # directly; there are no leftovers to enqueue.
            if __bufsize is None and len(chunks) == 1 and isinstance(chunks[0], bytes):
                if self._eot:
                    self._read = None
                return chunks[0], self._eot, trailers
            self._buffer.put_many(chunks)

        if self._buffer:
            data = self._buffer.get(
                __bufsize
                if __bufsize is not None and __bufsize > 0
                else len(self._buffer)
            )
        else:
            data = b""

        eot = self._eot and not self._buffer

        if eot:
            self._read = None

        return data, eot, trailers

    async def sendall(self, __data: bytes, __flags: int = 0) -> None:
        if self._write is None:
            raise OSError("stream write not permitted")

        await self._write(__data, self._stream_id, False)

    async def write(
        self, __data: bytes
    ) -> int:  # Defensive: incidental http.client compatibility.
        if self._write is None:
            raise OSError("stream write not permitted")

        await self._write(__data, self._stream_id, False)

        return len(__data)

    async def sendall_extended(  # Defensive: extended-send compatibility API; built-in extensions use sendall and close.
        self, __data: bytes, __close_stream: bool = False
    ) -> None:
        if self._write is None:
            raise OSError("stream write not permitted")

        await self._write(__data, self._stream_id, __close_stream)

    async def close(self) -> None:
        if self._write is not None:
            await self._write(b"", self._stream_id, True)
            self._write = None
        if self._read is not None:
            await self._read(None, self._stream_id, False, True)
            self._read = None


class AsyncLowLevelResponse:
    """Implemented for backward compatibility purposes. It is there to impose http.client like
    basic response object. So that we don't have to change urllib3 tested behaviors."""

    __internal_read_st: (
        typing.Callable[
            [int | None, int | None],
            typing.Awaitable[tuple[list[bytes], bool, HTTPHeaderDict | None]],
        ]
        | None
    )

    def __init__(
        self,
        method: str,
        status: int,
        version: int,
        reason: str,
        headers: HTTPHeaderDict,
        body: typing.Callable[
            [int | None, int | None],
            typing.Awaitable[tuple[list[bytes], bool, HTTPHeaderDict | None]],
        ]
        | None,
        *,
        authority: str | None = None,
        port: int | None = None,
        stream_id: int | None = None,
        # this obj should not be always available[...]
        dsa: AsyncDirectStreamAccess | None = None,
        stream_abort: typing.Callable[[int], typing.Awaitable[None]] | None = None,
    ) -> None:
        self.status = status
        self.version = version
        self.reason = reason
        self.msg = headers
        self._method = method

        self.__internal_read_st = body

        has_body = self.__internal_read_st is not None

        self.closed = has_body is False
        self._eot = self.closed

        # is kept to determine if we can upgrade conn
        self.authority = authority
        self.port = port

        # http.client compat layer
        self.debuglevel: int = 0  # no-op flag, kept for strict backward compatibility!
        self.chunked: bool = (  # is "chunked" being used? http1 only!
            self.version == 11 and "chunked" == self.msg.get("transfer-encoding")
        )
        self.chunk_left: int | None = None  # bytes left to read in current chunk
        self.length: int | None = None  # number of bytes left in response
        self.will_close: bool = (
            False  # no-op flag, kept for strict backward compatibility!
        )

        if not self.chunked:
            content_length = self.msg.get("content-length")
            self.length = int(content_length) if content_length else None

        #: not part of http.client but useful to track (raw) download speeds!
        self.data_in_count = 0

        self._stream_id = stream_id

        self.__buffer_excess: BytesQueueBuffer = BytesQueueBuffer()
        self.__promise: ResponsePromise | None = None
        self._dsa = dsa
        self._stream_abort = stream_abort

        self.trailers: HTTPHeaderDict | None = None

    @property
    def fp(
        self,
    ) -> (
        typing.NoReturn
    ):  # Defensive: incidental http.client file-pointer compatibility.
        raise RuntimeError(
            "urllib3-future no longer expose a filepointer-like in responses. It was a remnant from the http.client era. "
            "We no longer support it."
        )

    @property
    def from_promise(self) -> ResponsePromise | None:
        return self.__promise

    @from_promise.setter
    def from_promise(self, value: ResponsePromise) -> None:
        if value.stream_id != self._stream_id:
            raise ValueError(  # Defensive: built-in responses are assigned the promise for their own stream.
                "Trying to assign a ResponsePromise to an unrelated LowLevelResponse"
            )
        self.__promise = value

    @property
    def method(self) -> str:
        """Original HTTP verb used in the request."""
        return self._method

    def isclosed(self) -> bool:
        """Here we do not create a fp sock like http.client Response."""
        return self.closed

    async def read(self, __size: int | None = None) -> bytes:
        return await self._read(__size, read1=False)

    async def read1(self, __size: int | None = None) -> bytes:
        return await self._read(__size, read1=True)

    async def _read(self, __size: int | None, *, read1: bool) -> bytes:
        if self.closed is True or self.__internal_read_st is None:
            # overly protective, just in case.
            raise ValueError(
                "I/O operation on closed file."
            )  # Defensive: Should not be reachable in normal condition

        if __size == 0:
            return b""  # Defensive: This is unreachable, this case is already covered higher in the stack.

        buf_capacity = len(self.__buffer_excess)
        # any buffered data must be served first, even if smaller than
        # __size: reaching for the socket while holding deliverable bytes
        # can block forever on a live stream (e.g. SSE).
        # see https://github.com/jawah/urllib3.future/issues/379
        data_ready_to_go = __size is not None and buf_capacity > 0

        if self._eot is False and not data_ready_to_go:
            chunks, self._eot, self.trailers = await self.__internal_read_st(
                __size, self._stream_id
            )

            self.__buffer_excess.put_many(chunks)
            buf_capacity = len(self.__buffer_excess)

        if not read1 and __size is not None and __size > 0:
            while self._eot is False and buf_capacity < __size:
                chunks, self._eot, self.trailers = await self.__internal_read_st(
                    __size - buf_capacity, self._stream_id
                )
                self.__buffer_excess.put_many(chunks)
                buf_capacity = len(self.__buffer_excess)
                if not chunks:
                    break

        data = (
            self.__buffer_excess.get(
                __size if __size is not None and __size > 0 else buf_capacity
            )
            if buf_capacity
            else b""
        )

        size_in = len(data)

        buf_capacity -= size_in

        if self._eot and buf_capacity == 0:
            self._stream_abort = None
            self.closed = True
            self._sock = None

        if self.chunked:
            self.chunk_left = buf_capacity if buf_capacity else None
        elif self.length is not None:
            self.length -= size_in

        self.data_in_count += size_in

        return data

    async def abort(self) -> None:
        try:
            # Upgraded responses have no HTTP body, but their stream can still be open.
            if self._stream_abort is not None and (
                not self._eot or self._dsa is not None
            ):
                if self._stream_id is not None:
                    await self._stream_abort(self._stream_id)
        finally:
            self._eot = True
            self.close()

    def close(self) -> None:
        self._stream_abort = None
        self.__buffer_excess = BytesQueueBuffer()
        self.__internal_read_st = None
        self.closed = True
        self._dsa = None


class AsyncBaseBackend(BaseBackend):
    sock: AsyncSocket | SSLAsyncSocket | None  # type: ignore[assignment]

    async def _upgrade(self) -> None:  # type: ignore[override]
        """Upgrade conn from svn ver to max supported."""
        raise NotImplementedError

    async def _tunnel(self) -> None:  # type: ignore[override]
        """Emit proper CONNECT request to the http (server) intermediary."""
        raise NotImplementedError

    async def _new_conn(self) -> AsyncSocket | None:  # type: ignore[override]
        """Run protocol initialization from there. Return None to ensure that the child
        class correctly create the socket / connection."""
        raise NotImplementedError

    async def _post_conn(self) -> None:  # type: ignore[override]
        """Should be called after _new_conn proceed as expected.
        Expect protocol handshake to be done here."""
        raise NotImplementedError

    async def endheaders(  # type: ignore[override]
        self,
        message_body: bytes | None = None,
        *,
        encode_chunked: bool = False,
        expect_body_afterward: bool = False,
    ) -> ResponsePromise | None:
        """This method conclude the request context construction."""
        raise NotImplementedError

    async def getresponse(  # type: ignore[override]
        self, *, promise: ResponsePromise | None = None
    ) -> AsyncLowLevelResponse:
        """Fetch the HTTP response. You SHOULD not retrieve the body in that method, it SHOULD be done
        in the LowLevelResponse, so it enable stream capabilities and remain efficient.
        """
        raise NotImplementedError

    async def close(self) -> None:  # type: ignore[override]
        """End the connection, do some reinit, closing of fd, etc..."""
        raise NotImplementedError

    async def send(  # type: ignore[override]
        self,
        data: (bytes | typing.IO[typing.Any] | typing.Iterable[bytes] | str),
        *,
        eot: bool = False,
    ) -> ResponsePromise | None:
        """The send() method SHOULD be invoked after calling endheaders() if and only if the request
        context specify explicitly that a body is going to be sent."""
        raise NotImplementedError

    async def ping(self) -> None:  # type: ignore[override]
        raise NotImplementedError
