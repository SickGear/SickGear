from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class GotifyPriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

GOTIFY_PRIORITIES: Incomplete
GOTIFY_PRIORITY_MAP: Incomplete

class NotifyGotify(NotifyBase):
    """A wrapper for Gotify Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    fullpath: Incomplete
    priority: Incomplete
    schema: str
    def __init__(self, token, priority=None, **kwargs) -> None:
        """Initialize Gotify Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Gotify Notification."""
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
