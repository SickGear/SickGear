from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

KUMULOS_HTTP_ERROR_MAP: Incomplete

class NotifyKumulos(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    apikey: Incomplete
    serverkey: Incomplete
    def __init__(self, apikey, serverkey, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
