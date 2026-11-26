from ..common import NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

VALIDATE_API_KEY: Incomplete
VALIDATE_CHANNEL: Incomplete
DEFAULT_CHANNEL: str
DEFAULT_NOTIFY_URL: str
TRIGV_LEVELS: Incomplete
TRIGV_URGENCIES: Incomplete
TRIGV_HTTP_ERROR_MAP: Incomplete

class NotifyTrigv(NotifyBase):
    """A wrapper for Trigv push notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_url = DEFAULT_NOTIFY_URL
    attachment_support: bool
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    api_key: Incomplete
    targets: Incomplete
    supplemental_url: Incomplete
    image_url: Incomplete
    event_type: Incomplete
    priority: Incomplete
    urgency: Incomplete
    def __init__(self, api_key, targets=None, supplemental_url=None, image_url=None, urgency=None, event_type=None, priority=None, **kwargs) -> None:
        """Initialize Trigv Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Trigv Notification."""
    def _resolve_urgency(self, notify_type):
        """Map explicit urgency, Pushover-style priority, or defaults."""
    def __len__(self) -> int:
        """Returns the number of channels this instance will notify."""
    @property
    def url_identifier(self):
        """Returns identifiers that make this URL unique.

        Targets/channels are never included here; they identify where
        we deliver to, not the connection itself.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments to re-instantiate."""
