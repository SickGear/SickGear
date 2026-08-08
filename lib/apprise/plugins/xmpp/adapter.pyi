import asyncio
import slixmpp
import ssl
import threading
from .common import SECURE_MODES as SECURE_MODES, SecureXMPPMode as SecureXMPPMode
from _typeshed import Incomplete
from typing import Any, Callable

SLIXMPP_SUPPORT_AVAILABLE: bool
FuturesTimeoutError = Exception

class XMPPChannelBindingError(Exception):
    """SASL SCRAM-PLUS channel-binding authentication failure.

    Raised when the server rejects authentication because TLS
    channel-binding data (tls-unique or tls-exporter) was unavailable
    or mismatched.  Callers may retry with SCRAM-PLUS disabled.
    """

class XMPPConfig:
    """Connection configuration."""
    host: str
    port: int
    jid: str
    password: str
    secure: str
    verify_certificate: bool
    use_channel_binding: bool

LOGGING_ID: str
_LOG_BRIDGE_LOCK: Incomplete
_LOG_BRIDGED: bool

def bridge_slixmpp_logging() -> None:
    """Bridge Slixmpp logging into Apprise logging handlers.

    This is intentionally idempotent to prevent handler duplication when many
    notifications are sent within the same process.
    """
def _close_awaitable(obj: Any) -> None:
    """Best-effort close for coroutine-like objects.

    Some test patches raise before awaiting, leaving coroutines to be
    garbage collected and triggering runtime warnings.
    """

_CLIENT_SUBCLASS_CACHE: dict[int, type[Any]]

def _get_client_subclass(base_cls: type[Any]) -> type[Any]:
    """Return (and cache) the internal client subclass for a given base class.

    The tests monkeypatch `xmpp_adapter.slixmpp.ClientXMPP`, so we must resolve
    the base class dynamically at runtime, not at import time. We still cache
    the derived subclass per base class identity to avoid repeated class
    creation overhead in production.
    """
def _build_client(*args: Any, **kwargs: Any) -> Any: ...
def _disable_channel_binding(client: Any) -> None:
    """Patch the slixmpp feature_mechanisms plugin on *client* so that
    SASL mechanism selection never considers -PLUS (channel-binding)
    variants.

    Works by wrapping _send_auth() -- which is called after the server's
    mechanism list is stored in plugin.mech_list -- to strip every entry
    whose name ends with '-PLUS' before the SASL choose() call picks
    a mechanism.

    The whole operation is wrapped in contextlib.suppress so it degrades
    gracefully when the plugin is unavailable (e.g., in tests that use a
    fake ClientXMPP without plugin support).
    """

class SlixmppAdapter:
    """Send a message to one or more targets.

    When keepalive is False, process() performs a one-shot connect, send,
    disconnect.

    When keepalive is True, send_message() keeps a session alive across calls.
    The connection is closed only when close() is called or the instance is
    garbage collected.
    """
    _supported_version: Incomplete
    _enabled = SLIXMPP_SUPPORT_AVAILABLE
    timeout: Incomplete
    _want_muc: Incomplete
    logger: Incomplete
    nickname: Incomplete
    _state_lock: Incomplete
    _closing: bool
    _thread: threading.Thread | None
    _loop: asyncio.AbstractEventLoop | None
    _client: slixmpp.ClientXMPP | None
    _loop_ready: Incomplete
    _connect_lock: asyncio.Lock | None
    _session_started: asyncio.Event | None
    def __init__(self, config: XMPPConfig, targets: list[str, str], subject: str, body: str, timeout: float = 30.0, roster: bool = False, before_message: Callable[[], None] | None = None, keepalive: bool = False, want_muc: bool = False, default_nickname: str | None = None) -> None: ...
    def __del__(self) -> None:
        """Best effort close for keepalive sessions."""
    @staticmethod
    def _ssl_context(verify: bool) -> ssl.SSLContext: ...
    @staticmethod
    def _loop_tick(loop: asyncio.AbstractEventLoop) -> None:
        """Run one final loop tick, closing the coroutine on error."""
    @staticmethod
    def _finalize_loop(loop: asyncio.AbstractEventLoop) -> None:
        """Best-effort loop shutdown to avoid resource warnings."""
    def close(self) -> None:
        """Close any persistent connection and stop the keepalive worker."""
    def process(self) -> bool:
        """Send the message, always returning within timeout."""
    def _ensure_keepalive_worker(self) -> bool:
        """Ensure the background loop and client exist."""
    def _keepalive_runner(self) -> None: ...
    async def _connect_if_required(self) -> bool: ...
    async def _send_keepalive_async(self, targets: list[str, str], subject: str, body: str) -> bool: ...
    targets: Incomplete
    subject: Incomplete
    body: Incomplete
    def send_message(self, targets: list[str, str] | None = None, subject: str | None = None, body: str | None = None) -> bool:
        """Send a message, keeping the session alive if keepalive=True."""
    @staticmethod
    def package_dependency() -> str:
        """Defines our static dependency for this adapter to work."""
    @staticmethod
    def supported_version(version: str | None = None) -> bool:
        """Returns true if we currently have a version of Slixmpp supported.

        Provided string describes a version in format of major.minor.patch.
        """
