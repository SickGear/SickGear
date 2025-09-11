from . import subscription as subscription
from ...common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ...utils.base64 import base64_urlencode as base64_urlencode
from ...utils.parse import is_email as is_email, parse_bool as parse_bool, parse_list as parse_list
from ..base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class VapidPushMode:
    CHROME: str
    FIREFOX: str
    EDGE: str
    OPERA: str
    APPLE: str
    SAMSUNG: str
    BRAVE: str
    GENERIC: str

VAPID_API_LOOKUP: Incomplete
VAPID_PUSH_MODES: Incomplete

class NotifyVapid(NotifyBase):
    enabled: Incomplete
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    max_vapid_keyfile_size: int
    max_vapid_subfile_size: int
    body_maxlen: int
    title_maxlen: int
    storage_mode: Incomplete
    vapid_jwt_expiration_sec: int
    vapid_subscription_file: str
    image_size: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    keyfile: Incomplete
    subfile: Incomplete
    targets: Incomplete
    _invalid_targets: Incomplete
    subscriptions: Incomplete
    subscriptions_loaded: bool
    private_key_loaded: bool
    ttl: Incomplete
    include_image: Incomplete
    subscriber: Incomplete
    mode: Incomplete
    pem: Incomplete
    def __init__(self, subscriber, mode=None, targets=None, keyfile=None, subfile=None, include_image=None, ttl=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
    @property
    def jwt_token(self): ...
    @property
    def public_key(self): ...
