from __future__ import annotations

import io
import json as _json
import logging
import re
import sys
import typing
import warnings
from contextlib import contextmanager
from socket import timeout as SocketTimeout

try:
    import zlib
except ImportError:
    zlib = None  # type: ignore[assignment]

try:
    try:
        import brotlicffi as brotli  # type: ignore[import-not-found]
    except ImportError:
        import brotli  # type: ignore[import-not-found]
except ImportError:
    brotli = None

try:
    import zstandard as zstd

    # The package 'zstandard' added the 'eof' property starting
    # in v0.18.0 which we require to ensure a complete and
    # valid zstd stream was fed into the ZstdDecoder.
    # See: https://github.com/urllib3/urllib3/pull/2624
    _zstd_version = tuple(
        map(int, re.search(r"^([0-9]+)\.([0-9]+)", zstd.__version__).groups())  # type: ignore[union-attr]
    )
    if _zstd_version < (0, 18):  # Defensive:
        zstd = None  # type: ignore[assignment]

except (AttributeError, ImportError, ValueError):  # Defensive:
    try:
        from compression import zstd  # type: ignore[no-redef]
    except ImportError:
        zstd = None  # type: ignore[assignment]

from ._collections import HTTPHeaderDict
from ._typing import _TYPE_BODY
from ._constant import (
    C_INT_MAX,
    CHUNK_AMT_MAX,
    DECODE_GROWTH_FACTOR,
    DECODE_MIN_RAW_REFERENCE,
)
from .backend import LowLevelResponse, ResponsePromise
from .exceptions import (
    BaseSSLError,
    BodyNotHttplibCompatible,
    DecodeError,
    DependencyWarning,
    HTTPError,
    IncompleteRead,
    InvalidHeader,
    ProtocolError,
    ReadTimeoutError,
    ResponseNotChunked,
    ResponseNotReady,
    SSLError,
    MustRedialError,
)
from .util.response import is_fp_closed
from .util.retry import Retry
from .util.traffic_police import UnavailableTraffic

try:
    from jh2._hazmat import _BytesQueueBuffer as BytesQueueBuffer  # type: ignore[import-untyped]
except ImportError:
    from .util.response import BytesQueueBuffer

if typing.TYPE_CHECKING:
    from email.message import Message

    from typing_extensions import Literal

    from .connection import HTTPConnection
    from .connectionpool import HTTPConnectionPool
    from .contrib.webextensions import ExtensionFromHTTP
    from .util.traffic_police import TrafficPolice

log = logging.getLogger(__name__)


class ContentDecoder:
    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        raise NotImplementedError()

    @property
    def has_unconsumed_tail(self) -> bool:
        raise NotImplementedError()

    def flush(self) -> bytes:
        raise NotImplementedError()


class DeflateDecoder(ContentDecoder):
    def __init__(self) -> None:
        self._first_try = True
        self._first_try_data = b""
        self._unfed_data = b""
        self._obj = zlib.decompressobj()

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        data = self._unfed_data + data
        self._unfed_data = b""
        # Data received after EOF cannot produce more output from this
        # Deflate stream.
        if self._obj.eof:
            return b""
        if not data and not self._obj.unconsumed_tail:
            return data
        original_max_length = max_length
        if original_max_length < 0:
            max_length = 0
        elif original_max_length == 0:  # Defensive: direct decoder calls only.
            # We should not pass 0 to the zlib decompressor because 0 is
            # the default value that will make zlib decompress without a
            # length limit.
            # Data should be stored for subsequent calls.
            self._unfed_data = data
            return b""

        # Subsequent calls always reuse `self._obj`. zlib requires
        # passing the unconsumed tail if decompression is to continue.
        if not self._first_try:
            return self._obj.decompress(
                self._obj.unconsumed_tail + data, max_length=max_length
            )

        # First call tries with RFC 1950 ZLIB format.
        self._first_try_data += data
        try:
            decompressed = self._obj.decompress(data, max_length=max_length)
            if decompressed:
                self._first_try = False
                self._first_try_data = b""
            return decompressed
        # On failure, it falls back to RFC 1951 DEFLATE format.
        except zlib.error:
            self._first_try = False
            self._obj = zlib.decompressobj(-zlib.MAX_WBITS)
            try:
                return self.decompress(
                    self._first_try_data, max_length=original_max_length
                )
            finally:
                self._first_try_data = b""

    @property
    def has_unconsumed_tail(self) -> bool:
        return bool(self._unfed_data) or (
            bool(self._obj.unconsumed_tail)
            and not self._first_try
            and not self._obj.eof
        )

    def flush(self) -> bytes:
        return self._obj.flush()


