from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_MQTT_SUPPORT_ENABLED: bool
MQTT_PROTOCOL_MAP: Incomplete
HUMAN_MQTT_PROTOCOL_MAP: Incomplete

class NotifyMQTT(NotifyBase):
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
    def __init__(self, targets=None, version=None, qos=None, client_id=None, session=None, retain=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @property
    def CA_CERTIFICATE_FILE_LOCATIONS(self): ...
