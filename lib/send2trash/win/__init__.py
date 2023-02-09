# Copyright 2017 Virgil Dupras

# This software is licensed under the "BSD" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.hardcoded.net/licenses/bsd_license

from __future__ import unicode_literals
from platform import version

# if windows is vista or newer and pywin32 is available use IFileOperation
modern = int(version().split(".", 1)[0]) >= 6
if modern:
    try:
        # Attempt to use pywin32 to use IFileOperation
        from send2trash.win.modern import send2trash
    except ImportError:
        modern = False
if not modern:
    # use SHFileOperation as fallback
    from send2trash.win.legacy import send2trash  # noqa: F401
