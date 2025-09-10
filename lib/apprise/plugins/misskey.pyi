from ..common import NotifyType as NotifyType
from ..utils.parse import validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class MisskeyVisibility:
    PUBLIC: str
    HOME: str
    FOLLOWERS: str
    SPECIFIED: str

MISSKEY_VISIBILITIES: Incomplete

class NotifyMisskey(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    visibility: Incomplete
    schema: Incomplete
    api_url: Incomplete
    def __init__(self, token=None, visibility=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @staticmethod
    def parse_url(url): ...
