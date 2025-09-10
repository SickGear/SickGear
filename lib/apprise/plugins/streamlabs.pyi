from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class StrmlabsCall:
    ALERT: str
    DONATION: str

STRMLABS_CALLS: Incomplete

class StrmlabsAlert:
    FOLLOW: str
    SUBSCRIPTION: str
    DONATION: str
    HOST: str

STRMLABS_ALERTS: Incomplete

class NotifyStreamlabs(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    access_token: Incomplete
    call: Incomplete
    alert_type: Incomplete
    image_href: Incomplete
    sound_href: Incomplete
    duration: Incomplete
    special_text_color: Incomplete
    amount: Incomplete
    currency: Incomplete
    name: Incomplete
    identifier: Incomplete
    def __init__(self, access_token, call=..., alert_type=..., image_href: str = '', sound_href: str = '', duration: int = 1000, special_text_color: str = '', amount: int = 0, currency: str = 'USD', name: str = 'Anon', identifier: str = 'Apprise', **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
