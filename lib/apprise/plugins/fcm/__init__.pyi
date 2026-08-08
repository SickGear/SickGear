from ..base import NotifyBase as NotifyBase
from .color import FCMColorManager as FCMColorManager
from .common import FCMMode as FCMMode, FCM_MODES as FCM_MODES
from .oauth import GoogleOAuth as GoogleOAuth
from .priority import FCMPriorityManager as FCMPriorityManager, FCM_PRIORITIES as FCM_PRIORITIES
from _typeshed import Incomplete

NOTIFY_FCM_SUPPORT_ENABLED: bool

class GoogleOAuth: ...

FCM_HTTP_ERROR_MAP: Incomplete

class NotifyFCM(NotifyBase):
    """A wrapper for Google's Firebase Cloud Messaging Notifications."""
    enabled = NOTIFY_FCM_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_oauth2_url: str
    notify_legacy_url: str
    max_fcm_keyfile_size: int
    image_size: Incomplete
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    mode: Incomplete
    apikey: Incomplete
    keyfile: Incomplete
    project: Incomplete
    oauth: Incomplete
    targets: Incomplete
    data_kwargs: Incomplete
    include_image: Incomplete
    image_src: Incomplete
    priority: Incomplete
    color: Incomplete
    def __init__(self, project, apikey, targets=None, mode=None, keyfile=None, data_kwargs=None, image_url=None, include_image: bool = False, color=None, priority=None, **kwargs) -> None:
        """Initialize Firebase Cloud Messaging."""
    @property
    def access_token(self):
        """Generates a access_token based on the keyfile provided."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform FCM Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
