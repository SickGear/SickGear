class BaseError(Exception): ...

class ParseError(BaseError):
    errorcode: int
    errordesc: str

class AuthError(BaseError):
    errorcode: int
    errordesc: str

class UnsupportedError(BaseError):
    errorcode: int
    errordesc: str

class NetworkError(BaseError):
    errorcode: int
    errordesc: str
