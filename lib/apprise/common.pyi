from enum import Enum

class NotifyType(str, Enum):
    INFO = 'info'
    SUCCESS = 'success'
    WARNING = 'warning'
    FAILURE = 'failure'

NOTIFY_TYPES: frozenset[str]

class NotifyImageSize(str, Enum):
    XY_32 = '32x32'
    XY_72 = '72x72'
    XY_128 = '128x128'
    XY_256 = '256x256'

NOTIFY_IMAGE_SIZES: frozenset[str]

class NotifyFormat(str, Enum):
    TEXT = 'text'
    HTML = 'html'
    MARKDOWN = 'markdown'

NOTIFY_FORMATS: frozenset[str]

class OverflowMode(str, Enum):
    UPSTREAM = 'upstream'
    TRUNCATE = 'truncate'
    SPLIT = 'split'

OVERFLOW_MODES: frozenset[str]

class ConfigFormat(str, Enum):
    TEXT = 'text'

CONFIG_FORMATS: frozenset[str]

class ContentIncludeMode(str, Enum):
    STRICT = 'strict'
    NEVER = 'never'
    ALWAYS = 'always'

CONTENT_INCLUDE_MODES: frozenset[str]

class ContentLocation(str, Enum):
    LOCAL = 'local'
    HOSTED = 'hosted'
    INACCESSIBLE = 'n/a'

CONTENT_LOCATIONS: frozenset[str]

class PersistentStoreMode(str, Enum):
    AUTO = 'auto'
    FLUSH = 'flush'
    MEMORY = 'memory'

PERSISTENT_STORE_MODES: frozenset[str]

class PersistentStoreState(str, Enum):
    ACTIVE = 'active'
    STALE = 'stale'
    UNUSED = 'unused'

PERSISTENT_STORE_STATES: frozenset[str]
MATCH_ALL_TAG: str
MATCH_ALWAYS_TAG: str
