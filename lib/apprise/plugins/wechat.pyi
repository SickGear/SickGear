from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..utils.parse import parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

WECHAT_ERROR_CODES: Incomplete
WECHAT_TOKEN_ERROR_CODES: Incomplete
IS_USER: Incomplete
IS_DEPT: Incomplete
IS_TAG: Incomplete

class NotifyWeChat(NotifyBase):
    """A wrapper for WeCom (WeChat Work) Application Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    token_url: str
    notify_url: str
    body_maxlen: int
    title_maxlen: int
    notify_format: Incomplete
    storage_mode: Incomplete
    default_cache_expiry_sec: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    corpid: Incomplete
    corpsecret: Incomplete
    agentid: Incomplete
    users: Incomplete
    departments: Incomplete
    tag_ids: Incomplete
    invalid_targets: Incomplete
    def __init__(self, corpid, corpsecret, agentid, targets=None, **kwargs) -> None:
        """Initialize WeChat (WeCom Application) Object."""
    def _get_access_token(self):
        """Return the cached WeCom access token, fetching a fresh one
        if the cache is empty or the token has expired."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform WeChat (WeCom Application) Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique
        from another similar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified
        arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url) -> None:
        """WeCom does not expose a shareable single-URL credential form,
        so native URL detection is not supported."""
