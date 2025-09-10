from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NOTIFY_FORMATS as NOTIFY_FORMATS, NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, OVERFLOW_MODES as OVERFLOW_MODES, OverflowMode as OverflowMode, PersistentStoreMode as PersistentStoreMode
from ..locale import Translatable as Translatable
from ..persistent_store import PersistentStore as PersistentStore
from ..url import URLBase as URLBase
from ..utils.parse import parse_bool as parse_bool
from ..utils.time import zoneinfo as zoneinfo
from _typeshed import Incomplete
from collections.abc import Generator
from datetime import tzinfo
from typing import Any, ClassVar, TypedDict

class RequirementsSpec(TypedDict, total=False):
    packages_required: str | list[str] | None
    packages_recommended: str | list[str] | None
    details: Translatable | None

class NotifyBase(URLBase):
    enabled: bool
    category: str
    requirements: ClassVar[RequirementsSpec]
    service_url: Incomplete
    setup_url: Incomplete
    request_rate_per_sec: float
    image_size: Incomplete
    body_maxlen: int
    title_maxlen: int
    body_max_line_count: int
    persistent_storage: bool
    timezone: Incomplete
    notify_format: Incomplete
    overflow_mode: Incomplete
    storage_mode: Incomplete
    interpret_emojis: bool
    attachment_support: bool
    default_html_tag_id: str
    template_args: Incomplete
    overflow_max_display_count_width: int
    overflow_buffer: int
    overflow_display_count_threshold: int
    overflow_display_title_once: Incomplete
    overflow_amalgamate_title: bool
    __tzinfo: Incomplete
    __store: Incomplete
    url_identifier: bool
    __cached_url_identifier: Incomplete
    def __init__(self, **kwargs) -> None: ...
    def image_url(self, notify_type: NotifyType, image_size: NotifyImageSize | None = None, logo: bool = False, extension: str | None = None) -> str | None: ...
    def image_path(self, notify_type: NotifyType, extension: str | None = None) -> str | None: ...
    def image_raw(self, notify_type: NotifyType, extension: str | None = None) -> bytes | None: ...
    def color(self, notify_type: NotifyType, color_type: type | None = None) -> str | int | tuple[int, int, int]: ...
    def ascii(self, notify_type: NotifyType) -> str: ...
    def notify(self, *args: Any, **kwargs: Any) -> bool: ...
    async def async_notify(self, *args: Any, **kwargs: Any) -> bool: ...
    def _build_send_calls(self, body: str | None = None, title: str | None = None, notify_type: NotifyType = ..., overflow: str | OverflowMode | None = None, attach: list[str] | AppriseAttachment | None = None, body_format: NotifyFormat | None = None, **kwargs: Any) -> Generator[dict[str, Any], None, None]: ...
    def _apply_overflow(self, body: str | None, title: str | None = None, overflow: str | OverflowMode | None = None, body_format: NotifyFormat | None = None) -> list[dict[str, str]]: ...
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., **kwargs: Any) -> bool: ...
    def url_parameters(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...
    @staticmethod
    def parse_url(url: str, verify_host: bool = True, plus_to_space: bool = False) -> dict[str, Any] | None: ...
    @staticmethod
    def parse_native_url(url: str) -> dict[str, Any] | None: ...
    @property
    def store(self): ...
    @property
    def tzinfo(self) -> tzinfo: ...
