from _typeshed import Incomplete

class AppriseException(Exception):
    error_code: Incomplete
    def __init__(self, message, error_code: int = 0) -> None: ...

class ApprisePluginException(AppriseException):
    def __init__(self, message, error_code: int = 600) -> None: ...

class AppriseDiskIOError(AppriseException):
    def __init__(self, message, error_code=...) -> None: ...

class AppriseInvalidData(AppriseException):
    def __init__(self, message, error_code=...) -> None: ...

class AppriseFileNotFound(AppriseDiskIOError, FileNotFoundError):
    def __init__(self, message) -> None: ...
