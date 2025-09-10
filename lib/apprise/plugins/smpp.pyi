from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_SMPP_ENABLED: bool

class NotifySMPP(NotifyBase):
    enabled = NOTIFY_SMPP_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: str
    secure_protocol: str
    default_port: int
    default_secure_port: int
    setup_url: str
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    source: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    def __init__(self, source=None, targets=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
