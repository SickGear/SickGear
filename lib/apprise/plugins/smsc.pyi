from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

SMSC_API_URL: str
SMSC_FMT_JSON: int
SMSC_SENDER_ALPHA_MAXLEN: int
SMSC_SENDER_NUMERIC_MAXLEN: int
SMSC_HTTP_ERROR_MAP: Incomplete
SMSC_API_ERROR_MAP: Incomplete

class NotifySMSC(NotifyBase):
    """A wrapper for SMSC Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url = SMSC_API_URL
    body_maxlen: int
    title_maxlen: int
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    sender: Incomplete
    translit: Incomplete
    targets: Incomplete
    def __init__(self, targets=None, sender=None, translit=None, **kwargs) -> None:
        """Initialize SMSC Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform SMSC Notification."""
    def _base_params(self):
        """Build the common query parameters shared by SMS and MMS."""
    def _send_sms(self, body):
        """Send a plain SMS message."""
    def _send_mms(self, body, attach):
        """Send an MMS message with one or more file attachments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
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
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
