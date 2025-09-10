from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

TARGET_LIST_DELIM: Incomplete

class NotifyLine(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    notify_url: str
    setup_url: str
    title_maxlen: int
    body_maxlen: int
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    token: Incomplete
    include_image: Incomplete
    targets: Incomplete
    __cached_users: Incomplete
    def __init__(self, token, targets=None, include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
