from ..asset import AppriseAsset as AppriseAsset
from ..exception import ApprisePluginException as ApprisePluginException
from ..logger import logger as logger
from .parse import is_hostname as is_hostname
from _typeshed import Incomplete

class AppriseWKDException(ApprisePluginException):
    """Raised when a WKD operation fails in an unrecoverable way."""
    def __init__(self, message, error_code: int = 610) -> None: ...

class AppriseWKDController:
    """Web Key Directory controller for automatic OpenPGP key discovery.

    Fetches binary OpenPGP public key material for a given email address
    by querying the two WKD URL forms defined in RFC 9080.  Results are
    cached in memory to avoid redundant network requests within a single
    Apprise session.

    This class is intentionally decoupled from pgpy: it returns raw bytes
    and leaves key parsing to the caller (ApprisePGPController).  That
    separation makes it reusable for any future consumer that works with
    OpenPGP key material.
    """
    _ZB32: str
    max_response_size: int
    default_cache_expiry_sec: Incomplete
    asset: Incomplete
    verify_certificate: Incomplete
    request_timeout: Incomplete
    allow_redirects: Incomplete
    _cache: Incomplete
    def __init__(self, asset=None, verify_certificate: bool = True, request_timeout=(4, 4), allow_redirects: bool = True) -> None:
        """Initialise the WKD controller.

        Args:
            asset: Optional AppriseAsset used for the User-Agent string.
            verify_certificate: Whether TLS certificates are verified.
            request_timeout: (connect, read) timeout tuple passed to
                requests.get().
            allow_redirects: Whether HTTP redirects are followed.  WKD
                deployments commonly redirect (e.g. shared hosting), so
                this defaults to True.  Set to False to require a direct
                response from the WKD host.
        """
    @classmethod
    def zb32_encode(cls, data):
        """Return the z-base32 encoding of *data* (bytes).

        z-base32 is a human-oriented base-32 encoding (RFC 6189) used by
        WKD to build the hash component of the lookup URL.  Each group of
        five bits maps to one character in cls._ZB32.

        For a SHA-1 digest (20 bytes = 160 bits) this always produces
        exactly 32 characters with no padding.
        """
    @classmethod
    def wkd_urls(cls, email):
        """Return the (subdomain_url, direct_url) pair for *email*.

        Returns (None, None) when *email* is not a valid address.
        """
    def fetch(self, email):
        """Return binary OpenPGP key material for *email* via WKD.

        Tries the subdomain method first, then the direct method.
        Returns bytes on success, or None when no key is found or the
        email address is invalid.

        Results are cached in memory for default_cache_expiry_sec seconds
        so repeated calls within a session avoid unnecessary round-trips.
        """
    def _get(self, url):
        """Perform a single GET request and return the response body.

        Returns bytes when the server responds with HTTP 200 and a
        non-empty body within max_response_size, or None for any other
        outcome (network error, non-200 status, empty or oversized body).
        """
    def prune(self) -> None:
        """Remove expired entries from the in-memory cache."""
