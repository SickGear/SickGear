from __future__ import annotations

import os
import time
from pathlib import Path
from ssl import PEM_cert_to_DER_cert

from . import IS_ANDROID

# Threshold for considering a system trust store as stale (3 years, in seconds).
STALE_TRUST_STORE_THRESHOLD_SECONDS: int = 3 * 365 * 24 * 3600

# Most recent modification time observed across the trust store source files.
# Updated by `root_der_certificates`. ``None`` means "no usable info collected".
_LAST_NEWEST_MTIME: float | None = None

# source: http://gagravarr.org/writing/openssl-certs/others.shtml
BUNDLE_TRUST_STORE_DIRECTORIES: list[str] = [
    "/var/ssl",
    "/usr/share/ssl",
    "/usr/local/ssl",
    "/usr/local/openssl",
    "/usr/local/etc/openssl",
    "/usr/local/share/certs",
    "/usr/lib/ssl",
    "/usr/ssl",
    "/etc/openssl",
    "/etc/pki/ca-trust/extracted/pem",
    "/etc/pki/tls",
    "/etc/ssl",
    "/etc/certs",
    "/opt/etc/ssl",
    "/boot/system/data/ssl",
]

ANDROID_LEGACY_TRUST_STORE_DIRECTORY = "/system/etc/security/cacerts"
ANDROID_CONSCRYPT_TRUST_STORE_DIRECTORY = "/apex/com.android.conscrypt/cacerts"

KNOWN_TRUST_STORE_EXTENSIONS: list[str] = [
    "pem",
    "crt",
]

BANNED_KEYWORD_NOT_TLS: set[str] = {
    "email",
    "objsign",
    "trust",
    "timestamp",
    "codesign",
    "ocsp",
    "untrusted",
}


def _directory_has_entries(directory: str) -> bool:
    try:
        return next(Path(directory).iterdir(), None) is not None
    except OSError:
        return False


def _bundle_trust_store_directories() -> list[str]:
    directories = list(BUNDLE_TRUST_STORE_DIRECTORIES)

    if IS_ANDROID:
        if _directory_has_entries(ANDROID_CONSCRYPT_TRUST_STORE_DIRECTORY):
            directories.append(ANDROID_CONSCRYPT_TRUST_STORE_DIRECTORY)
        else:
            directories.append(ANDROID_LEGACY_TRUST_STORE_DIRECTORY)

    return directories


def root_der_certificates() -> list[bytes]:
    global _LAST_NEWEST_MTIME

    certificates: list[bytes] = []
    newest_mtime: float = 0.0
    # Track files we've already processed by their (device, inode) pair so that
    # symlinks pointing into the same canonical file (very common, e.g.
    # /etc/ssl/certs/*.pem -> /usr/share/ca-certificates/.../*.crt) and other
    # cross-directory aliases are read and parsed exactly once.
    seen_inodes: set[tuple[int, int]] = set()

    for directory in _bundle_trust_store_directories():
        if not os.path.exists(directory):
            continue

        # Use rglob to recursively search all files in directory and subdirectories
        for filepath in Path(directory).rglob("*"):
            try:
                if not filepath.is_file():  # Skip directories
                    continue

                extension = filepath.suffix.lstrip(".").lower()

                if extension not in KNOWN_TRUST_STORE_EXTENSIONS and extension.isdigit() is False:
                    continue

                if any(kw in str(filepath).lower() for kw in BANNED_KEYWORD_NOT_TLS):
                    continue

                try:
                    st = filepath.stat()
                except OSError:  # Defensive: stat may fail on broken symlinks
                    continue

                inode_key = (st.st_dev, st.st_ino)
                # Some very old cases, we may find st_ino reported
                # as 0.
                if st.st_ino != 0:
                    if inode_key in seen_inodes:
                        continue
                    seen_inodes.add(inode_key)

                if st.st_mtime > newest_mtime:
                    newest_mtime = st.st_mtime

                with open(filepath, encoding="utf-8") as f:
                    bundle = f.read()

                if not bundle.strip():  # Skip empty files
                    continue  # Defensive:

                line_ending = "\n" if "-----END CERTIFICATE-----\r\n" not in bundle else "\r\n"
                boundary = "-----END CERTIFICATE-----" + line_ending

                for chunk in bundle.split(boundary):
                    if chunk:
                        start_marker = chunk.find("-----BEGIN CERTIFICATE-----" + line_ending)

                        if start_marker == -1:
                            break  # Defensive: file that aren't PEM encoded in target directories(...)

                        pem_reconstructed = "".join([chunk[start_marker:], boundary])

                        try:
                            der_certificate = PEM_cert_to_DER_cert(pem_reconstructed)
                        except ValueError:  # Defensive: malformed cert/base64?
                            continue

                        if der_certificate not in certificates:
                            certificates.append(der_certificate)

            except (OSError, UnicodeDecodeError):  # Defensive: Skip files we can't read
                # OSError -> e.g. PermissionError
                # UnicodeDecodeError -> DER ASN.1 encoded
                continue

    _LAST_NEWEST_MTIME = newest_mtime if newest_mtime > 0 else None

    return certificates


def is_trust_store_stale(threshold_seconds: int = STALE_TRUST_STORE_THRESHOLD_SECONDS) -> bool:
    """Return True if the system trust store has not been updated for longer than
    ``threshold_seconds``.

    The decision relies on the most recent modification time observed during
    the last call to :func:`root_der_certificates`. If no modification time has
    been collected yet, returns False.
    """
    if _LAST_NEWEST_MTIME is None:
        return False
    return (time.time() - _LAST_NEWEST_MTIME) >= threshold_seconds
