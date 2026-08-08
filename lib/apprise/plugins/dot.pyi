from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool
from ..utils.sanitize import sanitize_payload as sanitize_payload
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

DOT_DITHER_TYPES: Incomplete
DOT_DITHER_KERNELS: Incomplete
DOT_MODES: Incomplete

class NotifyDot(NotifyBase):
    """A wrapper for Dot. Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    image_size: Incomplete
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    apikey: Incomplete
    device_id: Incomplete
    refresh_now: Incomplete
    mode: Incomplete
    signature: Incomplete
    icon: Incomplete
    image_data: Incomplete
    link: Incomplete
    border: Incomplete
    dither_type: Incomplete
    dither_kernel: Incomplete
    task_key: Incomplete
    text_api_url: Incomplete
    image_api_url: Incomplete
    def __init__(self, apikey=None, device_id=None, mode=..., refresh_now=None, signature=None, icon=None, link=None, border=None, dither_type=None, dither_kernel=None, image_data=None, task_key=None, **kwargs) -> None:
        """Initialize Notify Dot Object."""
    def _post(self, api_url, payload, headers):
        """POST payload to api_url; return True on success, False otherwise."""
    def _send_text(self, body, title, icon_data, headers):
        """Send body/title via the Text API."""
    def _send_image(self, image_data, headers):
        """Send image_data via the Image API."""
    def _resolve_attachment(self, attach, warn_label):
        """Return base64 string from the first usable attachment, or None."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Dot Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
