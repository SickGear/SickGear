from typing import Any

SetHandleInformation: Any
HANDLE_FLAG_INHERIT: int

def set_close_exec(fd: int) -> None: ...
