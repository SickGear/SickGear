from __future__ import annotations

import io
import asyncio
import json as _json
import sys
import typing
import warnings
from contextlib import asynccontextmanager
from socket import timeout as SocketTimeout

from .._collections import HTTPHeaderDict
from .._typing import _TYPE_BODY
from .._constant import (
    C_INT_MAX,
    CHUNK_AMT_MAX,
    DECODE_GROWTH_FACTOR,
    DECODE_MIN_RAW_REFERENCE,
)
from ..backend._async import AsyncLowLevelResponse
from ..exceptions import (
    BaseSSLError,
    BodyNotHttplibCompatible,
    HTTPError,
    IncompleteRead,
    ProtocolError,
    ReadTimeoutError,
    ResponseNotChunked,
    ResponseNotReady,
    SSLError,
    MustRedialError,
)
from ..response import ContentDecoder, HTTPResponse
from ..util.response import is_fp_closed
from ..util.retry import Retry
from ..util.traffic_police import UnavailableTraffic
from .connection import AsyncHTTPConnection

try:
    from jh2._hazmat import _BytesQueueBuffer as BytesQueueBuffer  # type: ignore[import-untyped]
except ImportError:
    from ..util.response import BytesQueueBuffer

if typing.TYPE_CHECKING:
    from email.message import Message

    from .._async.connectionpool import AsyncHTTPConnectionPool
    from ..contrib.webextensions._async import AsyncExtensionFromHTTP
    from ..util._async.traffic_police import AsyncTrafficPolice


