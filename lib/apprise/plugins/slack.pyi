from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

SLACK_HTTP_ERROR_MAP: Incomplete
CHANNEL_LIST_DELIM: Incomplete
CHANNEL_RE: Incomplete

class SlackMode:
    WEBHOOK: str
    BOT: str

SLACK_MODES: Incomplete

class NotifySlack(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    setup_url: str
    attachment_support: bool
    webhook_url: str
    api_url: str
    image_size: Incomplete
    body_maxlen: int
    notify_format: Incomplete
    default_notification_channel: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    _re_formatting_map: Incomplete
    _re_channel_support: Incomplete
    _re_user_id_support: Incomplete
    _re_url_support: Incomplete
    mode: Incomplete
    access_token: Incomplete
    token_a: Incomplete
    token_b: Incomplete
    token_c: Incomplete
    _lookup_users: Incomplete
    use_blocks: Incomplete
    channels: Incomplete
    _re_formatting_rules: Incomplete
    include_image: Incomplete
    include_footer: Incomplete
    include_timestamp: Incomplete
    def __init__(self, access_token=None, token_a=None, token_b=None, token_c=None, targets=None, include_image=None, include_footer=None, include_timestamp=None, use_blocks=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def lookup_userid(self, email): ...
    def _send(self, url, payload, attach=None, http_method: str = 'post', params=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
