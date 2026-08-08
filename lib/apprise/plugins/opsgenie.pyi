from ..common import NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ..utils.parse import is_uuid as is_uuid, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class OpsgenieCategory(NotifyBase):
    """We define the different category types that we can notify."""
    USER: str
    SCHEDULE: str
    ESCALATION: str
    TEAM: str

OPSGENIE_CATEGORIES: Incomplete

class OpsgenieAlertAction:
    """Defines the supported actions."""
    MAP: str
    NEW: str
    CLOSE: str
    DELETE: str
    ACKNOWLEDGE: str
    NOTE: str

OPSGENIE_ACTIONS: Incomplete

class OpsgenieRegion:
    US: str
    EU: str

OPSGENIE_API_LOOKUP: Incomplete
OPSGENIE_REGIONS: Incomplete

class OpsgeniePriority:
    LOW: int
    MODERATE: int
    NORMAL: int
    HIGH: int
    EMERGENCY: int

OPSGENIE_PRIORITIES: Incomplete
OPSGENIE_PRIORITY_MAP: Incomplete

class NotifyOpsgenie(NotifyBase):
    """A wrapper for Opsgenie Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    body_maxlen: int
    storage_mode: Incomplete
    opsgenie_body_minlen: int
    opsgenie_default_region: Incomplete
    default_batch_size: int
    opsgenie_message_map: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    apikey: Incomplete
    priority: Incomplete
    region_name: Incomplete
    action: Incomplete
    mapping: Incomplete
    details: Incomplete
    batch_size: Incomplete
    __tags: Incomplete
    entity: Incomplete
    alias: Incomplete
    targets: Incomplete
    def __init__(self, apikey, targets, region_name=None, details=None, priority=None, alias=None, entity=None, batch: bool = False, tags=None, action=None, mapping=None, **kwargs) -> None:
        """Initialize Opsgenie Object."""
    def _fetch(self, method, url, payload, params=None):
        """Performs server retrieval/update and returns JSON Response."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Opsgenie Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
