from .. import exception as exception
from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class AppriseAPIMethod:
    JSON: str
    FORM: str

APPRISE_API_METHODS: Incomplete

class NotifyAppriseAPI(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    socket_read_timeout: float
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    token: Incomplete
    method: Incomplete
    __tags: Incomplete
    headers: Incomplete
    def __init__(self, token=None, tags=None, method=None, headers=None, **kwargs) -> None: ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    @staticmethod
    def parse_native_url(url): ...
    @staticmethod
    def parse_url(url): ...
