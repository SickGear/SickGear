from .. import exception as exception
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_emails as parse_emails, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

SPARKPOST_HTTP_ERROR_MAP: Incomplete

class SparkPostRegion:
    US: str
    EU: str

SPARKPOST_API_LOOKUP: Incomplete
SPARKPOST_REGIONS: Incomplete

class NotifySparkPost(NotifyBase):
    service_name: str
    service_url: str
    attachment_support: bool
    secure_protocol: str
    request_rate_per_sec: float
    sparkpost_retry_wait_sec: int
    sparkpost_retry_attempts: int
    default_batch_size: int
    setup_url: str
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    names: Incomplete
    region_name: Incomplete
    from_name: Incomplete
    from_addr: Incomplete
    headers: Incomplete
    tokens: Incomplete
    batch: Incomplete
    def __init__(self, apikey, targets, cc=None, bcc=None, from_name=None, region_name=None, headers=None, tokens=None, batch=None, **kwargs) -> None: ...
    def __post(self, payload, retry): ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
