from .. import exception as exception
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..conversion import convert_between as convert_between
from ..utils.parse import is_email as is_email, parse_emails as parse_emails, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifySendPulse(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_format: Incomplete
    notify_email_url: str
    notify_oauth_url: str
    attachment_support: bool
    request_rate_per_sec: float
    storage_mode: Incomplete
    token_expiry: int
    token_expiry_edge: int
    default_empty_subject: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    names: Incomplete
    host: Incomplete
    from_addr: Incomplete
    client_id: Incomplete
    client_secret: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    template: Incomplete
    template_data: Incomplete
    def __init__(self, client_id, client_secret, from_addr=None, targets=None, cc=None, bcc=None, template=None, template_data=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def login(self): ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _fetch(self, url, payload, target=None, retry: int = 0): ...
    @staticmethod
    def parse_url(url): ...
