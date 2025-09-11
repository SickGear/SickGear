from ..common import NotifyType as NotifyType
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyFreeMobile(NotifyBase):
    service_name: Incomplete
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    title_maxlen: int
    body_maxlen: int
    template_tokens: Incomplete
    def __init__(self, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
