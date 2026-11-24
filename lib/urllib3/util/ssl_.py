from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import os
import re
import socket
import sys
import threading
import typing
import warnings
from binascii import Error as BinasciiError
from binascii import unhexlify
from concurrent.futures import Future
from functools import lru_cache
from pathlib import Path

from .._constant import MOZ_INTERMEDIATE_CIPHERS
from ..contrib.imcc import load_cert_chain as _ctx_load_cert_chain
from ..exceptions import ProxySchemeUnsupported, SSLError
from .url import _BRACELESS_IPV6_ADDRZ_RE, _IPV4_RE

from ..contrib.anytls import ssl, IS_NONSTDLIB, stdlib_ssl

if typing.TYPE_CHECKING:
    from ssl import VerifyMode

    from typing_extensions import Literal

    from .ssltransport import SSLTransport as SSLTransportType

SSLContext = None
SSLTransport = None
HAS_NEVER_CHECK_COMMON_NAME = False
ALPN_PROTOCOLS = ["http/1.1"]
DEFAULT_CIPHERS = MOZ_INTERMEDIATE_CIPHERS

_TYPE_VERSION_INFO = typing.Tuple[int, int, int, str, int]

IS_PYOPENSSL = False  # kept for BC reason

# Maps the length of a digest to a possible hash function producing this digest
HASHFUNC_MAP = {
    length: getattr(hashlib, algorithm, None)
    for length, algorithm in (
        (32, "md5"),
        (40, "sha1"),
        (64, "sha256"),
    )
}


def _compute_key_ctx_build(
    *args: str | bytes | int | Path | list[str] | bool | dict[str, typing.Any] | None,
) -> int:
    """We want a dedicated hashing techniques to cache ssl ctx, so that they are reusable across the runtime."""
    key: str = ""

    for arg in args:
        if arg is None:
            key += "\x00"
            continue
        if isinstance(
            arg,
            (
                str,
                bytes,
            ),
        ):
            key += str(hash(arg))
            continue
        if isinstance(arg, Path):
            # a file/directory may change at any moment
            # we must have a clue if the key cache
            # must be invalidated.
            key += str(arg)
            if arg.is_dir():
                try:
                    key += str(
                        max(
                            [arg.stat().st_mtime]
                            + [p.stat().st_mtime for p in arg.iterdir()],
                            default=arg.stat().st_mtime,
                        )
                    )
                except OSError:  # Defensive: CA directory entries can disappear during metadata inspection.
                    pass
            else:
                try:
                    key += str(Path(arg).stat().st_mtime)
                except OSError:
                    pass  # Defensive: race condition possible
        if isinstance(arg, (int, bool)):
            key += str(arg)
            continue
        if isinstance(arg, dict):
            key += str(arg)
            continue
        if isinstance(arg, list):
            key += "("
            for item in arg:
                key += item
            key += ")"

    return hash(key)


class _CacheableSSLContext:
    def __init__(self, maxsize: int | None = 32) -> None:
        self._maxsize = maxsize
        self._container: dict[int, ssl.SSLContext] = {}
        self._cursor: int | None = None
        self._lock: threading.RLock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._cursor = None
            self._container = {}

    @contextlib.contextmanager
    def lock(
        self,
        *args: str
        | bytes
        | Path
        | int
        | list[str]
        | bool
        | dict[str, typing.Any]
        | None,
    ) -> typing.Generator[None]:
        key = _compute_key_ctx_build(*args)
        with self._lock:
            self._cursor = key
            try:
                yield
            finally:
                self._cursor = None

    def get(self) -> ssl.SSLContext | None:
        with self._lock:
            if self._cursor is None:
                raise OSError("You MUST start WITH lock()")

            if self._cursor in self._container:
                return self._container[self._cursor]

            return None

    def save(
        self,
        ctx: ssl.SSLContext,
    ) -> None:
        with self._lock:
            if self._cursor is None:
                raise OSError("You MUST start WITH lock()")

            self._container[self._cursor] = ctx

            if self._maxsize and len(self._container) > self._maxsize:
                self._container.pop(next(self._container.keys().__iter__()))


_SSLContextCache = _CacheableSSLContext()


def _is_bpo_43522_fixed(
    implementation_name: str, version_info: _TYPE_VERSION_INFO
) -> bool:
    """Return True for CPython 3.8.9+, 3.9.3+ or 3.10+ where setting
    SSLContext.hostname_checks_common_name to False works.

    PyPy 7.3.7 doesn't work as it doesn't ship with OpenSSL 1.1.1l+
    so we're waiting for a version of PyPy that works before
    allowing this function to return 'True'.

    Outside of CPython and PyPy we don't know which implementations work
    or not so we conservatively use our hostname matching as we know that works
    on all implementations.

    https://github.com/urllib3/urllib3/issues/2192#issuecomment-821832963
    https://foss.heptapod.net/pypy/pypy/-/issues/3539#
    """
    if implementation_name != "cpython":
        return False

    major_minor = version_info[:2]
    micro = version_info[2]
    return (
        (major_minor == (3, 8) and micro >= 9)
        or (major_minor == (3, 9) and micro >= 3)
        or major_minor >= (3, 10)
    )


