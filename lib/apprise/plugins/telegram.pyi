from ..attachment.base import AttachBase as AttachBase
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..utils.parse import parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

TELEGRAM_IMAGE_XY: Incomplete
IS_CHAT_ID_RE: Incomplete

class TelegramMarkdownVersion:
    ONE: str
    TWO: str

TELEGRAM_MARKDOWN_VERSION_MAP: Incomplete
TELEGRAM_MARKDOWN_VERSIONS: Incomplete

class TelegramContentPlacement:
    BEFORE: str
    AFTER: str

TELEGRAM_CONTENT_PLACEMENT: Incomplete

class NotifyTelegram(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    notify_format: Incomplete
    notify_url: str
    attachment_support: bool
    image_size: Incomplete
    body_maxlen: int
    telegram_caption_maxlen: int
    title_maxlen: int
    request_rate_per_sec: float
    storage_mode: Incomplete
    templates: Incomplete
    mime_lookup: Incomplete
    __telegram_escape_html_entries: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    bot_token: Incomplete
    markdown_ver: Incomplete
    silent: Incomplete
    preview: Incomplete
    content: Incomplete
    topic: Incomplete
    detect_owner: Incomplete
    targets: Incomplete
    include_image: Incomplete
    def __init__(self, bot_token, targets, detect_owner: bool = True, include_image: bool = False, silent=None, preview=None, topic=None, content=None, mdv=None, **kwargs) -> None: ...
    def send_media(self, target, notify_type, payload=None, attach=None): ...
    def detect_bot_owner(self): ...
    def send(self, body, title: str = '', notify_type=..., attach=None, body_format=None, **kwargs): ...
    def _send_attachments(self, target, notify_type, attach, payload=None): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def __len__(self) -> int: ...
    @staticmethod
    def parse_url(url, **kwargs): ...
