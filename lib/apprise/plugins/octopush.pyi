from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_email as is_email, is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class OctopushType:
    """Octopush message types."""
    PREMIUM: str
    LOW_COST: str

OCTOPUSH_TYPE_MAP: Incomplete
OCTOPUSH_TYPES: Incomplete

class OctopushPurpose:
    """Octopush purposes."""
    ALERT: str
    WHOLESALE: str

OCTOPUSH_PURPOSES: Incomplete

class NotifyOctopush(NotifyBase):
    """A wrapper for Octopush Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    default_batch_size: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    api_login: Incomplete
    api_key: Incomplete
    batch: Incomplete
    replies: Incomplete
    mtype: Incomplete
    purpose: Incomplete
    sender: Incomplete
    targets: Incomplete
    def __init__(self, api_login, api_key, targets=None, batch: bool = False, sender=None, purpose=None, mtype=None, replies: bool = False, **kwargs) -> None:
        """Initialize Octopush Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Octopush Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object.

        """
