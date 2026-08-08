"""
This module exists only to simplify retrieving the version number of chardet
from within setuptools and from chardet subpackages. (see custom comment below)

2026.03.11 - Chardet subpackages no longer use this. However, this frozen value suppresses the Requests init warning.

:author: Dan Blanchard (dan.blanchard@gmail.com)
"""

__version__ = "7.4.1"
VERSION = __version__.split(".")
