from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

PUSHPLUS_RESPONSE_CODES: Incomplete
PUSHPLUS_FORMAT_MAP: Incomplete
PUSHPLUS_FORMAT_DEFAULT: str

class PushPlusChannel:
    """Defines the PushPlus delivery channels.

    The channel controls where the rendered notification is delivered.
    It is supplied as the channel= (or mode=) query parameter in the
    Apprise URL, e.g. pushplus://{token}?channel=mail.
    """
    WECHAT: str
    WEBHOOK: str
    WECOM: str
    MAIL: str
    SMS: str

PUSHPLUS_CHANNELS: Incomplete
PUSHPLUS_CHANNEL_DEFAULT: Incomplete
IS_TOPIC: Incomplete
PUSHPLUS_SCHEMA_MAP: Incomplete

class NotifyPushplus(NotifyBase):
    """A wrapper for PushPlus Notifications."""
    service_name: Incomplete
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    channel: Incomplete
    topics: Incomplete
    invalid_targets: Incomplete
    webhook: Incomplete
    def __init__(self, token, targets=None, channel=None, webhook=None, **kwargs) -> None:
        """Initialize Pushplus Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform PushPlus Notification."""
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
    @staticmethod
    def parse_native_url(url):
        """Support native PushPlus API URLs of the form:
        https://www.pushplus.plus/send?token=TOKEN[&other_params]
        """
