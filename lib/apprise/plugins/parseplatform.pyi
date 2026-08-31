from ..common import NotifyType as NotifyType
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

TARGET_LIST_DELIM: Incomplete

class ParsePlatformDevice:
    ALL: str
    IOS: str
    ANDROID: str

PARSE_PLATFORM_DEVICES: Incomplete

class NotifyParsePlatform(NotifyBase):
    """A wrapper for Parse Platform Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    fullpath: Incomplete
    application_id: Incomplete
    master_key: Incomplete
    devices: Incomplete
    device: Incomplete
    def __init__(self, app_id, master_key, device=None, **kwargs) -> None:
        """Initialize Parse Platform Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Parse Platform Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to
        substantiate this object."""
