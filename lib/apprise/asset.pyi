from .common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from .manager_plugins import NotificationManager as NotificationManager
from .utils.time import zoneinfo as zoneinfo
from _typeshed import Incomplete
from datetime import tzinfo
from typing import Any

N_MGR: Incomplete

class AppriseAsset:
    """Provides a supplimentary class that can be used to provide extra
    information and details that can be used by Apprise such as providing an
    alternate location to where images/icons can be found and the URL masks.

    Any variable that starts with an underscore (_) can only be initialized by
    this class manually and will/can not be parsed from a configuration file.
    """
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
    default_service_retry: int
    default_service_wait: float
    abort_on_chain_failure: bool
    encoding: str
    pgp_autogen: bool
    pem_autogen: bool
    secure_logging: bool
    http_redirects: bool
    __plugin_paths: Incomplete
    __storage_path: Incomplete
    __storage_salt: bytes
    __storage_idlen: int
    __storage_mode: Incomplete
    _recursion: int
    _uid: Incomplete
    _tzinfo: Incomplete
    def __init__(self, plugin_paths: list[str] | None = None, storage_path: str | None = None, storage_mode: str | PersistentStoreMode | None = None, storage_salt: str | bytes | None = None, storage_idlen: int | None = None, timezone: str | tzinfo | None = None, **kwargs: Any) -> None:
        """Asset Initialization."""
    def color(self, notify_type: NotifyType, color_type: type | None = None) -> str | int | tuple[int, int, int]:
        """Returns an HTML mapped color based on passed in notify type.

        if color_type is:
           None    then a standard hex string is returned as
                   a string format ('#000000').

           int     then the integer representation is returned
           tuple   then the the red, green, blue is returned in a tuple
        """
    def ascii(self, notify_type: NotifyType) -> str:
        """Returns an ascii representation based on passed in notify type."""
    def image_url(self, notify_type: NotifyType, image_size: NotifyImageSize | None = None, logo: bool = False, extension: str | None = None) -> str | None:
        """Apply our mask to our image URL.

        if logo is set to True, then the logo_url is used instead
        """
    def image_path(self, notify_type: NotifyType, image_size: NotifyImageSize, must_exist: bool = True, extension: str | None = None) -> str | None:
        """Apply our mask to our image file path."""
    def image_raw(self, notify_type: NotifyType, image_size: NotifyImageSize, extension: str | None = None) -> bytes | None:
        """Returns the raw image if it can (otherwise the function returns
        None)"""
    def details(self) -> dict[str, str]:
        """Returns the details associated with the AppriseAsset object."""
    @staticmethod
    def hex_to_rgb(value: str) -> tuple[int, int, int]:
        """Takes a hex string (such as #00ff00) and returns a tuple in the form
        of (red, green, blue)

        eg: #00ff00 becomes : (0, 65535, 0)
        """
    @staticmethod
    def hex_to_int(value: str) -> int:
        """Takes a hex string (such as #00ff00) and returns its integer
        equivalent.

        eg: #00000f becomes : 15
        """
    @property
    def plugin_paths(self) -> list[str]:
        """Return the plugin paths defined."""
    @property
    def storage_path(self) -> str | None:
        """Return the persistent storage path defined."""
    @property
    def storage_mode(self) -> PersistentStoreMode:
        """Return the persistent storage mode defined."""
    @property
    def storage_salt(self) -> bytes:
        """Return the provided namespace salt; this is always of type bytes."""
    @property
    def storage_idlen(self) -> int:
        """Return the persistent storage id length."""
    @property
    def tzinfo(self) -> tzinfo:
        """Return the timezone object"""
