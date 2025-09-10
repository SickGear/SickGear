from ..common import ContentLocation as ContentLocation
from ..utils.disk import path_decode as path_decode
from .base import AttachBase as AttachBase
from _typeshed import Incomplete

class AttachFile(AttachBase):
    service_name: Incomplete
    protocol: str
    location: Incomplete
    dirty_path: Incomplete
    __original_path: Incomplete
    def __init__(self, path, **kwargs) -> None: ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    download_path: Incomplete
    detected_name: Incomplete
    def download(self, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
