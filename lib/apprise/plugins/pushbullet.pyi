from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

PUSHBULLET_SEND_TO_ALL: str
PUSHBULLET_HTTP_ERROR_MAP: Incomplete

class NotifyPushBullet(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    setup_url: str
    notify_url: str
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    accesstoken: Incomplete
    targets: Incomplete
    def __init__(self, accesstoken, targets=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send(self, url, payload, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