def _is_has_never_check_common_name_reliable(
    openssl_version: str,
    openssl_version_number: int,
    implementation_name: str,
    version_info: _TYPE_VERSION_INFO,
) -> bool:
    # As of May 2023, all released versions of LibreSSL fail to reject certificates with
    # only common names, see https://github.com/urllib3/urllib3/pull/3024
    # Rustls has correct hostname verification and doesn't suffer from the
    # LibreSSL/old-OpenSSL common name checking bugs that this function guards against.
    if openssl_version.startswith("Rustls "):
        return True
    is_openssl = openssl_version.startswith("OpenSSL ")
    # Before fixing OpenSSL issue #14579, the SSL_new() API was not copying hostflags
    # like X509_CHECK_FLAG_NEVER_CHECK_SUBJECT, which tripped up CPython.
    # https://github.com/openssl/openssl/issues/14579
    # This was released in OpenSSL 1.1.1l+ (>=0x101010cf)
    is_openssl_issue_14579_fixed = openssl_version_number >= 0x101010CF

    return is_openssl and (
        is_openssl_issue_14579_fixed
        or _is_bpo_43522_fixed(implementation_name, version_info)
    )


# Mapping from 'ssl.PROTOCOL_TLSX' to 'TLSVersion.X'
_SSL_VERSION_TO_TLS_VERSION: dict[int, int] = {}

try:  # Do we have ssl at all?
    if ssl is None:
        raise ImportError("ssl")

    CERT_REQUIRED = ssl.CERT_REQUIRED
    HAS_NEVER_CHECK_COMMON_NAME = ssl.HAS_NEVER_CHECK_COMMON_NAME
    OP_NO_COMPRESSION = ssl.OP_NO_COMPRESSION
    OP_NO_TICKET = ssl.OP_NO_TICKET
    OPENSSL_VERSION = ssl.OPENSSL_VERSION
    OPENSSL_VERSION_NUMBER = ssl.OPENSSL_VERSION_NUMBER
    PROTOCOL_TLS = ssl.PROTOCOL_TLS
    PROTOCOL_TLS_CLIENT = ssl.PROTOCOL_TLS_CLIENT
    OP_NO_SSLv2 = ssl.OP_NO_SSLv2
    OP_NO_SSLv3 = ssl.OP_NO_SSLv3
    SSLContext = ssl.SSLContext
    TLSVersion = ssl.TLSVersion

    OP_NO_RENEGOTIATION = getattr(ssl, "OP_NO_RENEGOTIATION", None)  # noqa:

    PROTOCOL_SSLv23 = PROTOCOL_TLS

    # Setting SSLContext.hostname_checks_common_name = False didn't work before CPython
    # 3.8.9, 3.9.3, and 3.10 (but OK on PyPy) or OpenSSL 1.1.1l+
    if HAS_NEVER_CHECK_COMMON_NAME and not _is_has_never_check_common_name_reliable(
        OPENSSL_VERSION,
        OPENSSL_VERSION_NUMBER,
        sys.implementation.name,
        sys.version_info,
    ):
        HAS_NEVER_CHECK_COMMON_NAME = False

    # Need to be careful here in case old TLS versions get
    # removed in future 'ssl' module implementations.
    for attr in ("TLSv1", "TLSv1_1", "TLSv1_2"):
        try:
            _SSL_VERSION_TO_TLS_VERSION[getattr(ssl, f"PROTOCOL_{attr}")] = getattr(
                TLSVersion, attr
            )
        except AttributeError:  # Defensive:
            continue

    from .ssltransport import SSLTransport  # type: ignore[assignment]

    # Python built against (very) restrictive ssl library may ship with a single TLS version
    # thus, it seems to make attribute "minimum_version" and "maximum_version" unavailable.
    # note: it raises an exception! maybe a CPython bug.
    SUPPORT_MIN_MAX_TLS_VERSION = hasattr(ssl.SSLContext, "maximum_version")

    IS_FIPS: bool = "fips" in OPENSSL_VERSION.lower()

    # not necessarily declared in version string
    if IS_FIPS is False:
        if hasattr(ssl, "FIPS_mode") and callable(ssl.FIPS_mode):
            IS_FIPS = bool(ssl.FIPS_mode())  # Defensive: legacy FIPS detection hook.
        else:  # messy detection
            try:
                from _hashlib import openssl_md5

                try:
                    openssl_md5(b"x")
                except ValueError:
                    IS_FIPS = True
            except ImportError:
                pass

            if not IS_FIPS:
                # md5 is available in Python 3.7 -- 3.14, so far. unless removed by FIPS patch
                IS_FIPS = 32 not in HASHFUNC_MAP

except ImportError:
    OP_NO_COMPRESSION = 0x20000  # type: ignore[assignment]
    OP_NO_TICKET = 0x4000  # type: ignore[assignment]
    OP_NO_SSLv2 = 0x1000000  # type: ignore[assignment]
    OP_NO_SSLv3 = 0x2000000  # type: ignore[assignment]
    PROTOCOL_SSLv23 = PROTOCOL_TLS = 2  # type: ignore[assignment]
    PROTOCOL_TLS_CLIENT = PROTOCOL_TLS
    OP_NO_RENEGOTIATION = None  # noqa:
    SUPPORT_MIN_MAX_TLS_VERSION = False
    IS_FIPS = False


