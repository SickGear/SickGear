from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotificoMode:
    OFFICIAL: str
    SELFHOSTED: str

NOTIFICO_MODES: Incomplete

class NotificoFormat:
    Reset: str
    Bold: str
    Italic: str
    Underline: str
    BGSwap: str

class NotificoColor:
    Reset: str
    White: str
    Black: str
    Blue: str
    Green: str
    Red: str
    Brown: str
    Purple: str
    Orange: str
    Yellow: Incomplete
    LightGreen: str
    Teal: str
    LightCyan: str
    LightBlue: str
    Violet: str
    Grey: str
    LightGrey: str

class NotifyNotifico(NotifyBase):
    """A wrapper for Notifico Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    project_id: Incomplete
    msghook: Incomplete
    mode: Incomplete
    prefix: Incomplete
    color: Incomplete
    def __init__(self, project_id, msghook, color: bool = True, prefix: bool = True, **kwargs) -> None:
        """Initialize Notifico Object."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Notifico Notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Support https://n.tkte.ch/h/PROJ_ID/MESSAGE_HOOK/
        """
