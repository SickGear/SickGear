from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

TARGET_LIST_DELIM: Incomplete

class ParsePlatformDevice:
    ALL: str
    IOS: str
    ANDROID: str

PARSE_PLATFORM_DEVICES: Incomplete

class NotifyParsePlatform(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    fullpath: Incomplete
    application_id: Incomplete
    master_key: Incomplete
    devices: Incomplete
    device: Incomplete
    def __init__(self, app_id, master_key, device=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
