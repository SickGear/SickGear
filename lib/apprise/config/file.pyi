from ..common import ConfigFormat as ConfigFormat, ContentIncludeMode as ContentIncludeMode
from ..utils.disk import path_decode as path_decode
from .base import ConfigBase as ConfigBase
from _typeshed import Incomplete

class ConfigFile(ConfigBase):
    service_name: Incomplete
    protocol: str
    allow_cross_includes: Incomplete
    path: Incomplete
    __original_path: Incomplete
    config_path: Incomplete
    def __init__(self, path, **kwargs) -> None: ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    def read(self, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
