from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NotifyWorkflows(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    notify_format: Incomplete
    max_workflows_template_size: int
    adaptive_card_version: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    workflow: Incomplete
    signature: Incomplete
    include_image: Incomplete
    wrap: Incomplete
    template: Incomplete
    api_version: Incomplete
    tokens: Incomplete
    def __init__(self, workflow, signature, include_image=None, version=None, template=None, tokens=None, wrap=None, **kwargs) -> None: ...
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
