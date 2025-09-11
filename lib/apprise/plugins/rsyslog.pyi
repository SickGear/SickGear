from ..common import NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class syslog:
    LOG_KERN: int
    LOG_USER: int
    LOG_MAIL: int
    LOG_DAEMON: int
    LOG_AUTH: int
    LOG_SYSLOG: int
    LOG_LPR: int
    LOG_NEWS: int
    LOG_UUCP: int
    LOG_CRON: int
    LOG_LOCAL0: int
    LOG_LOCAL1: int
    LOG_LOCAL2: int
    LOG_LOCAL3: int
    LOG_LOCAL4: int
    LOG_LOCAL5: int
    LOG_LOCAL6: int
    LOG_LOCAL7: int
    LOG_INFO: int
    LOG_NOTICE: int
    LOG_WARNING: int
    LOG_CRIT: int

class SyslogFacility:
    KERN: str
    USER: str
    MAIL: str
    DAEMON: str
    AUTH: str
    SYSLOG: str
    LPR: str
    NEWS: str
    UUCP: str
    CRON: str
    LOCAL0: str
    LOCAL1: str
    LOCAL2: str
    LOCAL3: str
    LOCAL4: str
    LOCAL5: str
    LOCAL6: str
    LOCAL7: str

SYSLOG_FACILITY_MAP: Incomplete
SYSLOG_FACILITY_RMAP: Incomplete
SYSLOG_PUBLISH_MAP: Incomplete

class NotifyRSyslog(NotifyBase):
    service_name: str
    service_url: str
    protocol: str
    setup_url: str
    request_rate_per_sec: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    facility: Incomplete
    log_pid: Incomplete
    def __init__(self, facility=None, log_pid: bool = True, **kwargs) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
