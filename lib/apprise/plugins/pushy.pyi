from ..common import NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

VALIDATE_DEVICE: Incomplete
VALIDATE_TOPIC: Incomplete
PUSHY_HTTP_ERROR_MAP: Incomplete

class NotifyPushy(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    devices: Incomplete
    topics: Incomplete
    sound: Incomplete
    badge: Incomplete
    def __init__(self, apikey, targets=None, sound=None, badge=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
