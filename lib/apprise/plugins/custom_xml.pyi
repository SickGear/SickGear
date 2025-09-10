from .. import exception as exception
from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class XMLPayloadField:
    VERSION: str
    TITLE: str
    MESSAGE: str
    MESSAGETYPE: str

METHODS: Incomplete

class NotifyXML(NotifyBase):
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    request_rate_per_sec: int
    xsd_ver: str
    xsd_default_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    payload: str
    fullpath: Incomplete
    method: Incomplete
    payload_map: Incomplete
    params: Incomplete
    headers: Incomplete
    payload_overrides: Incomplete
    payload_extras: Incomplete
    xsd_url: Incomplete
    def __init__(self, headers=None, method=None, payload=None, params=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
