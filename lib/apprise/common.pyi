from enum import Enum

AWARE_DATE_ISO_FORMAT: str
NAIVE_DATE_ISO_FORMAT: str

class NotifyType(str, Enum):
    """A simple mapping of notification types most commonly used with all types
    of logging and notification services."""
    INFO = 'info'
    SUCCESS = 'success'
    WARNING = 'warning'
    FAILURE = 'failure'

NOTIFY_TYPES: frozenset[str]

class NotifyImageSize(str, Enum):
    """A list of pre-defined image sizes to make it easier to work with defined
    plugins."""
    XY_32 = '32x32'
    XY_72 = '72x72'
    XY_128 = '128x128'
    XY_256 = '256x256'

NOTIFY_IMAGE_SIZES: frozenset[str]

class NotifyFormat(str, Enum):
    """A list of pre-defined text message formats that can be passed via the
    apprise library."""
    TEXT = 'text'
    HTML = 'html'
    MARKDOWN = 'markdown'

NOTIFY_FORMATS: frozenset[str]

class OverflowMode(str, Enum):
    """A list of pre-defined modes of how to handle the text when it exceeds
    the defined maximum message size."""
    UPSTREAM = 'upstream'
    TRUNCATE = 'truncate'
    SPLIT = 'split'

OVERFLOW_MODES: frozenset[str]

class ConfigFormat(str, Enum):
    """A list of pre-defined config formats that can be passed via the apprise
    library."""
    TEXT = 'text'

CONFIG_FORMATS: frozenset[str]

class ContentIncludeMode(str, Enum):
    """The different Content inclusion modes.

    All content based plugins will have one of these associated with it.
    """
    STRICT = 'strict'
    NEVER = 'never'
    ALWAYS = 'always'

CONTENT_INCLUDE_MODES: frozenset[str]

class ContentLocation(str, Enum):
    """This is primarily used for handling file attachments.  The idea is to
    track the source of the attachment itself.  We don't want remote calls to a
    server to access local attachments for example.

    By knowing the attachment type and cross-associating it with how we plan on
    accessing the content, we can make a judgement call (for security reasons)
    if we will allow it.

    Obviously local uses of apprise can access both local and remote type
    files.
    """
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
    """Defines the persistent states describing what has been cached."""
    ACTIVE = 'active'
    STALE = 'stale'
    UNUSED = 'unused'

PERSISTENT_STORE_STATES: frozenset[str]
MATCH_ALL_TAG: str
MATCH_ALWAYS_TAG: str
APPRISE_MAX_SERVICE_RETRY: int
APPRISE_MAX_SERVICE_WAIT: float
