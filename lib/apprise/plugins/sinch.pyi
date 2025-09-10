from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class SinchRegion:
    USA: str
    EUROPE: str

SINCH_REGIONS: Incomplete

class NotifySinch(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    validity_period: int
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    service_plan_id: Incomplete
    api_token: Incomplete
    region: Incomplete
    source: Incomplete
    targets: Incomplete
    def __init__(self, service_plan_id, api_token, source, targets=None, region=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
