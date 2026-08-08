from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_USER: Incomplete
USER_DETECTION_RE: Incomplete
MENTION_DETECTION_RE: Incomplete
HASHTAG_DETECTION_RE: Incomplete
HASHTAG_VALUE_RE: Incomplete

class MastodonMessageVisibility:
    """The visibility of any status message made."""
    DEFAULT: str
    DIRECT: str
    PRIVATE: str
    UNLISTED: str
    PUBLIC: str

MASTODON_MESSAGE_VISIBILITIES: Incomplete

class NotifyMastodon(NotifyBase):
    """A wrapper for Notify Mastodon Notifications."""
    service_name: str
    service_url: str
    protocol: Incomplete
    secure_protocol: Incomplete
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    __toot_non_gif_images_batch: int
    mastodon_whoami: str
    mastodon_media: str
    mastodon_toot: str
    mastodon_dm: str
    title_maxlen: int
    mastodon_body_maxlen: int
    notify_format: Incomplete
    request_rate_per_sec: int
    ratelimit_reset: Incomplete
    ratelimit_remaining: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: Incomplete
    _whoami_cache: Incomplete
    token: Incomplete
    visibility: Incomplete
    api_url: Incomplete
    cache: Incomplete
    batch: Incomplete
    sensitive: Incomplete
    spoiler: Incomplete
    idempotency_key: Incomplete
    language: Incomplete
    targets: Incomplete
    hashtags: Incomplete
    ping: Incomplete
    def __init__(self, token=None, targets=None, batch: bool = True, sensitive=None, spoiler=None, visibility=None, cache: bool = True, key=None, language=None, ping=None, **kwargs) -> None:
        """Initialize Notify Mastodon Object."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    @property
    def body_maxlen(self):
        """Return the body space available after configured status tokens."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Wrapper to _send since we can alert more then one channel."""
    def ping_tokens(self, *args, normalize: bool = False, seen=None):
        """
        Takes one or more strings and returns Mastodon-recognizable mention
        and hashtag tokens detected within.
        """
    @staticmethod
    def ping_payload(tokens):
        """Return a status suffix from one or more ping tokens."""
    @staticmethod
    def normalize_ping_token(token):
        """Normalize a configured ping token into a mention or hashtag."""
    @staticmethod
    def valid_hashtag(token):
        """Return True if a token is a valid Mastodon hashtag."""
    def _whoami(self, lazy: bool = True):
        """Looks details of current authenticated user."""
    def _request(self, path, payload=None, method: str = 'POST'):
        """Wrapper to Mastodon API requests object."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
