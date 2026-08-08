from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_SIMPLEPUSH_ENABLED: bool

class NotifySimplePush(NotifyBase):
    """A wrapper for SimplePush Notifications."""
    enabled = NOTIFY_SIMPLEPUSH_ENABLED
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    event: Incomplete
    _iv: Incomplete
    _iv_hex: Incomplete
    _key: Incomplete
    def __init__(self, apikey, event=None, **kwargs) -> None:
        """Initialize SimplePush Object."""
    def _encrypt(self, content):
        """Encrypts message for use with SimplePush."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform SimplePush Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