def assert_fingerprint(cert: bytes | None, fingerprint: str) -> None:
    """
    Checks if given fingerprint matches the supplied certificate.

    :param cert:
        Certificate as bytes object.
    :param fingerprint:
        Fingerprint as string of hexdigits, can be interspersed by colons.
    """

    if cert is None:
        raise SSLError("No certificate for the peer.")

    fingerprint = fingerprint.replace(":", "").lower()
    digest_length = len(fingerprint)
    if digest_length not in HASHFUNC_MAP:
        raise SSLError(f"Fingerprint of invalid length: {fingerprint}")

    hashfunc = HASHFUNC_MAP[digest_length]

    if hashfunc is None:
        raise SSLError(
            f"Hash function implementation unavailable for fingerprint length: {digest_length}. "
            "Hint: your OpenSSL build may not include it for compliance issues."
        )

    # We need encode() here for py32; works on py2 and p33.
    try:
        fingerprint_bytes = unhexlify(fingerprint.encode())
    except BinasciiError as e:
        raise SSLError(e) from e

    cert_digest = hashfunc(cert).digest()

    if not hmac.compare_digest(cert_digest, fingerprint_bytes):
        raise SSLError(
            f'Fingerprints did not match. Expected "{fingerprint}", got "{cert_digest.hex()}"'
        )


def resolve_cert_reqs(candidate: None | int | str) -> VerifyMode:
    """
    Resolves the argument to a numeric constant, which can be passed to
    the wrap_socket function/method from the ssl module.
    Defaults to :data:`ssl.CERT_REQUIRED`.
    If given a string it is assumed to be the name of the constant in the
    :mod:`ssl` module or its abbreviation.
    (So you can specify `REQUIRED` instead of `CERT_REQUIRED`.
    If it's neither `None` nor a string we assume it is already the numeric
    constant which can directly be passed to wrap_socket.
    """
    if candidate is None:
        return CERT_REQUIRED

    if isinstance(candidate, str):
        res = getattr(ssl, candidate, None)
        if res is None:
            res = getattr(ssl, "CERT_" + candidate)
        return res  # type: ignore[no-any-return]

    return candidate  # type: ignore[return-value]


@typing.overload
def resolve_ssl_version(
    candidate: None | int | str,
    *,
    mitigate_tls_version: typing.Literal[True] = True,
) -> ssl.TLSVersion: ...


@typing.overload
def resolve_ssl_version(
    candidate: None | int | str,
    *,
    mitigate_tls_version: typing.Literal[False] = False,
) -> int: ...


def resolve_ssl_version(
    candidate: None | int | str, mitigate_tls_version: bool = False
) -> int | ssl.TLSVersion:
    """
    like resolve_cert_reqs
    """
    if candidate is None:
        if mitigate_tls_version:
            return PROTOCOL_TLS_CLIENT
        return PROTOCOL_TLS

    if isinstance(candidate, str):
        if mitigate_tls_version and hasattr(ssl, "TLSVersion"):
            res = getattr(ssl.TLSVersion, candidate, None)

            if res is not None:
                return res  # type: ignore[no-any-return]

            res = getattr(ssl.TLSVersion, candidate.replace("PROTOCOL_", ""), None)

            if res is not None:
                return res  # type: ignore[no-any-return]

        if mitigate_tls_version and candidate == "PROTOCOL_TLS":
            candidate = "PROTOCOL_TLS_CLIENT"

        res = getattr(ssl, candidate, None)
        if res is None:
            res = getattr(ssl, "PROTOCOL_" + candidate)
        return typing.cast(int, res)

    if mitigate_tls_version:
        if candidate in _SSL_VERSION_TO_TLS_VERSION:
            return _SSL_VERSION_TO_TLS_VERSION[candidate]
        if candidate == PROTOCOL_TLS_CLIENT or candidate == PROTOCOL_TLS:
            return PROTOCOL_TLS_CLIENT
        return ssl.TLSVersion.MAXIMUM_SUPPORTED

    return candidate


