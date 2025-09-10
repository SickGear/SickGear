from .. import __version__ as __version__
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_call_sign as is_call_sign, parse_call_sign as parse_call_sign
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

APRS_LOCALES: Incomplete
APRS_BAD_CHARMAP: Incomplete
APRS_COMPILED_MAP: Incomplete

class NotifyAprs(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_port: int
    body_maxlen: int
    device_id: str
    title_maxlen: int
    request_rate_per_sec: float
    aprs_encoding: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    sock: Incomplete
    targets: Incomplete
    user: Incomplete
    delay: Incomplete
    locale: Incomplete
    invalid_targets: Incomplete
    def __init__(self, targets=None, locale=None, delay=None, **kwargs) -> None: ...
    def socket_close(self) -> None: ...
    def socket_open(self): ...
    def aprsis_login(self): ...
    def socket_send(self, tx_data): ...
    def socket_reset(self): ...
    def socket_receive(self, rx_len): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @property
    def url_identifier(self): ...
    def __len__(self) -> int: ...
    def __del__(self) -> None: ...
    @staticmethod
    def parse_url(url): ...
