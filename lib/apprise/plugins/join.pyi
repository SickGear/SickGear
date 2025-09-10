from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

JOIN_HTTP_ERROR_MAP: Incomplete
IS_DEVICE_RE: Incomplete
IS_GROUP_RE: Incomplete
JOIN_IMAGE_XY: Incomplete

class JoinPriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

JOIN_PRIORITIES: Incomplete
JOIN_PRIORITY_MAP: Incomplete

class NotifyJoin(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    image_size: Incomplete
    body_maxlen: int
    default_join_group: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    include_image: Incomplete
    apikey: Incomplete
    priority: Incomplete
    targets: Incomplete
    def __init__(self, apikey, targets=None, include_image: bool = True, priority=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
