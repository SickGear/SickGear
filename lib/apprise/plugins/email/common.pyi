import dataclasses
from ...exception import ApprisePluginException as ApprisePluginException
from _typeshed import Incomplete

class AppriseEmailException(ApprisePluginException):
    def __init__(self, message, error_code: int = 601) -> None: ...

class WebBaseLogin:
    EMAIL: str
    USERID: str

class SecureMailMode:
    INSECURE: str
    SSL: str
    STARTTLS: str

SECURE_MODES: Incomplete

@dataclasses.dataclass
class EmailMessage:
    recipient: str
    to_addrs: list[str]
    body: str