class GzipDecoderState:
    FIRST_MEMBER = 0
    OTHER_MEMBERS = 1
    SWALLOW_DATA = 2


class GzipDecoder(ContentDecoder):
    def __init__(self) -> None:
        self._obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self._state = GzipDecoderState.FIRST_MEMBER
        self._unconsumed_tail = b""

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        if self._state == GzipDecoderState.SWALLOW_DATA:
            return b""

        if max_length == 0:  # Defensive: direct decoder calls only.
            # We should not pass 0 to the zlib decompressor because 0 is
            # the default value that will make zlib decompress without a
            # length limit.
            # Data should be stored for subsequent calls.
            self._unconsumed_tail += data
            return b""

        # zlib requires passing the unconsumed tail to the subsequent
        # call if decompression is to continue.
        data = self._unconsumed_tail + data
        if not data and self._obj.eof:
            return b""

        # Keep zlib's bytes object unless multiple outputs need combining.
        ret: bytes | bytearray = b""
        while True:
            try:
                chunk = self._obj.decompress(
                    data, max_length=max(max_length - len(ret), 0)
                )
                if not ret:
                    ret = chunk
                elif chunk:
                    if isinstance(ret, bytes):
                        ret = bytearray(ret)
                    ret += chunk
                    del chunk
            except zlib.error:
                previous_state = self._state
                # Ignore data after the first error
                self._state = GzipDecoderState.SWALLOW_DATA
                self._unconsumed_tail = b""
                if previous_state == GzipDecoderState.OTHER_MEMBERS:
                    # Allow trailing garbage acceptable in other gzip clients
                    return ret if isinstance(ret, bytes) else bytes(ret)
                raise

            self._unconsumed_tail = data = (
                self._obj.unconsumed_tail or self._obj.unused_data
            )
            if max_length > 0 and len(ret) >= max_length:
                break

            if not data:
                return ret if isinstance(ret, bytes) else bytes(ret)
            # When the end of a gzip member is reached, a new decompressor
            # must be created for unused (possibly future) data.
            if self._obj.eof:
                self._state = GzipDecoderState.OTHER_MEMBERS
                self._obj = zlib.decompressobj(16 + zlib.MAX_WBITS)

        return ret if isinstance(ret, bytes) else bytes(ret)

    @property
    def has_unconsumed_tail(self) -> bool:
        return bool(self._unconsumed_tail)

    def flush(self) -> bytes:
        if self._state == GzipDecoderState.SWALLOW_DATA:
            return b""
        return self._obj.flush()


if brotli is not None:

    class BrotliDecoder(ContentDecoder):
        # Supports both 'brotlipy' and 'Brotli' packages
        # since they share an import name. The top branches
        # are for 'brotlipy' and bottom branches for 'Brotli'
        def __init__(self) -> None:
            self._obj = brotli.Decompressor()
            # brotlicffi honors output_buffer_limit, so can_accept_more_data
            # is trustworthy. google brotli/brotlipy only expose process(),
            # ignore the limit and report can_accept_more_data=True while
            # output is still pending. Track pending output ourselves there
            # (issue #385).
            if hasattr(self._obj, "decompress"):
                setattr(self, "_decompress", self._obj.decompress)
                self._lack_output_buffer_limit = False
            else:
                setattr(self, "_decompress", self._obj.process)
                self._lack_output_buffer_limit = True
            self._pending_output = False

        # Requires Brotli >= 1.2.0 for `output_buffer_limit`.
        def _decompress(self, data: bytes, output_buffer_limit: int = -1) -> bytes:
            raise NotImplementedError()

        def decompress(self, data: bytes, max_length: int = -1) -> bytes:
            try:
                if max_length > 0:
                    decompressed = self._decompress(
                        data, output_buffer_limit=max_length
                    )
                else:
                    decompressed = self._decompress(data)
            except TypeError:
                # Fallback for Brotli/brotlicffi/brotlipy versions without
                # the `output_buffer_limit` parameter.
                warnings.warn(
                    "Brotli >= 1.2.0 is required to prevent decompression bombs.",
                    DependencyWarning,
                )
                decompressed = self._decompress(data)
            # non-empty output means more may remain; drives has_unconsumed_tail.
            self._pending_output = bool(decompressed)
            return decompressed

        @property
        def has_unconsumed_tail(self) -> bool:
            if self._lack_output_buffer_limit:
                return self._pending_output
            try:
                return not self._obj.can_accept_more_data()
            except AttributeError:
                return False

        def flush(self) -> bytes:
            if hasattr(self._obj, "flush"):
                return self._obj.flush()  # type: ignore[no-any-return]
            return b""


