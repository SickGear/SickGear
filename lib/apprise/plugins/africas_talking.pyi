from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class AfricasTalkingSMSMode:
    BULKSMS: str
    PREMIUM: str
    SANDBOX: str

AFRICAS_TALKING_SMS_MODES: Incomplete
AFRICAS_TALKING_HTTP_ERROR_MAP: Incomplete

class NotifyAfricasTalking(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: Incomplete
    title_maxlen: int
    body_maxlen: int
    default_batch_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    appuser: Incomplete
    apikey: Incomplete
    sender: Incomplete
    batch: Incomplete
    mode: Incomplete
    targets: Incomplete
    def __init__(self, appuser, apikey, targets=None, sender=None, batch=None, mode=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
