from __future__ import annotations

import ctypes
import hashlib
import sys
from ctypes import POINTER, c_char_p, c_int32, c_ubyte, c_uint32, c_void_p
from ssl import enum_certificates  # type: ignore[attr-defined]

from ._embed import root_der_certificates as _ccadb_root_certificates

# ROOT: Highest level of trust. Trust anchors. Self-Signed.
# MY: User installed/custom trust anchors. Self-Signed.
# CA: Intermediates CA. Not trusted directly, not self-signed.
WINDOWS_STORES: list[str] = [
    "ROOT",
    "MY",
    "CA",
]
SERVER_AUTH_OID: str = "1.3.6.1.5.5.7.3.1"


def root_der_certificates() -> list[bytes]:
    certificates: list[bytes] = []
    seen: set[bytes] = set()

    for system_store in WINDOWS_STORES:
        try:
            for cert_bytes, encoding_type, trust in enum_certificates(system_store):
                if not trust:
                    continue  # Defensive: edge case, rare one.

                # if not True, then, we MUST LOOK for SERVER_AUTH oid EKU
                if not isinstance(trust, bool) and SERVER_AUTH_OID not in trust:
                    continue

                # Check it's in X.509 ASN.1 format and is trusted
                if (
                    encoding_type == "x509_asn"  # X.509 ASN.1 data
                ):
                    # Same root may live in several stores (ROOT/MY/CA);
                    # ensure each DER appears at most once.
                    if cert_bytes in seen:
                        continue
                    seen.add(cert_bytes)
                    certificates.append(cert_bytes)
        except PermissionError:  # Defensive: we can't cover that scenario in CI.
            continue

    # Windows lazily materializes trusted roots, so the enumerated stores above
    # are only a subset of what the OS actually trusts. Enrich the result with
    # embedded CCADB roots, but ONLY those the Windows trust engine itself
    # vouches for (via the AuthRoot CTL). CCADB is merely a candidate list;
    # Windows remains the sole authority, so we never add a certificate the OS
    # does not recognize.
    for cert_bytes in _os_trusted_subset(_ccadb_root_certificates()):
        if cert_bytes not in seen:
            seen.add(cert_bytes)
            certificates.append(cert_bytes)

    return certificates


# The local "ROOT" store only holds roots that have actually been materialized:
# Windows downloads trusted roots lazily, on demand, so early on the enumerable
# store is a small subset of what the OS really trusts. To see the complete
# trusted set we read the AuthRoot CTL (Certificate Trust List), which lists
# every program root by SHA-1 thumbprint -- materialized or not -- and keep the
# embedded CCADB candidates whose thumbprint (and TLS server-auth EKU) it lists.
_DWORD = c_uint32
_BOOL = c_int32

# X509_ASN_ENCODING | PKCS_7_ASN_ENCODING
_ENCODING_TYPES = 0x00000001 | 0x00010000

# The trusted-root CTL is cached as the "EncodedCtl" binary value under
# AuthRoot\AutoUpdate, with SHA-1 SubjectIdentifiers. (A distrust CTL lives
# alongside as DisallowedCertEncodedCtl, but it identifies certs by *signature
# hash* -- CERT_SIGNATURE_HASH_PROP_ID -- not by thumbprint, so a thumbprint
# match cannot subtract it; for roots that distrust is moot anyway, since a
# distrusted root is dropped from the trusted CTL we gate on.)
_AUTHROOT_AUTOUPDATE_KEY = r"SOFTWARE\Microsoft\SystemCertificates\AuthRoot\AutoUpdate"
_AUTHROOT_CTL_VALUE = "EncodedCtl"

# A CTL entry stores per-root properties as attributes. The EKU property is keyed
# by szOID_CERT_PROP_ID_PREFIX + CERT_ENHKEY_USAGE_PROP_ID (9). Its value is the
# DER-encoded EKU OID sequence; absence of the property means "all purposes".
_EKU_PROP_OID = b"1.3.6.1.4.1.311.10.11.9"
# DER encodings of the OIDs we accept for TLS server authentication.
_SERVER_AUTH_OID_DER = bytes.fromhex("06082B06010505070301")  # 1.3.6.1.5.5.7.3.1
_ANY_EKU_OID_DER = bytes.fromhex("0604551D2500")  # 2.5.29.37.0 (anyExtendedKeyUsage)


class _CRYPT_BLOB(ctypes.Structure):
    # CRYPTOAPI_BLOB; CRYPT_DATA_BLOB / CRYPT_INTEGER_BLOB / CRYPT_OBJID_BLOB share this shape.
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-crypt_integer_blob
    _fields_ = (
        ("cbData", _DWORD),
        ("pbData", POINTER(c_ubyte)),
    )


