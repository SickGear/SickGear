from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from typing import Any

IS_CHANNEL: Incomplete
IS_CHANNEL_ID: Incomplete

class MattermostMode:
    """Supported Mattermost integration modes."""
    WEBHOOK: str
    BOT: str

MATTERMOST_MODES: Incomplete

class NotifyMattermost(NotifyBase):
    """A wrapper for Mattermost Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    title_maxlen: int
    attachment_support: bool
    storage_mode: Incomplete
    default_cache_expiry_sec: Incomplete
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: Incomplete
    fullpath: Incomplete
    mode: Incomplete
    token: Incomplete
    _invalid_targets: Incomplete
    targets: Incomplete
    include_image: Incomplete
    icon_url: Incomplete
    def __init__(self, token: str, fullpath: str | None = None, targets: list[str] | str | None = None, include_image: bool = False, icon_url: str | None = None, mode: str | None = None, **kwargs: Any) -> None:
        """Initialize Mattermost object."""
    def __len__(self) -> int:
        """Returns the number of outbound HTTP requests expected."""
    def _channel_lookup(self, channel: str) -> str | None:
        """
        Resolve a channel name to a channel_id.

        Resolution occurs only during send(); results are persistently cached.
        """
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., attach=None, **kwargs: Any) -> bool:
        """Perform Mattermost Notification."""
    @property
    def url_identifier(self) -> tuple[Any, ...]:
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url: str):
        """Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object."""
    @staticmethod
    def parse_native_url(url: str) -> dict[str, Any] | None:
        """
        Support parsing the webhook straight from URL
            https://HOST:443/workflows/WORKFLOWID/triggers/manual/paths/invoke
            https://mattermost.HOST/hooks/TOKEN
        """
