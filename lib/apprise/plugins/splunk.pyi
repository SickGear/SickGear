from ..common import NOTIFY_TYPES as NOTIFY_TYPES, NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class SplunkAction:
    MAP: str
    INFO: str
    WARNING: str
    CRITICAL: str
    ACKNOWLEDGE: str
    RECOVERY: str
    RESOLVE: str

SPLUNK_ACTIONS: Incomplete

class SplunkMessageType:
    CRITICAL: str
    WARNING: str
    ACKNOWLEDGEMENT: str
    INFO: str
    RECOVERY: str

SPLUNK_MESSAGE_TYPES: Incomplete

class NotifySplunk(NotifyBase):
    service_name: Incomplete
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    notify_url: str
    templates: Incomplete
    title_maxlen: int
    body_maxlen: int
    splunk_message_map: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    routing_key: Incomplete
    entity_id: Incomplete
    action: Incomplete
    mapping: Incomplete
    def __init__(self, apikey, routing_key, entity_id=None, action=None, mapping=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
