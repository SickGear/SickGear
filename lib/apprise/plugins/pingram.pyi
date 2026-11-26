from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..conversion import convert_between as convert_between
from ..utils.parse import is_email as is_email, is_phone_no as is_phone_no, parse_emails as parse_emails, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from collections.abc import Generator

IS_VALID_ID_RE: Incomplete

class PingramRegion:
    """Regions."""
    CA: str
    US: str
    EU: str

PINGRAM_API_LOOKUP: Incomplete
PINGRAM_REGIONS: Incomplete

class PingramChannel:
    """Channels."""
    EMAIL: str
    SMS: str
    INAPP: str
    WEB_PUSH: str
    MOBILE_PUSH: str
    SLACK: str
    CALL: str

PINGRAM_CHANNELS: frozenset[str]

class PingramMode:
    """Modes."""
    TEMPLATE: str
    MESSAGE: str

PINGRAM_MODES: frozenset[str]

class NotifyPingram(NotifyBase):
    """A wrapper for Pingram Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    default_message_type: str
    request_rate_per_sec: float
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    names: Incomplete
    from_addr: Incomplete
    reply_to: Incomplete
    mode: Incomplete
    message_type: Incomplete
    cc: Incomplete
    bcc: Incomplete
    region: Incomplete
    channels: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    tokens: Incomplete
    def __init__(self, apikey=None, message_type=None, targets=None, cc=None, bcc=None, reply_to=None, channels=None, region=None, mode=None, from_addr=None, tokens=None, **kwargs) -> None:
        """Initialize Notify Pingram Object."""
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
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs) -> Generator[Incomplete]:
        """Generates our Pingram payload."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Pingram Notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us
        to re-instantiate this object."""
