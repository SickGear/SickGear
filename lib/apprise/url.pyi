from .asset import AppriseAsset as AppriseAsset
from .logger import logger as logger
from .tag import AppriseTag as AppriseTag
from .utils.parse import parse_bool as parse_bool, parse_list as parse_list, parse_phone_no as parse_phone_no, parse_url as parse_url, urlencode as urlencode
from _typeshed import Incomplete

PATHSPLIT_LIST_DELIM: Incomplete

class PrivacyMode:
    Secret: str
    Outer: str
    Tail: str

HTML_LOOKUP: Incomplete

class URLBase:
    """This is the base class for all URL Manipulation."""
    service_name: Incomplete
    protocol: Incomplete
    secure_protocol: Incomplete
    request_rate_per_sec: int
    socket_connect_timeout: float
    socket_read_timeout: float
    url_identifier: Incomplete
    __cached_url_identifier: bool
    tags: Incomplete
    verify_certificate: bool
    redirects: bool
    logger = logger
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    asset: Incomplete
    schema: Incomplete
    secure: Incomplete
    host: Incomplete
    port: Incomplete
    user: Incomplete
    password: Incomplete
    fullpath: Incomplete
    _last_io_datetime: Incomplete
    def __init__(self, asset=None, **kwargs) -> None:
        """Initialize some general logging and common server arguments that
        will keep things consistent when working with the children that inherit
        this class."""
    def throttle(self, last_io=None, wait=None) -> None:
        """A common throttle control.

        if a wait is specified, then it will force a sleep of the specified
        time if it is larger then the calculated throttle time.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Assembles the URL associated with the notification based on the
        arguments provied."""
    def url_id(self, lazy: bool = True, hash_engine=...):
        """Returns a unique URL identifier that representing the Apprise URL
        itself. The url_id is always a hash string or None if it can't be
        generated.

        The idea is to only build the ID based on the credentials or specific
        elements relative to the URL itself. The URL ID should never factor in
        (or else it's a bug) the following:
          - any targets defined
          - all GET parameters options unless they explicitly change the
            complete function of the code.

             For example: GET parameters like ?image=false&avatar=no should
             have no bearing in the uniqueness of the Apprise URL Identifier.

             Consider plugins where some get parameters completely change
             how the entire upstream comunication works such as slack:// and
             matrix:// which has a mode. In these circumstances, they should
             be considered in he unique generation.

        The intention of this function is to help align Apprise URLs that are
        common with one another and therefore can share the same persistent
        storage even when subtle changes are made to them.

        Hence the following would all return the same URL Identifier:
             json://abc/def/ghi?image=no
             json://abc/def/ghi/?test=yes&image=yes
        """
    def __contains__(self, tags) -> bool:
        """Returns true if the tag specified is associated with this
        notification.

        tag can also be a tuple, set, and/or list
        """
    def __str__(self) -> str:
        """Returns the url path."""
    @staticmethod
    def escape_html(html, convert_new_lines: bool = False, whitespace: bool = True):
        """Takes html text as input and escapes it so that it won't conflict
        with any xml/html wrapping characters.

        Args:
            html (str): The HTML code to escape
            convert_new_lines (:obj:`bool`, optional): escape new lines (
)
            whitespace (:obj:`bool`, optional): escape whitespace

        Returns:
            str: The escaped html
        """
    @staticmethod
    def unquote(content, encoding: str = 'utf-8', errors: str = 'replace'):
        """Replace %xx escapes by their single-character equivalent. The
        optional encoding and errors parameters specify how to decode percent-
        encoded sequences.

        Wrapper to Python's `unquote` while remaining compatible with both
        Python 2 & 3 since the reference to this function changed between
        versions.

        Note: errors set to 'replace' means that invalid sequences are
              replaced by a placeholder character.

        Args:
            content (str): The quoted URI string you wish to unquote
            encoding (:obj:`str`, optional): encoding type
            errors (:obj:`str`, errors): how to handle invalid character found
                in encoded string (defined by encoding)

        Returns:
            str: The unquoted URI string
        """
    @staticmethod
    def quote(content, safe: str = '/', encoding=None, errors=None):
        """Replaces single character non-ascii characters and URI specific ones
        by their %xx code.

        Wrapper to Python's `quote` while remaining compatible with both
        Python 2 & 3 since the reference to this function changed between
        versions.

        Args:
            content (str): The URI string you wish to quote
            safe (str): non-ascii characters and URI specific ones that you
                        do not wish to escape (if detected). Setting this
                        string to an empty one causes everything to be
                        escaped.
            encoding (:obj:`str`, optional): encoding type
            errors (:obj:`str`, errors): how to handle invalid character found
                in encoded string (defined by encoding)

        Returns:
            str: The quoted URI string
        """
    @staticmethod
    def pprint(content, privacy: bool = True, mode=..., quote: bool = True, safe: str = '/', encoding=None, errors=None):
        """Privacy Print is used to mainpulate the string before passing it
        into part of the URL.  It is used to mask/hide private details such as
        tokens, passwords, apikeys, etc from on-lookers.  If the privacy=False
        is set, then the quote variable is the next flag checked.

        Quoting is never done if the privacy flag is set to true to avoid
        skewing the expected output.
        """
    @staticmethod
    def urlencode(query, doseq: bool = False, safe: str = '', encoding=None, errors=None):
        """Convert a mapping object or a sequence of two-element tuples.

        Wrapper to Python's `urlencode` while remaining compatible with both
        Python 2 & 3 since the reference to this function changed between
        versions.

        The resulting string is a series of key=value pairs separated by '&'
        characters, where both key and value are quoted using the quote()
        function.

        Note: If the dictionary entry contains an entry that is set to None
              it is not included in the final result set. If you want to
              pass in an empty variable, set it to an empty string.

        Args:
            query (str): The dictionary to encode
            doseq (:obj:`bool`, optional): Handle sequences
            safe (:obj:`str`): non-ascii characters and URI specific ones that
                you do not wish to escape (if detected). Setting this string
                to an empty one causes everything to be escaped.
            encoding (:obj:`str`, optional): encoding type
            errors (:obj:`str`, errors): how to handle invalid character found
                in encoded string (defined by encoding)

        Returns:
            str: The escaped parameters returned as a string
        """
    @staticmethod
    def split_path(path, unquote: bool = True):
        """Splits a URL up into a list object.

        Parses a specified URL and breaks it into a list.

        Args:
            path (str): The path to split up into a list.
            unquote (:obj:`bool`, optional): call unquote on each element
                 added to the returned list.

        Returns:
            list: A list containing all of the elements in the path
        """
    @staticmethod
    def parse_list(content, allow_whitespace: bool = True, unquote: bool = True):
        """A wrapper to utils.parse_list() with unquoting support.

        Parses a specified set of data and breaks it into a list.

        Args:
            content (str): The path to split up into a list. If a list is
                 provided, then it's individual entries are processed.

            allow_whitespace (:obj:`bool`, optional): whitespace is to be
                 treated as a delimiter

            unquote (:obj:`bool`, optional): call unquote on each element
                 added to the returned list.

        Returns:
            list: A unique list containing all of the elements in the path
        """
    @staticmethod
    def parse_phone_no(content, unquote: bool = True, prefix: bool = False):
        """A wrapper to utils.parse_phone_no() with unquoting support.

        Parses a specified set of data and breaks it into a list.

        Args:
            content (str): The path to split up into a list. If a list is
                 provided, then it's individual entries are processed.

            unquote (:obj:`bool`, optional): call unquote on each element
                 added to the returned list.

        Returns:
            list: A unique list containing all of the elements in the path
        """
    @property
    def app_id(self): ...
    @property
    def app_desc(self): ...
    @property
    def app_url(self): ...
    @property
    def request_timeout(self):
        """This is primarily used to fullfill the `timeout` keyword argument
        that is used by requests.get() and requests.put() calls."""
    @property
    def request_auth(self):
        """This is primarily used to fullfill the `auth` keyword argument that
        is used by requests.get() and requests.put() calls."""
    @property
    def request_url(self):
        """Assemble a simple URL that can be used by the requests library."""
    def url_parameters(self, *args, **kwargs):
        """Provides a default set of args to work with. This can greatly
        simplify URL construction in the acommpanied url() function.

        The following property returns a dictionary (of strings) containing all
        of the parameters that can be set on a URL and managed through this
        class.
        """
    @staticmethod
    def post_process_parse_url_results(results):
        """After parsing the URL, this function applies a bit of extra logic to
        support extra entries like `pass` becoming `password`, etc.

        This function assumes that parse_url() was called previously setting up
        the basics to be checked
        """
    @staticmethod
    def parse_url(url, verify_host: bool = True, plus_to_space: bool = False, strict_port: bool = False, sanitize: bool = True):
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
    def http_response_code_lookup(code, response_mask=None):
        """Parses the interger response code returned by a remote call from a
        web request into it's human readable string version.

        You can over-ride codes or add new ones by providing your own
        response_mask that contains a dictionary of integer -> string mapped
        variables
        """
    def __len__(self) -> int:
        """Should be over-ridden and allows the tracking of how many targets
        are associated with each URLBase object.

        Default is always 1
        """
    def schemas(self):
        """A simple function that returns a set of all schemas associated with
        this object based on the object.protocol and object.secure_protocol."""
