from __future__ import annotations

import collections
import io
import re
import typing

if typing.TYPE_CHECKING:
    import http.client as httplib


def is_fp_closed(obj: object) -> bool:
    """
    Checks whether a given file-like object is closed.

    :param obj:
        The file-like object to check.
    """

    try:
        # Check `isclosed()` first, in case Python3 doesn't set `closed`.
        # GH Issue #928
        return obj.isclosed()  # type: ignore[no-any-return, attr-defined]
    except AttributeError:
        pass

    try:
        # Check via the official file-like-object way.
        return obj.closed  # type: ignore[no-any-return, attr-defined]
    except AttributeError:
        pass

    try:
        # Check if the object is a container for another file-like object that
        # gets released on exhaustion (e.g. HTTPResponse).
        return obj.fp is None  # type: ignore[attr-defined]
    except AttributeError:
        pass

    raise ValueError("Unable to determine whether fp is closed.")


def parse_alt_svc(value: str) -> typing.Iterable[tuple[str, str]]:
    """Given an Alt-Svc value, extract from it the protocol-id and the alt-authority.
    https://httpwg.org/specs/rfc7838.html#alt-svc"""
    pattern = re.compile(
        r"(h[0-9]{1,3}(?:[\-0-9]{0,5}))=(?:[\"\']?)([a-z0-9\-_:.]+)(?:[\"\']?)",
        re.IGNORECASE,
    )

    yield from re.findall(pattern, value)


class BytesQueueBuffer:
    """Memory-efficient bytes buffer

    To return decoded data in read() and still follow the BufferedIOBase API, we need a
    buffer to always return the correct amount of bytes.

    This buffer should be filled using calls to put()

    Our maximum memory usage is determined by the sum of the size of:

     * self.buffer, which contains the full data
     * the largest chunk that we will copy in get()
    """

    def __init__(self) -> None:
        self.buffer: typing.Deque[bytes | memoryview[bytes]] = collections.deque()
        self._size: int = 0

    def __len__(self) -> int:
        return self._size

    def put(self, data: bytes | memoryview[bytes]) -> None:
        self.buffer.append(data)
        self._size += len(data)

    def put_many(self, chunks: typing.Iterable[bytes | memoryview[bytes]]) -> None:
        """Append several chunks at once, skipping empty ones."""
        for data in chunks:
            if data:
                self.buffer.append(data)
                self._size += len(data)

    def get(self, n: int) -> bytes:
        if n == 0:
            return b""
        elif not self.buffer:
            raise RuntimeError("buffer is empty")
        elif n < 0:
            raise ValueError("n should be > 0")

        if len(self.buffer[0]) == n and isinstance(self.buffer[0], bytes):
            self._size -= n
            return self.buffer.popleft()

        fetched = 0
        ret = io.BytesIO()
        while fetched < n:
            remaining = n - fetched
            chunk = self.buffer.popleft()
            chunk_length = len(chunk)
            if remaining < chunk_length:
                chunk = memoryview(chunk)
                left_chunk, right_chunk = chunk[:remaining], chunk[remaining:]
                ret.write(left_chunk)
                self.buffer.appendleft(right_chunk)
                self._size -= remaining
                break
            else:
                ret.write(chunk)
                self._size -= chunk_length
            fetched += chunk_length

            if not self.buffer:
                break

        return ret.getvalue()


def assert_header_parsing(
    headers: httplib.HTTPMessage,
) -> None:  # Defensive: dead code from http.client era
    """
    Asserts whether all headers have been successfully parsed.
    Extracts encountered errors from the result of parsing headers.

    Only works on Python 3.

    :param http.client.HTTPMessage headers: Headers to verify.

    :raises urllib3.exceptions.HeaderParsingError:
        If parsing errors are found.
    """
    from email.errors import (
        MultipartInvariantViolationDefect,
        StartBoundaryNotFoundDefect,
    )
    from ..exceptions import HeaderParsingError

    import http.client as httplib

    # This will fail silently if we pass in the wrong kind of parameter.
    # To make debugging easier add an explicit check.
    if not isinstance(headers, httplib.HTTPMessage):
        raise TypeError(f"expected httplib.Message, got {type(headers)}.")

    unparsed_data = None

    # get_payload is actually email.message.Message.get_payload;
    # we're only interested in the result if it's not a multipart message
    if not headers.is_multipart():
        payload = headers.get_payload()

        if isinstance(payload, (bytes, str)):
            unparsed_data = payload

    # httplib is assuming a response body is available
    # when parsing headers even when httplib only sends
    # header data to parse_headers() This results in
    # defects on multipart responses in particular.
    # See: https://github.com/urllib3/urllib3/issues/800

    # So we ignore the following defects:
    # - StartBoundaryNotFoundDefect:
    #     The claimed start boundary was never found.
    # - MultipartInvariantViolationDefect:
    #     A message claimed to be a multipart but no subparts were found.
    defects = [
        defect
        for defect in headers.defects
        if not isinstance(
            defect, (StartBoundaryNotFoundDefect, MultipartInvariantViolationDefect)
        )
    ]

    if defects or unparsed_data:
        raise HeaderParsingError(defects=defects, unparsed_data=unparsed_data)


def is_response_to_head(
    response: httplib.HTTPResponse,
) -> bool:  # Defensive: dead code from http.client era
    """
    Checks whether the request of a response has been a HEAD-request.

    :param http.client.HTTPResponse response:
        Response to check if the originating request
        used 'HEAD' as a method.
    """
    # FIXME: Can we do this somehow without accessing private httplib _method?
    method_str = response._method  # type: str  # type: ignore[attr-defined]
    return method_str.upper() == "HEAD"
