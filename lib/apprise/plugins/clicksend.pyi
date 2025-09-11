from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

CLICKSEND_HTTP_ERROR_MAP: Incomplete

class NotifyClickSend(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    default_batch_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    batch: Incomplete
    targets: Incomplete
    def __init__(self, targets=None, batch: bool = False, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
