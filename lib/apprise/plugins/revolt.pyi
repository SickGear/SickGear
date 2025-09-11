from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyRevolt(NotifyBase):
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
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    bot_token: Incomplete
    targets: Incomplete
    icon_url: Incomplete
    link: Incomplete
    ratelimit_reset: Incomplete
    ratelimit_remaining: float
    def __init__(self, bot_token, targets, icon_url=None, link=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send(self, payload, channel_id, retries: int = 1, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
