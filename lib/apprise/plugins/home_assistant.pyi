from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyHomeAssistant(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    default_insecure_port: int
    setup_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    fullpath: Incomplete
    port: Incomplete
    accesstoken: Incomplete
    nid: Incomplete
    def __init__(self, accesstoken, nid=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
