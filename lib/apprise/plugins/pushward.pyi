from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

PUSHWARD_HTTP_ERROR_MAP: Incomplete
PUSHWARD_LEVELS: Incomplete
PUSHWARD_DEFAULT_LEVELS: Incomplete

def pushward_level(value):
    """Resolve a full or short-form level (e.g. 'crit', 'c') to a canonical
    PushWard level, or None if it does not match one."""

class NotifyPushWard(NotifyBase):
    """A wrapper for PushWard Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    image_size: Incomplete
    title_maxlen: int
    body_maxlen: int
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    level: Incomplete
    level_map: Incomplete
    volume: Incomplete
    def __init__(self, apikey, level=None, info=None, success=None, warning=None, failure=None, volume=None, **kwargs) -> None:
        """Initialize PushWard Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform PushWard Notification."""
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
