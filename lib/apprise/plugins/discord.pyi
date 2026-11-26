from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from typing import Any

USER_ROLE_DETECTION_RE: Incomplete

class NotifyDiscord(NotifyBase):
    """A wrapper to Discord Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    attachment_support: bool
    image_size: Incomplete
    request_rate_per_sec: int
    clock_skew: Incomplete
    body_maxlen: int
    overflow_amalgamate_title: bool
    discord_max_fields: int
    max_discord_template_size: int
    discord_max_attachments: int
    discord_max_attach_bytes: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    webhook_id: Incomplete
    webhook_token: Incomplete
    tts: Incomplete
    avatar: Incomplete
    footer: Incomplete
    footer_logo: Incomplete
    include_image: Incomplete
    fields: Incomplete
    thread_id: Incomplete
    avatar_url: Incomplete
    href: Incomplete
    flags: Incomplete
    ping: list[str]
    batch: Incomplete
    ratelimit_reset: Incomplete
    ratelimit_remaining: float
    template: Incomplete
    tokens: dict
    def __init__(self, webhook_id: str, webhook_token: str, tts: bool = False, avatar: bool = True, footer: bool = False, footer_logo: bool = True, include_image: bool = False, fields: bool = True, avatar_url: str | None = None, href: str | None = None, thread: str | None = None, flags: int | None = None, ping: list[str] | None = None, template: str | None = None, tokens: dict | None = None, batch: bool | None = None, **kwargs: Any) -> None:
        """Initialize Discord Object."""
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Return a validated Discord webhook payload from template,
        or False on failure."""
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., attach: list[AttachBase] | None = None, **kwargs: Any) -> bool:
        """Perform Discord Notification."""
    def _send(self, payload: dict[str, Any], attach: list[AttachBase] | None = None, params: dict[str, str] | None = None, rate_limit: int = 1, **kwargs: Any) -> bool:
        """Wrapper to the requests (post) object."""
    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        """Returns the URL built dynamically based on specified arguments."""
    @property
    def url_identifier(self) -> tuple[str, str, str]:
        """Returns all of the identifiers that make this URL unique."""
    @staticmethod
    def parse_url(url: str) -> dict[str, Any] | None:
        """Parses the URL and returns arguments for instantiating this object.

        Syntax:
          discord://webhook_id/webhook_token
        """
    @staticmethod
    def parse_native_url(url: str) -> dict[str, Any] | None:
        """
        Support https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN
        Support Legacy URL as well:
            https://discordapp.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN
        """
    def ping_payload(self, *args: str) -> dict[str, Any]:
        '''
        Takes one or more strings and applies the payload associated with
        pinging the users detected within.

        This returns a dict that may contain:
          - allow_mentions
          - content (starting with "👉 " and containing mention tokens)
        '''
    @staticmethod
    def extract_markdown_sections(markdown: str) -> tuple[str, list[dict[str, str]]]:
        """Extract headers and their corresponding sections into embed
        fields."""