def create_urllib3_context(
    ssl_version: int | None = None,
    cert_reqs: int | None = None,
    options: int | None = None,
    ciphers: str | None = None,
    ssl_minimum_version: int | None = None,
    ssl_maximum_version: int | None = None,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
    use_recommended_ciphers: bool = True,
) -> ssl.SSLContext:
    """Creates and configures an :class:`ssl.SSLContext` instance for use with urllib3.

    :param ssl_version:
        The desired protocol version to use. This will default to
        PROTOCOL_TLS_CLIENT which will negotiate the highest protocol that both
        the server and your installation of OpenSSL support.
    :param ssl_minimum_version:
        The minimum version of TLS to be used. Use the 'ssl.TLSVersion' enum for specifying the value.
        By default, it is assigned to 'ssl.TLSVersion.TLSv1_2'.
    :param ssl_maximum_version:
        The maximum version of TLS to be used. Use the 'ssl.TLSVersion' enum for specifying the value.
        Not recommended to set to anything other than 'ssl.TLSVersion.MAXIMUM_SUPPORTED' which is the
        default value.
    :param cert_reqs:
        Whether to require the certificate verification. This defaults to
        ``ssl.CERT_REQUIRED``.
    :param options:
        Specific OpenSSL options. These default to ``ssl.OP_NO_SSLv2``,
        ``ssl.OP_NO_SSLv3``, ``ssl.OP_NO_COMPRESSION``, and ``ssl.OP_NO_TICKET``.
    :param ciphers:
        Which cipher suites to allow the server to select. Defaults to either system configured
        ciphers if OpenSSL 1.1.1+, otherwise uses a secure default set of ciphers.
    :param ssl_backend:
        Force the TLS implementation used to build the context, one of
        ``"rtls"``, ``"utls"`` or ``"ssl"`` (stdlib). Defaults to ``None``,
        which uses the backend resolved by :mod:`urllib3.contrib.anytls`.
        Raises :class:`~urllib3.exceptions.SSLError` if the requested backend
        is not available.
    :param use_recommended_ciphers:
        Apply urllib3-future's recommended cipher list when no cipher list or
        explicit TLS version bounds were provided.
    :returns:
        Constructed SSLContext object with specified options
    :rtype: SSLContext
    """
    if SSLContext is None:
        raise TypeError("Can't create an SSLContext object without an ssl module")

    if ssl_backend is not None:
        from ..contrib import anytls

        active_ssl = (
            anytls.stdlib_ssl if ssl_backend == "ssl" else getattr(anytls, ssl_backend)
        )
        if active_ssl is None:
            raise SSLError(
                f"The requested TLS backend {ssl_backend!r} is not available."
            )
        active_is_nonstdlib = ssl_backend in ("rtls", "utls")
        ssl_context_class = active_ssl.SSLContext
        protocol_tls = active_ssl.PROTOCOL_TLS
        protocol_tls_client = active_ssl.PROTOCOL_TLS_CLIENT
        tls_version = active_ssl.TLSVersion
        cert_required = active_ssl.CERT_REQUIRED
        # Option bit flags are library-specific; use the active backend's
        # values (falling back to the resolved-default constants when absent).
        op_no_sslv2 = getattr(active_ssl, "OP_NO_SSLv2", OP_NO_SSLv2)
        op_no_sslv3 = getattr(active_ssl, "OP_NO_SSLv3", OP_NO_SSLv3)
        op_no_compression = getattr(active_ssl, "OP_NO_COMPRESSION", OP_NO_COMPRESSION)
        op_no_ticket = getattr(active_ssl, "OP_NO_TICKET", OP_NO_TICKET)
    else:
        # Default path: keep using the module-level globals (resolved by
        # anytls at import time, and patchable in tests).
        active_ssl = ssl
        active_is_nonstdlib = IS_NONSTDLIB
        ssl_context_class = SSLContext
        protocol_tls = PROTOCOL_TLS
        protocol_tls_client = PROTOCOL_TLS_CLIENT
        tls_version = TLSVersion
        cert_required = CERT_REQUIRED
        op_no_sslv2 = OP_NO_SSLv2
        op_no_sslv3 = OP_NO_SSLv3
        op_no_compression = OP_NO_COMPRESSION
        op_no_ticket = OP_NO_TICKET

    # This means 'ssl_version' was specified as an exact value.
    if ssl_version not in (None, protocol_tls, protocol_tls_client):
        # Disallow setting 'ssl_version' and 'ssl_minimum|maximum_version'
        # to avoid conflicts.
        if ssl_minimum_version is not None or ssl_maximum_version is not None:
            raise ValueError(
                "Can't specify both 'ssl_version' and either "
                "'ssl_minimum_version' or 'ssl_maximum_version'"
            )

        else:
            if hasattr(active_ssl, "TLSVersion") and isinstance(
                ssl_version, tls_version
            ):
                ssl_minimum_version = ssl_version
                ssl_maximum_version = ssl_version
            else:
                # Use 'ssl_minimum_version' and 'ssl_maximum_version' instead.
                assert ssl_version is not None  # guarded by `not in (None, ...)`
                ssl_minimum_version = _SSL_VERSION_TO_TLS_VERSION.get(
                    ssl_version, tls_version.MINIMUM_SUPPORTED
                )
                ssl_maximum_version = _SSL_VERSION_TO_TLS_VERSION.get(
                    ssl_version, tls_version.MAXIMUM_SUPPORTED
                )

    # PROTOCOL_TLS is deprecated in Python 3.10 so we always use PROTOCOL_TLS_CLIENT
    context: ssl.SSLContext = ssl_context_class(protocol_tls_client)

    # utls (BoringSSL) have a way to propose
    # autoconfiguration of context based
    # on latest browser specs observed
    # over the wire.
    should_use_browser_autoconfig: bool = (
        hasattr(context, "set_fingerprint")
        and ssl_minimum_version is None
        and ssl_maximum_version is None
        and ciphers is None
        and options is None
        and (ssl_version is None or ssl_version in {protocol_tls, protocol_tls_client})
    )
    default_tlsv1_2 = False
    if SUPPORT_MIN_MAX_TLS_VERSION:
        if ssl_minimum_version is not None:
            context.minimum_version = ssl_minimum_version  # type: ignore[assignment]
        else:  # Python <3.10 defaults to 'MINIMUM_SUPPORTED' so explicitly set TLSv1.2 here
            context.minimum_version = tls_version.TLSv1_2
            default_tlsv1_2 = True

        if ssl_maximum_version is not None:
            context.maximum_version = ssl_maximum_version  # type: ignore[assignment]

    # Unless we're given ciphers defer to either system ciphers in
    # the case of OpenSSL 1.1.1+ or use our own secure default ciphers.
    if ciphers:
        context.set_ciphers(ciphers)
    elif use_recommended_ciphers and default_tlsv1_2 and not active_is_nonstdlib:
        context.set_ciphers(MOZ_INTERMEDIATE_CIPHERS)

    # Setting the default here, as we may have no ssl module on import
    cert_reqs = cert_required if cert_reqs is None else cert_reqs

    if options is None:
        options = 0
        # SSLv2 is easily broken and is considered harmful and dangerous
        options |= op_no_sslv2
        # SSLv3 has several problems and is now dangerous
        options |= op_no_sslv3
        # Disable compression to prevent CRIME attacks for OpenSSL 1.0+
        # (issue #309)
        options |= op_no_compression
        # TLSv1.2 only. Unless set explicitly, do not request tickets.
        # This may save some bandwidth on wire, and although the ticket is encrypted,
        # there is a risk associated with it being on wire,
        # if the server is not rotating its ticketing keys properly.
        options |= op_no_ticket

    if should_use_browser_autoconfig:
        context.set_fingerprint("chrome:stable")  # type: ignore[attr-defined]
    else:
        context.options |= options

    # Enable post-handshake authentication for TLS 1.3, see GH #1634. PHA is
    # necessary for conditional client cert authentication with TLS 1.3.
    # The attribute is None for OpenSSL <= 1.1.0 or does not exist in older
    # versions of Python.  We only enable on Python 3.7.4+ or if certificate
    # verification is enabled to work around Python issue #37428
    # See: https://bugs.python.org/issue37428
    if (cert_reqs == cert_required or sys.version_info >= (3, 7, 4)) and getattr(
        context, "post_handshake_auth", None
    ) is not None:
        context.post_handshake_auth = True

    # The order of the below lines setting verify_mode and check_hostname
    # matter due to safe-guards SSLContext has to prevent an SSLContext with
    # check_hostname=True, verify_mode=NONE/OPTIONAL.
    # We always set 'check_hostname=False' for pyOpenSSL so we rely on our own
    # 'ssl.match_hostname()' implementation.
    if cert_reqs == cert_required:
        context.verify_mode = cert_reqs  # type: ignore[assignment]
        context.check_hostname = True
    else:
        context.check_hostname = False
        context.verify_mode = cert_reqs  # type: ignore[assignment]

    if not should_use_browser_autoconfig:
        try:
            context.hostname_checks_common_name = False
        except AttributeError:
            pass

    # Enable logging of TLS session keys via defacto standard environment variable
    # 'SSLKEYLOGFILE', if the feature is available (Python 3.8+). Skip empty values.
    if hasattr(context, "keylog_filename"):
        if "SSLKEYLOGFILE" in os.environ:
            sslkeylogfile = os.path.expandvars(os.environ["SSLKEYLOGFILE"])
        else:
            sslkeylogfile = None

        if sslkeylogfile:
            context.keylog_filename = sslkeylogfile

    return context


