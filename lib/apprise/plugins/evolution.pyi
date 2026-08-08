from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyEvolution(NotifyBase):
    """A wrapper for Evolution API (WhatsApp) Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: int
    notify_format: Incomplete
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    instance: Incomplete
    phone: Incomplete
    invalid_targets: Incomplete
    def __init__(self, apikey, instance, targets=None, **kwargs) -> None:
        """Initialize Evolution API Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Evolution API Notification."""
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
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
