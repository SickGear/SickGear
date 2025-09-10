from ..common import NotifyType as NotifyType
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyIFTTT(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    ifttt_default_key_prefix: str
    ifttt_default_title_key: str
    ifttt_default_body_key: str
    ifttt_default_type_key: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    webhook_id: Incomplete
    events: Incomplete
    add_tokens: Incomplete
    del_tokens: Incomplete
    def __init__(self, webhook_id, events, add_tokens=None, del_tokens=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