@typing.overload
def ssl_wrap_socket(
    sock: socket.socket,
    keyfile: str | None = ...,
    certfile: str | None = ...,
    cert_reqs: int | None = ...,
    ca_certs: str | None = ...,
    server_hostname: str | None = ...,
    ssl_version: int | None = ...,
    ciphers: str | None = ...,
    ssl_context: ssl.SSLContext | None = ...,
    ca_cert_dir: str | None = ...,
    key_password: str | None = ...,
    ca_cert_data: None | str | bytes = ...,
    tls_in_tls: Literal[False] = ...,
    alpn_protocols: list[str] | None = ...,
    certdata: str | bytes | None = ...,
    keydata: str | bytes | None = ...,
    check_hostname: bool | None = ...,
    ssl_minimum_version: int | None = ...,
    ssl_maximum_version: int | None = ...,
    ech_config_list: bytes | None = ...,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = ...,
    use_recommended_ciphers: bool = ...,
) -> ssl.SSLSocket: ...


@typing.overload
def ssl_wrap_socket(
    sock: socket.socket,
    keyfile: str | None = ...,
    certfile: str | None = ...,
    cert_reqs: int | None = ...,
    ca_certs: str | None = ...,
    server_hostname: str | None = ...,
    ssl_version: int | None = ...,
    ciphers: str | None = ...,
    ssl_context: ssl.SSLContext | None = ...,
    ca_cert_dir: str | None = ...,
    key_password: str | None = ...,
    ca_cert_data: None | str | bytes = ...,
    tls_in_tls: bool = ...,
    alpn_protocols: list[str] | None = ...,
    certdata: str | bytes | None = ...,
    keydata: str | bytes | None = ...,
    check_hostname: bool | None = ...,
    ssl_minimum_version: int | None = ...,
    ssl_maximum_version: int | None = ...,
    ech_config_list: bytes | None = ...,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = ...,
    use_recommended_ciphers: bool = ...,
) -> ssl.SSLSocket | SSLTransportType: ...


