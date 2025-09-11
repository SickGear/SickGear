from .. import exception as exception
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

GROUP_REGEX: Incomplete
CONTACT_REGEX: Incomplete

class SMSEaglePriority:
    NORMAL: int
    HIGH: int

SMSEAGLE_PRIORITIES: Incomplete
SMSEAGLE_PRIORITY_MAP: Incomplete

class SMSEagleCategory:
    PHONE: str
    GROUP: str
    CONTACT: str

SMSEAGLE_CATEGORIES: Incomplete

class NotifySMSEagle(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_path: str
    attachment_support: bool
    body_maxlen: int
    default_batch_size: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    flash: Incomplete
    test: Incomplete
    batch: Incomplete
    status: Incomplete
    target_phones: Incomplete
    target_groups: Incomplete
    target_contacts: Incomplete
    invalid_targets: Incomplete
    token: Incomplete
    priority: Incomplete
    def __init__(self, token=None, targets=None, priority=None, batch: bool = False, status: bool = False, flash: bool = False, test: bool = False, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
