from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_WINDOWS_SUPPORT_ENABLED: bool

class NotifyWindows(NotifyBase):
    enabled = NOTIFY_WINDOWS_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: str
    protocol: str
    setup_url: str
    request_rate_per_sec: int
    image_size: Incomplete
    body_max_line_count: int
    default_popup_duration_sec: int
    url_identifier: bool
    templates: Incomplete
    template_args: Incomplete
    duration: Incomplete
    hwnd: Incomplete
    include_image: Incomplete
    def __init__(self, include_image: bool = True, duration=None, **kwargs) -> None: ...
    def _on_destroy(self, hwnd, msg, wparam, lparam): ...
    wc: Incomplete
    hinst: Incomplete
    classAtom: Incomplete
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
