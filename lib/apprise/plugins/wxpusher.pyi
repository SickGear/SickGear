from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_TOPIC: Incomplete
IS_USER: Incomplete
WXPUSHER_RESPONSE_CODES: Incomplete

class WxPusherContentType:
    TEXT: int
    HTML: int
    MARKDOWN: int

class SubscriptionType:
    UNVERIFIED: int
    PAID_USERS: int
    UNSUBSCRIBED: int

class NotifyWxPusher(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    __content_type_map: Incomplete
    token: Incomplete
    _invalid_targets: Incomplete
    _users: Incomplete
    _topics: Incomplete
    def __init__(self, token, targets=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
