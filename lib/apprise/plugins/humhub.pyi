from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyHumHub(NotifyBase):
    """A wrapper for HumHub Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    request_rate_per_sec: float
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    def __init__(self, targets=None, **kwargs) -> None:
        """Initialize HumHub Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform HumHub Notification."""
    def _send(self, url, payload=None, headers=None, auth=None, attach=None):
        """Wrapper to the requests (post) object.

        Returns (ok, content) where content is the raw response bytes
        on success, or None on failure.
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us
        to re-instantiate this object."""
