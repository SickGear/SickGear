from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_USER: Incomplete

class TwitterMessageMode:
    """Twitter Message Mode."""
    DM: str
    TWEET: str

TWITTER_MESSAGE_MODES: Incomplete

class NotifyTwitter(NotifyBase):
    """A wrapper to Twitter Notifications."""
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    attachment_support: bool
    title_maxlen: int
    twitter_tweet: str
    twitter_whoami: str
    twitter_lookup: str
    twitter_dm: str
    twitter_media: str
    __tweet_non_gif_images_batch: int
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
    def __init__(self, ckey, csecret, akey, asecret, targets=None, mode=None, cache: bool = True, batch: bool = True, **kwargs) -> None:
        """Initialize Twitter Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Twitter Notification."""
    def _send_tweet(self, body, title: str = '', notify_type=..., attachments=None, **kwargs):
        """Twitter Public Tweet via X API v2."""
    def _send_dm(self, body, title: str = '', notify_type=..., attachments=None, **kwargs):
        """Twitter Direct Message via X API v2.

        Requires a Basic or higher X API subscription.
        Free-tier accounts will receive a 403 error.
        """
    def _whoami(self, lazy: bool = True):
        """Looks up details of the current authenticated user via v2."""
    def _user_lookup(self, usernames, lazy: bool = True):
        """Looks up usernames and returns user IDs via v2.

        usernames can be a list/set/tuple as well.
        """
    def _fetch(self, url, payload=None, method: str = 'POST', json: bool = True, extra=None):
        """Wrapper to Twitter API requests object."""
    @property
    def body_maxlen(self):
        """The maximum allowable characters allowed in the body per message
        This is used during a Private DM Message Size (not Public Tweets which
        are limited to 280 characters)"""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
