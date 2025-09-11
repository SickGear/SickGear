from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..exception import AppriseException as AppriseException
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_hostname as is_hostname, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

MATRIX_V1_WEBHOOK_PATH: str
MATRIX_V2_API_PATH: str
MATRIX_V3_API_PATH: str
MATRIX_V3_MEDIA_PATH: str
MATRIX_V2_MEDIA_PATH: str

class MatrixDiscoveryException(AppriseException): ...

MATRIX_HTTP_ERROR_MAP: Incomplete
IS_ROOM_ALIAS: Incomplete
IS_ROOM_ID: Incomplete
IS_IMAGE: Incomplete

class MatrixMessageType:
    TEXT: str
    NOTICE: str

MATRIX_MESSAGE_TYPES: Incomplete

class MatrixVersion:
    V2: str
    V3: str

MATRIX_VERSIONS: Incomplete

class MatrixWebhookMode:
    DISABLED: str
    MATRIX: str
    SLACK: str
    T2BOT: str

MATRIX_WEBHOOK_MODES: Incomplete

class NotifyMatrix(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    attachment_support: bool
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    request_rate_per_sec: float
    default_retries: int
    default_wait_ms: int
    storage_mode: Incomplete
    default_cache_expiry_sec: Incomplete
    discovery_base_key: str
    discovery_identity_key: str
    discovery_cache_length_sec: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    rooms: Incomplete
    home_server: Incomplete
    user_id: Incomplete
    access_token: Incomplete
    transaction_id: int
    include_image: Incomplete
    discovery: Incomplete
    mode: Incomplete
    version: Incomplete
    msgtype: Incomplete
    def __init__(self, targets=None, mode=None, msgtype=None, version=None, include_image=None, discovery=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send_webhook_notification(self, body, title: str = '', notify_type=..., **kwargs): ...
    _re_slack_formatting_map: Incomplete
    _re_slack_formatting_rules: Incomplete
    def _slack_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _matrix_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _t2bot_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _send_server_notification(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send_attachments(self, attach): ...
    def _register(self): ...
    def _login(self): ...
    def _logout(self): ...
    def _room_join(self, room): ...
    def _room_create(self, room): ...
    def _joined_rooms(self): ...
    def _room_id(self, room): ...
    def _fetch(self, path, payload=None, params=None, attachment=None, method: str = 'POST', url_override=None): ...
    def __del__(self) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
    def server_discovery(self): ...
    @property
    def base_url(self): ...
    @property
    def identity_url(self): ...
