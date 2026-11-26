from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

EIGHT00COM_HTTP_ERROR_MAP: Incomplete

class NotifyEight00com(NotifyBase):
    """A wrapper for 800.com SMS/MMS Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    source: Incomplete
    targets: Incomplete
    def __init__(self, token=None, source=None, targets=None, **kwargs) -> None:
        """Initialize 800.com Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform 800.com SMS/MMS Notification."""
    def _send_sms(self, sender, recipient, body, headers):
        """Send a plain text SMS via the 800.com REST API."""
    def _send_mms(self, sender, recipient, body, attach, headers):
        """Send an MMS with one or more attachments via the 800.com API.

        Uses Pattern B (multi-file multipart/form-data).
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified
        arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this
        notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
