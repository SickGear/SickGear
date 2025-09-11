from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..logger import logger as logger
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_emails as parse_emails, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

MAILGUN_HTTP_ERROR_MAP: Incomplete

class MailgunRegion:
    US: str
    EU: str

MAILGUN_API_LOOKUP: Incomplete
MAILGUN_REGIONS: Incomplete

class NotifyMailgun(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    setup_url: str
    attachment_support: bool
    notify_format: Incomplete
    default_batch_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    names: Incomplete
    headers: Incomplete
    tokens: Incomplete
    batch: Incomplete
    region_name: Incomplete
    from_addr: Incomplete
    def __init__(self, apikey, targets, cc=None, bcc=None, from_addr=None, region_name=None, headers=None, tokens=None, batch: bool = False, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
