from .manager import PluginManager as PluginManager
from _typeshed import Incomplete

class ConfigurationManager(PluginManager):
    name: str
    fname_prefix: str
    _id: str
    module_name_prefix: Incomplete
    module_path: Incomplete
    module_filter_re: Incomplete
