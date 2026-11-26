from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, c_int32, c_long, c_void_p

# Load frameworks
_core = ctypes.CDLL(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
    use_errno=True,
)
_sec = ctypes.CDLL(
    "/System/Library/Frameworks/Security.framework/Security",
    use_errno=True,
)

# PID of the process that imported (and thus initialized) the CoreFoundation
# and Security frameworks above. CoreFoundation/Security are NOT fork-safe.
_INIT_PID = os.getpid()

# Type aliases (CFIndex is a signed long on macOS, 8 bytes on 64-bit)
CFTypeRef = c_void_p
CFArrayRef = c_void_p
CFDataRef = c_void_p
CFDictionaryRef = c_void_p
CFIndex = c_long
OSStatus = c_int32

# Trust settings result constants
# See: https://developer.apple.com/documentation/security/sectrustsettingsresult
_kSecTrustSettingsResultTrustRoot = 1
_kSecTrustSettingsResultTrustAsRoot = 2
_kSecTrustSettingsResultDeny = 3
_kSecTrustSettingsResultUnspecified = 4

# CFNumberType enum value for kCFNumberSInt32Type
_kCFNumberSInt32Type = 3

# CFStringEncoding value for kCFStringEncodingUTF8
_kCFStringEncodingUTF8 = 0x08000100

# CoreFoundation function prototypes

_CFStringCreateWithCString = _core.CFStringCreateWithCString
_CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_CFStringCreateWithCString.restype = c_void_p

_CFDictionaryCreate = _core.CFDictionaryCreate
_CFDictionaryCreate.argtypes = [c_void_p, POINTER(c_void_p), POINTER(c_void_p), CFIndex, c_void_p, c_void_p]
_CFDictionaryCreate.restype = CFDictionaryRef

_CFDictionaryGetValue = _core.CFDictionaryGetValue
_CFDictionaryGetValue.argtypes = [CFDictionaryRef, c_void_p]
_CFDictionaryGetValue.restype = c_void_p

_CFArrayGetCount = _core.CFArrayGetCount
_CFArrayGetCount.argtypes = [CFArrayRef]
_CFArrayGetCount.restype = CFIndex

_CFArrayGetValueAtIndex = _core.CFArrayGetValueAtIndex
_CFArrayGetValueAtIndex.argtypes = [CFArrayRef, CFIndex]
_CFArrayGetValueAtIndex.restype = CFTypeRef

_CFDataGetLength = _core.CFDataGetLength
_CFDataGetLength.argtypes = [CFDataRef]
_CFDataGetLength.restype = CFIndex

_CFDataGetBytePtr = _core.CFDataGetBytePtr
_CFDataGetBytePtr.argtypes = [CFDataRef]
_CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)

_CFNumberGetValue = _core.CFNumberGetValue
_CFNumberGetValue.argtypes = [c_void_p, c_int32, c_void_p]
_CFNumberGetValue.restype = ctypes.c_bool

_CFRelease = _core.CFRelease
_CFRelease.argtypes = [c_void_p]
_CFRelease.restype = None

# Security function prototypes
_SecItemCopyMatching = _sec.SecItemCopyMatching
_SecItemCopyMatching.argtypes = [CFDictionaryRef, POINTER(CFTypeRef)]
_SecItemCopyMatching.restype = OSStatus

_SecCertificateCopyData = _sec.SecCertificateCopyData
_SecCertificateCopyData.argtypes = [CFTypeRef]
_SecCertificateCopyData.restype = CFDataRef

_SecTrustSettingsCopyCertificates = _sec.SecTrustSettingsCopyCertificates
_SecTrustSettingsCopyCertificates.argtypes = [c_int32, POINTER(CFArrayRef)]
_SecTrustSettingsCopyCertificates.restype = OSStatus

_SecTrustSettingsCopyTrustSettings = _sec.SecTrustSettingsCopyTrustSettings
_SecTrustSettingsCopyTrustSettings.argtypes = [CFTypeRef, c_int32, POINTER(CFArrayRef)]
_SecTrustSettingsCopyTrustSettings.restype = OSStatus

# CF callbacks & boolean constants

_kCFTypeDictKeyCallBacks = c_void_p.in_dll(_core, "kCFTypeDictionaryKeyCallBacks")
_kCFTypeDictValueCallBacks = c_void_p.in_dll(_core, "kCFTypeDictionaryValueCallBacks")
_kCFBooleanTrue = c_void_p.in_dll(_core, "kCFBooleanTrue")

# SecItem / SecTrustSettings constants

_kSecClass = c_void_p.in_dll(_sec, "kSecClass")
_kSecClassCertificate = c_void_p.in_dll(_sec, "kSecClassCertificate")
_kSecMatchLimit = c_void_p.in_dll(_sec, "kSecMatchLimit")
_kSecMatchLimitAll = c_void_p.in_dll(_sec, "kSecMatchLimitAll")
_kSecMatchTrustedOnly = c_void_p.in_dll(_sec, "kSecMatchTrustedOnly")
_kSecReturnRef = c_void_p.in_dll(_sec, "kSecReturnRef")

# kSecTrustSettingsResult is a #define macro in the Security headers
# (not an exported dylib symbol), so we create the CFString ourselves.
_kSecTrustSettingsResult = _CFStringCreateWithCString(None, b"kSecTrustSettingsResult", _kCFStringEncodingUTF8)


def _make_query(keys: list[c_void_p], values: list[c_void_p]) -> CFDictionaryRef:
    """Build a CFDictionary for SecItem queries."""
    count = len(keys)
    key_arr = (c_void_p * count)(*keys)
    val_arr = (c_void_p * count)(*values)
    return _CFDictionaryCreate(  # type: ignore[no-any-return]
        None,
        key_arr,
        val_arr,
        count,
        _kCFTypeDictKeyCallBacks,
        _kCFTypeDictValueCallBacks,
    )


