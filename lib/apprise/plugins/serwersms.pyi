from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

SERWERSMS_GROUP_REGEX: Incomplete

class SerwerSMSCategory:
    """Tracks the target type for a SerwerSMS destination."""
    PHONE: str
    GROUP: str

class NotifySerwerSMS(NotifyBase):
    """A wrapper for SerwerSMS Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    notify_url_mms: str
    body_maxlen: int
    title_maxlen: int
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    sender: Incomplete
    target_phones: Incomplete
    target_groups: Incomplete
    invalid_targets: Incomplete
    def __init__(self, sender=None, targets=None, **kwargs) -> None:
        """Initialize SerwerSMS Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform SerwerSMS SMS/MMS Notification."""
    def _send_mms(self, label, fields, attach, headers):
        """Send MMS via the SerwerSMS MMS endpoint."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
