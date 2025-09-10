from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class Enigma2MessageType:
    INFO: int
    WARNING: int
    ERROR: int

MESSAGE_MAPPING: Incomplete

class NotifyEnigma2(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    timeout: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, timeout=None, headers=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
