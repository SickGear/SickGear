"""
Functions to display an error (error, warning or information) message.
"""

from hachoir.core.log import log
import sys
import traceback


def getBacktrace(empty="Empty backtrace."):
    """
    Try to get backtrace as string.
    Returns "Error while trying to get backtrace" on failure.
    """
    try:
        info = sys.exc_info()
        trace = traceback.format_exception(*info)
        if trace[0] != "None\n":
            return "".join(trace)
    except Exception:
        # No i18n here (imagine if i18n function calls error...)
        return "Error while trying to get backtrace"
    return empty


info = log.info
warning = log.warning
error = log.error
