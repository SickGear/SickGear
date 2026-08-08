from .logger import logger as logger
from _typeshed import Incomplete

DELIM: str
EMOJI_MAP: Incomplete
EMOJI_COMPILED_MAP: Incomplete
_EMOJI_PATTERN_LIST: Incomplete

def apply_emojis(content):
    """Takes the content and swaps any matched emoji's found with their utf-8
    encoded mapping."""
