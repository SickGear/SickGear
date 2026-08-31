from .. import exception as exception
from ..common import ContentLocation as ContentLocation
from .base import AttachBase as AttachBase
from _typeshed import Incomplete

class AttachMemory(AttachBase):
    """A wrapper for Memory based attachment sources."""
    service_name: Incomplete
    protocol: str
    location: Incomplete
    _data: Incomplete
    def __init__(self, content=None, name=None, mimetype=None, encoding: str = 'utf-8', **kwargs) -> None:
        """Initialize Memory Based Attachment Object."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def open(self, *args, **kwargs):
        """Return an independent handle to our memory object."""
    def __enter__(self):
        """Support with clause."""
    def download(self, **kwargs):
        """Handle memory download() call."""
    def base64(self, encoding: str = 'ascii'):
        """We need to over-ride this since the base64 sub-library seems to
        close our file descriptor making it no longer referencable."""
    def invalidate(self) -> None:
        """Removes data."""
    def exists(self):
        """Over-ride exists() call."""
    @staticmethod
    def parse_url(url):
        """Parses the URL so that we can handle all different file paths and
        return it as our path object."""
    @property
    def path(self):
        """Return the filename."""
    def __len__(self) -> int:
        """Returns the size of he memory attachment."""
    def __bool__(self) -> bool:
        """Allows the Apprise object to be wrapped in an based 'if statement'.

        True is returned if our content was downloaded correctly.
        """
