from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_bool as parse_bool, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class ExotelPriority:
    """
    Priorities
    """
    NORMAL: str
    HIGH: str

EXOTEL_PRIORITIES: Incomplete
EXOTEL_PRIORITY_MAP: Incomplete

class ExotelEncoding:
    """
    The different encodings supported
    """
    TEXT: str
    UNICODE: str

class ExotelRegion:
    """
    Regions
    """
    US: str
    IN: str

EXOTEL_API_LOOKUP: Incomplete
EXOTEL_REGIONS: Incomplete
EXOTEL_SOURCE_RE: Incomplete

def parse_exotel_source(source):
    """Parse an Exotel source as an ExoPhone or approved Sender ID."""

class NotifyExotel(NotifyBase):
    """
    A wrapper for Exotel Notifications
    """
    default_batch_size: int
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    sid: Incomplete
    token: Incomplete
    apikey: Incomplete
    invalid_targets: Incomplete
    region_name: Incomplete
    unicode: Incomplete
    batch: Incomplete
    priority: Incomplete
    source: Incomplete
    targets: Incomplete
    def __init__(self, sid, token, source, targets=None, apikey=None, batch=None, unicode=None, priority=None, region_name=None, **kwargs) -> None:
        """
        Initialize Exotel Object
        """
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """
        Perform Exotel Notification
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """
        Returns the URL built dynamically based on specified arguments.
        """
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object.

        """
