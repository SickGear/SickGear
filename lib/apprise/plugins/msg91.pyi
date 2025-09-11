from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class MSG91PayloadField:
    BODY: str
    MESSAGETYPE: str

RESERVED_KEYWORDS: Incomplete

class NotifyMSG91(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    component_key_re: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    authkey: Incomplete
    template: Incomplete
    short_url: Incomplete
    targets: Incomplete
    template_mapping: Incomplete
    def __init__(self, template, authkey, targets=None, short_url=None, template_mapping=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
