from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyXBMC(NotifyBase):
    service_name: str
    service_url: str
    xbmc_protocol: str
    xbmc_secure_protocol: str
    kodi_protocol: str
    kodi_secure_protocol: str
    protocol: Incomplete
    secure_protocol: Incomplete
    setup_url: str
    request_rate_per_sec: int
    body_max_line_count: int
    xbmc_default_port: int
    image_size: Incomplete
    xbmc_remote_protocol: int
    kodi_remote_protocol: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    duration: Incomplete
    schema: Incomplete
    headers: Incomplete
    include_image: Incomplete
    def __init__(self, include_image: bool = True, duration=None, **kwargs) -> None: ...
    def _payload_60(self, title, body, notify_type, **kwargs): ...
    def _payload_20(self, title, body, notify_type, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
