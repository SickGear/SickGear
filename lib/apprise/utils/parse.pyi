from .disk import tidy_path as tidy_path
from _typeshed import Incomplete

VALID_URL_RE: Incomplete
VALID_QUERY_RE: Incomplete
STRING_DELIMITERS: str
STRING_DELIMITERS_NO_WS: str
NOTIFY_CUSTOM_ADD_TOKENS: Incomplete
NOTIFY_CUSTOM_DEL_TOKENS: Incomplete
NOTIFY_CUSTOM_COLON_TOKENS: Incomplete
GET_SCHEMA_RE: Incomplete
URL_DETAILS_RE: Incomplete
GET_EMAIL_RE: Incomplete
IS_PHONE_NO: Incomplete
PHONE_NO_DETECTION_RE: Incomplete
IS_DOMAIN_SERVICE_TARGET: Incomplete
DOMAIN_SERVICE_TARGET_DETECTION_RE: Incomplete
PHONE_NO_WPREFIX_DETECTION_RE: Incomplete
IS_CALL_SIGN: Incomplete
CALL_SIGN_DETECTION_RE: Incomplete
URL_DETECTION_RE: Incomplete
EMAIL_DETECTION_RE: Incomplete
UUID4_RE: Incomplete
VALID_PYTHON_FILE_RE: Incomplete
REGEX_VALIDATE_LOOKUP: Incomplete

def is_ipaddr(addr, ipv4: bool = True, ipv6: bool = True):
    """Validates against IPV4 and IPV6 IP Addresses."""
def is_hostname(hostname, ipv4: bool = True, ipv6: bool = True, underscore: bool = True):
    """Validate hostname."""
def is_uuid(uuid):
    """Determine if the specified entry is uuid v4 string.

    Args:
        address (str): The string you want to check.

    Returns:
        bool: Returns False if the specified element is not a uuid otherwise
              it returns True
    """
def is_domain_service_target(entry, domain: str = 'notify'):
    """Determine if the specified entry a domain.service:target type

    Expects a string containing the following formats:
      - service
      - service:target
      - service:target1,target2
      - domain.service:target
      - domain.service:target1,target2

    Args:
        entry (str): The string you want to check.

    Returns:
        bool: Returns False if the entry specified is domain.service:target
    """
def is_phone_no(phone, min_len: int = 10):
    """Determine if the specified entry is a phone number.

    Args:
        phone (str): The string you want to check.
        min_len (int): Defines the smallest expected length of the phone
                       before it's to be considered invalid. By default
                       the phone number can't be any larger then 14

    Returns:
        bool: Returns False if the address specified is not a phone number
              and a dictionary of the parsed phone number if it is as:
                {
                    'country': '1',
                    'area': '800',
                    'line': '1234567',
                    'full': '18001234567',
                    'pretty': '+1 800-123-4567',
                }

        Non conventional numbers such as 411 would look like provided that
        `min_len` is set to at least a 3:
                {
                    'country': '',
                    'area': '',
                    'line': '411',
                    'full': '411',
                    'pretty': '411',
                }
    """
def is_call_sign(callsign):
    """Determine if the specified entry is a ham radio call sign.

    Args:
        callsign (str): The string you want to check.

    Returns:
        bool: Returns False if the enry specified is not a callsign
    """
def is_email(address):
    """Determine if the specified entry is an email address.

    Args:
        address (str): The string you want to check.

    Returns:
        bool: Returns False if the address specified is not an email address
              and a dictionary of the parsed email if it is as:
                {
                    'name': 'Parse Name'
                    'email': 'user@domain.com'
                    'full_email': 'label+user@domain.com'
                    'label': 'label'
                    'user': 'user',
                    'domain': 'domain.com'
                }
    """
def parse_qsd(qs, simple: bool = False, plus_to_space: bool = False, sanitize: bool = True):
    """Query String Dictionary Builder.

    A custom implimentation of the parse_qsl() function already provided by
    Python.  This function is slightly more light weight and gives us more
    control over parsing out arguments such as the plus/+ symbol at the head of
    a key/value pair.

    qs should be a query string part made up as part of the URL such as
    a=1&c=2&d=

    a=1 gets interpreted as { 'a': '1' } a=  gets interpreted as { 'a': '' } a
    gets interpreted as { 'a': '' }

     This function returns a result object that fits with the apprise expected
    parameters (populating the 'qsd' portion of the dictionary

    if simple is set to true, then a ONE dictionary is returned and is not sub-
    parsed for additional elements

    plus_to_space will cause all `+` references to become a space as per normal
    URL Encoded defininition. Normal URL parsing applies this, but `+` is very
    actively used character with passwords, api keys, tokens, etc.  So Apprise
    does not do this by default.

    if sanitize is set to False, then kwargs are not placed into lowercase
    """
