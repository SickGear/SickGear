from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_DBUS_SUPPORT_ENABLED: bool
NOTIFY_DBUS_IMAGE_SUPPORT: bool
LOOP_GLIB: Incomplete
LOOP_QT: Incomplete
MAINLOOP_MAP: Incomplete

class DBusUrgency:
    LOW: int
    NORMAL: int
    HIGH: int

DBUS_URGENCIES: Incomplete
DBUS_URGENCY_MAP: Incomplete

class NotifyDBus(NotifyBase):
    enabled = NOTIFY_DBUS_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: Incomplete
    setup_url: str
    request_rate_per_sec: int
    image_size: Incomplete
    message_timeout_ms: int
    body_max_line_count: int
    dbus_interface: str
    dbus_setting_location: str
    url_identifier: bool
    templates: Incomplete
    template_args: Incomplete
    registry: Incomplete
    schema: Incomplete
    urgency: Incomplete
    x_axis: Incomplete
    y_axis: Incomplete
    include_image: Incomplete
    def __init__(self, urgency=None, x_axis=None, y_axis=None, include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
