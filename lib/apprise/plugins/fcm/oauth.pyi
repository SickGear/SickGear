from ...logger import logger as logger
from _typeshed import Incomplete

class GoogleOAuth:
    scopes: Incomplete
    access_token_lifetime_sec: Incomplete
    default_token_uri: str
    clock_skew: Incomplete
    verify_certificate: Incomplete
    request_timeout: Incomplete
    user_agent: Incomplete
    def __init__(self, user_agent=None, timeout=(5, 4), verify_certificate: bool = True) -> None: ...
    encoding: str
    content: Incomplete
    private_key: Incomplete
    __refresh_token: Incomplete
    __access_token: Incomplete
    __access_token_expiry: Incomplete
    def __reset(self) -> None: ...
    def load(self, path): ...
    @property
    def access_token(self): ...
    @property
    def project_id(self): ...
