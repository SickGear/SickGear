from ...apprise_attachment import AppriseAttachment as AppriseAttachment
from ...common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ...utils.logic import dict_full_update as dict_full_update
from ...utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..base import NotifyBase as NotifyBase
from .color import FCMColorManager as FCMColorManager
from .common import FCMMode as FCMMode, FCM_MODES as FCM_MODES
from .oauth import GoogleOAuth as GoogleOAuth
from .priority import FCMPriorityManager as FCMPriorityManager, FCM_PRIORITIES as FCM_PRIORITIES
from _typeshed import Incomplete

NOTIFY_FCM_SUPPORT_ENABLED: bool

class GoogleOAuth: ...

FCM_HTTP_ERROR_MAP: Incomplete

class NotifyFCM(NotifyBase):
    enabled = NOTIFY_FCM_SUPPORT_ENABLED
    requirements: Incomplete
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_oauth2_url: str
    notify_legacy_url: str
    max_fcm_keyfile_size: int
    image_size: Incomplete
    body_maxlen: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    mode: Incomplete
    apikey: Incomplete
    keyfile: Incomplete
    project: Incomplete
    oauth: Incomplete
    targets: Incomplete
    data_kwargs: Incomplete
    include_image: Incomplete
    image_src: Incomplete
    priority: Incomplete
    color: Incomplete
    def __init__(self, project, apikey, targets=None, mode=None, keyfile=None, data_kwargs=None, image_url=None, include_image: bool = False, color=None, priority=None, **kwargs) -> None: ...
    @property
    def access_token(self): ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
