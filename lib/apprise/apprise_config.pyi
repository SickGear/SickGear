from . import common as common
from .asset import AppriseAsset as AppriseAsset
from .config.base import ConfigBase as ConfigBase
from .logger import logger as logger
from .manager_config import ConfigurationManager as ConfigurationManager
from .plugins.base import NotifyBase as NotifyBase
from .url import URLBase as URLBase
from .utils.cwe312 import cwe312_url as cwe312_url
from .utils.logic import is_exclusive_match as is_exclusive_match
from .utils.parse import GET_SCHEMA_RE as GET_SCHEMA_RE, parse_list as parse_list
from _typeshed import Incomplete
from typing import Any

C_MGR: Incomplete

class AppriseConfig:
    """Our Apprise Configuration File Manager.

    - Supports a list of URLs defined one after another (text format)
    """
    configs: Incomplete
    asset: Incomplete
    cache: Incomplete
    recursion: Incomplete
    insecure_includes: Incomplete
    def __init__(self, paths: str | list[str] | None = None, asset: AppriseAsset | None = None, cache: bool | int = True, recursion: int = 0, insecure_includes: bool = False, **kwargs: Any) -> None:
        """Loads all of the paths specified (if any).

        The path can either be a single string identifying one explicit
        location, otherwise you can pass in a series of locations to scan
        via a list.

        If no path is specified then a default list is used.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again. Setting this to False does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled and you're set up to
        make remote calls.  Only disable caching if you understand the
        consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.

        It's also worth nothing that the cache value is only set to elements
        that are not already of subclass ConfigBase()

        recursion defines how deep we recursively handle entries that use the
        `import` keyword. This keyword requires us to fetch more configuration
        from another source and add it to our existing compilation. If the
        file we remotely retrieve also has an `import` reference, we will only
        advance through it if recursion is set to 2 deep.  If set to zero
        it is off.  There is no limit to how high you set this value. It would
        be recommended to keep it low if you do intend to use it.

        insecure includes by default are disabled. When set to True, all
        Apprise Config files marked to be in STRICT mode are treated as being
        in ALWAYS mode.

        Take a file:// based configuration for example, only a file:// based
        configuration can import another file:// based one. because it is set
        to STRICT mode. If an http:// based configuration file attempted to
        import a file:// one it woul fail. However this import would be
        possible if insecure_includes is set to True.

        There are cases where a self hosting apprise developer may wish to load
        configuration from memory (in a string format) that contains import
        entries (even file:// based ones).  In these circumstances if you want
        these includes to be honored, this value must be set to True.
        """
    def add(self, configs: str | ConfigBase | list[str | ConfigBase], asset: AppriseAsset | None = None, tag: str | list[str] | None = None, cache: bool | int = True, recursion: int | None = None, insecure_includes: bool | None = None) -> bool:
        """Adds one or more config URLs into our list.

        You can override the global asset if you wish by including it with the
        config(s) that you add.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again. Setting this to False does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled and you're set up to
        make remote calls.  Only disable caching if you understand the
        consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.

        It's also worth nothing that the cache value is only set to elements
        that are not already of subclass ConfigBase()

        Optionally override the default recursion value.

        Optionally override the insecure_includes flag. if insecure_includes is
        set to True then all plugins that are set to a STRICT mode will be a
        treated as ALWAYS.
        """
    def add_config(self, content: str, asset: AppriseAsset | None = None, tag: str | list[str] | None = None, format: str | None = None, recursion: int | None = None, insecure_includes: bool | None = None) -> bool:
        """Adds one configuration file in it's raw format. Content gets loaded
        as a memory based object and only exists for the life of this
        AppriseConfig object it was loaded into.

        If you know the format ('text') you can specify it for
        slightly less overhead during this call.  Otherwise the configuration
        is auto-detected.

        Optionally override the default recursion value.

        Optionally override the insecure_includes flag. if insecure_includes is
        set to True then all plugins that are set to a STRICT mode will be a
        treated as ALWAYS.
        """
    def servers(self, tag: str | list[str] = ..., match_always: bool = True, *args: Any, **kwargs: Any) -> list[NotifyBase]:
        """Returns all of our servers dynamically build based on parsed
        configuration.

        If a tag is specified, it applies to the configuration sources
        themselves and not the notification services inside them.

        This is for filtering the configuration files polled for results.

        If the anytag is set, then any notification that is found set with that
        tag are included in the response.
        """
    @staticmethod
    def instantiate(url: str, asset: AppriseAsset | None = None, tag: str | list[str] | None = None, cache: bool | int | None = None, recursion: int = 0, insecure_includes: bool = False, suppress_exceptions: bool = True) -> ConfigBase | None:
        """Returns the instance of a instantiated configuration plugin based on
        the provided Config URL.

        If the url fails to be parsed, then None is returned.
        """
    def clear(self) -> None:
        """Empties our configuration list."""
    def server_pop(self, index: int) -> NotifyBase:
        """Removes an indexed Apprise Notification from the servers."""
    def pop(self, index: int = -1) -> ConfigBase:
        """Removes an indexed Apprise Configuration from the stack and returns
        it.

        By default, the last element is removed from the list
        """
    def __getitem__(self, index: int) -> ConfigBase:
        """Returns the indexed config entry of a loaded apprise
        configuration."""
    def __bool__(self) -> bool:
        """Allows the Apprise object to be wrapped in an 'if statement'.

        True is returned if at least one service has been loaded.
        """
    def __iter__(self) -> Iterator[ConfigBase]:
        """Returns an iterator to our config list."""
    def __len__(self) -> int:
        """Returns the number of config entries loaded."""
