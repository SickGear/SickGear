from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_TOPIC: Incomplete
IS_REGION: Incomplete
AWS_HTTP_ERROR_MAP: Incomplete

class NotifySNS(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: float
    body_maxlen: int
    title_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    aws_access_key_id: Incomplete
    aws_secret_access_key: Incomplete
    aws_region_name: Incomplete
    topics: Incomplete
    phone: Incomplete
    notify_url: Incomplete
    aws_service_name: str
    aws_canonical_uri: str
    aws_auth_version: str
    aws_auth_algorithm: str
    aws_auth_request: str
    def __init__(self, access_key_id, secret_access_key, region_name, targets=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    def _post(self, payload, to): ...
    def aws_prepare_request(self, payload, reference=None): ...
    def aws_auth_signature(self, to_sign, reference): ...
    @staticmethod
    def aws_response_to_dict(aws_response): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
