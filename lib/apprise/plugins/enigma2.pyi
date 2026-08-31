from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class Enigma2MessageType:
    INFO: int
    WARNING: int
    ERROR: int

MESSAGE_MAPPING: Incomplete

class NotifyEnigma2(NotifyBase):
    """A wrapper for Enigma2 Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    timeout: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, timeout=None, headers=None, **kwargs) -> None:
        """Initialize Enigma2 Object.

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Enigma2 Notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
