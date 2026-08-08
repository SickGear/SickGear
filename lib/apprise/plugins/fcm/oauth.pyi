from ...logger import logger as logger
from _typeshed import Incomplete

class GoogleOAuth:
    """A OAuth simplified implimentation to Google's Firebase Cloud
    Messaging."""
    scopes: Incomplete
    access_token_lifetime_sec: Incomplete
    default_token_uri: str
    clock_skew: Incomplete
    verify_certificate: Incomplete
    redirects: Incomplete
    request_timeout: Incomplete
    user_agent: Incomplete
    def __init__(self, user_agent=None, timeout=(5, 4), verify_certificate: bool = True, redirects: bool = True) -> None:
        """Initialize our OAuth object."""
    encoding: str
    content: Incomplete
    private_key: Incomplete
    __refresh_token: Incomplete
    __access_token: Incomplete
    __access_token_expiry: Incomplete
    def __reset(self) -> None:
        """Reset object internal variables."""
    def load(self, path):
        """Generate our SSL details."""
    @property
    def access_token(self):
        """Returns our access token (if it hasn't expired yet)

        - if we do not have one we'll fetch one.
        - if it expired, we'll renew it
        - if a key simply can't be acquired, then we return None
        """
    @property
    def project_id(self):
        """Returns the project id found in the file."""
