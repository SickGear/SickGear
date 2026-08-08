from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import APPRISE_MAX_SERVICE_RETRY as APPRISE_MAX_SERVICE_RETRY, APPRISE_MAX_SERVICE_WAIT as APPRISE_MAX_SERVICE_WAIT, NOTIFY_FORMATS as NOTIFY_FORMATS, NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, OVERFLOW_MODES as OVERFLOW_MODES, OverflowMode as OverflowMode, PersistentStoreMode as PersistentStoreMode
from ..locale import Translatable as Translatable
from ..persistent_store import PersistentStore as PersistentStore
from ..url import URLBase as URLBase
from ..utils.format import smart_split as smart_split
from ..utils.parse import parse_bool as parse_bool
from ..utils.time import zoneinfo as zoneinfo
from _typeshed import Incomplete
from collections.abc import Generator
from datetime import tzinfo
from typing import Any, ClassVar, TypedDict

class RequirementsSpec(TypedDict, total=False):
    """Defines our plugin requirements."""
    packages_required: str | list[str] | None
    packages_recommended: str | list[str] | None
    details: Translatable | None

class NotifyBase(URLBase):
    """This is the base class for all notification services."""
    enabled: bool
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.

        The plugin manager uses this to maintain a reference counter per
        library.  When every plugin that declared a given library is disabled,
        its counter reaches zero and the manager evicts the library from
        `sys.modules`, releasing the associated Python objects from memory.

        Names must be the importable top-level namespace - the same string you
        would pass to `import` - not the pip install name:

            ('paho',)        # paho-mqtt installs as 'paho'
            ('slixmpp',)
            ('cryptography',)

        Submodules are handled automatically; declaring the top-level name is
        sufficient.

        Override this in any plugin that conditionally imports a heavy optional
        library.  Return an empty tuple (the default) when the plugin has no
        optional dependencies that are worth evicting.
        """
    @classmethod
    def enable(self) -> None:
        """Mark this plugin as enabled.

        This is the counterpart to :meth:`disable`.  Calling this restores the
        plugin to an active state so it will be used for notifications again.
        Note that if the plugin's runtime dependencies were evicted from memory
        by the plugin manager, re-enabling will restore the flag but the
        plugin may not function until the process is restarted.
        """
    @classmethod
    def disable(self) -> None:
        """Mark this plugin as disabled.

        The plugin will not be used for notifications.  The plugin manager
        calls this when honouring `APPRISE_DENY_SERVICES` /
        `APPRISE_ALLOW_SERVICES` and uses the result of
        :method:`runtime_deps` to decrement its per-library reference counters,
        potentially evicting unused libraries from `sys.modules`.
        """
    category: str
    requirements: ClassVar[RequirementsSpec]
    service_url: Incomplete
    setup_url: Incomplete
    request_rate_per_sec: float
    image_size: Incomplete
    body_maxlen: int
    title_maxlen: int
    body_max_line_count: int
    persistent_storage: bool
    timezone: Incomplete
    notify_format: Incomplete
    overflow_mode: Incomplete
    storage_mode: Incomplete
    interpret_emojis: bool
    service_retry: int
    service_wait: float
    optional: bool
    attachment_support: bool
    default_html_tag_id: str
    template_args: Incomplete
    overflow_max_display_count_width: int
    overflow_buffer: int
    overflow_display_count_threshold: int
    overflow_display_title_once: Incomplete
    overflow_amalgamate_title: bool
    __tzinfo: Incomplete
    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Automatically wrap any __len__ defined on a subclass so that it
        multiplies its base target count by (retry + 1).

        This ensures every plugin's __len__ reflects the total number of
        transmission attempts (targets * retry-factor) without requiring
        each plugin to be updated individually.
        """
    retry: Incomplete
    wait: Incomplete
    __store: Incomplete
    url_identifier: bool
    __cached_url_identifier: Incomplete
    def __init__(self, **kwargs) -> None:
        """Initialize some general configuration that will keep things
        consistent when working with the notifiers that will inherit this
        class."""
    def image_url(self, notify_type: NotifyType, image_size: NotifyImageSize | None = None, logo: bool = False, extension: str | None = None) -> str | None:
        """Returns Image URL if possible."""
    def image_path(self, notify_type: NotifyType, extension: str | None = None) -> str | None:
        """Returns the path of the image if it can."""
    def image_raw(self, notify_type: NotifyType, extension: str | None = None) -> bytes | None:
        """Returns the raw image if it can."""
    def color(self, notify_type: NotifyType, color_type: type | None = None) -> str | int | tuple[int, int, int]:
        """Returns the html color (hex code) associated with the
        notify_type."""
    def ascii(self, notify_type: NotifyType) -> str:
        """Returns the ascii characters associated with the notify_type."""
    def notify(self, *args: Any, **kwargs: Any) -> bool:
        """Performs notification."""
    async def async_notify(self, *args: Any, **kwargs: Any) -> bool:
        """Performs notification for asynchronous callers."""
    def _build_send_calls(self, body: str | None = None, title: str | None = None, notify_type: NotifyType = ..., overflow: str | OverflowMode | None = None, attach: list[str] | AppriseAttachment | None = None, body_format: NotifyFormat | None = None, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
        """Get a list of dictionaries that can be used to call send() or (in
        the future) async_send()."""
    def _apply_overflow(self, body: str | None, title: str | None = None, overflow: str | OverflowMode | None = None, body_format: NotifyFormat | None = None) -> list[dict[str, str]]:
        """
        Apply overflow behaviour (UPSTREAM, TRUNCATE, SPLIT) to title/body.

        Takes the message body and title as input.  This function then
        applies any defined overflow restrictions associated with the
        notification service and may alter the message if/as required.

        The function will always return a list object in the following
        structure:
            [
                {
                    title: 'the title goes here',
                    body: 'the message body goes here',
                },
                {
                    title: 'the title goes here',
                    body: 'the continued message body goes here',
                },
            ]
        """
    def send(self, body: str, title: str = '', notify_type: NotifyType = ..., **kwargs: Any) -> bool:
        """Should preform the actual notification itself."""
    def __len__(self) -> int:
        """Returns the number of HTTP requests this instance will make,
        factoring in the configured retry count.

        Subclasses that override this are automatically wrapped by
        __init_subclass__ to apply the same retry multiplier, so they
        should return their raw target count without worrying about retry.
        """
    def url_parameters(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Provides a default set of parameters to work with.

        This can greatly simplify URL construction in the acommpanied url()
        function in all defined plugin services.
        """
    @staticmethod
    def parse_url(url: str, verify_host: bool = True, plus_to_space: bool = False) -> dict[str, Any] | None:
        """Parses the URL and returns it broken apart into a dictionary.

        This is very specific and customized for Apprise.

        In addition to the fields extracted by URLBase.parse_url(), this
        method extracts the NotifyBase-level query-string parameters:
        ``format``, ``overflow``, ``emojis``, ``tz``, ``store``, ``retry``,
        ``wait``, and ``optional``.  The extracted values are placed
        directly in the returned results dict under their respective keys,
        ready to be consumed by NotifyBase.__init__() (or a subclass).
        Child classes should call this method via ``super()`` and then
        layer their own parameter extraction on top of the returned dict.

        Args:
            url (str): The URL you want to fully parse.
            verify_host (:obj:`bool`, optional): a flag kept with the parsed
                 URL which some child classes will later use to verify SSL
                 keys (if SSL transactions take place).  Unless under very
                 specific circumstances, it is strongly recomended that
                 you leave this default value set to True.

        Returns:
            A dictionary is returned containing the URL fully parsed if
            successful, otherwise None is returned.
        """
    @staticmethod
    def parse_native_url(url: str) -> dict[str, Any] | None:
        """This is a base class that can be optionally over-ridden by child
        classes who can build their Apprise URL based on the one provided by
        the notification service they choose to use.

        The intent of this is to make Apprise a little more userfriendly to
        people who aren't familiar with constructing URLs and wish to use the
        ones that were just provied by their notification serivice that they're
        using.

        This function will return None if the passed in URL can't be matched as
        belonging to the notification service. Otherwise this function should
        return the same set of results that parse_url() does.
        """
    @property
    def store(self):
        """Returns a pointer to our persistent store for use.

        The best use cases are:
         self.store.get('key')
         self.store.set('key', 'value')
         self.store.delete('key1', 'key2', ...)

        You can also access the keys this way:
         self.store['key']

        And clear them:
         del self.store['key']
        """
    @property
    def tzinfo(self) -> tzinfo:
        """Returns our tzinfo file associated with this plugin if set
        otherwise the default timezone is returned.
        """
