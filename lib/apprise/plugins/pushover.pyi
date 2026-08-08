from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..conversion import convert_between as convert_between
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

PUSHOVER_E2EE_SUPPORT: bool
PUSHOVER_SEND_TO_ALL: str
VALIDATE_DEVICE: Incomplete
VALIDATE_GROUP: Incomplete

class PushoverPriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

class PushoverSound:
    PUSHOVER: str
    BIKE: str
    BUGLE: str
    CASHREGISTER: str
    CLASSICAL: str
    COSMIC: str
    FALLING: str
    GAMELAN: str
    INCOMING: str
    INTERMISSION: str
    MAGIC: str
    MECHANICAL: str
    PIANOBAR: str
    SIREN: str
    SPACEALARM: str
    TUGBOAT: str
    ALIEN: str
    CLIMB: str
    PERSISTENT: str
    ECHO: str
    UPDOWN: str
    NONE: str

PUSHOVER_SOUNDS: Incomplete
PUSHOVER_PRIORITIES: Incomplete
PUSHOVER_PRIORITY_MAP: Incomplete
PUSHOVER_HTTP_ERROR_MAP: Incomplete
VALIDATE_ENCRYPTION_KEY: Incomplete

class NotifyPushover(NotifyBase):
    """A wrapper for Pushover Notifications."""
    service_name: str
    requirements: Incomplete
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    attachment_support: bool
    body_maxlen: int
    default_pushover_sound: Incomplete
    attach_max_size_bytes: int
    attach_supported_mime_type: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    user_key: Incomplete
    invalid_targets: Incomplete
    devices: Incomplete
    groups: Incomplete
    supplemental_url: Incomplete
    supplemental_url_title: Incomplete
    sound: Incomplete
    priority: Incomplete
    interval: Incomplete
    expire: Incomplete
    encryption_key: Incomplete
    e2ee: Incomplete
    def __init__(self, user_key, token, targets=None, priority=None, sound=None, interval=None, expire=None, supplemental_url=None, supplemental_url_title=None, encryption_key=None, e2ee=None, **kwargs) -> None:
        """Initialize Pushover Object."""
    def _encrypt_field(self, plaintext, key_bytes):
        """Encrypt a single Pushover message field for E2EE.

        Implements the field-level encryption scheme from
        https://pushover.net/api#e2ee -- per field:

        1. gzip-compress the plaintext string (UTF-8)
        2. AES-256-CBC-encrypt the compressed data (random 16-byte IV,
           PKCS7 padding) using the caller-supplied 256-bit key
        3. Compute HMAC-SHA256 over (IV || ciphertext) with the same key
        4. Return base64(IV || ciphertext || HMAC)

        Raises on any crypto error; the caller must not silently fall
        back to sending plaintext when encryption fails.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Pushover Notification."""
    def _send(self, payload, attach=None):
        """Wrapper to the requests (post) object."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def __len__(self) -> int:
        """Returns the number of HTTP requests this instance will make.

        Devices are batched into a single call; each group requires its own.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def runtime_deps():
        """Return optional runtime dependency package names.

        E2EE support requires the ``cryptography`` package.
        """
