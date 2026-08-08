from ..common import NotifyType as NotifyType
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_GROUP_ID: Incomplete

class NotifyWhatsApp(NotifyBase):
    """A wrapper for WhatsApp Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    fb_graph_version: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    component_key_re: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    from_phone_id: Incomplete
    template: Incomplete
    language: Incomplete
    targets: Incomplete
    template_mapping: Incomplete
    components: Incomplete
    component_keys: Incomplete
    def __init__(self, token, from_phone_id, template=None, targets=None, language=None, template_mapping=None, **kwargs) -> None:
        """Initialize WhatsApp Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform WhatsApp Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
