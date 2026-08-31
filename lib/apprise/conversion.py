# BSD 2-Clause License
#
# Apprise - Push Notification Library.
# Copyright (c) 2026, Chris Caron <lead2gold@gmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from bisect import bisect_left
import contextlib
from html.parser import HTMLParser
import re

#from markdown import markdown

from .common import NotifyFormat
from .url import URLBase

# Cap list indentation so deeply nested input stays linear.
LIST_DEPTH_MAX = 4

# Apply the same depth cap to blockquote prefixes.
BLOCKQUOTE_DEPTH_MAX = 4

# Bound the context-stack depth so adversarially nested HTML cannot
# exhaust memory.  Frames beyond this limit are silently dropped.
MAX_FRAME_DEPTH = 200


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

    __slots__ = ("in_quote", "prefix")

    def __init__(self, prefix="", in_quote=False):
        """Initialize a paragraph boundary."""

        # Store the continuation prefix
        self.prefix = prefix

        # Track whether the boundary remains inside a quote
        self.in_quote = in_quote


def convert_between(from_format, to_format, content):
    """Converts between different suported formats. If no conversion exists, or
    the selected one fails, the original text will be returned.

    This function returns the content translated (if required)
    """

    # Map each supported format pair to its converter
    converters = {
#        (NotifyFormat.MARKDOWN, NotifyFormat.HTML): markdown_to_html,
        (NotifyFormat.TEXT, NotifyFormat.HTML): text_to_html,
        (NotifyFormat.HTML, NotifyFormat.TEXT): html_to_text,
        # For now; use same converter for Markdown support
#        (NotifyFormat.HTML, NotifyFormat.MARKDOWN): html_to_text,
    }

    # Fetch the converter registered for this format pair.
    convert = converters.get((from_format, to_format))

    # Preserve the original content when no conversion is available
    return convert(content) if convert else content


#def markdown_to_html(content):
#    """Converts specified content from markdown to HTML."""
#    return markdown(
#        content,
#        extensions=["markdown.extensions.nl2br", "markdown.extensions.tables"],
#    )


def text_to_html(content):
    """Converts specified content from plain text to HTML."""

    # First eliminate any carriage returns
    return URLBase.escape_html(content, convert_new_lines=True)


def html_to_text(content):
    """Converts a content from HTML to plain text."""

    # Initialize the plain-text parser.
    parser = HTMLConverter()

    # Feed and finalize the HTML document
    parser.feed(content)
    parser.close()

    # Return the finalized parser output.
    return parser.converted


class HTMLConverter(HTMLParser):
    """An HTML to plain text converter tuned for email messages."""

    # The following tags must start on a new line
    BLOCK_TAGS = (
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "div",
        "td",
        "th",
        "code",
        "pre",
        "label",
        "li",
    )

    # the folowing tags ignore any internal text
    IGNORE_TAGS = (
        "form",
        "input",
        "textarea",
        "select",
        "ul",
        "ol",
        "style",
        "link",
        "meta",
        "title",
        "html",
        "head",
        "script",
    )

    # Condense Whitespace
    WS_TRIM = re.compile(r"[\s]+", re.DOTALL | re.MULTILINE)

    # Sentinel value for block tag boundaries, which may be consolidated into a
    # single line break.
    BLOCK_END = {}

    def __init__(self, **kwargs):
        """Initialize the HTML converter."""

        # Initialize the standard-library HTML parser.
        super().__init__(**kwargs)

        # Should we store the text content or not?
        self._do_store = True

        # Initialize internal result list
        self._result = []

        # Initialize public result field (not populated until close() is
        # called)
        self.converted = ""

    def close(self):
        """Finalize the converted content."""

        # Combine buffered fragments into one string.
        string = "".join(self._finalize(self._result))

        # Publish the normalized result.
        self.converted = string.strip()

    def _finalize(self, result):
        """Combines and strips consecutive strings, then converts consecutive
        block ends into singleton newlines.

        [ {be} " Hello " {be} {be} " World!" ] -> "\nHello\nWorld!"
        """

        # None means the last visited item was a block end.
        accum = None

        for item in result:
            if item == self.BLOCK_END:
                # Multiple consecutive block ends; do nothing.
                if accum is None:
                    continue

                # First block end; yield the current string, plus a newline.
                yield accum.strip() + "\n"
                accum = None

            # Multiple consecutive strings; combine them.
            elif accum is not None:
                accum += item

            # First consecutive string; store it.
            else:
                accum = item

        # Yield the last string if we have not already done so.
        if accum is not None:
            yield accum.strip()

    def handle_data(self, data, *args, **kwargs):
        """Store our data if it is not on the ignore list."""

        # Ignore data while an ignored container is active.
        if self._do_store:
            # Collapse whitespace before buffering visible text.
            content = self.WS_TRIM.sub(" ", data)

            # Preserve the normalized fragment for final assembly.
            self._result.append(content)

    def handle_starttag(self, tag, attrs):
        """Process our starting HTML Tag."""

        # Toggle storage according to the newly opened container.
        self._do_store = tag not in self.IGNORE_TAGS

        # Start block elements on a fresh output line.
        if tag in self.BLOCK_TAGS:
            self._result.append(self.BLOCK_END)

        # Prefix each list item with a plain-text bullet.
        if tag == "li":
            self._result.append("- ")

        # Preserve explicit HTML line breaks.
        elif tag == "br":
            self._result.append("\n")

        # Render horizontal rules on their own line.
        elif tag == "hr":
            # Remove spacing that would precede the rule.
            if self._result and isinstance(self._result[-1], str):
                self._result[-1] = self._result[-1].rstrip(" ")

            self._result.append("\n---\n")

        # Mark the start of quoted plain text.
        elif tag == "blockquote":
            self._result.append(" >")

    def handle_endtag(self, tag):
        """Edge case handling of open/close tags."""

        # Resume storage after leaving an ignored container.
        self._do_store = True

        # Close block elements with a line boundary.
        if tag in self.BLOCK_TAGS:
            self._result.append(self.BLOCK_END)
