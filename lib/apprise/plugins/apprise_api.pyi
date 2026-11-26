from .. import exception as exception
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS, parse_list as parse_list, validate_regex as validate_regex
from ..utils.sanitize import sanitize_payload as sanitize_payload
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class AppriseAPIMethod:
    """Defines the method to post data tot he remote server."""
    JSON: str
    FORM: str

APPRISE_API_METHODS: Incomplete

class NotifyAppriseAPI(NotifyBase):
    """A wrapper for Apprise (Persistent) API Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    socket_read_timeout: float
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    method: Incomplete
    __tags: Incomplete
    headers: Incomplete
    def __init__(self, token=None, tags=None, method=None, headers=None, **kwargs) -> None:
        """Initialize Apprise API Object.

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Apprise API Notification."""
    @staticmethod
    def parse_native_url(url):
        """
        Support http://hostname/notify/token and
                http://hostname/path/notify/token
        """
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
