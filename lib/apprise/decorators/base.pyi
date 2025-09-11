from .. import common as common
from ..logger import logger as logger
from ..manager_plugins import NotificationManager as NotificationManager
from ..plugins.base import NotifyBase as NotifyBase
from ..utils.logic import dict_full_update as dict_full_update
from ..utils.parse import URL_DETAILS_RE as URL_DETAILS_RE, parse_url as parse_url, url_assembly as url_assembly
from _typeshed import Incomplete

N_MGR: Incomplete

class CustomNotifyPlugin(NotifyBase):
    service_url: str
    category: str
    attachment_support: bool
    storage_mode: Incomplete
    templates: Incomplete
    @staticmethod
    def parse_url(url): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    _default_args: Incomplete
    @staticmethod
    def instantiate_plugin(url, send_func, name=None): ...
