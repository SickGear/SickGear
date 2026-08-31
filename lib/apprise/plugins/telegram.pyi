from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..conversion import build_backtick_run_index as build_backtick_run_index, commonmark_prepend_title as commonmark_prepend_title, commonmark_scan_angle_dest as commonmark_scan_angle_dest, find_unescaped_run as find_unescaped_run
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from collections.abc import Generator

TELEGRAM_IMAGE_XY: Incomplete
IS_CHAT_ID_RE: Incomplete

class TelegramMarkdownVersion:
    """Telegram Markdown Version."""
    ONE: str
    TWO: str

TELEGRAM_MARKDOWN_VERSION_MAP: Incomplete
TELEGRAM_MARKDOWN_VERSIONS: Incomplete

class TelegramContentPlacement:
    """The Telegram Content Placement."""
    BEFORE: str
    AFTER: str

TELEGRAM_CONTENT_PLACEMENT: Incomplete

class NotifyTelegram(NotifyBase):
    """A wrapper for Telegram Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_format: Incomplete
    notify_url: str
    attachment_support: bool
    image_size: Incomplete
    body_maxlen: int
    telegram_caption_maxlen: int
    title_maxlen: int
    request_rate_per_sec: float
    max_telegram_template_size: int
    storage_mode: Incomplete
    templates: Incomplete
    mime_lookup: Incomplete
    __telegram_escape_html_entries: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    bot_token: Incomplete
    markdown_ver: Incomplete
    silent: Incomplete
    preview: Incomplete
    content: Incomplete
    topic: Incomplete
    detect_owner: Incomplete
    targets: Incomplete
    include_image: Incomplete
    template: Incomplete
    tokens: Incomplete
    def __init__(self, bot_token, targets, detect_owner: bool = True, include_image: bool = False, silent=None, preview=None, topic=None, content=None, mdv=None, template=None, tokens=None, **kwargs) -> None:
        """Initialize Telegram Object."""
    def send_media(self, target, notify_type, payload=None, attach=None):
        """Sends a sticker based on the specified notify type."""
    def detect_bot_owner(self):
        """Takes a bot and attempts to detect it's chat id from that."""
    _TELEGRAM_STRICT_CHARS: str
    _TELEGRAM_V1_ESCAPABLE: str
    _TELEGRAM_RESERVED_FULL: str
    @classmethod
    def _strict_escape(cls, text):
        """Escape an unescaped MarkdownV2 fragment without double-escaping."""
    @classmethod
    def _commonmark_to_telegram(cls, body, strict: bool = False):
        """Translate CommonMark to Telegram Markdown v1 or v2.

        CommonMark     Markdown v1     MarkdownV2
        -------------  --------------  --------------------
        **bold**       *bold*          *bold*
        *italic*       _italic_        _italic_
        `code`         `code`          `code`
        [l](<u>)       [l](u)          [l](u)
        \\*            known escapes   all reserved escapes

        Both versions strip angle brackets from link destinations. Strict
        mode additionally escapes every MarkdownV2-reserved character.
        """
    @classmethod
    def _repair_split_chunk(cls, text, strict, pending):
        """Repair one Telegram Markdown chunk and return its pending state.

        Each returned chunk is independently valid. ``pending`` carries only
        the state needed to interpret delimiters appearing in later chunks:

        Key             Meaning
        --------------  ----------------------------------------------
        ``in_code``     Width of a code fence continued from this chunk
        ``in_link_dest`` Link destination continues into the next chunk
        ``*`` / ``_``   Emphasis closes to discard in a later chunk

        Returns ``(repaired_text, next_pending)``.
        """
    def _build_send_calls(self, body=None, title=None, body_format=None, **kwargs) -> Generator[Incomplete, Incomplete]:
        """Convert HTML-derived CommonMark and repair each split chunk.

        Pending Telegram entity state is carried between generated calls.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, body_format=None, **kwargs):
        """Perform Telegram Notification."""
    def _send_attachments(self, target, notify_type, attach, payload=None):
        """Sends our attachments."""
    def _gen_rich_payload(self, body, title, notify_type):
        """Generates and validates our Rich Message 'blocks' content from
        our configured template.

        Returns the parsed InputRichMessage dictionary, or False if the
        template could not be loaded, read, parsed, or validated.
        """
    def _send_rich_message(self, body, title, notify_type, attach=None):
        """Sends a Telegram Rich Message (built from our configured
        template) to every target, followed by any attachments exactly as
        they would be sent for a normal notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url, **kwargs):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
