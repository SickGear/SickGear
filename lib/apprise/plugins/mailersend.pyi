from .. import exception as exception
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..conversion import convert_between as convert_between
from ..utils.parse import is_email as is_email, parse_list as parse_list, validate_regex as validate_regex
from ..utils.sanitize import sanitize_payload as sanitize_payload
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

MAILERSEND_HTTP_ERROR_MAP: Incomplete

class NotifyMailerSend(NotifyBase):
    """A wrapper for MailerSend Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    notify_format: Incomplete
    attachment_support: bool
    request_rate_per_sec: float
    default_empty_subject: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    from_email: Incomplete
    reply_to: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    def __init__(self, apikey, from_email, targets=None, reply_to=None, cc=None, bcc=None, **kwargs) -> None:
        """Initialize MailerSend Object."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified
        arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this
        notification."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform MailerSend Notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