def _data_to_bytes(data_ref: c_void_p) -> bytes:
    """Convert a CFDataRef to Python bytes, releasing the CFDataRef."""
    try:
        length = _CFDataGetLength(data_ref)
        ptr = _CFDataGetBytePtr(data_ref)
        return bytes(ctypes.string_at(ptr, length))
    finally:
        _CFRelease(data_ref)


def _is_cert_trusted(cert_ref: c_void_p, domain: int) -> bool:
    """Check whether a certificate's trust settings indicate it should be trusted.

    Calls SecTrustSettingsCopyTrustSettings to retrieve per-certificate trust
    settings for the given domain, then inspects the kSecTrustSettingsResult
    value in each trust settings dictionary entry.

    Returns True if the certificate should be included in the trust store.
    """
    trust_settings = CFArrayRef()
    status = _SecTrustSettingsCopyTrustSettings(cert_ref, domain, byref(trust_settings))

    if status != 0:
        # No explicit trust settings for this cert in this domain.
        # For the system domain (2), this is expected -- system roots have
        # implicit trust. For user/admin, it means no override exists.
        return True  # Defensive: Not tested in CI

    try:
        settings_count = _CFArrayGetCount(trust_settings)

        if settings_count == 0:
            # An empty trust settings array means "trust for everything"
            # (unconditional trust). This is the common case for user-added CAs.
            return True

        for i in range(settings_count):
            settings_dict = _CFArrayGetValueAtIndex(trust_settings, i)
            result_ref = _CFDictionaryGetValue(settings_dict, _kSecTrustSettingsResult)

            if result_ref is None:
                # No kSecTrustSettingsResult key in this entry means
                # kSecTrustSettingsResultTrustRoot (implicit default).
                return True  # Defensive: Not tested in CI

            result_value = c_int32()
            if _CFNumberGetValue(result_ref, _kCFNumberSInt32Type, byref(result_value)):
                if result_value.value == _kSecTrustSettingsResultDeny:
                    return False  # Defensive: Not tested in CI
                if result_value.value in (
                    _kSecTrustSettingsResultTrustRoot,
                    _kSecTrustSettingsResultTrustAsRoot,
                ):
                    return True
                # kSecTrustSettingsResultUnspecified or unknown: continue
                # checking next entry.

        # If we exhausted all entries without a definitive trust or deny,
        # the certificate's trust is unspecified in this domain.
        # Treat as trusted -- downstream TLS evaluation will still verify the chain.
        return True  # Defensive: Not tested in CI
    finally:
        _CFRelease(trust_settings)


def root_der_certificates() -> list[bytes]:
    """Return a list of DER-encoded certificates trusted for TLS server auth,
    covering system roots, admin/user trust settings, and personal CAs.

    Certificates explicitly denied via trust settings are excluded.
    Duplicates across domains and queries are removed.
    """
    # Fork guard: CoreFoundation/Security cannot be used safely in a process
    # that forked (without exec()) after the frameworks were initialized.
    # This protection is heuristic, and it's the best I could do with confidence.
    # Refs:
    #   - CPython issue #77906 "Python crashes on macOS after fork with no exec":
    #     https://github.com/python/cpython/issues/77906
    #   - Apple fork(2) man page, CAVEATS ("...you must exec."):
    #     https://keith.github.io/xcode-man-pages/fork.2.html
    if os.getpid() != _INIT_PID:
        return []  # Defensive: forked-child path

    certificates: list[bytes] = []
    seen: set[bytes] = set()

    # 1) Trust settings enumeration across all three domains:
    #    0 = kSecTrustSettingsDomainUser
    #    1 = kSecTrustSettingsDomainAdmin
    #    2 = kSecTrustSettingsDomainSystem
    for domain in (0, 1, 2):
        cert_array = CFArrayRef()
        status = _SecTrustSettingsCopyCertificates(domain, byref(cert_array))
        if status != 0:
            # errSecNoTrustSettings (-25263) is expected for the system domain
            # and for domains with no overrides. Other errors are also benign
            # here -- we simply skip the domain.
            continue
        try:
            count = _CFArrayGetCount(cert_array)
            for i in range(count):
                cert_ref = _CFArrayGetValueAtIndex(cert_array, i)
                if not _is_cert_trusted(cert_ref, domain):
                    continue  # Defensive: Not tested in CI
                der_data = _data_to_bytes(_SecCertificateCopyData(cert_ref))
                if der_data not in seen:
                    seen.add(der_data)
                    certificates.append(der_data)
        finally:
            _CFRelease(cert_array)

    # 2) Personal CA certificates from keychain marked as trusted.
    #    This catches certificates that may not have explicit trust settings
    #    but are trusted via keychain policies.
    query = _make_query(
        keys=[_kSecClass, _kSecMatchLimit, _kSecMatchTrustedOnly, _kSecReturnRef],
        values=[_kSecClassCertificate, _kSecMatchLimitAll, _kCFBooleanTrue, _kCFBooleanTrue],
    )

    try:
        result = CFTypeRef()
        status = _SecItemCopyMatching(query, byref(result))

        if status == 0:
            try:
                count = _CFArrayGetCount(result)
                for i in range(count):
                    cert_ref = _CFArrayGetValueAtIndex(result, i)
                    der_data = _data_to_bytes(_SecCertificateCopyData(cert_ref))
                    if der_data not in seen:
                        seen.add(der_data)
                        certificates.append(der_data)
            finally:
                _CFRelease(result)
    except OSError:  # Defensive: should never happen under normal conditions(...)
        pass
    finally:
        _CFRelease(query)

    return certificates
