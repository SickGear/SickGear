from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_domain_service_target as is_domain_service_target, parse_bool as parse_bool, parse_domain_service_targets as parse_domain_service_targets, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

RE_IS_LONG_LIVED_TOKEN: Incomplete
PERSISTENT_ENTRY: Incomplete

class NotifyHomeAssistant(NotifyBase):
    """
    A wrapper for Home Assistant Notifications
    """
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    default_insecure_port: int
    default_batch_size: int
    default_domain: str
    setup_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    fullpath: Incomplete
    prefix: Incomplete
    port: Incomplete
    accesstoken: Incomplete
    nid: Incomplete
    batch: Incomplete
    targets: Incomplete
    _invalid_targets: Incomplete
    def __init__(self, accesstoken, nid=None, targets=None, batch=None, prefix=None, **kwargs) -> None:
        """Initialize Home Assistant Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Sends Message."""
    def _ha_post(self, url, payload, headers, auth=None, persistent: bool = False):
        """
        Wrapper to single upstream server post
        """
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """
        Returns the number of targets associated with this notification
        """
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
