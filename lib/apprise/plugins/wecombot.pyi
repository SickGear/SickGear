from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyWeComBot(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    title_maxlen: int
    template_tokens: Incomplete
    template_args: Incomplete
    key: Incomplete
    api_url: Incomplete
    def __init__(self, key, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
