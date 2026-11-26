from .common import NotifyFormat as NotifyFormat
from .url import URLBase as URLBase
from _typeshed import Incomplete
from bisect import bisect_left as bisect_left
from collections.abc import Generator
from html.parser import HTMLParser

LIST_DEPTH_MAX: int
BLOCKQUOTE_DEPTH_MAX: int
MAX_FRAME_DEPTH: int

class _Marker(str):
    """Identify converter-generated structure."""
class _ListMarker(_Marker):
    """Identify a generated list marker."""
class _QuoteMarker(_Marker):
    """Identify a generated quote prefix."""
class _ListIndent(_Marker):
    """Identify list continuation indentation."""

class _ParaBreak:
    """Represent a paragraph boundary and its prefix."""
    __slots__: Incomplete
    prefix: Incomplete
    in_quote: Incomplete
    def __init__(self, prefix: str = '', in_quote: bool = False) -> None:
        """Initialize a paragraph boundary."""

def convert_between(from_format, to_format, content):
    """Converts between different suported formats. If no conversion exists, or
    the selected one fails, the original text will be returned.

    This function returns the content translated (if required)
    """
def text_to_html(content):
    """Converts specified content from plain text to HTML."""
def html_to_text(content):
    """Converts a content from HTML to plain text."""

class HTMLConverter(HTMLParser):
    """An HTML to plain text converter tuned for email messages."""
    BLOCK_TAGS: Incomplete
    IGNORE_TAGS: Incomplete
    WS_TRIM: Incomplete
    BLOCK_END: Incomplete
    _do_store: bool
    _result: Incomplete
    converted: str
    def __init__(self, **kwargs) -> None:
        """Initialize the HTML converter."""
    def close(self) -> None:
        """Finalize the converted content."""
    def _finalize(self, result) -> Generator[Incomplete]:
        '''Combines and strips consecutive strings, then converts consecutive
        block ends into singleton newlines.

        [ {be} " Hello " {be} {be} " World!" ] -> "
Hello
World!"
        '''
    def handle_data(self, data, *args, **kwargs) -> None:
        """Store our data if it is not on the ignore list."""
    def handle_starttag(self, tag, attrs) -> None:
        """Process our starting HTML Tag."""
    def handle_endtag(self, tag) -> None:
        """Edge case handling of open/close tags."""
