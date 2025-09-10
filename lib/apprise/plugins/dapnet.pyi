from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_call_sign as is_call_sign, parse_bool as parse_bool, parse_call_sign as parse_call_sign, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class DapnetPriority:
    NORMAL: int
    EMERGENCY: int

DAPNET_PRIORITIES: Incomplete
DAPNET_PRIORITY_MAP: Incomplete

class NotifyDapnet(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    default_batch_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    targets: Incomplete
    priority: Incomplete
    txgroups: Incomplete
    batch: Incomplete
    def __init__(self, targets=None, priority=None, txgroups=None, batch: bool = False, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