class AsyncHTTPResponse(HTTPResponse):
    def __init__(
        self,
        body: _TYPE_BODY = "",
        headers: typing.Mapping[str, str] | typing.Mapping[bytes, bytes] | None = None,
        status: int = 0,
        version: int = 0,
        reason: str | None = None,
        preload_content: bool = True,
        decode_content: bool = True,
        original_response: AsyncLowLevelResponse | None = None,
        pool: AsyncHTTPConnectionPool | None = None,
        connection: AsyncHTTPConnection | None = None,
        msg: Message | None = None,
        retries: Retry | None = None,
        enforce_content_length: bool = True,
        request_method: str | None = None,
        request_url: str | None = None,
        auto_close: bool = True,
        police_officer: AsyncTrafficPolice[AsyncHTTPConnection] | None = None,
    ) -> None:
        if isinstance(headers, HTTPHeaderDict):
            self.headers = headers
        else:
            self.headers = HTTPHeaderDict(headers)  # type: ignore[arg-type]
        try:
            self.status = int(status)
        except ValueError:
            self.status = 0  # merely for tests, was supported due to broken httplib.
        self.version = version
        self.reason = reason
        self.decode_content = decode_content
        self._has_decoded_content = False
        self._request_url: str | None = request_url
        self._retries: Retry | None = None

        self._extension: AsyncExtensionFromHTTP | None = None  # type: ignore[assignment]

        self.retries = retries

        self.chunked = False

        if "transfer-encoding" in self.headers:
            tr_enc = self.headers.get("transfer-encoding", "").lower()
            # Don't incur the penalty of creating a list and then discarding it
            encodings = (enc.strip() for enc in tr_enc.split(","))

            if "chunked" in encodings:
                self.chunked = True

        self._decoder: ContentDecoder | None = None
        self._decoder_initialized = False

        self.enforce_content_length = enforce_content_length
        self.auto_close = auto_close

        self._body = None
        self._uncached_read_occurred = False
        self._fp: AsyncLowLevelResponse | typing.IO[typing.Any] | None = None  # type: ignore[assignment]
        self._original_response = original_response  # type: ignore[assignment]
        self._fp_bytes_read = 0

        if msg is not None:
            warnings.warn(
                "Passing msg=.. is deprecated and no-op in urllib3.future and is scheduled to be removed in a future major.",
                DeprecationWarning,
                stacklevel=2,
            )

        self.msg = msg

        if body and isinstance(body, (str, bytes)):
            self._body = body

        self._pool: AsyncHTTPConnectionPool = pool  # type: ignore[assignment]
        self._connection: AsyncHTTPConnection | None = connection  # type: ignore[assignment]

        if hasattr(body, "read"):
            self._fp = body  # type: ignore[assignment]

        # Are we using the chunked-style of transfer encoding?
        self.chunk_left: int | None = None

        # Determine length of response
        self._request_method: str | None = request_method
        self.length_remaining: int | None = self._init_length(self._request_method)

        # Used to return the correct amount of bytes for partial read()s
        self._decoded_buffer = BytesQueueBuffer()

        # Tracks the size of the last successful raw read so that
        # ``read(amt=-1)`` can bound how much it drains from the decoder's
        # internal buffer per call (issue #364, GHSA-mf9v-mfxr-j63j).
        self._last_raw_read_size: int = 0

        self._police_officer: AsyncTrafficPolice[AsyncHTTPConnection] | None = (
            police_officer  # type: ignore[assignment]
        )

        self._preloaded_content: bool = preload_content

        self._loop = asyncio.get_running_loop() if police_officer is not None else None
        if self._police_officer is not None:
            self._police_officer.memorize(self, self._connection)
            # we can utilize a ConnectionPool without level-0 PoolManager!
            # Direct collection after pool close need not hold a parent checkout.
            parent = self._police_officer.parent
            if parent is not None and (self._pool is not None or parent.busy):
                parent.memorize(self, self._pool)

    async def readinto(self, b: bytearray) -> int:  # type: ignore[override]
        temp = await self.read(len(b))
        if len(temp) == 0:
            return 0
        else:
            b[: len(temp)] = temp
            return len(temp)

    @asynccontextmanager
    async def _error_catcher(self) -> typing.AsyncGenerator[None, None]:  # type: ignore[override]
        """
        Catch low-level python exceptions, instead re-raising urllib3
        variants, so that low-level exceptions are not leaked in the
        high-level api.

        On exit, release the connection back to the pool.
        """
        clean_exit = False

        try:
            try:
                yield

            except SocketTimeout as e:
                # FIXME: Ideally we'd like to include the url in the ReadTimeoutError but
                # there is yet no clean way to get at it from this context.
                raise ReadTimeoutError(self._pool, None, "Read timed out.") from e  # type: ignore[arg-type]

            except BaseSSLError as e:
                # FIXME: Is there a better way to differentiate between SSLErrors?
                if "read operation timed out" not in str(e):
                    # SSL errors related to framing/MAC get wrapped and reraised here
                    raise SSLError(e) from e

                raise ReadTimeoutError(self._pool, None, "Read timed out.") from e  # type: ignore[arg-type]

            except (OSError, MustRedialError) as e:
                # This includes IncompleteRead.
                raise ProtocolError(f"Connection broken: {e!r}", e) from e

            # If no exception is thrown, we should avoid cleaning up
            # unnecessarily.
            clean_exit = True
        finally:
            # If we didn't terminate cleanly, we need to throw away our
            # connection.
            if not clean_exit:
                # The response may not be closed but we're not going to use it
                # anymore so close it now to ensure that the connection is
                # released back to the pool.
                if self._original_response:
                    self._original_response.close()

                # Closing the response may not actually be sufficient to close
                # everything, so if we have a hold of the connection close that
                # too.
                if self._connection:
                    await self._connection.close()

            # If we hold the original response but it's closed now, we should
            # return the connection back to the pool.
            if self._original_response and self._original_response.isclosed():
                self.release_conn()

    async def drain_conn(self) -> None:  # type: ignore[override]
        """
        Read and discard any remaining HTTP response data in the response connection.

        Unread data in the HTTPResponse connection blocks the connection from being released back to the pool.
        """
        # A sized read would close upgraded responses and clear their stream access.
        amt = 2**16 if getattr(self._fp, "_dsa", None) is None else None
        try:
            while await self._raw_read(amt):
                pass
        except (HTTPError, OSError, BaseSSLError):
            pass
        if self._has_decoded_content:
            # `_raw_read` skips decompression, so we should clean up the
            # decoder to avoid keeping unnecessary data in memory.
            self._decoded_buffer = BytesQueueBuffer()
            self._decoder = None
        if (
            self._police_officer is not None
            and self._fp is not None
            and is_fp_closed(self._fp)
            and getattr(self._fp, "_dsa", None) is None
        ):
            self._police_officer.forget(self)
            self._police_officer = None

    @property
    def trailers(self) -> HTTPHeaderDict | None:
        """
        Retrieve post-response (trailing headers) if any.
        This WILL return None if no HTTP Trailer Headers have been received.
        """
        if self._fp is None:
            return None

        if hasattr(self._fp, "trailers"):
            return self._fp.trailers

        return None

    @property
    def extension(self) -> AsyncExtensionFromHTTP | None:  # type: ignore[override]
        return self._extension

    async def start_extension(self, item: AsyncExtensionFromHTTP) -> None:  # type: ignore[override]
        if self._extension is not None:
            raise OSError("extension already plugged in")

        if not hasattr(self._fp, "_dsa"):
            raise ResponseNotReady()

        await item.start(self)

        self._extension = item

    async def json(self) -> typing.Any:
        """
        Parses the body of the HTTP response as JSON.

        To use a custom JSON decoder pass the result of :attr:`HTTPResponse.data` to the decoder.

        This method can raise either `UnicodeDecodeError` or `json.JSONDecodeError`.

        Read more :ref:`here <json>`.
        """
        return _json.loads(await self.data)

    @property
    async def data(self) -> bytes:  # type: ignore[override]
        # For backwards-compat with earlier urllib3 0.4 and earlier.
        if self._body:
            return self._body  # type: ignore[return-value]

        if self._fp:
            return await self.read(cache_content=True)

        return None  # type: ignore[return-value]

    async def _fp_read(  # type: ignore[override]
        self, amt: int | None = None, *, read1: bool = False
    ) -> bytes:
        """
        Read a response with the thought that reading the number of bytes
        larger than can fit in a 32-bit int at a time via SSL in some
        known cases leads to an overflow error that has to be prevented
        if `amt` or `self.length_remaining` indicate that a problem may
        happen.

        The known cases:
          * 3.8 <= CPython < 3.9.7 because of a bug
            https://github.com/urllib3/urllib3/issues/2513#issuecomment-1152559900.
          * urllib3 injected with pyOpenSSL-backed SSL-support.
          * CPython < 3.10 only when `amt` does not fit 32-bit int.
        """
        assert self._fp
        requires_safe_read = (
            (amt and amt > C_INT_MAX)
            or (self.length_remaining and self.length_remaining > C_INT_MAX)
        ) and sys.version_info < (3, 10)
        if read1 and isinstance(self._fp, AsyncLowLevelResponse):
            if requires_safe_read:
                amt = (
                    CHUNK_AMT_MAX if amt is None or amt < 0 else min(amt, CHUNK_AMT_MAX)
                )
            return await self._fp.read1(amt)
        if requires_safe_read:
            buffer = io.BytesIO()
            # Besides `max_chunk_amt` being a maximum chunk size, it
            # affects memory overhead of reading a response by this
            # method in CPython.
            # `c_int_max` equal to 2 GiB - 1 byte is the actual maximum
            # chunk size that does not lead to an overflow error, but
            # 256 MiB is a compromise.
            is_async_ll = isinstance(self._fp, AsyncLowLevelResponse)
            while amt is None or amt != 0:
                if amt is not None:
                    chunk_amt = min(amt, CHUNK_AMT_MAX)
                    amt -= chunk_amt
                else:
                    chunk_amt = CHUNK_AMT_MAX
                try:
                    if is_async_ll:
                        data = await self._fp.read(chunk_amt)
                    else:
                        data = self._fp.read(chunk_amt)
                except ValueError:  # Defensive: overly protective
                    break  # Defensive: can also be an indicator that read ended, should not happen.
                if not data:
                    break
                buffer.write(data)
                del data  # to reduce peak memory usage by `max_chunk_amt`.
            return buffer.getvalue()
        else:
            # StringIO doesn't like amt=None
            if isinstance(self._fp, AsyncLowLevelResponse):
                return await self._fp.read(amt)
            return self._fp.read(amt) if amt is not None else self._fp.read()  # type: ignore[no-any-return]

    async def _raw_read(  # type: ignore[override]
        self,
        amt: int | None = None,
        *,
        read1: bool = False,
    ) -> bytes:
        """
        Reads `amt` of bytes from the socket.
        """
        if self._fp is None:
            return None  # type: ignore[return-value]

        fp_closed = getattr(self._fp, "closed", False)

        async with self._error_catcher():
            data = (await self._fp_read(amt, read1=read1)) if not fp_closed else b""

            # Mocking library often use io.BytesIO
            # which does not auto-close when reading data
            # with amt=None.
            is_foreign_fp_unclosed = amt is None and not getattr(
                self._fp, "closed", False
            )

            if (amt is not None and amt != 0 and not data) or is_foreign_fp_unclosed:
                if is_foreign_fp_unclosed:
                    data_len = len(data)
                    self._fp_bytes_read += data_len
                    if self.length_remaining is not None:
                        self.length_remaining -= data_len

                # Platform-specific: Buggy versions of Python.
                # Close the connection when no data is returned
                #
                # This is redundant to what httplib/http.client _should_
                # already do.  However, versions of python released before
                # December 15, 2012 (http://bugs.python.org/issue16298) do
                # not properly close the connection in all cases. There is
                # no harm in redundantly calling close.
                self._fp.close()
                if (
                    not is_foreign_fp_unclosed
                    and self.enforce_content_length
                    and self.length_remaining is not None
                    and self.length_remaining != 0
                ):
                    # This is an edge case that httplib failed to cover due
                    # to concerns of backward compatibility. We're
                    # addressing it here to make sure IncompleteRead is
                    # raised during streaming, so all calls with incorrect
                    # Content-Length are caught.
                    raise IncompleteRead(self._fp_bytes_read, self.length_remaining)

        if data and not is_foreign_fp_unclosed:
            data_len = len(data)
            self._fp_bytes_read += data_len
            if self.length_remaining is not None:
                self.length_remaining -= data_len

        if isinstance(data, (bytes, bytearray)) and data:
            self._last_raw_read_size = len(data)

        return data

    async def read1(  # type: ignore[override]
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
    ) -> bytes:
        """
        Similar to ``http.client.HTTPResponse.read1`` and documented
        in :meth:`io.BufferedReader.read1`, but with an additional parameter:
        ``decode_content``.

        :param amt:
            How much of the content to read.

        :param decode_content:
            If True, will attempt to decode the body based on the
            'content-encoding' header.
        """

        # A zero-byte read must not consume data or change response state.
        if amt == 0:
            return b""

        data = await self._read(
            amt=amt or -1,
            decode_content=decode_content,
            read1=True,
        )
        self._uncached_read_occurred = True

        return data

    async def read(  # type: ignore[override]
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
    ) -> bytes:
        """Read response data asynchronously.

        ``amt=None`` reads the remaining body. Positive sizes read up to that
        many bytes, and zero returns empty bytes without consuming input.
        Negative sizes retain incremental behavior for backward compatibility,
        unlike synchronous HTTPResponse.read().
        """
        return await self._read(
            amt=amt,
            decode_content=decode_content,
            cache_content=cache_content,
        )

    async def _read(  # type: ignore[override]
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
        *,
        read1: bool = False,
    ) -> bytes:
        # Zero-byte reads must not advance the transport or the decoder.
        if amt == 0:
            return b""
        try:
            self._init_decoder()
            if decode_content is None:
                decode_content = self.decode_content

            if amt is not None:
                cache_content = False

                if amt < 0:
                    # Drain any pending data already buffered inside the
                    # decoder before triggering another raw read. Without
                    # this, ``stream(amt=-1)`` would loop forever on
                    # ``_decoder.has_unconsumed_tail`` whenever the decoder
                    # retains bytes (e.g., gzip body whose decoded output
                    # exceeded the previous ``max_length`` cap). The
                    # decoded chunk is bounded by a reasonable growth
                    # factor of the most recent raw read so a single recv
                    # carrying many HTTP/2/3 frames cannot expand into
                    # arbitrarily large memory (issue #364, see also
                    # GHSA-mf9v-mfxr-j63j).
                    if self._decoder and self._decoder.has_unconsumed_tail:
                        cap = (
                            max(
                                self._last_raw_read_size,
                                DECODE_MIN_RAW_REFERENCE,
                            )
                            * DECODE_GROWTH_FACTOR
                        )
                        decoded_data = self._decode(
                            b"",
                            decode_content,
                            flush_decoder=False,
                            max_length=cap,
                        )
                        if decoded_data:
                            self._decoded_buffer.put(decoded_data)

                    if len(self._decoded_buffer):
                        return self._decoded_buffer.get(len(self._decoded_buffer))  # type: ignore[no-any-return]

                if amt > 0:
                    # Drain any pending data already buffered inside the
                    # decoder before triggering another raw read. This
                    # prevents decompression bombs where a single raw
                    # chunk would otherwise produce a huge decoded
                    # output (see GHSA-mf9v-mfxr-j63j).
                    if (
                        self._decoder
                        and self._decoder.has_unconsumed_tail
                        and len(self._decoded_buffer) < amt
                    ):
                        decoded_data = self._decode(
                            b"",
                            decode_content,
                            flush_decoder=False,
                            max_length=amt - len(self._decoded_buffer),
                        )
                        self._decoded_buffer.put(decoded_data)

                    if amt <= len(self._decoded_buffer):
                        return self._decoded_buffer.get(amt)  # type: ignore[no-any-return]

            if self._police_officer is not None:
                async with self._police_officer.borrow(self):
                    data = await self._raw_read(amt, read1=read1)
            else:
                data = await self._raw_read(amt, read1=read1)

            if not cache_content:
                self._uncached_read_occurred = True

            if amt and amt < 0:
                amt = len(data)

            flush_decoder = False
            if amt is None:
                flush_decoder = True
            elif amt != 0 and not data:
                flush_decoder = True

            decoder = self._decoder
            if not self._decoded_buffer:
                if (
                    decoder is None
                    and decode_content
                    and isinstance(self._fp, AsyncLowLevelResponse)
                    and (amt is not None or not cache_content)
                ):
                    return data

                if not data and (decoder is None or not decoder.has_unconsumed_tail):
                    return data

            if amt is None:
                data = self._decode(data, decode_content, flush_decoder)
                # A previous bounded read may have left decoded output buffered.
                if self._decoded_buffer:
                    data = self._decoded_buffer.get(len(self._decoded_buffer)) + data
                if cache_content and not self._uncached_read_occurred:
                    self._body = data
            else:
                # do not waste memory on buffer when not decoding
                if not decode_content:
                    if self._has_decoded_content:
                        raise RuntimeError(
                            "Calling read(decode_content=False) is not supported after "
                            "read(decode_content=True) was called."
                        )
                    return data

                decoded_data = self._decode(
                    data,
                    decode_content,
                    flush_decoder,
                    max_length=amt - len(self._decoded_buffer),
                )
                self._decoded_buffer.put(decoded_data)

                single_exchange = read1 and hasattr(self._fp, "_eot")
                while len(self._decoded_buffer) < amt and data and not single_exchange:
                    # TODO make sure to initially read enough data to get past the headers
                    # For example, the GZ file header takes 10 bytes, we don't want to read
                    # it one byte at a time
                    if self._police_officer is not None:
                        async with self._police_officer.borrow(self):
                            data = await self._raw_read(amt)
                    else:
                        data = await self._raw_read(amt)

                    decoded_data = self._decode(
                        data,
                        decode_content,
                        flush_decoder,
                        max_length=amt - len(self._decoded_buffer),
                    )
                    self._decoded_buffer.put(decoded_data)
                data = self._decoded_buffer.get(amt)

            return data
        finally:
            if (
                self._fp
                and (getattr(self._fp, "_eot", False) or is_fp_closed(self._fp))
                and self._police_officer is not None
            ):
                # an HTTP extension could be live, we don't want to accidentally kill it!
                if (
                    not hasattr(self._fp, "_dsa")
                    or self._fp._dsa is None
                    or self._fp._dsa.closed
                ):
                    self._police_officer.forget(self)
                    self._police_officer = None

    async def stream(  # type: ignore[override]
        self, amt: int | None = 2**16, decode_content: bool | None = None
    ) -> typing.AsyncGenerator[bytes, None]:
        if amt == 0:
            return
        if self._fp is None:
            return
        while (
            not is_fp_closed(self._fp)
            or self._decoded_buffer
            or (self._decoder and self._decoder.has_unconsumed_tail)
        ):
            data = await self.read1(amt=amt, decode_content=decode_content)

            if data:
                yield data

    async def _handle_chunk(  # type: ignore[override]
        self, amt: int | None, decode_content: bool | None = None
    ) -> bytes:
        """Read one transfer-decoded body segment from the protocol backend."""
        return await self.read1(
            amt=-1 if amt is None else amt,
            decode_content=decode_content,
        )

    async def read_chunked(  # type: ignore[override]
        self, amt: int | None = None, decode_content: bool | None = None
    ) -> typing.AsyncGenerator[bytes, None]:
        """Read an HTTP/1.1 chunked response as transfer-decoded segments."""
        self._init_decoder()
        if not self.chunked:
            raise ResponseNotChunked(
                "Response is not chunked. "
                "Header 'transfer-encoding: chunked' is missing."
            )
        if not self.supports_chunked_reads():
            raise BodyNotHttplibCompatible(
                "Body should be http.client.HTTPResponse like. "
                "It should have an fp attribute which returns raw chunks."
            )
        if decode_content is None:
            decode_content = self.decode_content
        if amt == 0:
            return
        if amt is not None and amt < 0:
            amt = None

        async with self._error_catcher():
            while self._fp is not None and (
                not is_fp_closed(self._fp)
                or len(self._decoded_buffer) > 0
                or (self._decoder and self._decoder.has_unconsumed_tail)
            ):
                data = await self._handle_chunk(amt, decode_content)
                if data:
                    yield data

            if decode_content:
                data = self._flush_decoder()
                if data:
                    yield data

    def supports_chunked_reads(self) -> bool:
        return isinstance(self._fp, AsyncLowLevelResponse) or hasattr(self._fp, "fp")

    async def close(self) -> None:  # type: ignore[override]
        if self.extension is not None and not self.extension.closed:
            await self.extension.close()

        if (
            isinstance(self._fp, AsyncLowLevelResponse)
            and self._police_officer is not None
        ):
            police = self._police_officer
            try:
                async with police.borrow(self) as conn:
                    try:
                        await self._fp.abort()
                    except (OSError, BaseSSLError):
                        # A failed reset write makes the transport unusable.
                        await conn.close()
                    finally:
                        self._fp.close()
                        self._connection = None
            except UnavailableTraffic:
                self._fp.close()
                self._connection = None
            finally:
                if self._fp.closed:
                    police.forget(self)
                    self._police_officer = None
        elif isinstance(self._fp, AsyncLowLevelResponse) and self._fp._eot:
            self._fp.close()
            self._connection = None
        else:
            if not self.closed and self._fp:
                self._fp.close()
            if self._connection:
                await self._connection.close()  # Defensive: external file-like body.

        if not self.auto_close:
            io.IOBase.close(self)

    async def __aiter__(self) -> typing.AsyncIterator[bytes]:
        buffer: list[bytes] = []
        async for chunk in self.stream(-1, decode_content=True):
            if b"\n" in chunk:
                chunks = chunk.split(b"\n")
                yield b"".join([*buffer, chunks[0], b"\n"])
                for x in chunks[1:-1]:
                    yield x + b"\n"
                if chunks[-1]:
                    buffer = [chunks[-1]]
                else:
                    buffer = []
            else:
                buffer.append(chunk)
        if buffer:
            yield b"".join(buffer)

    async def _close_from_gc(self) -> None:
        police = self._police_officer
        reclaimed = police._reclaim_reservation(self) if police is not None else None
        try:
            await self.close()
        finally:
            if reclaimed is not None and police is not None:
                police._signals.terminate_writing()
                police.release()
                if police._shutdown:
                    await police.kill(reclaimed, idle_only=True)

    def __del__(self) -> None:
        if not getattr(self, "closed", True):
            loop = getattr(self, "_loop", None)
            police = getattr(self, "_police_officer", None)
            if loop is not None and not loop.is_closed() and police is not None:
                try:
                    loop.call_soon_threadsafe(police._schedule_gc_close, self)
                    return
                except (
                    RuntimeError,
                    NotImplementedError,
                ):  # Defensive: loop closed after the check, or scheduling unsupported.
                    pass  # Closed loop or unsupported runtime: local cleanup only.
            if self._fp:
                self._fp.close()
            if not self.auto_close:
                io.IOBase.close(self)
