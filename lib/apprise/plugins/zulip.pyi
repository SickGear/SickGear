from ..common import NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

VALIDATE_BOTNAME: Incomplete
VALIDATE_ORG: Incomplete
ZULIP_HTTP_ERROR_MAP: Incomplete
TARGET_LIST_DELIM: Incomplete
IS_VALID_TARGET_RE: Incomplete

class NotifyZulip(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    default_hostname: str
    default_notification_stream: str
    hostname: Incomplete
    botname: Incomplete
    organization: Incomplete
    token: Incomplete
    targets: Incomplete
    def __init__(self, botname, organization, token, targets=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
