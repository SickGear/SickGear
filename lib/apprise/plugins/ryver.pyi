from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class RyverWebhookMode:
    SLACK: str
    RYVER: str

RYVER_WEBHOOK_MODES: Incomplete

class NotifyRyver(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    organization: Incomplete
    mode: Incomplete
    include_image: Incomplete
    _re_formatting_map: Incomplete
    _re_formatting_rules: Incomplete
    def __init__(self, organization, token, mode=..., include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