class _CTL_USAGE(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-ctl_usage
    _fields_ = (
        ("cUsageIdentifier", _DWORD),
        ("rgpszUsageIdentifier", POINTER(c_char_p)),
    )


class _FILETIME(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-filetime
    _fields_ = (
        ("dwLowDateTime", _DWORD),
        ("dwHighDateTime", _DWORD),
    )


class _CRYPT_ALGORITHM_IDENTIFIER(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-crypt_algorithm_identifier
    _fields_ = (
        ("pszObjId", c_char_p),
        ("Parameters", _CRYPT_BLOB),
    )


class _CRYPT_ATTRIBUTE(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-crypt_attribute
    _fields_ = (
        ("pszObjId", c_char_p),
        ("cValue", _DWORD),
        ("rgValue", POINTER(_CRYPT_BLOB)),
    )


class _CTL_ENTRY(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-ctl_entry
    _fields_ = (
        ("SubjectIdentifier", _CRYPT_BLOB),  # SHA-1 thumbprint of the trusted root
        ("cAttribute", _DWORD),
        ("rgAttribute", POINTER(_CRYPT_ATTRIBUTE)),
    )


class _CTL_INFO(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-ctl_info
    _fields_ = (
        ("dwVersion", _DWORD),
        ("SubjectUsage", _CTL_USAGE),
        ("ListIdentifier", _CRYPT_BLOB),
        ("SequenceNumber", _CRYPT_BLOB),
        ("ThisUpdate", _FILETIME),
        ("NextUpdate", _FILETIME),
        ("SubjectAlgorithm", _CRYPT_ALGORITHM_IDENTIFIER),
        ("cCTLEntry", _DWORD),
        ("rgCTLEntry", POINTER(_CTL_ENTRY)),
        ("cExtension", _DWORD),
        ("rgExtension", c_void_p),
    )


class _CTL_CONTEXT(ctypes.Structure):
    # https://learn.microsoft.com/en-us/windows/win32/api/wincrypt/ns-wincrypt-ctl_context
    _fields_ = (
        ("dwMsgAndCertEncodingType", _DWORD),
        ("pbCtlEncoded", POINTER(c_ubyte)),
        ("cbCtlEncoded", _DWORD),
        ("pCtlInfo", POINTER(_CTL_INFO)),
        ("hCertStore", c_void_p),
        ("hCryptMsg", c_void_p),
        ("pbCtlContent", POINTER(c_ubyte)),
        ("cbCtlContent", _DWORD),
    )


# Load crypt32 and bind the CTL function prototypes at import time. Guarded by
# the platform check so non-Windows never touches WinDLL;
_crypt32 = None
_CertCreateCTLContext = None
_CertFreeCTLContext = None
if sys.platform == "win32":
    try:
        _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    except OSError:  # Defensive: crypt32 failed to load.
        _crypt32 = None
    else:
        _CertCreateCTLContext = _crypt32.CertCreateCTLContext
        _CertCreateCTLContext.argtypes = [_DWORD, c_char_p, _DWORD]
        _CertCreateCTLContext.restype = POINTER(_CTL_CONTEXT)

        _CertFreeCTLContext = _crypt32.CertFreeCTLContext
        _CertFreeCTLContext.argtypes = [POINTER(_CTL_CONTEXT)]
        _CertFreeCTLContext.restype = _BOOL


def _sha1(data: bytes) -> bytes:
    """SHA-1 digest used purely as an identity/join key against the CTL."""
    try:
        return hashlib.sha1(data, usedforsecurity=False).digest()
    except TypeError:  # Defensive: missing usedforsecurity
        return hashlib.sha1(data).digest()


def _read_authroot_encoded_ctl() -> bytes | None:
    """Read the trusted-root CTL blob from the registry. Returns the raw
    (DER / PKCS#7-signed) bytes if available.
    """
    if sys.platform != "win32":  # Defensive: winreg is Windows-only.
        return None
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _AUTHROOT_AUTOUPDATE_KEY)
    except OSError:  # Defensive: registry key unavailable
        return None

    try:
        try:
            data, _ = winreg.QueryValueEx(key, _AUTHROOT_CTL_VALUE)
        except OSError:  # Defensive: CTL value unavailable
            return None
        if isinstance(data, (bytes, bytearray)) and data[:1] == b"\x30":  # ASN.1 SEQUENCE tag (0x30)
            return bytes(data)
        return None  # Defensive: value is not a CTL blob
    finally:
        winreg.CloseKey(key)


def _entry_allows_server_auth(entry: _CTL_ENTRY) -> bool:
    """Return True if a CTL entry is trusted for TLS server authentication."""
    count = entry.cAttribute
    attrs = entry.rgAttribute
    if not count or not attrs:
        return True  # Defensive: entry without attributes -> all purposes

    for j in range(count):
        attr = attrs[j]
        if attr.pszObjId != _EKU_PROP_OID:
            continue
        # Found the EKU property: include only if it lists serverAuth / anyEKU.
        for k in range(attr.cValue):
            blob = attr.rgValue[k]
            if blob.cbData and blob.pbData:
                raw = ctypes.string_at(blob.pbData, blob.cbData)
                if _SERVER_AUTH_OID_DER in raw or _ANY_EKU_OID_DER in raw:
                    return True
        return False

    return True  # no EKU property -> all purposes


def _authroot_ctl_thumbprints() -> set[bytes]:
    """SHA-1 thumbprints of the roots the AuthRoot CTL trusts for TLS server authentication."""
    encoded = _read_authroot_encoded_ctl()
    if _CertCreateCTLContext is None or _CertFreeCTLContext is None or not encoded:
        return set()  # Defensive: crypt32 unavailable or no CTL blob

    ctl = _CertCreateCTLContext(_ENCODING_TYPES, encoded, len(encoded))
    if not ctl:
        return set()  # Defensive: CTL failed to decode

    thumbprints: set[bytes] = set()
    try:
        info = ctl.contents.pCtlInfo.contents
        entries = info.rgCTLEntry
        for i in range(info.cCTLEntry):
            entry = entries[i]
            if not _entry_allows_server_auth(entry):
                continue
            blob = entry.SubjectIdentifier
            if blob.cbData and blob.pbData:
                thumbprints.add(ctypes.string_at(blob.pbData, blob.cbData))
    finally:
        _CertFreeCTLContext(ctl)

    return thumbprints


def _os_trusted_subset(candidates: list[bytes]) -> list[bytes]:
    """Guarantees every added certificate is one the OS's trust list recognizes!"""
    if not candidates:
        return []
    trusted = _authroot_ctl_thumbprints()
    if not trusted:
        return []  # Defensive: empty OS trust list
    return [der for der in candidates if _sha1(der) in trusted]


__all__ = ("root_der_certificates",)
