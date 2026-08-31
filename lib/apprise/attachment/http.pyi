from ..common import ContentLocation as ContentLocation
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import URL_PATH_SAFE_CHARS as URL_PATH_SAFE_CHARS
from .base import AttachBase as AttachBase
from _typeshed import Incomplete

class AttachHTTP(AttachBase):
    """A wrapper for HTTP based attachment sources."""
    service_name: Incomplete
    protocol: str
    secure_protocol: str
    chunk_size: int
    location: Incomplete
    _lock: Incomplete
    schema: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    _temp_file: Incomplete
    qsd: Incomplete
    def __init__(self, headers=None, **kwargs) -> None:
        """Initialize HTTP Object.

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with
        """
    detected_mimetype: Incomplete
    detected_name: Incomplete
    download_path: Incomplete
    def download(self, **kwargs):
        """Perform retrieval of the configuration based on the specified
        request."""
    def invalidate(self) -> None:
        """Close our temporary file."""
    def __del__(self) -> None:
        """Tidy memory if open."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
