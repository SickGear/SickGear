from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class FORMPayloadField:
    VERSION: str
    TITLE: str
    MESSAGE: str
    MESSAGETYPE: str

METHODS: Incomplete

class NotifyForm(NotifyBase):
    __attach_as_re: Incomplete
    attach_as_count: str
    attach_as_default: Incomplete
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    request_rate_per_sec: int
    form_version: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    fullpath: Incomplete
    method: Incomplete
    attach_as: Incomplete
    attach_multi_support: bool
    payload_map: Incomplete
    params: Incomplete
    headers: Incomplete
    payload_overrides: Incomplete
    payload_extras: Incomplete
    def __init__(self, headers=None, method=None, payload=None, params=None, attach_as=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
