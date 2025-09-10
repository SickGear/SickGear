from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyMSTeams(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url_v1: str
    notify_url_v2: str
    notify_url_v3: str
    image_size: Incomplete
    body_maxlen: int
    notify_format: Incomplete
    max_msteams_template_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    version: Incomplete
    team: Incomplete
    token_a: Incomplete
    token_b: Incomplete
    token_c: Incomplete
    token_d: Incomplete
    include_image: Incomplete
    template: Incomplete
    tokens: Incomplete
    def __init__(self, token_a, token_b, token_c, token_d=None, team=None, version=None, include_image: bool = True, template=None, tokens=None, **kwargs) -> None: ...
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
