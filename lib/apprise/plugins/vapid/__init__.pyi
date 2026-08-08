from . import subscription as subscription
from ..base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class VapidPushMode:
    """Supported Vapid Push Services."""
    CHROME: str
    FIREFOX: str
    EDGE: str
    OPERA: str
    APPLE: str
    SAMSUNG: str
    BRAVE: str
    GENERIC: str

VAPID_API_LOOKUP: Incomplete
VAPID_PUSH_MODES: Incomplete

class NotifyVapid(NotifyBase):
    """A wrapper for WebPush/Vapid notifications."""
    enabled: Incomplete
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    max_vapid_keyfile_size: int
    max_vapid_subfile_size: int
    body_maxlen: int
    title_maxlen: int
    storage_mode: Incomplete
    vapid_jwt_expiration_sec: int
    vapid_subscription_file: str
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    keyfile: Incomplete
    subfile: Incomplete
    targets: Incomplete
    _invalid_targets: Incomplete
    subscriptions: Incomplete
    subscriptions_loaded: bool
    private_key_loaded: bool
    ttl: Incomplete
    include_image: Incomplete
    subscriber: Incomplete
    mode: Incomplete
    pem: Incomplete
    def __init__(self, subscriber, mode=None, targets=None, keyfile=None, subfile=None, include_image=None, ttl=None, **kwargs) -> None:
        """Initialize Vapid Messaging."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Vapid Notification."""
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
    @property
    def jwt_token(self):
        """Returns our VAPID Token based on class details."""
    @property
    def public_key(self):
        """Returns our public key representation."""
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
