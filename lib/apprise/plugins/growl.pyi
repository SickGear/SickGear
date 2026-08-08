from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_GROWL_SUPPORT_ENABLED: bool

class GrowlPriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

GROWL_PRIORITIES: Incomplete
GROWL_PRIORITY_MAP: Incomplete

class NotifyGrowl(NotifyBase):
    """A wrapper to Growl Notifications."""
    enabled = NOTIFY_GROWL_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: str
    service_url: str
    protocol: str
    setup_url: str
    image_size: Incomplete
    request_rate_per_sec: int
    body_max_line_count: int
    default_port: int
    growl_notification_type: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    port: Incomplete
    priority: Incomplete
    growl: Incomplete
    sticky: Incomplete
    version: Incomplete
    include_image: Incomplete
    def __init__(self, priority=None, version: int = 2, include_image: bool = True, sticky: bool = False, **kwargs) -> None:
        """Initialize Growl Object."""
    def register(self):
        """Registers with the Growl server."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Growl Notification."""
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
