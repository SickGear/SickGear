from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

WEBEX_HTTP_ERROR_MAP: Incomplete

class WebexTeamsMode:
    """Tracks the mode of which we're using Webex Teams."""
    WEBHOOK: str
    BOT: str

WEBEX_TEAMS_MODES: Incomplete

class NotifyWebexTeams(NotifyBase):
    """A wrapper for Webex Teams Notifications."""
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    notify_url: str
    api_url: str
    attachment_support: bool
    title_maxlen: int
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    mode: Incomplete
    access_token: Incomplete
    targets: Incomplete
    token: Incomplete
    def __init__(self, token=None, access_token=None, targets=None, mode=None, **kwargs) -> None:
        """Initialize Webex Teams Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Webex Teams Notification."""
    def _send_webhook(self, body):
        """Post via incoming webhook (no attachment support)."""
    def _send_bot(self, body, attach=None):
        """Post via Bot/API to one or more rooms (supports attachments)."""
    def _post_to_room(self, body, room_id, attach=None):
        """Send a single message (and optional attachments) to a room."""
    @property
    def body_maxlen(self):
        """The maximum allowable characters allowed in the body per message.
        Webhook mode is limited to 1000 chars; the Bot API allows 7439."""
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
        """Parses the URL and returns enough arguments that can allow us
        to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Support:
          https://api.ciscospark.com/v1/webhooks/incoming/WEBHOOK_TOKEN
          https://webexapis.com/v1/webhooks/incoming/WEBHOOK_TOKEN
        """
