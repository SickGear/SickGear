import types
from _typeshed import Incomplete

LOGGER_NAME: str

def trace(self, message, *args, **kwargs) -> None: ...
def deprecate(self, message, *args, **kwargs) -> None: ...

logger: Incomplete

class LogCapture:
    __buffer_ptr: Incomplete
    __path: Incomplete
    __delete: Incomplete
    __level: Incomplete
    __restore_level: Incomplete
    __logger: Incomplete
    __handler: Incomplete
    def __init__(self, path=None, level=None, name=..., delete: bool = True, fmt: str = '%(asctime)s - %(levelname)s - %(message)s') -> None: ...
    def __enter__(self): ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, tb: types.TracebackType | None): ...
