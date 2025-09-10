from .. import exception as exception
from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class JSONPayloadField:
    VERSION: str
    TITLE: str
    MESSAGE: str
    ATTACHMENTS: str
    MESSAGETYPE: str

METHODS: Incomplete

class NotifyJSON(NotifyBase):
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    request_rate_per_sec: int
    json_version: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    fullpath: Incomplete
    method: Incomplete
    params: Incomplete
    headers: Incomplete
    payload_extras: Incomplete
    def __init__(self, headers=None, method=None, payload=None, params=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
