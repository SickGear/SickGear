from .exceptions import *
from . import http as http, mixin as mixin
from .datetimes import _parse_date as _parse_date, registerDateHandler as registerDateHandler
from .encodings import convert_to_utf8 as convert_to_utf8
from .html import _BaseHTMLProcessor as _BaseHTMLProcessor
from .mixin import _FeedParserMixin as _FeedParserMixin
from .parsers.loose import _LooseFeedParser as _LooseFeedParser
from .parsers.strict import _StrictFeedParser as _StrictFeedParser
from .sanitizer import replace_doctype as replace_doctype
from .urls import convert_to_idn as convert_to_idn, make_safe_absolute_uri as make_safe_absolute_uri
from .util import FeedParserDict as FeedParserDict
from typing import Any, Optional

class urllib:
    class parse:
        urlparse: Any = ...

bytes_: Any
unicode_: Any
unichr = chr
basestring = str
PREFERRED_XML_PARSERS: Any
_XML_AVAILABLE: bool
SUPPORTED_VERSIONS: Any

def _open_resource(url_file_stream_or_string: Any, etag: Any, modified: Any, agent: Any, referrer: Any, handlers: Any, request_headers: Any, result: Any): ...

LooseFeedParser: Any
StrictFeedParser: Any

def parse(url_file_stream_or_string: Any, etag: Optional[Any] = ..., modified: Optional[Any] = ..., agent: Optional[Any] = ..., referrer: Optional[Any] = ..., handlers: Optional[Any] = ..., request_headers: Optional[Any] = ..., response_headers: Optional[Any] = ..., resolve_relative_uris: Optional[Any] = ..., sanitize_html: Optional[Any] = ...): ...
