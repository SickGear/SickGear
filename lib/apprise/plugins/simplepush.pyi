from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_SIMPLEPUSH_ENABLED: bool

class NotifySimplePush(NotifyBase):
    enabled = NOTIFY_SIMPLEPUSH_ENABLED
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    event: Incomplete
    _iv: Incomplete
    _iv_hex: Incomplete
    _key: Incomplete
    def __init__(self, apikey, event=None, **kwargs) -> None: ...
    def _encrypt(self, content): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
