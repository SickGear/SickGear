from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_CHANNEL: Incomplete
IS_USER: Incomplete
IS_ROOM_ID: Incomplete
RC_HTTP_ERROR_MAP: Incomplete

class RocketChatAuthMode:
    WEBHOOK: str
    TOKEN: str
    BASIC: str

ROCKETCHAT_AUTH_MODES: Incomplete

class NotifyRocketChat(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    image_size: Incomplete
    title_maxlen: int
    body_maxlen: int
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: Incomplete
    api_url: Incomplete
    channels: Incomplete
    rooms: Incomplete
    users: Incomplete
    webhook: Incomplete
    headers: Incomplete
    mode: Incomplete
    avatar: Incomplete
    def __init__(self, webhook=None, targets=None, mode=None, avatar=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send_webhook_notification(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send_basic_notification(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _payload(self, body, title: str = '', notify_type=...): ...
    def _send(self, payload, notify_type, path: str = 'api/v1/chat.postMessage', **kwargs): ...
    def login(self): ...
    def logout(self): ...
    @staticmethod
    def parse_url(url): ...
