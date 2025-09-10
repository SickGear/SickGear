from ..logger import logger as logger
from _typeshed import Incomplete

ESCAPED_PATH_SEPARATOR: Incomplete
ESCAPED_WIN_PATH_SEPARATOR: Incomplete
ESCAPED_NUX_PATH_SEPARATOR: Incomplete
TIDY_WIN_PATH_RE: Incomplete
TIDY_WIN_TRIM_RE: Incomplete
TIDY_NUX_PATH_RE: Incomplete
__PATH_DECODER: Incomplete

def path_decode(path): ...
def tidy_path(path): ...
def dir_size(path, max_depth: int = 3, missing_okay: bool = True, _depth: int = 0, _errors=None): ...
def bytes_to_str(value): ...
