from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyNextcloud(NotifyBase):
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
    template_kwargs: Incomplete
    targets: Incomplete
    version: Incomplete
    url_prefix: Incomplete
    headers: Incomplete
    def __init__(self, targets=None, version=None, headers=None, url_prefix=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
