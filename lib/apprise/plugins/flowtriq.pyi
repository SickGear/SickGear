from ..common import NotifyType as NotifyType
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

FLOWTRIQ_SEVERITY_MAP: Incomplete

class NotifyFlowtriq(NotifyBase):
    """A wrapper for Flowtriq Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    apikey: Incomplete
    webhook_path: Incomplete
    def __init__(self, apikey, webhook_path, **kwargs) -> None:
        """Initialize Flowtriq Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Flowtriq Notification."""
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
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
