from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyPushDeer(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    default_hostname: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    push_key: Incomplete
    def __init__(self, pushkey, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False): ...
    @staticmethod
    def parse_url(url): ...
