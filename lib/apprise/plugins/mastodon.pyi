from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_USER: Incomplete
USER_DETECTION_RE: Incomplete

class MastodonMessageVisibility:
    DEFAULT: str
    DIRECT: str
    PRIVATE: str
    UNLISTED: str
    PUBLIC: str

MASTODON_MESSAGE_VISIBILITIES: Incomplete

class NotifyMastodon(NotifyBase):
    service_name: str
    service_url: str
    protocol: Incomplete
    secure_protocol: Incomplete
    setup_url: str
    attachment_support: bool
    image_size: Incomplete
    __toot_non_gif_images_batch: int
    mastodon_whoami: str
    mastodon_media: str
    mastodon_toot: str
    mastodon_dm: str
    title_maxlen: int
    body_maxlen: int
    notify_format: Incomplete
    request_rate_per_sec: int
    ratelimit_reset: Incomplete
    ratelimit_remaining: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    schema: Incomplete
    _whoami_cache: Incomplete
    token: Incomplete
    visibility: Incomplete
    api_url: Incomplete
    cache: Incomplete
    batch: Incomplete
    sensitive: Incomplete
    spoiler: Incomplete
    idempotency_key: Incomplete
    language: Incomplete
    targets: Incomplete
    def __init__(self, token=None, targets=None, batch: bool = True, sensitive=None, spoiler=None, visibility=None, cache: bool = True, key=None, language=None, **kwargs) -> None: ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def _whoami(self, lazy: bool = True): ...
    def _request(self, path, payload=None, method: str = 'POST'): ...
    @staticmethod
    def parse_url(url): ...
