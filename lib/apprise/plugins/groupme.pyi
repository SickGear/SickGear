from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

GROUPME_BOT_URL: str
GROUPME_IMAGE_URL: str
GROUPME_HTTP_ERROR_MAP: Incomplete

class NotifyGroupMe(NotifyBase):
    """A wrapper for GroupMe Bot Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url = GROUPME_BOT_URL
    groupme_image_url = GROUPME_IMAGE_URL
    title_maxlen: int
    body_maxlen: int
    attachment_support: bool
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    bot_id: Incomplete
    token: Incomplete
    def __init__(self, bot_id, token=None, **kwargs) -> None:
        """Initialize GroupMe Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform GroupMe Bot Notification."""
    def _upload_image(self, attachment):
        """Upload an image attachment to GroupMe's image service.

        Returns the hosted image URL on success, or None on failure.
        """
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
