from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

WEBEX_HTTP_ERROR_MAP: Incomplete

class NotifyWebexTeams(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    notify_format: Incomplete
    templates: Incomplete
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
    @staticmethod
    def parse_native_url(url): ...
