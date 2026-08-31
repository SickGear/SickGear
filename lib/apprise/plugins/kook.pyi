from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

KOOK_HTTP_ERROR_MAP: Incomplete
KOOK_API_URL: str
KOOK_API_TYPE_TEXT: int
KOOK_API_TYPE_IMAGE: int
KOOK_API_TYPE_FILE: int
KOOK_API_TYPE_KMARKDOWN: int

class KookMode:
    """Tracks the mode of operation for the Kook plugin."""
    WEBHOOK: str
    BOT: str

KOOK_MODES: Incomplete
IS_TARGET_ID: Incomplete
KOOK_DM_PREFIX: str

class NotifyKook(NotifyBase):
    """A wrapper for Kook Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: Incomplete
    dm_url: Incomplete
    asset_url: Incomplete
    webhook_notify_url: Incomplete
    attachment_support: bool
    body_maxlen: int
    title_maxlen: int
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    mode: Incomplete
    channels: Incomplete
    dm_users: Incomplete
    _invalid_targets: Incomplete
    def __init__(self, token, targets=None, mode=None, **kwargs) -> None:
        """Initialize Kook Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Kook Notification."""
    def _send_webhook(self, body):
        """Post a notification via Kook incoming webhook."""
    def _send_bot(self, body, attach=None):
        """Post a notification via Kook Bot API to channels and DM users."""
    def _upload(self, attachment):
        """Upload a file to the Kook CDN and return the CDN URL.

        Returns None on any failure.
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """Support pasting full Kook incoming webhook URLs directly.

        Supports: https://www.kookapp.cn/api/v3/incoming/{key}
        """
