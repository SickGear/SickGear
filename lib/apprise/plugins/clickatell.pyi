from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyClickatell(NotifyBase):
    service_name: Incomplete
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    source: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    def __init__(self, apikey, source=None, targets=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
