from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_GLIB_SUPPORT_ENABLED: bool
NOTIFY_GLIB_IMAGE_SUPPORT: bool

class GLibUrgency:
    LOW: int
    NORMAL: int
    HIGH: int

GLIB_URGENCIES: Incomplete
GLIB_URGENCY_MAP: Incomplete

class NotifyGLib(NotifyBase):
    enabled = NOTIFY_GLIB_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: Incomplete
    setup_url: str
    request_rate_per_sec: int
    image_size: Incomplete
    message_timeout_ms: int
    body_max_line_count: int
    glib_interface: str
    glib_setting_location: str
    templates: Incomplete
    template_args: Incomplete
    registry: Incomplete
    urgency: Incomplete
    x_axis: Incomplete
    y_axis: Incomplete
    include_image: Incomplete
    def __init__(self, urgency=None, x_axis=None, y_axis=None, include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
