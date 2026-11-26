from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from typing import Any

class PingletPriority:
    SILENT: str
    NORMAL: str
    URGENT: str

PINGLET_PRIORITIES: Incomplete
PINGLET_PRIORITY_MAP: Incomplete
PINGLET_LEVEL_MAP: Incomplete

class NotifyPinglet(NotifyBase):
    """A wrapper for Pinglet Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: float
    body_maxlen: int
    max_badge_count: int
    max_badge_key_len: int
    max_badge_value_len: int
    max_data_key_len: int
    max_data_value_len: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    namespace: Incomplete
    topic: Incomplete
    fullpath: Incomplete
    priority: Incomplete
    badges: Incomplete
    data: Incomplete
    def __init__(self, token: str, namespace: str, topic: str, priority: str | None = None, badges: dict[str, Any] | None = None, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Initialize Pinglet Object."""
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., **kwargs: Any) -> bool:
        """Perform Pinglet Notification."""
    @property
    def url_identifier(self) -> tuple[Any, ...]:
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url: str) -> dict[str, Any] | None:
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
