from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_SMPP_ENABLED: bool

class NotifySMPP(NotifyBase):
    """A wrapper for SMPP Notifications."""
    enabled = NOTIFY_SMPP_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: str
    secure_protocol: str
    default_port: int
    default_secure_port: int
    setup_url: str
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    source: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    def __init__(self, source=None, targets=None, **kwargs) -> None:
        """Initialize SMPP Object."""
    @property
    def url_identifier(self):
        """Returns all the identifiers that make this URL unique from another
        similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification.

        Always return 1 at least
        """
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform SMPP Notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
