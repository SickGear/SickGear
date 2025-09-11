from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_USER: Incomplete

class TwitterMessageMode:
    DM: str
    TWEET: str

TWITTER_MESSAGE_MODES: Incomplete

class NotifyTwitter(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    attachment_support: bool
    title_maxlen: int
    twitter_lookup: str
    twitter_whoami: str
    twitter_dm: str
    twitter_tweet: str
    __tweet_non_gif_images_batch: int
    twitter_media: str
    request_rate_per_sec: int
    ratelimit_reset: Incomplete
    ratelimit_remaining: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    ckey: Incomplete
    csecret: Incomplete
    akey: Incomplete
    asecret: Incomplete
    mode: Incomplete
    cache: Incomplete
    batch: Incomplete
    targets: Incomplete
    _whoami_cache: Incomplete
    _user_cache: Incomplete
    def __init__(self, ckey, csecret, akey, asecret, targets=None, mode=None, cache: bool = True, batch: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send_tweet(self, body, title: str = '', notify_type=..., attachments=None, **kwargs): ...
    def _send_dm(self, body, title: str = '', notify_type=..., attachments=None, **kwargs): ...
    def _whoami(self, lazy: bool = True): ...
    def _user_lookup(self, screen_name, lazy: bool = True): ...
    def _fetch(self, url, payload=None, method: str = 'POST', json: bool = True): ...
    @property
    def body_maxlen(self): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