if zstd is not None:
    # help distinguish external library from stdlib one
    _zstd_native = not hasattr(zstd.ZstdDecompressor, "decompressobj")

    def _new_zstd_obj() -> typing.Any:
        return (
            zstd.ZstdDecompressor().decompressobj()
            if not _zstd_native
            else zstd.ZstdDecompressor()
        )

    class ZstdDecoder(ContentDecoder):
        def __init__(self) -> None:
            self._obj = _new_zstd_obj()

        def _decompress_chunk(self, data: bytes, max_length: int) -> bytes:
            if _zstd_native:
                return self._obj.decompress(data, max_length=max_length)  # type: ignore[no-any-return]
            return self._obj.decompress(data)  # type: ignore[no-any-return]

        def decompress(self, data: bytes, max_length: int = -1) -> bytes:
            if not data and not self.has_unconsumed_tail:
                return b""
            if self._obj.eof:
                data = self._obj.unused_data + data
                self._obj = _new_zstd_obj()
            part = self._decompress_chunk(data, max_length)
            length = len(part)
            data_parts = [part]
            # Every loop iteration is supposed to read data from a separate frame.
            # The loop breaks when:
            #   - enough data is read;
            #   - no more unused data is available;
            #   - end of the last read frame has not been reached (i.e.,
            #     more data has to be fed).
            while (
                self._obj.eof
                and self._obj.unused_data
                and (max_length < 0 or length < max_length)
            ):
                unused_data = self._obj.unused_data
                # The third-party `zstandard` decompressobj cannot be reused
                # after eof; stdlib `compression.zstd` can be reused while it
                # still `needs_input`. Reset accordingly.
                if not _zstd_native or not getattr(self._obj, "needs_input", True):
                    self._obj = _new_zstd_obj()
                part = self._decompress_chunk(
                    unused_data,
                    (max_length - length) if max_length > 0 else -1,
                )
                part_length = len(part)
                if part_length:
                    data_parts.append(part)
                    length += part_length
                elif getattr(self._obj, "needs_input", True):
                    break
            return b"".join(data_parts)

        @property
        def has_unconsumed_tail(self) -> bool:
            return not (
                getattr(self._obj, "needs_input", True) or self._obj.eof
            ) or bool(self._obj.unused_data)

        def flush(self) -> bytes:
            if _zstd_native:
                if not self._obj.eof:
                    raise DecodeError("Zstandard data is incomplete")
                return b""

            ret = self._obj.flush()
            if not self._obj.eof:
                raise DecodeError("Zstandard data is incomplete")
            return ret  # type: ignore[no-any-return]


class MultiDecoder(ContentDecoder):
    """
    From RFC7231:
        If one or more encodings have been applied to a representation, the
        sender that applied the encodings MUST generate a Content-Encoding
        header field that lists the content codings in the order in which
        they were applied.
    """

    # Maximum allowed number of chained HTTP encodings in the
    # Content-Encoding header.
    max_decode_links = 5

    def __init__(self, modes: str) -> None:
        encodings = [m.strip() for m in modes.split(",")]

        if len(encodings) > self.max_decode_links:
            raise DecodeError(
                "Too many content encodings in the chain: "
                f"{len(encodings)} > {self.max_decode_links}"
            )

        self._decoders = [_get_decoder(e) for e in encodings]

    def flush(self) -> bytes:
        return self._decoders[0].flush()

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        if max_length <= 0:
            for d in reversed(self._decoders):
                data = d.decompress(data)
            return data

        ret = bytearray()
        # Every while loop iteration goes through all decoders once.
        # It exits when enough data is read or no more data can be read.
        # It is possible that the while loop iteration does not produce
        # any data because we retrieve up to `max_length` from every
        # decoder, and the amount of bytes may be insufficient for the
        # next decoder to produce enough/any output.
        while True:
            any_data = False
            for d in reversed(self._decoders):
                data = d.decompress(data, max_length=max_length - len(ret))
                if data:
                    any_data = True
                # We should not break when no data is returned because
                # next decoders may produce data even with empty input.
            ret += data
            if not any_data or len(ret) >= max_length:
                return bytes(ret)
            data = b""

    @property
    def has_unconsumed_tail(self) -> bool:
        return any(d.has_unconsumed_tail for d in self._decoders)


