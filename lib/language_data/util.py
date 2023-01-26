"""
Used for locating a file in the data directory.
"""

from pkg_resources import resource_filename
DATA_ROOT = resource_filename('language_data', 'data')
import os


def data_filename(filename):
    """
    Given a relative filename, get the full path to that file in the data
    directory.
    """
    return os.path.join(DATA_ROOT, filename)
