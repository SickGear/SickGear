from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

ZOOM_HTTP_ERROR_MAP: Incomplete

class ZoomMode:
    """Tracks the notification mode for Zoom Team Chat."""
    SIMPLE: str
    FULL: str

ZOOM_MODES: Incomplete
ZOOM_MODE_DEFAULT: Incomplete

class NotifyZoom(NotifyBase):
    """A wrapper for Zoom Team Chat Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    zoom_webhook_url: str
    body_maxlen: int
    title_maxlen: int
    overflow_amalgamate_title: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    webhook_id: Incomplete
    token: Incomplete
    mode: Incomplete
    def __init__(self, webhook_id, token, mode=None, **kwargs) -> None:
        """Initialize Zoom Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Zoom Team Chat Notification."""
    def _fetch(self, url, payload, content_type=None):
        """Wrapper to a Zoom webhook POST request."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique
        from another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified
        arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """Support https://inbots.zoom.us/incoming/hook/WEBHOOK_ID"""
