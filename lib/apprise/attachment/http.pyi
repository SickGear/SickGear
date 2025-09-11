from ..common import ContentLocation as ContentLocation
from ..url import PrivacyMode as PrivacyMode
from .base import AttachBase as AttachBase
from _typeshed import Incomplete

class AttachHTTP(AttachBase):
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
    def __init__(self, headers=None, **kwargs) -> None: ...
    detected_mimetype: Incomplete
    detected_name: Incomplete
    download_path: Incomplete
    def download(self, **kwargs): ...
    def invalidate(self) -> None: ...
    def __del__(self) -> None: ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
