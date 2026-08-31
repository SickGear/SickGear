from .. import exception as exception
from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS
from ..utils.sanitize import sanitize_payload as sanitize_payload
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class JSONPayloadField:
    """Identifies the fields available in the JSON Payload."""
    VERSION: str
    TITLE: str
    MESSAGE: str
    ATTACHMENTS: str
    MESSAGETYPE: str

METHODS: Incomplete

class NotifyJSON(NotifyBase):
    """A wrapper for JSON Notifications."""
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    request_rate_per_sec: int
    json_version: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    fullpath: Incomplete
    method: Incomplete
    params: Incomplete
    headers: Incomplete
    payload_extras: Incomplete
    def __init__(self, headers=None, method=None, payload=None, params=None, **kwargs) -> None:
        """Initialize JSON Object.

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform JSON Notification."""
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
