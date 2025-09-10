from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_GROUP_RE: Incomplete

class BulkSMSRoutingGroup:
    ECONOMY: str
    STANDARD: str
    PREMIUM: str

BULKSMS_ROUTING_GROUPS: Incomplete

class BulkSMSEncoding:
    TEXT: str
    UNICODE: str
    BINARY: str

class NotifyBulkSMS(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    default_batch_size: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    source: Incomplete
    route: Incomplete
    unicode: Incomplete
    batch: Incomplete
    targets: Incomplete
    groups: Incomplete
    def __init__(self, source=None, targets=None, unicode=None, batch=None, route=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
