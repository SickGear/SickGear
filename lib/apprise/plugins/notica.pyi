from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NoticaMode:
    SELFHOSTED: str
    OFFICIAL: str

NOTICA_MODES: Incomplete

class NotifyNotica(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    mode: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, token, headers=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
