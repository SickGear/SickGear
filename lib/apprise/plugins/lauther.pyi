from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class LautherPriority:
    LOWEST: int
    LOW: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

LAUTHER_PRIORITIES: Incomplete
LAUTHER_PRIORITY_MAP: Incomplete

class NotifyLauther(NotifyBase):
    """A wrapper for Lauther Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    priority: Incomplete
    sound: Incomplete
    click: Incomplete
    icon: Incomplete
    color: Incomplete
    group: Incomplete
    route: Incomplete
    def __init__(self, token, priority=None, sound=None, click=None, icon=None, color=None, group=None, route=None, **kwargs) -> None:
        """Initialize Lauther Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform the Lauther Notification."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
