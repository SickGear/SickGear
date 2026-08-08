from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

CHIME_HTTP_ERROR_MAP: Incomplete
CHIME_WEBHOOK_URL: str
IS_WEBHOOK_ID: Incomplete

class NotifyChime(NotifyBase):
    """A wrapper for Amazon Chime Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url = CHIME_WEBHOOK_URL
    notify_format: Incomplete
    title_maxlen: int
    body_maxlen: int
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    webhook_id: Incomplete
    token: Incomplete
    def __init__(self, webhook_id, token, **kwargs) -> None:
        """Initialize Amazon Chime Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Amazon Chime Notification."""
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
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """Support native Amazon Chime webhook URLs.

        For example:
          https://hooks.chime.aws/incomingwebhooks/
              xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx?token=AaBbCcDd%3D%3D
        """