def ssl_wrap_socket(
    sock: socket.socket,
    keyfile: str | None = None,
    certfile: str | None = None,
    cert_reqs: int | None = None,
    ca_certs: str | None = None,
    server_hostname: str | None = None,
    ssl_version: int | None = None,
    ciphers: str | None = None,
    ssl_context: ssl.SSLContext | None = None,
    ca_cert_dir: str | None = None,
    key_password: str | None = None,
    ca_cert_data: None | str | bytes = None,
    tls_in_tls: bool = False,
    alpn_protocols: list[str] | None = None,
    certdata: str | bytes | None = None,
    keydata: str | bytes | None = None,
    check_hostname: bool | None = None,
    ssl_minimum_version: int | None = None,
    ssl_maximum_version: int | None = None,
    ech_config_list: bytes | None = None,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
    use_recommended_ciphers: bool = False,
) -> ssl.SSLSocket | SSLTransportType:
    """
    All arguments except for server_hostname, ssl_context, and ca_cert_dir have
    the same meaning as they do when using :func:`ssl.wrap_socket`.

    :param server_hostname:
        When SNI is supported, the expected hostname of the certificate
    :param ssl_context:
        A pre-made :class:`SSLContext` object. If none is provided, one will
        be created using :func:`create_urllib3_context`.
    :param ciphers:
        A string of ciphers we wish the client to support.
    :param ca_cert_dir:
        A directory containing CA certificates in multiple separate files, as
        supported by OpenSSL's -CApath flag or the capath argument to
        SSLContext.load_verify_locations().
    :param key_password:
        Optional password if the keyfile is encrypted.
    :param ca_cert_data:
        Optional string containing CA certificates in PEM format suitable for
        passing as the cadata parameter to SSLContext.load_verify_locations()
    :param tls_in_tls:
        Use SSLTransport to wrap the existing socket.
    :param alpn_protocols:
        Manually specify other protocols to be announced during tls handshake.
    :param certdata:
        Specify an in-memory client intermediary certificate for mTLS.
    :param keydata:
        Specify an in-memory client intermediary key for mTLS.
    :param ssl_backend:
        Force the TLS implementation (``"rtls"``, ``"utls"`` or ``"ssl"``)
        used to build the context. Ignored when ``ssl_context`` is provided.
    """
    context = ssl_context
    cache_disabled: bool = context is not None
    if context is None and use_recommended_ciphers and ciphers is None:
        ciphers = MOZ_INTERMEDIATE_CIPHERS

    with _SSLContextCache.lock(
        keyfile,
        certfile if certfile is None else Path(certfile),
        cert_reqs,
        ca_certs,
        ssl_version,
        ciphers,
        ca_cert_dir if ca_cert_dir is None else Path(ca_cert_dir),
        alpn_protocols,
        certdata,
        keydata,
        key_password,
        ca_cert_data,
        os.getenv("SSLKEYLOGFILE", None),
        ssl_minimum_version,
        ssl_maximum_version,
        check_hostname,
        ssl_backend,
    ):
        cached_ctx = _SSLContextCache.get() if not cache_disabled else None

        if cached_ctx is None:
            if context is None:
                # Note: This branch of code and all the variables in it are only used in tests.
                # We should consider deprecating and removing this code.
                context = create_urllib3_context(
                    ssl_version,
                    cert_reqs,
                    ciphers=ciphers,
                    ssl_minimum_version=ssl_minimum_version,
                    ssl_maximum_version=ssl_maximum_version,
                    ssl_backend=ssl_backend,
                    use_recommended_ciphers=False,
                )

            if cert_reqs is not None:
                context.verify_mode = cert_reqs  # type: ignore[assignment]

            if check_hostname is not None:
                context.check_hostname = check_hostname

            if ca_certs or ca_cert_dir or ca_cert_data:
                # SSLContext does not support bytes for cadata[...]
                if ca_cert_data and isinstance(ca_cert_data, bytes):
                    ca_cert_data = ca_cert_data.decode()

                try:
                    context.load_verify_locations(ca_certs, ca_cert_dir, ca_cert_data)
                except OSError as e:
                    raise SSLError(e) from e

            elif hasattr(context, "load_default_certs"):
                try:
                    store_stats = _cert_store_stats(context)

                    # try to load OS default certs; works well on Windows.
                    if "x509_ca" not in store_stats or not store_stats["x509_ca"]:
                        context.load_default_certs()
                except (
                    AttributeError,
                    NotImplementedError,
                ):  # Defensive: 3rd party like truststore(...)
                    pass

            # Attempt to detect if we get the goofy behavior of the
            # keyfile being encrypted and OpenSSL asking for the
            # passphrase via the terminal and instead error out.
            if keyfile and key_password is None and _is_key_file_encrypted(keyfile):
                raise SSLError("Client private key is encrypted, password is required")

            if certfile:
                if key_password is None:
                    context.load_cert_chain(certfile, keyfile)
                else:
                    context.load_cert_chain(certfile, keyfile, key_password)
            elif certdata and keydata:
                if IS_NONSTDLIB:
                    context.load_cert_chain(certdata, keydata, key_password)
                else:
                    try:
                        _ctx_load_cert_chain(context, certdata, keydata, key_password)
                    except io.UnsupportedOperation as e:
                        warnings.warn(
                            "Passing in-memory client/intermediary certificate for mTLS is unsupported on your platform. "
                            f"Reason: {e}. It will be picked out if you upgrade to a QUIC connection or if you install "
                            "alternative ssl backend (rtls/utls).",
                            UserWarning,
                        )

            try:
                context.set_alpn_protocols(alpn_protocols or ALPN_PROTOCOLS)
            except (
                NotImplementedError
            ):  # Defensive: in CI, we always have set_alpn_protocols
                pass

            if ciphers:
                context.set_ciphers(ciphers)

            if not cache_disabled:
                _SSLContextCache.save(context)
        else:
            context = cached_ctx

    if ech_config_list and hasattr(context, "set_ech_configs"):
        # we need to mutate the ctx, so it's going to be a copy
        # ech config list is specific to a single connection.
        context = context.set_ech_configs(ech_config_list)

    return _ssl_wrap_socket_impl(sock, context, tls_in_tls, server_hostname)


