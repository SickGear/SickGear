from ..common import NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_SESSIONOGS_ENABLED: bool
IS_PUBLIC_KEY: Incomplete
IS_ROOM_TOKEN: Incomplete
IS_SEED: Incomplete
SOGS_HTTP_ERROR_MAP: Incomplete

def _encode_varint(n):
    """Encode an integer as a protobuf-style base-128 varint."""
def _ld_field(field_num, data):
    """Encode a protobuf length-delimited field (wire type 2)."""
def _build_session_message(text):
    """Encode text as a Session protocol Content protobuf message.

    Builds: Content { dataMessage { body: text } }
    and appends a minimal Session padding marker byte (0x80).
    """

class NotifySessionOGS(NotifyBase):
    """A wrapper for Session Open Group Server (SOGS) Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: Incomplete
    setup_url: str
    notify_url: str
    title_maxlen: int
    body_maxlen: int
    enabled = NOTIFY_SESSIONOGS_ENABLED
    requirements: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    public_key: Incomplete
    seed: Incomplete
    _signing_key: Incomplete
    _bot_pubkey_bytes: Incomplete
    rooms: Incomplete
    invalid_rooms: Incomplete
    def __init__(self, public_key, seed, targets=None, **kwargs) -> None:
        """Initialize Session Open Group Server Object."""
    def _sogs_auth_headers(self, method, path, body_bytes=None):
        """
        Build the four X-SOGS-* authentication headers for a request.

        The signature covers:
            SERVER_KEY || NONCE || TIMESTAMP || METHOD || PATH [|| HBODY]
        where HBODY is the 64-byte blake2b hash of the request body when
        the body is non-empty.  The signing key is the bot's Ed25519 key.
        """
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Session Open Group Server Notification."""
    def _post(self, room, body_bytes):
        """POST a notification to a single SOGS room."""
    @property
    def url_identifier(self):
        """
        Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow us to
        re-instantiate this object.
        """
    @staticmethod
    def runtime_deps():
        """
        Return a tuple of top-level Python package names that this
        plugin imported as optional runtime dependencies.
        """
