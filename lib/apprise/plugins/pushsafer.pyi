from .. import exception as exception
from ..common import NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class PushSaferSound:
    SILENT: int
    AHEM: int
    APPLAUSE: int
    ARROW: int
    BABY: int
    BELL: int
    BICYCLE: int
    BOING: int
    BUZZER: int
    CAMERA: int
    CAR_HORN: int
    CASH_REGISTER: int
    CHIME: int
    CREAKY_DOOR: int
    CUCKOO_CLOCK: int
    DISCONNECT: int
    DOG: int
    DOORBELL: int
    FANFARE: int
    GUN_SHOT: int
    HONK: int
    JAW_HARP: int
    MORSE: int
    ELECTRICITY: int
    RADIO_TURNER: int
    SIRENS: int
    MILITARY_TRUMPETS: int
    UFO: int
    LONG_WHAH: int
    GOODBYE: int
    HELLO: int
    NO: int
    OKAY: int
    OOOHHHWEEE: int
    WARNING: int
    WELCOME: int
    YEAH: int
    YES: int
    BEEP1: int
    WEEE: int
    CUTINOUT: int
    FLICK_GLASS: int
    SHORT_WHAH: int
    LASER: int
    WIND_CHIME: int
    ECHO: int
    ZIPPER: int
    HIHAT: int
    BEEP2: int
    BEEP3: int
    BEEP4: int
    ALARM_ARMED: int
    ALARM_DISARMED: int
    BACKUP_READY: int
    DOOR_CLOSED: int
    DOOR_OPENED: int
    WINDOW_CLOSED: int
    WINDOW_OPEN: int
    LIGHT_ON: int
    LIGHT_OFF: int
    DOORBELL_RANG: int

PUSHSAFER_SOUND_MAP: Incomplete

class PushSaferPriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

PUSHSAFER_PRIORITIES: Incomplete
PUSHSAFER_PRIORITY_MAP: Incomplete
DEFAULT_PRIORITY: str

class PushSaferVibration:
    LOW: int
    NORMAL: int
    HIGH: int

PUSHSAFER_VIBRATIONS: Incomplete
PICTURE_PARAMETER: Incomplete
PUSHSAFER_SEND_TO_ALL: str

class NotifyPushSafer(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    attachment_support: bool
    request_rate_per_sec: float
    default_pushsafer_icon: int
    setup_url: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    priority: Incomplete
    sound: Incomplete
    vibration: Incomplete
    privatekey: Incomplete
    targets: Incomplete
    def __init__(self, privatekey, targets=None, priority=None, sound=None, vibration=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send(self, payload, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
