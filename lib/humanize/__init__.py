"""Main package for humanize."""
from humanize.filesize import naturalsize
from humanize.i18n import activate, deactivate
from humanize.number import apnumber, fractional, intcomma, intword, ordinal, scientific
from humanize.time import (
    naturaldate,
    naturalday,
    naturaldelta,
    naturaltime,
    precisedelta,
)

__version__ = VERSION = '3.1.0'


__all__ = [
    "__version__",
    "activate",
    "apnumber",
    "deactivate",
    "fractional",
    "intcomma",
    "intword",
    "naturaldate",
    "naturalday",
    "naturaldelta",
    "naturalsize",
    "naturaltime",
    "ordinal",
    "precisedelta",
    "scientific",
    "VERSION",
]
