from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

USER_ROLE_DETECTION_RE: Incomplete

class NotifyDiscord(NotifyBase):
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
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
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
    ratelimit_reset: Incomplete
    ratelimit_remaining: float
    def __init__(self, webhook_id, webhook_token, tts: bool = False, avatar: bool = True, footer: bool = False, footer_logo: bool = True, include_image: bool = False, fields: bool = True, avatar_url=None, href=None, thread=None, flags=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send(self, payload, attach=None, params=None, rate_limit: int = 1, **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
    @staticmethod
    def extract_markdown_sections(markdown): ...
