from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..conversion import build_backtick_run_index as build_backtick_run_index, commonmark_emphasis_run as commonmark_emphasis_run, commonmark_force_close_spans as commonmark_force_close_spans, commonmark_scan_angle_dest as commonmark_scan_angle_dest, find_unescaped_run as find_unescaped_run
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from collections.abc import Generator

class NotifyEvolution(NotifyBase):
    """A wrapper for Evolution API (WhatsApp) Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: int
    notify_format: Incomplete
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    instance: Incomplete
    phone: Incomplete
    invalid_targets: Incomplete
    def __init__(self, apikey, instance, targets=None, **kwargs) -> None:
        """Initialize Evolution API Object."""
    @classmethod
    def _commonmark_to_whatsapp(cls, body):
        """Translate CommonMark to WhatsApp formatting.

        CommonMark          WhatsApp
        ------------------  ---------------------------
        **bold**            *bold*
        *italic*            _italic_
        `code`              ```code``` (triple backticks)
        [label](<url>)      label (url)
        \\*                 *

        WhatsApp auto-links bare URLs but has no custom-label link syntax.
        Backslash escapes are removed because WhatsApp does not use them.
        """
    def _build_send_calls(self, body=None, title=None, body_format=None, **kwargs) -> Generator[Incomplete, Incomplete]:
        """Convert HTML-derived CommonMark before splitting for WhatsApp.

        Direct Markdown and other source formats pass through unchanged.
        """
    def send(self, body, title: str = '', notify_type=..., body_format=None, **kwargs):
        """Perform Evolution API Notification."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
