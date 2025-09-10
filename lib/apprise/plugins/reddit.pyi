from .. import __title__ as __title__, __version__ as __version__
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

REDDIT_HTTP_ERROR_MAP: Incomplete

class RedditMessageKind:
    AUTO: str
    SELF: str
    LINK: str

REDDIT_MESSAGE_KINDS: Incomplete

class NotifyReddit(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    body_maxlen: int
    title_maxlen: int
    notify_format: Incomplete
    auth_url: str
    submit_url: str
    request_rate_per_sec: int
    clock_skew: Incomplete
    access_token_lifetime_sec: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    subreddits: Incomplete
    nsfw: Incomplete
    sendreplies: Incomplete
    spoiler: Incomplete
    resubmit: Incomplete
    advertisement: Incomplete
    flair_id: Incomplete
    flair_text: Incomplete
    __refresh_token: Incomplete
    __access_token: Incomplete
    __access_token_expiry: Incomplete
    kind: Incomplete
    user: Incomplete
    password: Incomplete
    client_id: Incomplete
    client_secret: Incomplete
    ratelimit_reset: Incomplete
    ratelimit_remaining: float
    def __init__(self, app_id=None, app_secret=None, targets=None, kind=None, nsfw: bool = False, sendreplies: bool = True, resubmit: bool = False, spoiler: bool = False, advertisement: bool = False, flair_id=None, flair_text=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def login(self): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _fetch(self, url, payload=None): ...
    @staticmethod
    def parse_url(url): ...
