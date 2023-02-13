#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import os
import string

from exceptions_helper import ex

from . import logger
from sg_helpers import scantree

# this is for the drive letter code, it only works on windows
if 'nt' == os.name:
    from ctypes import windll


# adapted from
# http://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python/827490
def get_win_drives():
    """ Return list of detected drives """
    assert 'nt' == os.name

    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(letter)
        bitmask >>= 1

    return drives


def folders_at_path(path, include_parent=False, include_files=False):
    """ Returns a list of dictionaries with the folders contained at the given path
        Give the empty string as the path to list the contents of the root path
        under Unix this means "/", (on Windows this will be a list of drive letters)
    """

    # walk up the tree until we find a valid path
    while path and not os.path.isdir(path):
        if path == os.path.dirname(path):
            path = ''
            break
        else:
            path = os.path.dirname(path)

    if '' == path:
        if 'nt' == os.name:
            entries = [{'currentPath': r'\My Computer'}]
            for letter in get_win_drives():
                letter_path = '%s:\\' % letter
                entries.append({'name': letter_path, 'path': letter_path})
            return entries
        else:
            path = '/'

    # fix up the path and find the parent
    path = os.path.abspath(os.path.normpath(path))
    parent_path = os.path.dirname(path)

    # if we're at the root then the next step is the meta-node showing our drive letters
    if 'nt' == os.name and path == parent_path:
        parent_path = ''

    try:
        file_list = get_file_list(path, include_files)
    except OSError as e:
        logger.log('Unable to open %s: %r / %s' % (path, e, ex(e)), logger.WARNING)
        file_list = get_file_list(parent_path, include_files)

    file_list = sorted(file_list, key=lambda x: os.path.basename(x['name']).lower())

    entries = [{'currentPath': path}]
    if include_parent and path != parent_path:
        entries.append({'name': '..', 'path': parent_path})
    entries.extend(file_list)

    return entries


def get_file_list(path, include_files):

    result = []

    hide_names = [
        # windows specific
        'boot', 'bootmgr', 'cache', r'config\.msi', 'msocache', 'recovery', r'\$recycle\.bin', 'recycler',
        'system volume information', 'temporary internet files',
        # osx specific
        r'\.fseventd', r'\.spotlight', r'\.trashes', r'\.vol', 'cachedmessages', 'caches', 'trash',
        # general
        r'\.git']

    # filter directories to protect
    for direntry in scantree(path, exclude=hide_names, filter_kind=not include_files, recurse=False) or []:
        result.append(dict(name=direntry.name, path=direntry.path, isFile=int(direntry.is_file(follow_symlinks=False))))

    return result
