from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

FLOCK_HTTP_ERROR_MAP: Incomplete
IS_CHANNEL_RE: Incomplete
IS_USER_RE: Incomplete

class NotifyFlock(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    notify_api: str
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    targets: Incomplete
    token: Incomplete
    include_image: Incomplete
    def __init__(self, token, targets=None, include_image: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _post(self, url, headers, payload): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
