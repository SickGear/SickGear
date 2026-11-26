from ..common import ConfigFormat as ConfigFormat, ContentIncludeMode as ContentIncludeMode
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS
from .base import ConfigBase as ConfigBase
from _typeshed import Incomplete

MIME_IS_TEXT: Incomplete

class ConfigHTTP(ConfigBase):
    """A wrapper for HTTP based configuration sources."""
    service_name: Incomplete
    protocol: str
    secure_protocol: str
    max_error_buffer_size: int
    allow_cross_includes: Incomplete
    schema: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, headers=None, **kwargs) -> None:
        """Initialize HTTP Object.

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    default_config_format: Incomplete
    def read(self, **kwargs):
        """Perform retrieval of the configuration based on the specified
        request."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
