from .. import exception as exception
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

RESEND_HTTP_ERROR_MAP: Incomplete

class NotifyResend(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_format: Incomplete
    notify_url: str
    attachment_support: bool
    request_rate_per_sec: float
    default_empty_subject: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    from_email: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    def __init__(self, apikey, from_email, targets=None, cc=None, bcc=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
