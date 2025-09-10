from ..common import NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.base64 import decode_b64_dict as decode_b64_dict, encode_b64_dict as encode_b64_dict
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class OneSignalCategory:
    PLAYER: str
    EMAIL: str
    USER: str
    SEGMENT: str

ONESIGNAL_CATEGORIES: Incomplete

class NotifyOneSignal(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_url: str
    image_size: Incomplete
    default_batch_size: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    app: Incomplete
    batch_size: Incomplete
    use_contents: Incomplete
    decode_tpl_args: Incomplete
    include_image: Incomplete
    targets: Incomplete
    template_id: Incomplete
    subtitle: Incomplete
    language: Incomplete
    custom_data: Incomplete
    postback_data: Incomplete
    def __init__(self, app, apikey, targets=None, include_image: bool = True, template=None, subtitle=None, language=None, batch=None, use_contents=None, decode_tpl_args=None, custom=None, postback=None, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url): ...
