from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyFeishu(NotifyBase):
    service_name: Incomplete
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    templates: Incomplete
    title_maxlen: int
    body_maxlen: int
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    def __init__(self, token, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