def _get_decoder(mode: str) -> ContentDecoder:
    if "," in mode:
        return MultiDecoder(mode)

    if zlib is not None and mode == "gzip":
        return GzipDecoder()

    if brotli is not None and mode == "br":
        return BrotliDecoder()

    if zstd is not None and mode == "zstd":
        return ZstdDecoder()

    # Preserve the historical fallback to deflate for unknown modes. Callers
    # only pass advertised/supported modes here.
    if zlib is not None:
        return DeflateDecoder()

    # Normal responses filter unsupported encodings before calling this factory.
    raise DecodeError(
        f"Unsupported content encoding: {mode}"
    )  # Defensive: no matching decoder and zlib is unavailable.


class HTTPResponse(io.IOBase):
    """
    HTTP Response container.

    Backwards-compatible with :class:`http.client.HTTPResponse` but the response ``body`` is
    loaded and decoded on-demand when the ``data`` property is accessed.  This
    class is also compatible with the Python standard library's :mod:`io`
    module, and can hence be treated as a readable object in the context of that
    framework.

    Extra parameters for behaviour not present in :class:`http.client.HTTPResponse`:

    :param preload_content:
        If True, the response's body will be preloaded during construction.

    :param decode_content:
        If True, will attempt to decode the body based on the
        'content-encoding' header.

    :param original_response:
        When this HTTPResponse wrapper is generated from an :class:`http.client.HTTPResponse`
        object, it's convenient to include the original for debug purposes. It's
        otherwise unused.

    :param retries:
        The retries contains the last :class:`~urllib3.util.retry.Retry` that
        was used during the request.

    :param enforce_content_length:
        Enforce content length checking. Body returned by server must match
        value of Content-Length header, if present. Otherwise, raise error.
    """

    CONTENT_DECODERS = []
    if zlib is not None:
        CONTENT_DECODERS += ["gzip", "deflate"]
    if brotli is not None:
        CONTENT_DECODERS += ["br"]
    if zstd is not None:
        CONTENT_DECODERS += ["zstd"]
    REDIRECT_STATUSES = [301, 302, 303, 307, 308]

    DECODER_ERROR_CLASSES: tuple[type[Exception], ...] = (IOError,)
    if zlib is not None:
        DECODER_ERROR_CLASSES += (zlib.error,)
    if brotli is not None:
        DECODER_ERROR_CLASSES += (brotli.error,)

    if zstd is not None:
        DECODER_ERROR_CLASSES += (zstd.ZstdError,)

    def __init__(
        self,
        body: _TYPE_BODY = "",
        headers: typing.Mapping[str, str] | typing.Mapping[bytes, bytes] | None = None,
        status: int = 0,
        version: int = 0,
        reason: str | None = None,
        preload_content: bool = True,
        decode_content: bool = True,
        original_response: LowLevelResponse | None = None,
        pool: HTTPConnectionPool | None = None,
        connection: HTTPConnection | None = None,
        msg: Message | None = None,
        retries: Retry | None = None,
        enforce_content_length: bool = True,
        request_method: str | None = None,
        request_url: str | None = None,
        auto_close: bool = True,
        police_officer: TrafficPolice[HTTPConnection] | None = None,
    ) -> None:
        if isinstance(headers, HTTPHeaderDict):
            self.headers = headers
        else:
            self.headers = HTTPHeaderDict(headers)  # type: ignore[arg-type]
        try:
            self.status = int(status)
        except ValueError:
            self.status = 0  # merely for tests, was supported due to broken httplib.

        # Mind this case for later on!
        if preload_content and status == 101:
            preload_content = False

        self.version = version
        self.reason = reason
        self.decode_content = decode_content
        self._has_decoded_content = False
        self._request_url: str | None = request_url
        self._retries: Retry | None = None

        self._extension: ExtensionFromHTTP | None = None

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
        self._fp: LowLevelResponse | typing.IO[typing.Any] | None = None
        self._original_response = original_response
        self._fp_bytes_read = 0

        self.msg = msg  # no-op, kept for BC.

        if body and isinstance(body, (str, bytes)):
            self._body = body

        self._pool = pool
        self._connection = connection

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

        self._police_officer: TrafficPolice[HTTPConnection] | None = police_officer

        if self._police_officer is not None:
            self._police_officer.memorize(self, self._connection)
            # Direct collection after pool close need not hold a parent checkout.
            parent = self._police_officer.parent
            if parent is not None and (self._pool is not None or parent.busy):
                parent.memorize(self, self._pool)

        self._preloaded_content = preload_content

        # If requested, preload the body.
        if preload_content and not self._body:
            self._body = self.read(decode_content=decode_content)

    def is_from_promise(self, promise: ResponsePromise) -> bool:
        """
        Determine if this response came from given promise.
        """
        return (
            self._fp is not None
            and hasattr(self._fp, "from_promise")
            and self._fp.from_promise == promise
        )

    def get_redirect_location(self) -> str | None | Literal[False]:
        """
        Should we redirect and where to?

        :returns: Truthy redirect location string if we got a redirect status
            code and valid location. ``None`` if redirect status and no
            location. ``False`` if not a redirect status code.
        """
        if self.status in self.REDIRECT_STATUSES:
            return self.headers.get("location")
        return False

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
    def extension(self) -> ExtensionFromHTTP | None:
        return self._extension

    def start_extension(self, item: ExtensionFromHTTP) -> None:
        if self._extension is not None:
            raise OSError("extension already plugged in")

        if not hasattr(self._fp, "_dsa"):
            raise ResponseNotReady()

        item.start(self)

        self._extension = item

    def json(self) -> typing.Any:
        """
        Parses the body of the HTTP response as JSON.

        To use a custom JSON decoder pass the result of :attr:`HTTPResponse.data` to the decoder.

        This method can raise either `UnicodeDecodeError` or `json.JSONDecodeError`.

        Read more :ref:`here <json>`.
        """
        return _json.loads(self.data)

    @property
    def retries(self) -> Retry | None:
        return self._retries

    @retries.setter
    def retries(self, retries: Retry | None) -> None:
        # Override the request_url if retries has a redirect location.
        if retries is not None and retries.history:
            if isinstance(retries.history[-1].redirect_location, str):
                self.url = retries.history[-1].redirect_location
        self._retries = retries

    def _init_decoder(self) -> None:
        """
        Set-up the _decoder attribute if necessary.
        """
        if self._decoder_initialized:
            return

        if self._decoder is None:
            # Note: content-encoding value should be case-insensitive, per RFC 7230
            # Section 3.2
            content_encoding = self.headers.get("content-encoding", "").lower()
            if content_encoding in self.CONTENT_DECODERS:
                self._decoder = _get_decoder(content_encoding)
            elif "," in content_encoding:
                encodings = [e.strip() for e in content_encoding.split(",")]
                if encodings and all(e in self.CONTENT_DECODERS for e in encodings):
                    self._decoder = _get_decoder(content_encoding)

        self._decoder_initialized = True

    def _decode(
        self,
        data: bytes,
        decode_content: bool | None,
        flush_decoder: bool,
        max_length: int | None = None,
    ) -> bytes:
        """
        Decode the data passed in and potentially flush the decoder.
        """
        if not decode_content:
            if self._has_decoded_content:
                raise RuntimeError(
                    "Calling read(decode_content=False) is not supported after "
                    "read(decode_content=True) was called."
                )
            return data

        if max_length is None or flush_decoder:
            max_length = -1

        try:
            if self._decoder:
                data = self._decoder.decompress(data, max_length=max_length)
                self._has_decoded_content = True
        except self.DECODER_ERROR_CLASSES as e:
            content_encoding = self.headers.get("content-encoding", "").lower()
            raise DecodeError(
                "Received response with content-encoding: %s, but "
                "failed to decode it." % content_encoding,
                e,
            ) from e
        if flush_decoder:
            data += self._flush_decoder()

        return data

    def _flush_decoder(self) -> bytes:
        """
        Flushes the decoder. Should only be called if the decoder is actually
        being used.
        """
        if self._decoder:
            return self._decoder.decompress(b"") + self._decoder.flush()
        return b""

    # Compatibility methods for `io` module
    def readinto(self, b: bytearray) -> int:
        temp = self.read(len(b))
        if len(temp) == 0:
            return 0
        else:
            b[: len(temp)] = temp
            return len(temp)

    # Compatibility method for http.cookiejar
    def info(self) -> HTTPHeaderDict:
        return self.headers

    def geturl(self) -> str | None:
        return self.url

    def release_conn(self) -> None:
        if not self._connection:
            return None

        if (
            self._police_officer is not None
            and self._police_officer.is_held(self._connection) is True
        ):
            self._police_officer.release()

        self._connection = None

    def drain_conn(self) -> None:
        """
        Read and discard any remaining HTTP response data in the response connection.

        Unread data in the HTTPResponse connection blocks the connection from being released back to the pool.
        """
        # A sized read would close upgraded responses and clear their stream access.
        amt = 2**16 if getattr(self._fp, "_dsa", None) is None else None
        try:
            while self._raw_read(amt):
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
    def data(self) -> bytes:
        # For backwards-compat with earlier urllib3 0.4 and earlier.
        if self._body:
            return self._body  # type: ignore[return-value]

        if self._fp:
            return self.read(cache_content=True)

        return None  # type: ignore[return-value]

    @property
    def connection(self) -> HTTPConnection | None:
        return self._connection

    def isclosed(self) -> bool:
        return is_fp_closed(self._fp)

    def tell(self) -> int:
        """
        Obtain the number of bytes pulled over the wire so far. May differ from
        the amount of content returned by :meth:``urllib3.response.HTTPResponse.read``
        if bytes are encoded on the wire (e.g, compressed).
        """
        return self._fp_bytes_read

    def _init_length(self, request_method: str | None) -> int | None:
        """
        Set initial length value for Response content if available.
        """
        length: int | None
        content_length: str | None = self.headers.get("content-length")

        if content_length is not None:
            if self.chunked:
                # This Response will fail with an IncompleteRead if it can't be
                # received as chunked. This method falls back to attempt reading
                # the response before raising an exception.
                log.warning(
                    "Received response with both Content-Length and "
                    "Transfer-Encoding set. This is expressly forbidden "
                    "by RFC 7230 sec 3.3.2. Ignoring Content-Length and "
                    "attempting to process response as Transfer-Encoding: "
                    "chunked."
                )
                return None

            try:
                # RFC 7230 section 3.3.2 specifies multiple content lengths can
                # be sent in a single Content-Length header
                # (e.g. Content-Length: 42, 42). This line ensures the values
                # are all valid ints and that as long as the `set` length is 1,
                # all values are the same. Otherwise, the header is invalid.
                if "," in content_length:
                    lengths = {int(val) for val in content_length.split(",")}
                    if len(lengths) > 1:
                        raise InvalidHeader(
                            "Content-Length contained multiple "
                            "unmatching values (%s)" % content_length
                        )
                    length = lengths.pop()
                else:
                    length = int(content_length)
            except ValueError:
                length = None
            else:
                if length < 0:
                    length = None

        else:  # if content_length is None
            length = None

        # Check for responses that shouldn't include a body
        if (
            self.status in (204, 304)
            or 100 <= self.status < 200
            or request_method == "HEAD"
        ):
            length = 0

        return length

    @contextmanager
    def _error_catcher(self) -> typing.Generator[None, None, None]:
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
                    self._connection.close()

            # If we hold the original response but it's closed now, we should
            # return the connection back to the pool.
            if self._original_response and self._original_response.isclosed():
                self.release_conn()

    def _fp_read(self, amt: int | None = None, *, read1: bool = False) -> bytes:
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
        if read1 and isinstance(self._fp, LowLevelResponse):
            if requires_safe_read:
                amt = (
                    CHUNK_AMT_MAX if amt is None or amt < 0 else min(amt, CHUNK_AMT_MAX)
                )
            return self._fp.read1(amt)
        if requires_safe_read:
            buffer = io.BytesIO()
            # Besides `max_chunk_amt` being a maximum chunk size, it
            # affects memory overhead of reading a response by this
            # method in CPython.
            # `c_int_max` equal to 2 GiB - 1 byte is the actual maximum
            # chunk size that does not lead to an overflow error, but
            # 256 MiB is a compromise.
            while amt is None or amt != 0:
                if amt is not None:
                    chunk_amt = min(amt, CHUNK_AMT_MAX)
                    amt -= chunk_amt
                else:
                    chunk_amt = CHUNK_AMT_MAX
                try:
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
            return self._fp.read(amt) if amt is not None else self._fp.read()

    def _raw_read(
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
        fp_upgraded = getattr(self._fp, "_dsa", None) is not None

        with self._error_catcher():
            data = (
                self._fp_read(amt, read1=read1)
                if not fp_closed and not fp_upgraded
                else b""
            )

            # Mocking library often use io.BytesIO
            # which does not auto-close when reading data
            # with amt=None.
            is_foreign_fp_unclosed = (
                amt is None
                and not getattr(self._fp, "closed", False)
                and not fp_upgraded
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

    def read1(
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

        data = self._read(
            amt=amt or -1,
            decode_content=decode_content,
            read1=True,
        )
        self._uncached_read_occurred = True

        return data

    def read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
    ) -> bytes:
        """
        Similar to :meth:`http.client.HTTPResponse.read`, but with two additional
        parameters: ``decode_content`` and ``cache_content``.

        :param amt:
            How much of the content to read. ``None`` or a negative value reads
            the remaining body. For a non-negative value, caching is skipped
            because partial content is not the full response. Use :meth:`read1`
            or :meth:`stream` for incremental reads.

        :param decode_content:
            If True, will attempt to decode the body based on the
            'content-encoding' header.

        :param cache_content:
            If True, will save the returned data such that the same result is
            returned despite of the state of the underlying file object. This
            is useful if you want the ``.data`` property to continue working
            after having ``.read()`` the file object. (Overridden if ``amt`` is
            non-negative.)

        .. note::
            ``AsyncHTTPResponse.read()`` retains incremental reads for negative
            ``amt`` values for backward compatibility.
        """
        # Normalize only public read(); read1() and stream() share _read().
        if amt is not None and amt < 0:
            amt = None
        return self._read(
            amt=amt,
            decode_content=decode_content,
            cache_content=cache_content,
        )

    def _read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
        *,
        read1: bool = False,
    ) -> bytes:
        """We need this private method to restore BC with urllib3 fast-path for streaming/chunks.
        see https://github.com/jawah/urllib3.future/issues/379"""
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
                with self._police_officer.borrow(self):
                    data = self._raw_read(amt, read1=read1)
            else:
                data = self._raw_read(amt, read1=read1)

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
                    and isinstance(self._fp, LowLevelResponse)
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
                        with self._police_officer.borrow(self):
                            data = self._raw_read(amt)
                    else:
                        data = self._raw_read(amt)

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
                hasattr(self._fp, "_eot")
                and (
                    self._fp._eot  # type: ignore[union-attr]
                    or is_fp_closed(self._fp)
                )
                and self._police_officer is not None
            ):
                # an HTTP extension could be live, we don't want to accidentally kill it!
                if (
                    not hasattr(self._fp, "_dsa")
                    or self._fp._dsa is None  # type: ignore[union-attr]
                    or self._fp._dsa.closed is True  # type: ignore[union-attr]
                ):
                    self._police_officer.forget(self)
                    self._police_officer = None

    def stream(
        self, amt: int | None = 2**16, decode_content: bool | None = None
    ) -> typing.Generator[bytes, None, None]:
        """
        A generator wrapper for the read() method. A call will block until
        ``amt`` bytes have been read from the connection or until the
        connection is closed.

        :param amt:
            How much of the content to read. The generator will return up to
            much data per iteration, but may return less. This is particularly
            likely when using compressed data. However, the empty string will
            never be returned. Setting -1 will output chunks as soon as they
            arrive.

        :param decode_content:
            If True, will attempt to decode the body based on the
            'content-encoding' header.
        """
        if amt == 0:
            return
        if self._fp is None:
            return
        while (
            not is_fp_closed(self._fp)
            or len(self._decoded_buffer) > 0
            or (self._decoder and self._decoder.has_unconsumed_tail)
        ):
            data = self.read1(amt=amt, decode_content=decode_content)

            if data:
                yield data

    def _handle_chunk(
        self, amt: int | None, decode_content: bool | None = None
    ) -> bytes:
        """Read one transfer-decoded body segment from the protocol backend."""
        return self.read1(
            amt=-1 if amt is None else amt,
            decode_content=decode_content,
        )

    def read_chunked(
        self, amt: int | None = None, decode_content: bool | None = None
    ) -> typing.Generator[bytes, None, None]:
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

        with self._error_catcher():
            while self._fp is not None and (
                not is_fp_closed(self._fp)
                or len(self._decoded_buffer) > 0
                or (self._decoder and self._decoder.has_unconsumed_tail)
            ):
                data = self._handle_chunk(amt, decode_content)
                if data:
                    yield data

            if decode_content:
                data = self._flush_decoder()
                if data:
                    yield data

    # Overrides from io.IOBase
    def readable(self) -> bool:
        return True

    def __del__(self) -> None:
        if not getattr(self, "closed", True):
            police = getattr(self, "_police_officer", None)
            reclaimed = (
                police._reclaim_reservation(self) if police is not None else None
            )
            try:
                self.close()
            finally:
                if reclaimed is not None and police is not None:
                    police.release()
                    if police._shutdown:
                        police.kill(reclaimed, idle_only=True)

    def close(self) -> None:
        if self.extension is not None and self.extension.closed is False:
            self.extension.close()

        if isinstance(self._fp, LowLevelResponse) and self._police_officer is not None:
            police = self._police_officer
            try:
                with police.borrow(self) as conn:
                    try:
                        self._fp.abort()
                    except (OSError, BaseSSLError):
                        # A failed reset write makes the transport unusable.
                        conn.close()
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
        elif isinstance(self._fp, LowLevelResponse) and self._fp._eot:
            self._fp.close()
            self._connection = None
        else:
            if not self.closed and self._fp:
                self._fp.close()
            if self._connection:
                self._connection.close()  # Defensive: external file-like body.

        if not self.auto_close:
            io.IOBase.close(self)

    @property
    def closed(self) -> bool:
        if not self.auto_close:
            return io.IOBase.closed.__get__(self)  # type: ignore[no-any-return]
        elif self._fp is None:
            return True
        elif hasattr(self._fp, "isclosed"):
            return self._fp.isclosed()
        elif hasattr(self._fp, "closed"):
            return self._fp.closed
        else:
            return True

    def fileno(self) -> int:
        if self._fp is None:
            raise OSError("HTTPResponse has no file to get a fileno from")
        elif hasattr(self._fp, "fileno"):
            return self._fp.fileno()
        else:
            raise OSError(
                "The file-like object this HTTPResponse is wrapped "
                "around has no file descriptor"
            )

    def flush(self) -> None:
        if (
            self._fp is not None
            and hasattr(self._fp, "flush")
            and not getattr(self._fp, "closed", False)
        ):
            return self._fp.flush()  # type: ignore[return-value]

    def supports_chunked_reads(self) -> bool:
        """
        Checks if the underlying file-like object looks like a
        :class:`http.client.HTTPResponse` object. We do this by testing for
        the fp attribute. If it is present we assume it returns raw chunks as
        processed by read_chunked().
        """
        return isinstance(self._fp, LowLevelResponse) or hasattr(self._fp, "fp")

    def _update_chunk_length(self) -> None:
        """Compatibility hook for consumers of urllib3's private chunk parser.

        urllib3-future removes transfer framing in the protocol backend, before
        bytes reach ``HTTPResponse``. There is no chunk length to update here.
        """

    @property
    def url(self) -> str | None:
        """
        Returns the URL that was the source of this response.
        If the request that generated this response redirected, this method
        will return the final redirect location.
        """
        return self._request_url

    @url.setter
    def url(self, url: str) -> None:
        self._request_url = url

    # Compatibility methods for http.client.HTTPResponse
    def getheaders(self) -> HTTPHeaderDict:  # Defensive: kept for BC, dead code
        return self.headers

    def getheader(
        self, name: str, default: str | None = None
    ) -> str | None:  # Defensive: kept for BC, dead code
        return self.headers.get(name, default)

    def __iter__(self) -> typing.Iterator[bytes]:
        buffer: list[bytes] = []
        for chunk in self.stream(-1, decode_content=True):
            if b"\n" in chunk:
                chunks = chunk.split(b"\n")
                yield b"".join(buffer) + chunks[0] + b"\n"
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

    def shutdown(self) -> None:
        """urllib3 implemented this method in version 2.3 to palliate for a
        thread safety issue[...] using another thread safety issue[...]
        fortunately, we don't need that hack with urllib3-future thanks to
        our extensive safety with TrafficPolice. You may safely remove that
        call."""
        pass


# Kept for BC-purposes.
BaseHTTPResponse = HTTPResponse
