from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_phone_no as parse_phone_no, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class RingCentralAuthMode:
    """Authentication modes supported by RingCentral."""
    BASIC: str
    JWT: str

RINGCENTRAL_AUTH_MODES: Incomplete

class RingCentralEnvironment:
    """RingCentral API environment targets."""
    PRODUCTION: str
    SANDBOX: str

RINGCENTRAL_ENVIRONMENTS: Incomplete
RINGCENTRAL_ENV_URL_SUFFIX: Incomplete

class NotifyRingCentral(NotifyBase):
    """A wrapper for RingCentral Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    notify_url_sms: str
    notify_url_mms: str
    access_token_url: str
    revoke_token_url: str
    access_token_ttl: int
    refresh_token_ttl: int
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    _access_token: Incomplete
    _expire_time: float
    _scope: Incomplete
    _owner: Incomplete
    _endpoint_id: Incomplete
    mode: Incomplete
    client_id: Incomplete
    client_secret: Incomplete
    token: Incomplete
    source: Incomplete
    environment: Incomplete
    targets: Incomplete
    def __init__(self, source, targets=None, environment=None, token=None, client_id=None, client_secret=None, mode=None, **kwargs) -> None:
        """Initialize RingCentral Object."""
    def login(self):
        """Authenticate with the RingCentral OAuth token endpoint."""
    def logout(self) -> None:
        """Revoke the current access token."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform RingCentral Notification."""
    def _send(self, url, payload, headers, name: str = 'notification', throttle: bool = True, files=None):
        """POST helper shared by login, logout, and send calls."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    def __del__(self) -> None:
        """Destructor -- revoke the auth token on cleanup."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
