from .common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from .manager_plugins import NotificationManager as NotificationManager
from .utils.time import zoneinfo as zoneinfo
from _typeshed import Incomplete
from datetime import tzinfo
from typing import Any

N_MGR: Incomplete

class AppriseAsset:
    app_id: str
    app_desc: str
    app_url: str
    html_notify_map: Incomplete
    default_html_color: str
    ascii_notify_map: Incomplete
    default_ascii_chars: str
    default_extension: str
    default_image_size: Incomplete
    theme: str
    image_url_mask: str
    image_url_logo: str
    image_path_mask: Incomplete
    body_format: Incomplete
    async_mode: bool
    interpret_emojis: Incomplete
    interpret_escapes: bool
    encoding: str
    pgp_autogen: bool
    pem_autogen: bool
    secure_logging: bool
    __plugin_paths: Incomplete
    __storage_path: Incomplete
    __storage_salt: bytes
    __storage_idlen: int
    __storage_mode: Incomplete
    _recursion: int
    _uid: Incomplete
    _tzinfo: Incomplete
    def __init__(self, plugin_paths: list[str] | None = None, storage_path: str | None = None, storage_mode: str | PersistentStoreMode | None = None, storage_salt: str | bytes | None = None, storage_idlen: int | None = None, timezone: str | tzinfo | None = None, **kwargs: Any) -> None: ...
    def color(self, notify_type: NotifyType, color_type: type | None = None) -> str | int | tuple[int, int, int]: ...
    def ascii(self, notify_type: NotifyType) -> str: ...
    def image_url(self, notify_type: NotifyType, image_size: NotifyImageSize | None = None, logo: bool = False, extension: str | None = None) -> str | None: ...
    def image_path(self, notify_type: NotifyType, image_size: NotifyImageSize, must_exist: bool = True, extension: str | None = None) -> str | None: ...
    def image_raw(self, notify_type: NotifyType, image_size: NotifyImageSize, extension: str | None = None) -> bytes | None: ...
    def details(self) -> dict[str, str]: ...
    @staticmethod
    def hex_to_rgb(value: str) -> tuple[int, int, int]: ...
    @staticmethod
    def hex_to_int(value: str) -> int: ...
    @property
    def plugin_paths(self) -> list[str]: ...
    @property
    def storage_path(self) -> str | None: ...
    @property
    def storage_mode(self) -> PersistentStoreMode: ...
    @property
    def storage_salt(self) -> bytes: ...
    @property
    def storage_idlen(self) -> int: ...
    @property
    def tzinfo(self) -> tzinfo: ...
