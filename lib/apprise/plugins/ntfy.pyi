from ..attachment.base import AttachBase as AttachBase
from ..attachment.memory import AttachMemory as AttachMemory
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_hostname as is_hostname, is_ipaddr as is_ipaddr, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class NtfyMode:
    CLOUD: str
    PRIVATE: str

NTFY_MODES: Incomplete
NTFY_AUTH_DETECT_RE: Incomplete

class NtfyAuth:
    BASIC: str
    TOKEN: str

NTFY_AUTH: Incomplete

class NtfyPriority:
    MAX: str
    HIGH: str
    NORMAL: str
    LOW: str
    MIN: str

NTFY_PRIORITIES: Incomplete
NTFY_PRIORITY_MAP: Incomplete

class NotifyNtfy(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    setup_url: str
    cloud_notify_url: str
    attachment_support: bool
    title_maxlen: int
    body_maxlen: int
    overflow_amalgamate_title: bool
    ntfy_json_upstream_size_limit: int
    image_size: Incomplete
    time_to_live: int
    __auto_cloud_host: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    mode: Incomplete
    include_image: Incomplete
    auth: Incomplete
    attach: Incomplete
    filename: Incomplete
    click: Incomplete
    delay: Incomplete
    email: Incomplete
    token: Incomplete
    priority: Incomplete
    __tags: Incomplete
    avatar_url: Incomplete
    topics: Incomplete
    def __init__(self, targets=None, attach=None, filename=None, click=None, delay=None, email=None, priority=None, tags=None, mode=None, include_image: bool = True, avatar_url=None, auth=None, token=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _send(self, topic, body=None, title=None, attach=None, image_url=None, **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @staticmethod
    def parse_native_url(url): ...
