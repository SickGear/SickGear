from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..conversion import build_backtick_run_index as build_backtick_run_index, commonmark_emphasis_run as commonmark_emphasis_run, commonmark_escape_link_url as commonmark_escape_link_url, commonmark_force_close_spans as commonmark_force_close_spans, commonmark_prepend_title as commonmark_prepend_title, commonmark_scan_angle_dest as commonmark_scan_angle_dest, find_unescaped_run as find_unescaped_run
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from collections.abc import Generator

class NotifyGoogleChat(NotifyBase):
    """A wrapper to Google Chat Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    notify_format: Incomplete
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    workspace: Incomplete
    webhook_key: Incomplete
    webhook_token: Incomplete
    thread_key: Incomplete
    def __init__(self, workspace, webhook_key, webhook_token, thread_key=None, **kwargs) -> None:
        """Initialize Google Chat Object."""
    @classmethod
    def _commonmark_to_google_chat(cls, body):
        """Translate CommonMark to Google Chat formatting.

        CommonMark          Google Chat
        ------------------  -----------------
        **bold**            *bold*
        *italic*            _italic_
        `code`              `code`
        [label](<url>)      <url|label>
        &, <, >             HTML entities

        Chat uses HTML-like anchors, so text and code escape ``&``, ``<``,
        and ``>`` before delivery.
        """
    def _build_send_calls(self, body=None, title=None, body_format=None, **kwargs) -> Generator[Incomplete, Incomplete]:
        """Convert HTML-derived CommonMark before splitting for Chat.

        Direct Markdown and other source formats pass through unchanged.
        """
    def send(self, body, title: str = '', notify_type=..., body_format=None, **kwargs):
        """Perform Google Chat Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object.

        Syntax:
          gchat://workspace/webhook_key/webhook_token
          gchat://workspace/webhook_key/webhook_token/thread_key
        """
    @staticmethod
    def parse_native_url(url):
        """
        Support
           https://chat.googleapis.com/v1/spaces/{workspace}/messages
                 '?key={key}&token={token}
           https://chat.googleapis.com/v1/spaces/{workspace}/messages
                 '?key={key}&token={token}&threadKey={thread}
        """
