from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..asset import AppriseAsset as AppriseAsset
from ..exception import ApprisePluginException as ApprisePluginException
from ..logger import logger as logger
from _typeshed import Incomplete

def _ensure_imghdr_shim() -> None:
    """Install a minimal imghdr shim when the module is absent.

    pgpy 0.6.0 imports imghdr, which was removed from the standard
    library in Python 3.13 (PEP 594). pgpy's only use of imghdr is
    ImageEncoding.encodingof(), which Apprise never calls. Returning
    None from what() is the same safe fallback the library uses
    internally for non-JPEG data.
    """

PGP_SUPPORT: bool

class ApprisePGPException(ApprisePluginException):
    """Thrown when there is an error with the Pretty Good Privacy
    Controller."""
    def __init__(self, message, error_code: int = 602) -> None: ...

class ApprisePGPController:
    """Pretty Good Privacy Controller Tool for the Apprise Library."""
    max_pgp_public_key_size: int
    max_pgp_private_key_size: int
    __key_lookup: Incomplete
    path: Incomplete
    email: Incomplete
    wkd: Incomplete
    asset: Incomplete
    _pub_keyfile: Incomplete
    _prv_keyfile: Incomplete
    def __init__(self, path, pub_keyfile=None, prv_keyfile=None, email=None, asset=None, wkd=None, **kwargs) -> None:
        """Path should be the directory keys can be written and read from such
        as <notifyobject>.store.path.

        Optionally additionally specify a pub_keyfile and/or prv_keyfile to
        use explicit key files, and/or an AppriseWKDController to enable Web
        Key Directory key discovery when no local key is found.
        """
    def keygen(self, email=None, name=None, force: bool = False):
        """Generates a set of keys based on email configured."""
    def _pub_key_candidates(self, *emails):
        """Returns the ordered list of candidate public-key filenames to
        search, highest priority first.

        Shared by public_keyfile() and the diagnostic warning in public_key()
        so both always reflect exactly the same search order.
        """
    def _prv_key_candidates(self):
        """Returns the ordered list of candidate private-key filenames to
        search, highest priority first.

        Shared by private_keyfile() and the diagnostic warning in private_key()
        so both always reflect exactly the same search order.
        """
    def public_keyfile(self, *emails):
        """Returns the first match of a useable public key based emails
        provided."""
    def private_keyfile(self):
        """Returns the path to the private key file if one can be found.

        Returns the explicit path when prv_keyfile was provided, looks for a
        matching auto-generated key in self.path otherwise.  Returns False
        when an explicit keyfile was given but could not be accessed, and
        None when no key file could be located at all.
        """
    def private_key(self):
        """Loads and returns the PGP private key object.

        Reads from the explicit prv_keyfile if one was provided, otherwise
        scans the persistent storage path for an auto-generated private key.
        Returns None when no usable private key could be found or loaded.
        Passphrase-protected keys are not supported and will be rejected.
        """
    def sign(self, message):
        """Creates a detached PGP signature for the given message string.

        Returns a (signature_str, micalg) tuple on success where
        signature_str is the armored PGP signature block and micalg is the
        MIME hash algorithm label (e.g. 'pgp-sha256') for the
        Content-Type header of the multipart/signed container.
        Returns None when signing is not possible.
        """
    def _fetch_wkd_key(self, *emails):
        """Attempt a Web Key Directory lookup for each email in turn.

        Returns a pgpy.PGPKey on the first successful fetch, or None if
        WKD is not configured, no emails are provided, or all lookups
        fail.
        """
    def public_key(self, *emails, autogen=None):
        """Opens a spcified pgp public file and returns the key from it which
        is used to encrypt the message."""
    def encrypt(self, message, *emails, autogen=None):
        """If provided a path to a pgp-key, content is encrypted.

        Pass autogen=False to suppress key auto-generation during the
        public-key lookup.  This is used in sign mode for opportunistic
        encryption: only encrypt when a pre-existing key is found.
        """
    def prune(self) -> None:
        """Prunes old entries from the public_key index."""
    @property
    def pub_keyfile(self):
        """Returns the Public Keyfile Path if set otherwise it returns None
        This property returns False if a keyfile was provided, but was
        invalid."""
    @property
    def prv_keyfile(self):
        """Returns the Private Keyfile Path if set, otherwise returns None.
        Returns False when an explicit keyfile was provided but could not
        be accessed."""
