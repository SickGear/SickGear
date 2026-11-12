from __future__ import annotations

import socket
import typing
from enum import IntEnum


class HTTPStatus(IntEnum):
    """HTTP status codes and reason phrases

    Status codes from the following RFCs are all observed:

        * RFC 7231: Hypertext Transfer Protocol (HTTP/1.1), obsoletes 2616
        * RFC 6585: Additional HTTP Status Codes
        * RFC 3229: Delta encoding in HTTP
        * RFC 4918: HTTP Extensions for WebDAV, obsoletes 2518
        * RFC 5842: Binding Extensions to WebDAV
        * RFC 7238: Permanent Redirect
        * RFC 2295: Transparent Content Negotiation in HTTP
        * RFC 2774: An HTTP Extension Framework
        * RFC 7725: An HTTP Status Code to Report Legal Obstacles
        * RFC 7540: Hypertext Transfer Protocol Version 2 (HTTP/2)
        * RFC 2324: Hyper Text Coffee Pot Control Protocol (HTCPCP/1.0)
        * RFC 8297: An HTTP Status Code for Indicating Hints
        * RFC 8470: Using Early Data in HTTP
    """

    phrase: str
    description: str
    standard: bool

    def __new__(
        cls, value: int, phrase: str, description: str = "", is_standard: bool = True
    ) -> HTTPStatus:
        obj = int.__new__(cls, value)
        obj._value_ = value

        obj.phrase = phrase
        obj.description = description
        obj.standard = is_standard
        return obj

    # informational
    CONTINUE = 100, "Continue", "Request received, please continue"
    SWITCHING_PROTOCOLS = (
        101,
        "Switching Protocols",
        "Switching to new protocol; obey Upgrade header",
    )
    PROCESSING = 102, "Processing"
    EARLY_HINTS = 103, "Early Hints"

    # success
    OK = 200, "OK", "Request fulfilled, document follows"
    CREATED = 201, "Created", "Document created, URL follows"
    ACCEPTED = (202, "Accepted", "Request accepted, processing continues off-line")
    NON_AUTHORITATIVE_INFORMATION = (
        203,
        "Non-Authoritative Information",
        "Request fulfilled from cache",
    )
    NO_CONTENT = 204, "No Content", "Request fulfilled, nothing follows"
    RESET_CONTENT = 205, "Reset Content", "Clear input form for further input"
    PARTIAL_CONTENT = 206, "Partial Content", "Partial content follows"
    MULTI_STATUS = 207, "Multi-Status"
    ALREADY_REPORTED = 208, "Already Reported"
    IM_USED = 226, "IM Used"

    # redirection
    MULTIPLE_CHOICES = (
        300,
        "Multiple Choices",
        "Object has several resources -- see URI list",
    )
    MOVED_PERMANENTLY = (
        301,
        "Moved Permanently",
        "Object moved permanently -- see URI list",
    )
    FOUND = 302, "Found", "Object moved temporarily -- see URI list"
    SEE_OTHER = 303, "See Other", "Object moved -- see Method and URL list"
    NOT_MODIFIED = (304, "Not Modified", "Document has not changed since given time")
    USE_PROXY = (
        305,
        "Use Proxy",
        "You must use proxy specified in Location to access this resource",
    )
    TEMPORARY_REDIRECT = (
        307,
        "Temporary Redirect",
        "Object moved temporarily -- see URI list",
    )
    PERMANENT_REDIRECT = (
        308,
        "Permanent Redirect",
        "Object moved permanently -- see URI list",
    )

    # client error
    BAD_REQUEST = (400, "Bad Request", "Bad request syntax or unsupported method")
    UNAUTHORIZED = (401, "Unauthorized", "No permission -- see authorization schemes")
    PAYMENT_REQUIRED = (402, "Payment Required", "No payment -- see charging schemes")
    FORBIDDEN = (403, "Forbidden", "Request forbidden -- authorization will not help")
    NOT_FOUND = (404, "Not Found", "Nothing matches the given URI")
    METHOD_NOT_ALLOWED = (
        405,
        "Method Not Allowed",
        "Specified method is invalid for this resource",
    )
    NOT_ACCEPTABLE = (406, "Not Acceptable", "URI not available in preferred format")
    PROXY_AUTHENTICATION_REQUIRED = (
        407,
        "Proxy Authentication Required",
        "You must authenticate with this proxy before proceeding",
    )
    REQUEST_TIMEOUT = (408, "Request Timeout", "Request timed out; try again later")
    CONFLICT = 409, "Conflict", "Request conflict"
    GONE = (410, "Gone", "URI no longer exists and has been permanently removed")
    LENGTH_REQUIRED = (411, "Length Required", "Client must specify Content-Length")
    PRECONDITION_FAILED = (
        412,
        "Precondition Failed",
        "Precondition in headers is false",
    )
    REQUEST_ENTITY_TOO_LARGE = (413, "Request Entity Too Large", "Entity is too large")
    REQUEST_URI_TOO_LONG = (414, "Request-URI Too Long", "URI is too long")
    UNSUPPORTED_MEDIA_TYPE = (
        415,
        "Unsupported Media Type",
        "Entity body in unsupported format",
    )
    REQUESTED_RANGE_NOT_SATISFIABLE = (
        416,
        "Requested Range Not Satisfiable",
        "Cannot satisfy request range",
    )
    EXPECTATION_FAILED = (
        417,
        "Expectation Failed",
        "Expect condition could not be satisfied",
    )
    IM_A_TEAPOT = (
        418,
        "I'm a Teapot",
        "Server refuses to brew coffee because it is a teapot.",
    )
    MISDIRECTED_REQUEST = (
        421,
        "Misdirected Request",
        "Server is not able to produce a response",
    )
    UNPROCESSABLE_ENTITY = 422, "Unprocessable Entity"
    LOCKED = 423, "Locked"
    FAILED_DEPENDENCY = 424, "Failed Dependency"
    TOO_EARLY = 425, "Too Early"
    UPGRADE_REQUIRED = 426, "Upgrade Required"
    PRECONDITION_REQUIRED = (
        428,
        "Precondition Required",
        "The origin server requires the request to be conditional",
    )
    TOO_MANY_REQUESTS = (
        429,
        "Too Many Requests",
        "The user has sent too many requests in "
        'a given amount of time ("rate limiting")',
    )
    REQUEST_HEADER_FIELDS_TOO_LARGE = (
        431,
        "Request Header Fields Too Large",
        "The server is unwilling to process the request because its header "
        "fields are too large",
    )
    UNAVAILABLE_FOR_LEGAL_REASONS = (
        451,
        "Unavailable For Legal Reasons",
        "The server is denying access to the "
        "resource as a consequence of a legal demand",
    )

    # server errors
    INTERNAL_SERVER_ERROR = (
        500,
        "Internal Server Error",
        "Server got itself in trouble",
    )
    NOT_IMPLEMENTED = (501, "Not Implemented", "Server does not support this operation")
    BAD_GATEWAY = (502, "Bad Gateway", "Invalid responses from another server/proxy")
    SERVICE_UNAVAILABLE = (
        503,
        "Service Unavailable",
        "The server cannot process the request due to a high load",
    )
    GATEWAY_TIMEOUT = (
        504,
        "Gateway Timeout",
        "The gateway server did not receive a timely response",
    )
    HTTP_VERSION_NOT_SUPPORTED = (
        505,
        "HTTP Version Not Supported",
        "Cannot fulfill request",
    )
    VARIANT_ALSO_NEGOTIATES = 506, "Variant Also Negotiates"
    INSUFFICIENT_STORAGE = 507, "Insufficient Storage"
    LOOP_DETECTED = 508, "Loop Detected"
    NOT_EXTENDED = 510, "Not Extended"
    NETWORK_AUTHENTICATION_REQUIRED = (
        511,
        "Network Authentication Required",
        "The client needs to authenticate to gain network access",
    )