def is_ipaddress(hostname: str | bytes) -> bool:
    """Detects whether the hostname given is an IPv4 or IPv6 address.
    Also detects IPv6 addresses with Zone IDs.

    :param str hostname: Hostname to examine.
    :return: True if the hostname is an IP address, False otherwise.
    """
    if isinstance(hostname, bytes):
        # IDN A-label bytes are ASCII compatible.
        hostname = hostname.decode("ascii")
    return bool(_IPV4_RE.match(hostname) or _BRACELESS_IPV6_ADDRZ_RE.match(hostname))


def _is_key_file_encrypted(key_file: str) -> bool:
    """Detects if a key file is encrypted or not."""
    with open(key_file) as f:
        for line in f:
            # Look for Proc-Type: 4,ENCRYPTED
            if "ENCRYPTED" in line:
                return True

    return False


def _ssl_wrap_socket_impl(
    sock: socket.socket,
    ssl_context: ssl.SSLContext,
    tls_in_tls: bool,
    server_hostname: str | None = None,
) -> ssl.SSLSocket | SSLTransportType:
    if tls_in_tls:
        if not SSLTransport:
            # Import error, ssl is not available.
            raise ProxySchemeUnsupported(
                "TLS in TLS requires support for the 'ssl' module"
            )

        SSLTransport._validate_ssl_context_for_tls_in_tls(ssl_context)
        return SSLTransport(sock, ssl_context, server_hostname)

    return ssl_context.wrap_socket(sock, server_hostname=server_hostname)


def is_capable_for_quic(
    ctx: ssl.SSLContext | None, ssl_maximum_version: ssl.TLSVersion | int | None
) -> bool:
    """
    Quickly uncover if passed parameters for HTTPSConnection does not exclude QUIC.
    Some parameters may defacto exclude HTTP/3 over QUIC.
    -> TLS 1.3 required
    -> One of the three supported ciphers (listed below)
    """
    quic_disable: bool = False

    if ctx is not None:
        if ssl.OP_NO_TLSv1_3 in ctx.options:
            quic_disable = True
        elif SUPPORT_MIN_MAX_TLS_VERSION and isinstance(
            ctx.maximum_version, ssl.TLSVersion
        ):
            if (
                ctx.maximum_version != ssl.TLSVersion.MAXIMUM_SUPPORTED
                and ctx.maximum_version <= ssl.TLSVersion.TLSv1_2
            ):
                quic_disable = True

    if ssl_maximum_version and ssl_maximum_version <= ssl.TLSVersion.TLSv1_2:
        quic_disable = True

    return not quic_disable


@lru_cache(maxsize=1)
def _get_clear_error() -> typing.Callable[[], None] | None:
    try:
        from ..contrib.imcc._ctypes import _OpenSSL

        return _OpenSSL().ERR_clear_error
    except (ImportError, OSError):
        return None


_T = typing.TypeVar("_T")


def _inspect_cert_store(ctx: ssl.SSLContext, operation: typing.Callable[[], _T]) -> _T:
    # rtls/utls contexts also inherit from stdlib SSLContext for compatibility.
    if (
        hasattr(ctx, "set_ech_configs")
        or stdlib_ssl is None
        or not isinstance(
            ctx, getattr(stdlib_ssl, "_SSLContext", stdlib_ssl.SSLContext)
        )
    ):
        return operation()

    clear_error = _get_clear_error()
    if clear_error is not None:
        try:
            return operation()
        finally:
            # X509_check_ca() can leave errors after a successful inspection.
            clear_error()

    # OpenSSL errors belong to the OS thread. Never reuse this worker for TLS.
    result: Future[_T] = Future()

    def run() -> None:
        try:
            result.set_result(operation())
        except BaseException as exc:
            result.set_exception(exc)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return result.result()


