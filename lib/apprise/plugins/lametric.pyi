from ..common import NotifyType as NotifyType
from ..utils.parse import is_hostname as is_hostname, is_ipaddr as is_ipaddr, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

LAMETRIC_APP_ID_DETECTOR_RE: Incomplete
LAMETRIC_IS_APP_TOKEN: Incomplete

class LametricMode:
    CLOUD: str
    DEVICE: str

LAMETRIC_MODES: Incomplete

class LametricPriority:
    INFO: str
    WARNING: str
    CRITICAL: str

LAMETRIC_PRIORITIES: Incomplete

class LametricIconType:
    INFO: str
    ALERT: str
    NONE: str

LAMETRIC_ICON_TYPES: Incomplete

class LametricSoundCategory:
    NOTIFICATIONS: str
    ALARMS: str

class LametricSound:
    ALARM01: Incomplete
    ALARM02: Incomplete
    ALARM03: Incomplete
    ALARM04: Incomplete
    ALARM05: Incomplete
    ALARM06: Incomplete
    ALARM07: Incomplete
    ALARM08: Incomplete
    ALARM09: Incomplete
    ALARM10: Incomplete
    ALARM11: Incomplete
    ALARM12: Incomplete
    ALARM13: Incomplete
    BICYCLE: Incomplete
    CAR: Incomplete
    CASH: Incomplete
    CAT: Incomplete
    DOG01: Incomplete
    DOG02: Incomplete
    ENERGY: Incomplete
    KNOCK: Incomplete
    EMAIL: Incomplete
    LOSE01: Incomplete
    LOSE02: Incomplete
    NEGATIVE01: Incomplete
    NEGATIVE02: Incomplete
    NEGATIVE03: Incomplete
    NEGATIVE04: Incomplete
    NEGATIVE05: Incomplete
    NOTIFICATION01: Incomplete
    NOTIFICATION02: Incomplete
    NOTIFICATION03: Incomplete
    NOTIFICATION04: Incomplete
    OPEN_DOOR: Incomplete
    POSITIVE01: Incomplete
    POSITIVE02: Incomplete
    POSITIVE03: Incomplete
    POSITIVE04: Incomplete
    POSITIVE05: Incomplete
    POSITIVE06: Incomplete
    STATISTIC: Incomplete
    THUNDER: Incomplete
    WATER01: Incomplete
    WATER02: Incomplete
    WIN01: Incomplete
    WIN02: Incomplete
    WIND: Incomplete
    WIND_SHORT: Incomplete

LAMETRIC_SOUNDS: Incomplete

class NotifyLametric(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    request_rate_per_sec: float
    setup_url: str
    title_maxlen: int
    cloud_notify_url: str
    device_notify_url: str
    default_device_user: str
    lametric_icon_id_mapping: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    mode: Incomplete
    lametric_app_id: Incomplete
    lametric_app_ver: Incomplete
    lametric_app_access_token: Incomplete
    lametric_apikey: Incomplete
    priority: Incomplete
    icon: Incomplete
    icon_type: Incomplete
    cycles: Incomplete
    sound: Incomplete
    def __init__(self, apikey=None, app_token=None, app_id=None, app_ver=None, priority=None, icon=None, icon_type=None, sound=None, mode=None, cycles=None, **kwargs) -> None: ...
    @staticmethod
    def sound_lookup(lookup): ...
    def _cloud_notification_payload(self, body, notify_type, headers): ...
    user: Incomplete
    def _device_notification_payload(self, body, notify_type, headers): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
