from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyEmby(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    emby_device_id: str
    emby_message_timeout_ms: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: str
    access_token: Incomplete
    user_id: Incomplete
    modal: Incomplete
    port: Incomplete
    def __init__(self, modal: bool = False, **kwargs) -> None: ...
    def login(self, **kwargs): ...
    def sessions(self, user_controlled: bool = True): ...
    def logout(self, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def is_authenticated(self): ...
    @property
    def emby_auth_header(self): ...
    @staticmethod
    def parse_url(url): ...
    def __del__(self) -> None: ...