def parse_url(url, default_schema: str = 'http', verify_host: bool = True, strict_port: bool = False, simple: bool = False, plus_to_space: bool = False, sanitize: bool = True):
    """A function that greatly simplifies the parsing of a url specified by the
    end user.

    Valid syntaxes are:
       <schema>://<user>@<host>:<port>/<path>
       <schema>://<user>:<passwd>@<host>:<port>/<path>
       <schema>://<host>:<port>/<path>
       <schema>://<host>/<path>
       <schema>://<host>
       <host>

    Argument parsing is also supported:
       <schema>://<user>@<host>:<port>/<path>?key1=val&key2=val2
       <schema>://<user>:<passwd>@<host>:<port>/<path>?key1=val&key2=val2
       <schema>://<host>:<port>/<path>?key1=val&key2=val2
       <schema>://<host>/<path>?key1=val&key2=val2
       <schema>://<host>?key1=val&key2=val2

    The function returns a simple dictionary with all of
    the parsed content within it and returns 'None' if the
    content could not be extracted.

    The output of 'http://hostname' would look like:
       {
         'schema': 'http',
         'url': 'http://hostname',
         'host': 'hostname',

         'user': None,
         'password': None,
         'port': None,
         'fullpath': None,
         'path': None,
         'query': None,

         'qsd': {},

         'qsd+': {},
         'qsd-': {},
         'qsd:': {}
       }

    The simple switch cleans the dictionary response to only include the
    fields that were detected.

    The output of 'http://hostname' with the simple flag set would look like:
       {
         'schema': 'http',
         'url': 'http://hostname',
         'host': 'hostname',
       }

    If the URL can't be parsed then None is returned

    If sanitize is set to False, then kwargs are not placed in lowercase
    and wrapping whitespace is not removed
    """
def parse_bool(arg, default: bool = False):
    """Support string based boolean settings.

    If the content could not be parsed, then the default is returned.
    """
def parse_domain_service_targets(*args, store_unparseable: bool = True, domain: str = 'notify', **kwargs):
    """
    Takes a string containing the following formats separated by space
      - service
      - service:target
      - service:target1,target2
      - domain.service:target
      - domain.service:target1,target2

      If no domain is parsed, the default domain is returned.

      Targets can be comma separated (if multiple are to be defined)
    """
def parse_phone_no(*args, store_unparseable: bool = True, prefix: bool = False, **kwargs):
    """Takes a string containing phone numbers separated by comma's and/or
    spaces and returns a list."""
def parse_call_sign(*args, store_unparseable: bool = True, **kwargs):
    """Takes a string containing ham radio call signs separated by comma and/or
    spacesand returns a list."""
def parse_emails(*args, store_unparseable: bool = True, **kwargs):
    """Takes a string containing emails separated by comma's and/or spaces and
    returns a list."""
def url_assembly(encode: bool = False, **kwargs):
    """This function reverses the parse_url() function by taking in the
    provided result set and re-assembling a URL."""
def urlencode(query, doseq: bool = False, safe: str = '', encoding=None, errors=None):
    """Convert a mapping object or a sequence of two-element tuples.

    Wrapper to Python's unquote while remaining compatible with both
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
def parse_urls(*args, store_unparseable: bool = True, **kwargs):
    """Takes a string containing URLs separated by comma's and/or spaces and
    returns a list."""
def parse_list(*args, cast=None, allow_whitespace: bool = True, sort: bool = True):
    """Take a string list and break it into a delimited list of arguments. This
    funciton also supports the processing of a list of delmited strings and
    will always return a unique set of arguments. Duplicates are always
    combined in the final results.

    You can append as many items to the argument listing for
    parsing.

    Hence: parse_list('.mkv, .iso, .avi') becomes:
        ['.mkv', '.iso', '.avi']

    Hence: parse_list('.mkv, .iso, .avi', ['.avi', '.mp4']) becomes:
        ['.mkv', '.iso', '.avi', '.mp4']

    The parsing is very forgiving and accepts spaces, slashes, commas
    semicolons, and pipes as delimiters
    """
def validate_regex(value, regex: str = '[^\\s]+', flags=..., strip: bool = True, fmt=None):
    """A lot of the tokens, secrets, api keys, etc all have some regular
    expression validation they support.  This hashes the regex after it's
    compiled and returns it's content if matched, otherwise it returns None.

    This function greatly increases performance as it prevents apprise modules
    from having to pre-compile all of their regular expressions.

    value is the element being tested regex is the regular expression to be
    compiled and tested. By default  we extract the first chunk of code while
    eliminating surrounding  whitespace (if present)

    flags is the regular expression flags that should be applied format is used
    to alter the response format if the regular  expression matches. You
    identify your format using {tags}.  Effectively nesting your ID's between
    {}. Consider a regex of:   '(?P<year>[0-9]{2})[0-9]+(?P<value>[A-Z])' to
    which you could set your format up as '{value}-{year}'. This would
    substitute the matched groups and format a response.
    """
