from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_MQTT_SUPPORT_ENABLED: bool
MQTT_PROTOCOL_MAP: Incomplete
HUMAN_MQTT_PROTOCOL_MAP: Incomplete

class NotifyMQTT(NotifyBase):
    """A wrapper for MQTT Notifications."""
    enabled = NOTIFY_MQTT_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    request_rate_per_sec: float
    mqtt_insecure_port: int
    mqtt_secure_port: int
    mqtt_keepalive: int
    mqtt_transport: str
    mqtt_block_time_sec: float
    mqtt_inflight_messages: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    topics: Incomplete
    version: Incomplete
    client_id: Incomplete
    session: Incomplete
    retain: Incomplete
    qos: Incomplete
    port: Incomplete
    ca_certs: Incomplete
    mqtt_protocol: Incomplete
    client: Incomplete
    __initial_connect: bool
    def __init__(self, targets=None, version=None, qos=None, client_id=None, session=None, retain=None, **kwargs) -> None:
        """Initialize MQTT Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform MQTT Notification."""
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
        """There are no parameters nessisary for this protocol; simply having
        windows:// is all you need.

        This function just makes sure that is in place.
        """
    @property
    def CA_CERTIFICATE_FILE_LOCATIONS(self):
        """Return possible locations to root certificate authority (CA)
        bundles.

        Taken from https://golang.org/src/crypto/x509/root_linux.go
        TODO: Maybe refactor to a general utility function?
        """
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
