from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifySpike(NotifyBase):
    service_name: Incomplete
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    token: Incomplete
    webhook_url: Incomplete
    def __init__(self, token, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
