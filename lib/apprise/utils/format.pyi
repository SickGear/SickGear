from _typeshed import Incomplete
from apprise.common import NotifyFormat as NotifyFormat

PUNCTUATION_CHARS: str
PUNCT_SPLIT_PATTERN: Incomplete
HTML_ENTITY_LOOKBACK: int
HTML_ENTITY_LOOKAHEAD: int
MARKDOWN_CONSTRUCT_LOOKBACK: int

def html_adjust(text: str, window_start: int, split_at: int) -> int:
    """
    Adjust the split point to avoid splitting inside short HTML entities
    such as '&nbsp;'.

    If the split falls inside '&...;' within a small window around the
    boundary, move the split back to '&' so the entire entity is kept
    in the next chunk.
    """
def markdown_adjust(text: str, window_start: int, split_at: int) -> int:
    """
    Adjust the split point to avoid splitting inside simple Markdown
    link / image constructs like [Text](URL) or ![Alt](URL).

    This is a best-effort heuristic and does not attempt full Markdown
    parsing. If the boundary falls between '['/'!' and the closing ')'
    of a nearby link/image, move the split back to that start.
    """
def smart_split(text: str, limit: int, body_format: NotifyFormat) -> list[str]:
    """
    Split `text` into chunks of at most `limit` characters.

    Soft split priority:
      1. Last newline before `limit` (\\n or \\r)
      2. Last space or tab before `limit`
      3. Last punctuation+whitespace (.,!?:; followed by space/tab/newline)
      4. Hard split at `limit`

    `body_format` controls additional safety rules:
      - NotifyFormat.TEXT: generic splitting only
      - NotifyFormat.HTML: avoid splitting inside '&...;' entities
      - NotifyFormat.MARKDOWN: same as HTML, plus a best-effort check to
        avoid splitting inside [Text](URL) / ![Alt](URL) patterns.
    """
