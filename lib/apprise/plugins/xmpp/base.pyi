from ...common import NotifyType as NotifyType
from ...url import PrivacyMode as PrivacyMode
from ...utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..base import NotifyBase as NotifyBase
from .adapter import SLIXMPP_SUPPORT_AVAILABLE as SLIXMPP_SUPPORT_AVAILABLE, SlixmppAdapter as SlixmppAdapter, XMPPChannelBindingError as XMPPChannelBindingError, XMPPConfig as XMPPConfig
from .common import SECURE_MODES as SECURE_MODES, SecureXMPPMode as SecureXMPPMode
from _typeshed import Incomplete
from typing import Any

IS_JID: Incomplete

class NotifyXMPP(NotifyBase):
    """Send notifications via XMPP using Slixmpp."""
    enabled: Incomplete
    requirements: Incomplete
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    xmpp_host: Incomplete
    targets: list[str, str]
    want_muc: bool
    secure_mode: Incomplete
    roster: Incomplete
    subject: Incomplete
    keepalive: Incomplete
    scramplus: Incomplete
    secure: bool
    name: Incomplete
    _adapter: SlixmppAdapter | None
    def __init__(self, targets: list[str, str] | None = None, secure_mode: str | None = None, roster: bool | None = None, subject: bool | None = None, keepalive: bool | None = None, name: str | None = None, xmpp_host: str | None = None, scramplus: bool | None = None, **kwargs: Any) -> None: ...
    def __del__(self) -> None:
        """Best-effort close for keepalive sessions."""
    @property
    def url_identifier(self) -> tuple[str, str, str, str, int | None]:
        """Return the pieces that uniquely identify this configuration."""
    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        """Return the URL representation of this notification."""
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., **kwargs: Any) -> bool:
        """Send a notification to one or more XMPP targets."""
    @property
    def title_maxlen(self) -> int | None:
        """
        Depending on if the subject field is set, we can control
        how the message is constructed.
        """
    @staticmethod
    def normalize_jid(value: str, default_host: str) -> tuple[str, bool]:
        """Normalize and validate a JID.

        Behaviour:
        - If value is 'user' then it becomes 'user@default_host'.
        - If value is 'user@host' then it becomes 'user@host'.
        - If value is 'user@host/resource' then it becomes
           'user@host/resource'.
        - If value is 'user/resource' then it becomes
           'user@default_host/resource'.
        - If value already contains '@', it is used as-is, including an
           optional '/resource' suffix.
        """
    @staticmethod
    def parse_url(url: str) -> dict[str, Any] | None:
        """Parse an XMPP URL into constructor arguments."""
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
