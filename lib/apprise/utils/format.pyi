from _typeshed import Incomplete
from apprise.common import NotifyFormat as NotifyFormat

PUNCTUATION_CHARS: str
PUNCT_SPLIT_PATTERN: Incomplete
HTML_ENTITY_LOOKBACK: int
HTML_ENTITY_LOOKAHEAD: int

def html_adjust(text: str, window_start: int, split_at: int) -> int:
    """
    Adjust the split point to avoid splitting inside short HTML entities
    such as '&nbsp;'.

    If the split falls inside '&...;' within a small window around the
    boundary, move the split back to '&' so the entire entity is kept
    in the next chunk.
    """
def markdown_adjust(text: str, window_start: int, split_at: int) -> int:
    """Move a split left when it cuts a Markdown or Chat link.

    Protected forms are ``[label](url)``, ``![alt](url)``, and
    ``<url|label>``. The scan looks backward for an opener and at most one
    window forward for its closer, keeping adjustment work linear.

    Returns the original split or the construct's opening position.
    """
def smart_split(text: str, limit: int, body_format: NotifyFormat) -> list[str]:
    """Split text within ``limit``, preferring natural boundaries.

    Priority             Boundary
    -------------------  ---------------------------------------
    1                    Newline
    2                    Space or tab
    3                    Punctuation followed by whitespace
    4                    Hard character limit

    HTML avoids splitting entities. Markdown additionally protects common
    link constructs when they can fit within a chunk.
    """
