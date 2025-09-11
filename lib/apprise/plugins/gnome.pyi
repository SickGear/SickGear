from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_GNOME_SUPPORT_ENABLED: bool

class GnomeUrgency:
    LOW: int
    NORMAL: int
    HIGH: int

GNOME_URGENCIES: Incomplete
GNOME_URGENCY_MAP: Incomplete

class NotifyGnome(NotifyBase):
    enabled = NOTIFY_GNOME_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: str
    setup_url: str
    image_size: Incomplete
    request_rate_per_sec: int
    body_max_line_count: int
    title_maxlen: int
    url_identifier: bool
    templates: Incomplete
    template_args: Incomplete
    urgency: Incomplete
    include_image: Incomplete
    def __init__(self, urgency=None, include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
