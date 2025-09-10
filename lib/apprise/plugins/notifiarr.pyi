from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from .discord import USER_ROLE_DETECTION_RE as USER_ROLE_DETECTION_RE
from _typeshed import Incomplete

CHANNEL_LIST_DELIM: Incomplete
CHANNEL_REGEX: Incomplete

class NotifyNotifiarr(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    request_rate_per_sec: float
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    include_image: Incomplete
    source: Incomplete
    event: int
    targets: Incomplete
    def __init__(self, apikey=None, include_image=None, event=None, targets=None, source=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send(self, payload): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
