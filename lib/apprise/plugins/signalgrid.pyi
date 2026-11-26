from ..common import NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from typing import Any

SIGNALGRID_TYPE_MAP: Incomplete

class NotifySignalgrid(NotifyBase):
    """A wrapper for Signalgrid Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    attachment_support: bool
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    client_key: Incomplete
    targets: Incomplete
    critical: Incomplete
    def __init__(self, client_key: str | None = None, targets: list[str] | None = None, critical: bool = False, **kwargs: Any) -> None:
        """Initialize Signalgrid Object."""
    def __len__(self) -> int:
        """Returns the number of channels associated with this
        notification."""
    def send(self, body: str, title: str = '', notify_type: str = ..., attach: Any | None = None, **kwargs: Any) -> bool:
        """Perform Signalgrid Notification."""
    def _send_to_channel(self, body: str, title: str, notify_type: str, channel: str) -> bool:
        """Post a single notification to one Signalgrid channel."""
    @property
    def url_identifier(self) -> tuple[Any, ...]:
        """Return identifiers unique to this Signalgrid configuration.

        Channels are delivery destinations, not connection identity, so
        they're intentionally left out here.
        """
    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        """Return the Signalgrid Apprise URL."""
    @staticmethod
    def parse_url(url: str) -> dict[str, Any] | None:
        """Parse Signalgrid URL."""
