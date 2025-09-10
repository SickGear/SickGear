from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class PagerDutySeverity:
    INFO: str
    WARNING: str
    ERROR: str
    CRITICAL: str

PAGERDUTY_SEVERITY_MAP: Incomplete
PAGERDUTY_SEVERITIES: Incomplete

class PagerDutyRegion:
    US: str
    EU: str

PAGERDUTY_API_LOOKUP: Incomplete
PAGERDUTY_REGIONS: Incomplete

class NotifyPagerDuty(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    image_size: Incomplete
    event_action: str
    default_region: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    integration_key: Incomplete
    source: Incomplete
    component: Incomplete
    region_name: Incomplete
    severity: Incomplete
    click: Incomplete
    class_id: Incomplete
    group: Incomplete
    details: Incomplete
    include_image: Incomplete
    def __init__(self, apikey, integrationkey=None, source=None, component=None, group=None, class_id=None, include_image: bool = True, click=None, details=None, region_name=None, severity=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
