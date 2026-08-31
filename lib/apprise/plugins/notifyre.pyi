from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFYRE_API_VERSION: str
NOTIFYRE_SMS_URL: Incomplete
NOTIFYRE_FAX_URL: Incomplete

class NotifyreMode:
    """Delivery modes supported by the Notifyre plugin."""
    SMS: str
    FAX: str

NOTIFYRE_MODES: Incomplete

class NotifyNotifyre(NotifyBase):
    """A wrapper for Notifyre Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    mode: Incomplete
    apikey: Incomplete
    source: Incomplete
    campaign: Incomplete
    template: Incomplete
    ref: Incomplete
    hq: Incomplete
    header: Incomplete
    targets: Incomplete
    def __init__(self, apikey, targets=None, mode=None, source=None, campaign=None, template=None, ref=None, hq=None, header=None, **kwargs) -> None:
        """Initialize Notifyre Object."""
    @property
    def body_maxlen(self):
        """Maximum body length varies by mode.

        SMS is limited to 160 characters per segment; fax has no
        meaningful API-side limit so a generous ceiling is used.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Notifyre Notification."""
    def _send_sms(self, body, attach=None):
        """Send an SMS notification to all targets."""
    def _send_fax(self, body, attach=None):
        """Send a fax notification with optional document attachments."""
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
