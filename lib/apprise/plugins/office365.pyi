from .. import exception as exception
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_email as is_email, parse_emails as parse_emails, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyOffice365(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    request_rate_per_sec: float
    setup_url: str
    graph_url: str
    auth_url: str
    attachment_support: bool
    storage_mode: Incomplete
    outlook_attachment_inline_max: int
    scope: str
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    tenant: Incomplete
    source: Incomplete
    client_id: Incomplete
    secret: Incomplete
    names: Incomplete
    cc: Incomplete
    bcc: Incomplete
    targets: Incomplete
    token: Incomplete
    token_expiry: Incomplete
    from_email: Incomplete
    from_name: Incomplete
    def __init__(self, tenant, client_id, secret, source=None, targets=None, cc=None, bcc=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def upload_attachment(self, attachment, message_id, name=None): ...
    def authenticate(self): ...
    def _fetch(self, url, payload=None, headers=None, content_type: str = 'application/json', method: str = 'POST'): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
