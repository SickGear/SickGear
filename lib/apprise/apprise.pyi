from . import __version__ as __version__, common as common, plugins as plugins
from .apprise_attachment import AppriseAttachment as AppriseAttachment
from .apprise_config import AppriseConfig as AppriseConfig
from .asset import AppriseAsset as AppriseAsset
from .common import ContentLocation as ContentLocation
from .config.base import ConfigBase as ConfigBase
from .conversion import convert_between as convert_between
from .emojis import apply_emojis as apply_emojis
from .locale import AppriseLocale as AppriseLocale
from .logger import logger as logger
from .manager_plugins import NotificationManager as NotificationManager
from .plugins.base import NotifyBase as NotifyBase
from .tag import AppriseTag as AppriseTag
from .utils.cwe312 import cwe312_url as cwe312_url
from .utils.json import AppriseJSONEncoder as AppriseJSONEncoder
from .utils.logic import is_exclusive_match as is_exclusive_match
from .utils.parse import parse_list as parse_list, parse_urls as parse_urls
from _typeshed import Incomplete
from collections.abc import Generator, Iterator
from typing import Any

N_MGR: Incomplete

class Apprise:
    """Our Notification Manager."""
    servers: Incomplete
    asset: Incomplete
    locale: Incomplete
    debug: Incomplete
    location: Incomplete
    def __init__(self, servers: str | dict | NotifyBase | AppriseConfig | ConfigBase | list[str | dict | NotifyBase | AppriseConfig | ConfigBase] | None = None, asset: AppriseAsset | None = None, location: ContentLocation | None = None, debug: bool = False) -> None:
        """Loads a set of server urls while applying the Asset() module to each
        if specified.

        If no asset is provided, then the default asset is used.

        Optionally specify a global ContentLocation for a more strict means of
        handling Attachments.
        """
    @staticmethod
    def instantiate(url: str | dict, asset: AppriseAsset | None = None, tag: str | list[str] | None = None, suppress_exceptions: bool = True) -> NotifyBase | None:
        """Returns the instance of a instantiated plugin based on the provided
        Server URL.  If the url fails to be parsed, then None is returned.

        The specified url can be either a string (the URL itself) or a
        dictionary containing all of the components needed to istantiate
        the notification service.  If identifying a dictionary, at the bare
        minimum, one must specify the schema.

        An example of a url dictionary object might look like:
          {
            schema: 'mailto',
            host: 'google.com',
            user: 'myuser',
            password: 'mypassword',
          }

        Alternatively the string is much easier to specify:
          mailto://user:mypassword@google.com

        The dictionary works well for people who are calling details() to
        extract the components they need to build the URL manually.
        """
    def add(self, servers: str | dict | NotifyBase | AppriseConfig | ConfigBase | list[str | dict | NotifyBase | AppriseConfig | ConfigBase], asset: AppriseAsset | None = None, tag: str | list[str] | None = None) -> bool:
        """Adds one or more server URLs into our list.

        You can override the global asset if you wish by including it with the
        server(s) that you add.

        The tag allows you to associate 1 or more tag values to the server(s)
        being added. tagging a service allows you to exclusively access them
        when calling the notify() function.
        """
    def clear(self) -> None:
        """Empties our server list."""
    def find(self, tag: Any = ..., match_always: bool = True) -> Iterator[NotifyBase]:
        """Returns a list of all servers matching against the tag specified."""
    @staticmethod
    def _extract_filter_retry(tag):
        '''Return the retry override embedded in a filter tag, or None.

        A filter like "3:endpoint:2" or "endpoint:2" carries ":2" as the
        call-level retry count.  When present it overrides each matched
        server\'s configured retry for this single notify() call.
        '''
    @staticmethod
    def _filter_has_explicit_priority(tag):
        """Return True if any token in *tag* carries an explicit priority
        prefix.

        When True, notify() dispatches matched servers as a flat batch
        (no escalation) because the caller selected an exact priority level.
        When False, matched servers are grouped by their own tag priorities
        and dispatched in ascending order with early-True exit.
        """
    @staticmethod
    def _server_priority_for_tag_name(server, tag_name):
        """Return the dispatch priority stored on *server* for *tag_name*.

        Looks up the AppriseTag in server.tags whose bare name equals
        *tag_name* and returns its priority.  Returns 0 when the tag is
        absent or stored as a plain string (no explicit priority).
        """
    @staticmethod
    def _match_service_retry(server, tag):
        """Return the call-time retry override for *server* given *tag*.

        Iterates the OR tokens in *tag* in order.  The first token that
        both carries a retry suffix AND matches *server* determines the
        override.  Returns None when no such token exists.

        Matching follows the same rules as _token_matches_data:
          - no priority prefix  -> name-only match
          - explicit priority   -> name + priority-exact match
        """
    @staticmethod
    def _inject_per_service_retries(all_calls, tag):
        """Return *all_calls* with per-service _retry_override injected.

        For each (server, kwargs) pair, finds the first filter token in
        *tag* that matches the service and carries a retry suffix.  When
        found, injects that value as _retry_override so that all dispatch
        paths (sequential, threadpool, asyncio) pick it up automatically.
        Services with no matching retry token are left unchanged.
        """
    @staticmethod
    def _build_tag_chains(all_calls, tag):
        '''Group *all_calls* into per-OR-token escalation chains.

        Returns {chain_key: {priority: [(server, kwargs)]}}.

        Each service is assigned to the chain of the first OR token whose
        bare tag name appears in the service\'s own tags.  The chain key is
        that bare tag name.  Services that don\'t match any token by name
        fall into a catch-all chain keyed as "".

        When *tag* is MATCH_ALL_TAG or None, a single chain "" is built
        using the existing _server_priority_for_filter logic.
        '''
    @staticmethod
    def _server_priority_for_filter(server, tag):
        """Return the effective dispatch priority for *server* given *tag*.

        The priority comes from the AppriseTag stored on the server whose
        name matches one of the tag-filter names.  When multiple server tags
        match, the minimum (highest-precedence) priority is returned.
        Returns 0 when no matching priority tag is found.
        """
    def notify(self, body: str | bytes, title: str | bytes = '', notify_type: str | common.NotifyType = ..., body_format: str | None = None, tag: Any = ..., match_always: bool = True, attach: Any = None, interpret_escapes: bool | None = None) -> bool | None:
        '''Send a notification to all the plugins previously loaded.

        If the body_format specified is NotifyFormat.MARKDOWN, it will be
        converted to HTML if the Notification type expects this.

        if the tag is specified (either a string or a set/list/tuple of
        strings), then only the notifications flagged with that tagged value
        are notified.  By default, all added services are notified
        (tag=MATCH_ALL_TAG)

        This function returns True if all notifications were successfully sent,
        False if even just one of them fails, and None if no notifications were
        sent at all as a result of tag filtering and/or simply having empty
        configuration files that were read.

        A filter tag may carry an optional priority prefix and/or retry suffix:

          "endpoint"       -> match all entries; escalate by priority
          "3:endpoint"     -> match ONLY priority-3 entries; flat dispatch
          "endpoint:2"     -> match all entries; retry each up to 2 times
          "3:endpoint:2"   -> exclusive priority-3 match with 2 retries

        When no priority prefix is given, matched services are grouped by
        their configured tag priority and dispatched in ascending order
        (lowest number = highest urgency).  If every service in the lowest
        priority group succeeds, Apprise returns True immediately without
        running higher-numbered priority groups (escalation chain).

        When an explicit priority prefix IS given (e.g. "3:endpoint"), only
        services whose matching tag carries that exact priority are notified,
        and all matched services are dispatched as a single flat batch.

        Attach can contain a list of attachment URLs.  attach can also be
        represented by an AttachBase() (or list of) object(s). This identifies
        the products you wish to notify

        Set interpret_escapes to True if you want to pre-escape a string such
        as turning a 
 into an actual new line, etc.
        '''
    async def async_notify(self, *args: Any, **kwargs: Any) -> bool | None:
        """Send a notification to all the plugins previously loaded, for
        asynchronous callers.

        The arguments are identical to those of Apprise.notify().
        """
    def _create_notify_calls(self, *args, **kwargs):
        """Creates notifications for all the plugins loaded.

        Returns a list of (server, notify() kwargs) tuples for plugins with
        parallelism disabled and another list for plugins with parallelism
        enabled.
        """
    def _create_notify_gen(self, body, title: str = '', notify_type=..., body_format=None, tag=..., match_always: bool = True, attach=None, interpret_escapes=None) -> Generator[Incomplete]:
        """Internal generator function for _create_notify_calls()."""
    @staticmethod
    def _notify_sequential(*servers_kwargs):
        """Process a list of notify() calls sequentially and synchronously.

        Each server is attempted once and then retried up to server.retry
        additional times on failure before moving on.  When server.wait is
        greater than zero, the process sleeps that many seconds between
        each retry attempt.

        A per-call retry override may be injected into kwargs under the key
        ``_retry_override``; when present it takes precedence over the
        server's own retry attribute for this invocation only.

        Exceptions raised by a plugin's notify() -- including those from
        third-party @notify-decorated functions that are outside our control
        -- are caught here and treated as a delivery failure.  The retry
        logic still applies, so a plugin that raises on the first attempt
        will be retried the configured number of times before giving up.
        """
    @staticmethod
    def _notify_parallel_threadpool(*servers_kwargs):
        """Process a list of notify() calls in parallel via a thread pool.

        Each server runs in its own thread.  Within each thread, the server
        is retried up to server.retry additional times on failure with an
        optional server.wait second sleep between each attempt.

        Falls back to _notify_sequential() when only a single server is
        given to avoid the overhead of spawning a thread pool for one call.

        Exceptions from a plugin's notify() -- including those from
        third-party @notify-decorated functions -- are caught inside each
        thread and treated as delivery failures so the retry logic can
        still run.
        """
    @staticmethod
    async def _notify_parallel_asyncio(*servers_kwargs):
        """Process a list of async_notify() calls concurrently via asyncio.

        All coroutines are gathered with asyncio.gather().  Each server is
        retried up to server.retry additional times on failure with an
        optional asyncio.sleep(server.wait) between attempts.

        Unlike the thread-pool path, there is no single-server optimisation
        here because asyncio can pipeline work across coroutines while one
        is awaiting I/O.

        Exceptions from a plugin's async_notify() -- including those from
        third-party @notify-decorated coroutines -- are caught inside each
        coroutine and treated as delivery failures so the retry loop can
        still run for that service.
        """
    def json(self, lang: str | None = None, show_requirements: bool = False, show_disabled: bool = False, indent: int | None = None, path: str | None = None) -> str | bool:
        """Returns a json response associated with the Apprise object."""
    def details(self, lang: str | None = None, show_requirements: bool = False, show_disabled: bool = False) -> dict[str, Any]:
        """Returns the details associated with the Apprise object."""
    def urls(self, privacy: bool = False) -> list[str]:
        """Returns all of the loaded URLs defined in this apprise object."""
    def pop(self, index: int) -> NotifyBase:
        """Removes an indexed Notification Service from the stack and returns
        it.

        The thing is we can never pop AppriseConfig() entries, only what was
        loaded within them. So pop needs to carefully iterate over our list and
        only track actual entries.
        """
    def __getitem__(self, index: int) -> NotifyBase:
        """Returns the indexed server entry of a loaded notification server."""
    def __getstate__(self) -> dict[str, object]:
        """Pickle Support dumps()"""
    def __setstate__(self, state: dict[str, object]) -> None:
        """Pickle Support loads()"""
    def __bool__(self) -> bool:
        """Allows the Apprise object to be wrapped in an 'if statement'.

        True is returned if at least one service has been loaded.
        """
    def __iter__(self) -> Iterator[NotifyBase]:
        """Returns an iterator to each of our servers loaded.

        This includes those found inside configuration.
        """
    def __len__(self) -> int:
        """Returns the number of servers loaded; this includes those found
        within loaded configuration.

        This funtion nnever actually counts the Config entry themselves (if
        they exist), only what they contain.
        """
