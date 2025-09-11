from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifySFR(NotifyBase):
    service_name: Incomplete
    service_url: str
    protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    space_id: Incomplete
    voice: Incomplete
    lang: Incomplete
    media: Incomplete
    sender: Incomplete
    timeout: Incomplete
    targets: Incomplete
    def __init__(self, space_id=None, targets=None, lang=None, sender=None, media=None, timeout=None, voice=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
