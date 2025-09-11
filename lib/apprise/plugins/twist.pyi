from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_email as is_email, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_CHANNEL: Incomplete
IS_CHANNEL_ID: Incomplete
LIST_DELIM: Incomplete

class NotifyTwist(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    body_maxlen: int
    notify_format: Incomplete
    api_url: str
    request_rate_per_sec: float
    default_notification_channel: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    channels: Incomplete
    channel_ids: Incomplete
    token: Incomplete
    default_workspace: Incomplete
    _cached_workspaces: Incomplete
    _cached_channels: Incomplete
    email: Incomplete
    user: Incomplete
    host: Incomplete
    def __init__(self, email=None, targets=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def login(self): ...
    def logout(self): ...
    def get_workspaces(self): ...
    def get_channels(self, wid): ...
    def _channel_migration(self): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _fetch(self, url, payload=None, method: str = 'POST', login: bool = False): ...
    @staticmethod
    def parse_url(url): ...
    def __del__(self) -> None: ...
