from . import templates as templates
from ...common import NotifyFormat as NotifyFormat, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ...conversion import convert_between as convert_between
from ...logger import logger as logger
from ...url import PrivacyMode as PrivacyMode
from ...utils.parse import is_email as is_email, is_hostname as is_hostname, is_ipaddr as is_ipaddr, parse_bool as parse_bool, parse_emails as parse_emails
from ..base import NotifyBase as NotifyBase
from .common import AppriseEmailException as AppriseEmailException, EmailMessage as EmailMessage, SECURE_MODES as SECURE_MODES, SecureMailMode as SecureMailMode, WebBaseLogin as WebBaseLogin
from _typeshed import Incomplete

class NotifyEmail(NotifyBase):
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    storage_mode: Incomplete
    notify_format: Incomplete
    socket_connect_timeout: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    reply_to: Incomplete
    names: Incomplete
    headers: Incomplete
    from_addr: Incomplete
    smtp_host: Incomplete
    secure_mode: Incomplete
    host: Incomplete
    secure: bool
    port: Incomplete
    pgp: Incomplete
    pgp_key: Incomplete
    use_pgp: Incomplete
    def __init__(self, smtp_host=None, from_addr=None, secure_mode=None, targets=None, cc=None, bcc=None, reply_to=None, headers=None, use_pgp=None, pgp_key=None, **kwargs) -> None: ...
    user: Incomplete
    def apply_email_defaults(self, secure_mode=None, port=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def _get_charset(input_string): ...
    @staticmethod
    def prepare_emails(subject, body, from_addr, to, cc: set | None = None, bcc: set | None = None, reply_to: set | None = None, smtp_host=None, notify_format=..., attach=None, headers: dict | None = None, names=None, pgp=None, tzinfo=None): ...
