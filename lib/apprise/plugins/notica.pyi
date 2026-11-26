from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NoticaMode:
    """Tracks if we're accessing the notica upstream server or a locally hosted
    one."""
    SELFHOSTED: str
    OFFICIAL: str

NOTICA_MODES: Incomplete

class NotifyNotica(NotifyBase):
    """A wrapper for Notica Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    mode: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, token, headers=None, **kwargs) -> None:
        """Initialize Notica Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Notica Notification."""
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
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Support https://notica.us/?abc123
        """
