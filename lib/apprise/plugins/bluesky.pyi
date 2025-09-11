from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

HANDLE_HOST_PARSE_RE: Incomplete
IS_USER: Incomplete

class NotifyBlueSky(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    attachment_support: bool
    clock_skew: Incomplete
    access_token_lifetime_sec: Incomplete
    xrpc_suffix_did: str
    xrpc_suffix_session: str
    xrpc_suffix_record: str
    xrpc_suffix_blob: str
    plc_directory: str
    request_rate_per_sec: int
    ratelimit_reset: Incomplete
    ratelimit_remaining: int
    bluesky_default_host: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    __access_token: Incomplete
    __refresh_token: Incomplete
    __access_token_expiry: Incomplete
    __endpoint: Incomplete
    host: Incomplete
    user: Incomplete
    def __init__(self, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def get_identifier(self, user=None, login: bool = False): ...
    def login(self): ...
    def _fetch(self, url, payload=None, params=None, method: str = 'POST', content_type=None, login: bool = False): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
