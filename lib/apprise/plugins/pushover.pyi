from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..conversion import convert_between as convert_between
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

PUSHOVER_SEND_TO_ALL: str
VALIDATE_DEVICE: Incomplete

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

class NotifyPushover(NotifyBase):
    service_name: str
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
    targets: Incomplete
    supplemental_url: Incomplete
    supplemental_url_title: Incomplete
    sound: Incomplete
    priority: Incomplete
    retry: Incomplete
    expire: Incomplete
    def __init__(self, user_key, token, targets=None, priority=None, sound=None, retry=None, expire=None, supplemental_url=None, supplemental_url_title=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send(self, payload, attach=None): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
