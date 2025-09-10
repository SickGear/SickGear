from .notifier import GrowlNotifier as GrowlNotifier
from .shim import RawConfigParser as RawConfigParser
from .version import __version__ as __version__
from _typeshed import Incomplete
from optparse import OptionParser

DEFAULT_CONFIG: Incomplete
config: Incomplete

class ClientParser(OptionParser):
    def __init__(self) -> None: ...
    def parse_args(self, args=None, values=None): ...

def main() -> None: ...
