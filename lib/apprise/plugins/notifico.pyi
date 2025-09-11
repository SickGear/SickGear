from ..common import NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotificoFormat:
    Reset: str
    Bold: str
    Italic: str
    Underline: str
    BGSwap: str

class NotificoColor:
    Reset: str
    White: str
    Black: str
    Blue: str
    Green: str
    Red: str
    Brown: str
    Purple: str
    Orange: str
    Yellow: Incomplete
    LightGreen: str
    Teal: str
    LightCyan: str
    LightBlue: str
    Violet: str
    Grey: str
    LightGrey: str

class NotifyNotifico(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    project_id: Incomplete
    msghook: Incomplete
    prefix: Incomplete
    color: Incomplete
    api_url: Incomplete
    def __init__(self, project_id, msghook, color: bool = True, prefix: bool = True, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
