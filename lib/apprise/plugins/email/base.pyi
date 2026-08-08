from . import templates as templates
from ...common import NotifyFormat as NotifyFormat, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ...conversion import convert_between as convert_between
from ...logger import logger as logger
from ...url import PrivacyMode as PrivacyMode
from ...utils.parse import is_email as is_email, is_hostname as is_hostname, is_ipaddr as is_ipaddr, parse_bool as parse_bool, parse_emails as parse_emails
from ..base import NotifyBase as NotifyBase
from .common import AppriseEmailException as AppriseEmailException, EmailMessage as EmailMessage, SECURE_MODES as SECURE_MODES, SecureMailMode as SecureMailMode, WebBaseLogin as WebBaseLogin
from _typeshed import Incomplete

class PGPMode:
    """PGP security mode for outbound email."""
    NONE: str
    SIGN: str
    ENCRYPT: str

PGP_MODES: Incomplete
PGP_MODE_DEFAULT: Incomplete

class NotifyEmail(NotifyBase):
    """
    A wrapper to Email Notifications

    """
    service_name: str
    protocol: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    storage_mode: Incomplete
    notify_format: Incomplete
    socket_connect_timeout: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    reply_to: Incomplete
    names: Incomplete
    headers: Incomplete
    from_addr: Incomplete
    smtp_host: Incomplete
    secure_mode: Incomplete
    host: Incomplete
    secure: bool
    port: Incomplete
    pgp_mode: Incomplete
    use_wkd: Incomplete
    pgp: Incomplete
    pgp_key: Incomplete
    pgp_privkey: Incomplete
    def __init__(self, smtp_host=None, from_addr=None, secure_mode=None, targets=None, cc=None, bcc=None, reply_to=None, headers=None, pgp_mode=None, pgp_key=None, pgp_privkey=None, use_wkd: bool = False, **kwargs) -> None:
        """
        Initialize Email Object

        The smtp_host and secure_mode can be automatically detected depending
        on how the URL was built
        """
    user: Incomplete
    def apply_email_defaults(self, secure_mode=None, port=None, **kwargs) -> None:
        """
        A function that prefills defaults based on the email
        it was provided.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs): ...
    def url(self, privacy: bool = False, *args, **kwargs):
        """
        Returns the URL built dynamically based on specified arguments.
        """
    @property
    def url_identifier(self):
        """
        Returns all of the identifiers that make this URL unique from
        another similar one. Targets or end points should never be identified
        here.
        """
    def __len__(self) -> int:
        """
        Returns the number of targets associated with this notification
        """
    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object.

        """
    @staticmethod
    def _get_charset(input_string):
        """
        Get utf-8 charset if non ascii string only

        Encode an ascii string to utf-8 is bad for email deliverability
        because some anti-spam gives a bad score for that
        like SUBJ_EXCESS_QP flag on Rspamd
        """
    @staticmethod
    def prepare_emails(subject, body, from_addr, to, cc: set | None = None, bcc: set | None = None, reply_to: set | None = None, smtp_host=None, notify_format=..., attach=None, headers: dict | None = None, names=None, pgp=None, pgp_mode=..., tzinfo=None):
        """
        Generator for emails
            from_addr: must be in format: (from_name, from_addr)
            to: must be in the format:
                 [(to_name, to_addr), (to_name, to_addr)), ...]
            cc: must be a set of email addresses
            bcc: must be a set of email addresses
            reply_to: must be either None, or an email address
            smtp_host: This is used to generate the email's Message-ID. Set
                       this correctly to avoid getting flagged as Spam
            notify_format: can be either 'text' or 'html'
            attach: must be of class AppriseAttachment
            headers: Optionally provide a dictionary of additional headers you
                     would like to include in the email payload
            names: This is a dictionary of email addresses as keys and the
                   Names to associate with them when sending the email.
                   This is cross referenced for the cc and bcc lists
            pgp:      ApprisePGPController for signing and/or encrypting
                      email via Pretty Good Privacy.  Pass None to skip.
            pgp_mode: PGPMode string controlling what PGP operation to
                      perform.  PGPMode.ENCRYPT encrypts (existing
                      behaviour).  PGPMode.SIGN signs with the sender's
                      private key and opportunistically encrypts when a
                      recipient public key is available.
        """
    @staticmethod
    def runtime_deps():
        """Return a tuple of top-level Python package names that this plugin
        imported as optional runtime dependencies.
        """