def _cert_store_stats(ctx: ssl.SSLContext) -> dict[str, int]:
    return _inspect_cert_store(ctx, ctx.cert_store_stats)


def _load_default_certs_eagerly(ctx: ssl.SSLContext) -> None:
    """Populate default trust when a lazy OpenSSL directory cannot be exported."""
    ctx.load_default_certs()
    if stdlib_ssl is None or not isinstance(ctx, stdlib_ssl.SSLContext):
        return  # Defensive: alternative runtimes/contexts have no OpenSSL directory to scan.

    paths = stdlib_ssl.get_default_verify_paths()
    capath = os.environ.get(paths.openssl_capath_env, paths.openssl_capath)
    # Only OpenSSL's hashed certificate entries belong to this trust source.
    for directory in capath.split(os.pathsep):
        with contextlib.suppress(OSError), os.scandir(directory) as entries:
            for entry in entries:
                if re.fullmatch(r"[a-fA-F0-9]{8}\.[0-9]+", entry.name):
                    with contextlib.suppress(OSError, ValueError):
                        ctx.load_verify_locations(cafile=entry.path)


def _get_ca_certs(ctx: ssl.SSLContext) -> list[bytes]:
    return _inspect_cert_store(ctx, lambda: ctx.get_ca_certs(binary_form=True))


def convert_ssl_ctx_nonstdlib(ctx: ssl.SSLContext) -> ssl.SSLContext:
    """Attempt to convert stdlib SSLContext to the active non-stdlib backend
    (rtls or utls) SSLContext. Best effort only.

    If the active backend is the stdlib ssl, the context is returned as-is.
    If the passed context is already a non-stdlib context (detected via the
    ``set_ech_configs`` attribute, exposed by both rtls and utls), it is
    likewise returned as-is.
    """
    if not IS_NONSTDLIB:
        return ctx

    if hasattr(ctx, "set_ech_configs"):  # already a non-stdlib context, exit early.
        return ctx

    import ssl as stdlib_ssl

    ssl_ctx_have_certs = _cert_store_stats(ctx).get("x509_ca", 0) > 0

    ca_cert_data: str | None = None

    if ssl_ctx_have_certs:
        ctx_root_certificates: list[bytes] = _get_ca_certs(ctx)

        if ctx_root_certificates:
            ca_cert_data = "\n".join(
                stdlib_ssl.DER_cert_to_PEM_cert(cert) for cert in ctx_root_certificates
            )

    new_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    new_ctx.verify_mode = ssl.VerifyMode(int(ctx.verify_mode))

    if ca_cert_data:
        new_ctx.load_verify_locations(cadata=ca_cert_data)
    else:
        new_ctx.load_default_certs()

    opt_match_no_tls: bool = False

    try:
        if stdlib_ssl.OP_NO_TLSv1_3 in ctx.options:  # Defensive: legacy TLS options.
            new_ctx.options |= ssl.OP_NO_TLSv1_3
            opt_match_no_tls = True
        if stdlib_ssl.OP_NO_TLSv1_2 in ctx.options:  # Defensive: legacy TLS options.
            new_ctx.options |= ssl.OP_NO_TLSv1_2
            opt_match_no_tls = True
    except TypeError:  # Defensive: foreign Options enum compatibility.
        # TODO: Investigate this weird edge case.
        #       Debug info:
        #         print(stdlib_ssl.OP_NO_TLSv1_3.__class__ == ssl.Options)  # False
        #         print(stdlib_ssl.OP_NO_TLSv1_3.__class__ == stdlib_ssl.Options)  # True
        #         print(ctx.options.__class__ == ssl.Options)  # False
        #         print(ctx.options.__class__ == stdlib_ssl.Options)  # False
        #         print(ctx.options.__class__)  # <flag 'Options'>
        #         print(ctx.options.__module__) # ssl
        #         print(isinstance(ctx.options, stdlib_ssl.Options))  # False
        #         print(isinstance(ctx.options, ssl.Options))  # False
        #         print(isinstance(ctx.options, enum.IntEnum))  # False
        #         print(isinstance(ctx.options, enum.Enum))  # True
        #         print(isinstance(ctx.options, int))  # True

        options = ssl.Options(ctx.options)

        if ssl.OP_NO_TLSv1_3 in options:
            new_ctx.options |= ssl.OP_NO_TLSv1_3
            opt_match_no_tls = True
        if ssl.OP_NO_TLSv1_2 in options:
            new_ctx.options |= ssl.OP_NO_TLSv1_2
            opt_match_no_tls = True

    if not opt_match_no_tls:
        new_ctx.minimum_version = ssl.TLSVersion(int(ctx.minimum_version))
        new_ctx.maximum_version = ssl.TLSVersion(int(ctx.maximum_version))

    if hasattr(ctx, "check_hostname") and ctx.check_hostname is False:
        new_ctx.check_hostname = False

    return new_ctx


# Backwards-compatibility alias (deprecated name).
convert_ssl_ctx_rtls = convert_ssl_ctx_nonstdlib