# another hack to maintain backwards compatibility
# Mapping status codes to official W3C names
responses: typing.Mapping[int, str] = {
    v: v.phrase for v in HTTPStatus.__members__.values()
}

# Default value for `blocksize` - a new parameter introduced to
# http.client.HTTPConnection & http.client.HTTPSConnection in Python 3.7
# The maximum TCP packet size is 65535 octets. But OSes can have a recv buffer greater than 65k, so
# passing the highest value does improve responsiveness.
# udp usually is set to 212992
# and tcp usually is set to 131072 (16384 * 8) or (65535 * 2)
try:
    # dynamically retrieve the kernel rcvbuf size.
    stream = socket.socket(type=socket.SOCK_STREAM)
    dgram = socket.socket(type=socket.SOCK_DGRAM)

    DEFAULT_BLOCKSIZE: int = stream.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    UDP_DEFAULT_BLOCKSIZE: int = dgram.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)

    stream.close()
    dgram.close()
except OSError:  # Defensive: should be unreachable, overly protective.
    DEFAULT_BLOCKSIZE = 131072
    UDP_DEFAULT_BLOCKSIZE = 212992

TCP_DEFAULT_BLOCKSIZE: int = DEFAULT_BLOCKSIZE

UDP_LINUX_GRO: int = 104
UDP_LINUX_SEGMENT: int = 103
UDP_MAX_RECV_BURST: int = 64

# Mozilla TLS recommendations for ciphers
# General-purpose servers with a variety of clients, recommended for almost all systems.
MOZ_INTERMEDIATE_CIPHERS: str = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305"

DEFAULT_BACKGROUND_WATCH_WINDOW: float = 5.0
MINIMAL_BACKGROUND_WATCH_WINDOW: float = 0.05

DEFAULT_KEEPALIVE_DELAY: float = 600.0
DEFAULT_KEEPALIVE_IDLE_WINDOW: float = 60.0
MINIMAL_KEEPALIVE_IDLE_WINDOW: float = 1.0

DEFAULT_TCP_KEEPALIVE_ATTEMPT_COUNT: int = 2

C_INT_MAX = 2**31 - 1
CHUNK_AMT_MAX = 2**28

# Bound the amount of decompressed bytes a single ``read(amt=-1)`` (or one
# iteration of ``stream(amt=-1)``) is allowed to drain from the decoder's
# internal buffer at once. The cap is expressed as a multiple of the most
# recent raw read size so that small frames still produce usable chunks while
# pathological "decompression-bomb" payloads cannot expand a single recv into
# arbitrarily large memory allocations. See GHSA-mf9v-mfxr-j63j and
# https://github.com/jawah/urllib3.future/issues/364
DECODE_GROWTH_FACTOR: int = 128
# Floor used as the reference raw size before any raw read has occurred (or
# when the last raw read returned an unusually small amount of body bytes).
# This is a safety net only: in practice ``_last_raw_read_size`` is already
# populated by the time the drain path runs (the decoder only has an
# unconsumed tail because a previous raw read fed it). 1 KiB combined with
# ``DECODE_GROWTH_FACTOR`` still yields a sensible minimum decoded chunk.
DECODE_MIN_RAW_REFERENCE: int = 1024

HTTP1_ONLY_HEADERS = frozenset(
    {
        b"transfer-encoding",
        b"connection",
        b"upgrade",
        b"keep-alive",
    }
)
