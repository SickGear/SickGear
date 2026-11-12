from __future__ import annotations

import platform
import sys

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_ANDROID = sys.platform == "android" or hasattr(sys, "getandroidapilevel")
IS_LINUX = sys.platform.startswith("linux") or IS_ANDROID
IS_BSD = sys.platform.startswith(("freebsd", "openbsd", "netbsd"))

# macOS version detection
MACOS_VERSION: tuple[int, ...] | None = None

if IS_MACOS:
    version_str = platform.mac_ver()[0]
    MACOS_VERSION = tuple(map(int, version_str.split(".")))


if IS_WINDOWS:
    from ._windows import root_der_certificates
elif IS_MACOS and MACOS_VERSION >= (10, 15):  # type: ignore[operator]
    from ._macos import root_der_certificates
elif IS_LINUX or IS_BSD:
    from ._linux import root_der_certificates
else:
    from ._embed import root_der_certificates


__all__ = ("root_der_certificates",)
