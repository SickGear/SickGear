from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

BARK_SOUNDS: Incomplete

class NotifyBarkLevel:
    ACTIVE: str
    TIME_SENSITIVE: str
    PASSIVE: str
    CRITICAL: str

BARK_LEVELS: Incomplete

class NotifyBark(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    notify_url: Incomplete
    category: Incomplete
    group: Incomplete
    targets: Incomplete
    include_image: Incomplete
    click: Incomplete
    badge: Incomplete
    sound: Incomplete
    volume: Incomplete
    icon: Incomplete
    level: Incomplete
    def __init__(self, targets=None, include_image: bool = True, sound=None, category=None, group=None, level=None, click=None, badge=None, volume=None, icon=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
