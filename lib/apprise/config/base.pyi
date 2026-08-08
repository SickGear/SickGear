from .. import common as common, plugins as plugins
from ..asset import AppriseAsset as AppriseAsset
from ..logger import logging as logging
from ..manager_config import ConfigurationManager as ConfigurationManager
from ..manager_plugins import NotificationManager as NotificationManager
from ..tag import AppriseTag as AppriseTag
from ..url import URLBase as URLBase
from ..utils.cwe312 import cwe312_url as cwe312_url
from ..utils.parse import GET_SCHEMA_RE as GET_SCHEMA_RE, parse_bool as parse_bool, parse_list as parse_list, parse_urls as parse_urls
from ..utils.time import zoneinfo as zoneinfo
from _typeshed import Incomplete
from collections import deque as deque

VALID_TOKEN: Incomplete
N_MGR: Incomplete
C_MGR: Incomplete

class ConfigBase(URLBase):
    """This is the base class for all supported configuration sources."""
    encoding: str
    default_config_format: Incomplete
    config_format: Incomplete
    max_buffer_size: int
    allow_cross_includes: Incomplete
    config_path: Incomplete
    _cached_time: Incomplete
    _cached_servers: Incomplete
    recursion: Incomplete
    insecure_includes: Incomplete
    cache: Incomplete
    def __init__(self, cache: bool | int = True, recursion: int = 0, insecure_includes: bool = False, **kwargs: object) -> None:
        """Initialize some general logging and common server arguments that
        will keep things consistent when working with the configurations that
        inherit this class.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again.  For local file references
        this makes no difference at all.  But for remote content, this does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled.  Only disable caching
        if you understand the consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.

        recursion defines how deep we recursively handle entries that use the
        `include` keyword. This keyword requires us to fetch more configuration
        from another source and add it to our existing compilation. If the
        file we remotely retrieve also has an `include` reference, we will only
        advance through it if recursion is set to 2 deep.  If set to zero
        it is off.  There is no limit to how high you set this value. It would
        be recommended to keep it low if you do intend to use it.

        insecure_include by default are disabled. When set to True, all
        Apprise Config files marked to be in STRICT mode are treated as being
        in ALWAYS mode.

        Take a file:// based configuration for example, only a file:// based
        configuration can include another file:// based one. because it is set
        to STRICT mode. If an http:// based configuration file attempted to
        include a file:// one it woul fail. However this include would be
        possible if insecure_includes is set to True.

        There are cases where a self hosting apprise developer may wish to load
        configuration from memory (in a string format) that contains 'include'
        entries (even file:// based ones).  In these circumstances if you want
        these 'include' entries to be honored, this value must be set to True.
        """
    def servers(self, asset: AppriseAsset | None = None, **kwargs: object) -> list[plugins.NotifyBase]:
        """Performs reads loaded configuration and returns all of the services
        that could be parsed and loaded."""
    def read(self) -> str | None:
        """This object should be implimented by the child classes."""
    def expired(self) -> bool:
        """Simply returns True if the configuration should be considered as
        expired or False if content should be retrieved."""
    @staticmethod
    def __normalize_tag_groups(group_tags: dict[str, set[str]]) -> None:
        """
        Used to normalize a tag assign map which looks like:
          {
             'group': set('{tag1}', '{group1}', '{tag2}'),
             'group1': set('{tag2}','{tag3}'),
          }

          Then normalized it (merging groups); with respect to the above, the
          output would be:
          {
             'group': set('{tag1}', '{tag2}', '{tag3}),
             'group1': set('{tag2}','{tag3}'),
          }

        """
    @staticmethod
    def parse_url(url: str, verify_host: bool = True) -> dict[str, object] | None:
        """Parses the URL and returns it broken apart into a dictionary.

        This is very specific and customized for Apprise.

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
    def detect_config_format(content: str, **kwargs: object) -> common.ConfigFormat | None:
        """Takes the specified content and attempts to detect the format type.

        The function returns the actual format type if detected, otherwise it
        returns None
        """
    @staticmethod
    def config_parse(content: str, asset: AppriseAsset | None = None, config_format: str | common.ConfigFormat | None = None, **kwargs: object) -> tuple[list[object], list[str]]:
        """Takes the specified config content and loads it based on the
        specified config_format.

        If a format isn't specified, then it is auto detected.
        """
    @staticmethod
    def config_parse_text(content: str, asset: AppriseAsset | None = None) -> tuple[list[object], list[str]]:
        """Parse the specified content as though it were a simple text file
        only containing a list of URLs.

        Return a tuple that looks like (servers, configs) where:
          - servers contains a list of loaded notification plugins
          - configs contains a list of additional configuration files
            referenced.

        You may also optionally associate an asset with the notification.

        The file syntax is:

            #
            # pound/hashtag allow for line comments
            #
            # One or more tags can be idenified using comma's (,) to separate
            # them.
            <Tag(s)>=<URL>

            # Or you can use this format (no tags associated)
            <URL>

            # you can also use the keyword 'include' and identify a
            # configuration location (like this file) which will be included
            # as additional configuration entries when loaded.
            include <ConfigURL>

            # Assign tag contents to a group identifier
            <Group(s)>=<Tag(s)>
        """
    def pop(self, index: int = -1) -> object:
        """Removes an indexed Notification Service from the stack and returns
        it.

        By default, the last element of the list is removed.
        """
    def clear_cache(self) -> None:
        """Cleans cache"""
    @staticmethod
    def _special_token_handler(schema: str, tokens: dict[str, object]) -> dict[str, object]:
        """This function takes a list of tokens and updates them to no longer
        include any special tokens such as +,-, and :

        - schema must be a valid schema of a supported plugin type
        - tokens must be a dictionary containing the yaml entries parsed.

        The idea here is we can post process a set of tokens provided in
        a YAML file where the user provided some of the special keywords.

        We effectivley look up what these keywords map to their appropriate
        value they're expected
        """
    def __getitem__(self, index: int) -> object:
        """Returns the indexed server entry associated with the loaded
        notification servers."""
    def __iter__(self) -> object:
        """Returns an iterator to our server list."""
    def __len__(self) -> int:
        """Returns the total number of servers loaded."""
    def __bool__(self) -> bool:
        """Allows the Apprise object to be wrapped in an 'if statement'.

        True is returned if our content was downloaded correctly.
        """
