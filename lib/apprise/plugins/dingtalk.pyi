from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_PHONE_NO: Incomplete

class NotifyDingTalk(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    secret: Incomplete
    targets: Incomplete
    def __init__(self, token, targets=None, secret=None, **kwargs) -> None: ...
    def get_signature(self): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def title_maxlen(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
