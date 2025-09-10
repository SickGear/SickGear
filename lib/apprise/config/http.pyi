from ..common import ConfigFormat as ConfigFormat, ContentIncludeMode as ContentIncludeMode
from ..url import PrivacyMode as PrivacyMode
from .base import ConfigBase as ConfigBase
from _typeshed import Incomplete

MIME_IS_TEXT: Incomplete

class ConfigHTTP(ConfigBase):
    service_name: Incomplete
    protocol: str
    secure_protocol: str
    max_error_buffer_size: int
    allow_cross_includes: Incomplete
    schema: Incomplete
    fullpath: Incomplete
    headers: Incomplete
    def __init__(self, headers=None, **kwargs) -> None: ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    default_config_format: Incomplete
    def read(self, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
