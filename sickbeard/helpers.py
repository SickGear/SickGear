# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty    of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement
import getpass

import os
import re
import shutil
import socket
import stat
import tempfile
import time
import traceback
import urllib
import hashlib
import httplib
import urlparse
import uuid
import base64
import zipfile
import datetime

import sickbeard
import subliminal
import adba
import requests
import requests.exceptions

try:
    import json
except ImportError:
    from lib import simplejson as json

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import elementtree.ElementTree as etree

from xml.dom.minidom import Node

from sickbeard.exceptions import MultipleShowObjectsException, ex
from sickbeard import logger, classes
from sickbeard.common import USER_AGENT, mediaExtensions, subtitleExtensions
from sickbeard import db
from sickbeard import encodingKludge as ek
from sickbeard import notifiers
from sickbeard import clients

from lib.cachecontrol import CacheControl, caches
from itertools import izip, cycle


def indentXML(elem, level=0):
    '''
    Does our pretty printing, makes Matt very happy
    '''
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indentXML(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        # Strip out the newlines from text
        if elem.text:
            elem.text = elem.text.replace('\n', ' ')
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def remove_extension(name):
    """
    Remove download or media extension from name (if any)
    """

    if name and "." in name:
        base_name, sep, extension = name.rpartition('.')  # @UnusedVariable
        if base_name and extension.lower() in ['nzb', 'torrent'] + mediaExtensions:
            name = base_name

    return name


def remove_non_release_groups(name):
    """
    Remove non release groups from name
    """

    if name and "-" in name:
        name_group = name.rsplit('-', 1)
        if name_group[-1].upper() in ["RP", "NZBGEEK"]:
            name = name_group[0]

    return name


def replaceExtension(filename, newExt):
    '''
    >>> replaceExtension('foo.avi', 'mkv')
    'foo.mkv'
    >>> replaceExtension('.vimrc', 'arglebargle')
    '.vimrc'
    >>> replaceExtension('a.b.c', 'd')
    'a.b.d'
    >>> replaceExtension('', 'a')
    ''
    >>> replaceExtension('foo.bar', '')
    'foo.'
    '''
    sepFile = filename.rpartition(".")
    if sepFile[0] == "":
        return filename
    else:
        return sepFile[0] + "." + newExt


def isSyncFile(filename):
    extension = filename.rpartition(".")[2].lower()
    if extension == '!sync' or extension == 'lftp-pget-status':
        return True
    else:
        return False


def isMediaFile(filename):
    # ignore samples
    if re.search('(^|[\W_])(sample\d*)[\W_]', filename, re.I):
        return False

    # ignore MAC OS's retarded "resource fork" files
    if filename.startswith('._'):
        return False

    sepFile = filename.rpartition(".")

    if re.search('extras?$', sepFile[0], re.I):
        return False

    if sepFile[2].lower() in mediaExtensions:
        return True
    else:
        return False


def isRarFile(filename):
    archive_regex = '(?P<file>^(?P<base>(?:(?!\.part\d+\.rar$).)*)\.(?:(?:part0*1\.)?rar)$)'

    if re.search(archive_regex, filename):
        return True

    return False


def sanitizeFileName(name):
    '''
    >>> sanitizeFileName('a/b/c')
    'a-b-c'
    >>> sanitizeFileName('abc')
    'abc'
    >>> sanitizeFileName('a"b')
    'ab'
    >>> sanitizeFileName('.a.b..')
    'a.b'
    '''

    # remove bad chars from the filename
    name = re.sub(r'[\\/\*]', '-', name)
    name = re.sub(r'[:"<>|?]', '', name)

    # remove leading/trailing periods and spaces
    name = name.strip(' .')

    return name


def _remove_file_failed(file):
    try:
        ek.ek(os.remove, file)
    except:
        pass

def findCertainShow(showList, indexerid):

    results = []
    if showList and indexerid:
        results = filter(lambda x: int(x.indexerid) == int(indexerid), showList)

    if len(results) == 1:
        return results[0]
    elif len(results) > 1:
        raise MultipleShowObjectsException()

def makeDir(path):
    if not ek.ek(os.path.isdir, path):
        try:
            ek.ek(os.makedirs, path)
            # do the library update for synoindex
            notifiers.synoindex_notifier.addFolder(path)
        except OSError:
            return False
    return True


def searchIndexerForShowID(regShowName, indexer=None, indexer_id=None, ui=None):
    showNames = [re.sub('[. -]', ' ', regShowName)]

    # Query Indexers for each search term and build the list of results
    for i in sickbeard.indexerApi().indexers if not indexer else int(indexer or []):
        # Query Indexers for each search term and build the list of results
        lINDEXER_API_PARMS = sickbeard.indexerApi(i).api_params.copy()
        if ui is not None: lINDEXER_API_PARMS['custom_ui'] = ui
        t = sickbeard.indexerApi(i).indexer(**lINDEXER_API_PARMS)

        for name in showNames:
            logger.log(u"Trying to find " + name + " on " + sickbeard.indexerApi(i).name, logger.DEBUG)

            try:
                search = t[indexer_id] if indexer_id else t[name]
            except:
                continue

            try:
                seriesname = search.seriesname
            except:
                seriesname = None

            try:
                series_id = search.id
            except:
                series_id = None

            if not (seriesname and series_id):
                continue

            if str(name).lower() == str(seriesname).lower and not indexer_id:
                return (seriesname, i, int(series_id))
            elif int(indexer_id) == int(series_id):
                return (seriesname, i, int(indexer_id))

        if indexer:
            break

    return (None, None, None)


def sizeof_fmt(num):
    '''
    >>> sizeof_fmt(2)
    '2.0 bytes'
    >>> sizeof_fmt(1024)
    '1.0 KB'
    >>> sizeof_fmt(2048)
    '2.0 KB'
    >>> sizeof_fmt(2**20)
    '1.0 MB'
    >>> sizeof_fmt(1234567)
    '1.2 MB'
    '''
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0


def listMediaFiles(path):
    if not dir or not ek.ek(os.path.isdir, path):
        return []

    files = []
    for curFile in ek.ek(os.listdir, path):
        fullCurFile = ek.ek(os.path.join, path, curFile)

        # if it's a folder do it recursively
        if ek.ek(os.path.isdir, fullCurFile) and not curFile.startswith('.') and not curFile == 'Extras':
            files += listMediaFiles(fullCurFile)

        elif isMediaFile(curFile):
            files.append(fullCurFile)

    return files


def copyFile(srcFile, destFile):
    ek.ek(shutil.copyfile, srcFile, destFile)
    try:
        ek.ek(shutil.copymode, srcFile, destFile)
    except OSError:
        pass


def moveFile(srcFile, destFile):
    try:
        ek.ek(os.rename, srcFile, destFile)
        fixSetGroupID(destFile)
    except OSError:
        copyFile(srcFile, destFile)
        ek.ek(os.unlink, srcFile)


def link(src, dst):
    if os.name == 'nt':
        import ctypes

        if ctypes.windll.kernel32.CreateHardLinkW(unicode(dst), unicode(src), 0) == 0: raise ctypes.WinError()
    else:
        os.link(src, dst)


def hardlinkFile(srcFile, destFile):
    try:
        ek.ek(link, srcFile, destFile)
        fixSetGroupID(destFile)
    except Exception, e:
        logger.log(u"Failed to create hardlink of " + srcFile + " at " + destFile + ": " + ex(e) + ". Copying instead",
                   logger.ERROR)
        copyFile(srcFile, destFile)


def symlink(src, dst):
    if os.name == 'nt':
        import ctypes

        if ctypes.windll.kernel32.CreateSymbolicLinkW(unicode(dst), unicode(src), 1 if os.path.isdir(src) else 0) in [0,
                                                                                                                      1280]: raise ctypes.WinError()
    else:
        os.symlink(src, dst)


def moveAndSymlinkFile(srcFile, destFile):
    try:
        ek.ek(os.rename, srcFile, destFile)
        fixSetGroupID(destFile)
        ek.ek(symlink, destFile, srcFile)
    except:
        logger.log(u"Failed to create symlink of " + srcFile + " at " + destFile + ". Copying instead", logger.ERROR)
        copyFile(srcFile, destFile)


def make_dirs(path):
    """
    Creates any folders that are missing and assigns them the permissions of their
    parents
    """

    logger.log(u"Checking if the path " + path + " already exists", logger.DEBUG)

    if not ek.ek(os.path.isdir, path):
        # Windows, create all missing folders
        if os.name == 'nt' or os.name == 'ce':
            try:
                logger.log(u"Folder " + path + " doesn't exist, creating it", logger.DEBUG)
                ek.ek(os.makedirs, path)
            except (OSError, IOError), e:
                logger.log(u"Failed creating " + path + " : " + ex(e), logger.ERROR)
                return False

        # not Windows, create all missing folders and set permissions
        else:
            sofar = ''
            folder_list = path.split(os.path.sep)

            # look through each subfolder and make sure they all exist
            for cur_folder in folder_list:
                sofar += cur_folder + os.path.sep

                # if it exists then just keep walking down the line
                if ek.ek(os.path.isdir, sofar):
                    continue

                try:
                    logger.log(u"Folder " + sofar + " doesn't exist, creating it", logger.DEBUG)
                    ek.ek(os.mkdir, sofar)
                    # use normpath to remove end separator, otherwise checks permissions against itself
                    chmodAsParent(ek.ek(os.path.normpath, sofar))
                    # do the library update for synoindex
                    notifiers.synoindex_notifier.addFolder(sofar)
                except (OSError, IOError), e:
                    logger.log(u"Failed creating " + sofar + " : " + ex(e), logger.ERROR)
                    return False

    return True


def rename_ep_file(cur_path, new_path, old_path_length=0):
    """
    Creates all folders needed to move a file to its new location, renames it, then cleans up any folders
    left that are now empty.

    cur_path: The absolute path to the file you want to move/rename
    new_path: The absolute path to the destination for the file WITHOUT THE EXTENSION
    old_path_length: The length of media file path (old name) WITHOUT THE EXTENSION
    """

    new_dest_dir, new_dest_name = os.path.split(new_path)  # @UnusedVariable

    if old_path_length == 0 or old_path_length > len(cur_path):
        # approach from the right
        cur_file_name, cur_file_ext = os.path.splitext(cur_path)  # @UnusedVariable
    else:
        # approach from the left
        cur_file_ext = cur_path[old_path_length:]
        cur_file_name = cur_path[:old_path_length]

    if cur_file_ext[1:] in subtitleExtensions:
        # Extract subtitle language from filename
        sublang = os.path.splitext(cur_file_name)[1][1:]

        # Check if the language extracted from filename is a valid language
        try:
            language = subliminal.language.Language(sublang, strict=True)
            cur_file_ext = '.' + sublang + cur_file_ext
        except ValueError:
            pass

    # put the extension on the incoming file
    new_path += cur_file_ext

    make_dirs(os.path.dirname(new_path))

    # move the file
    try:
        logger.log(u"Renaming file from " + cur_path + " to " + new_path)
        ek.ek(os.rename, cur_path, new_path)
    except (OSError, IOError), e:
        logger.log(u"Failed renaming " + cur_path + " to " + new_path + ": " + ex(e), logger.ERROR)
        return False

    # clean up any old folders that are empty
    delete_empty_folders(ek.ek(os.path.dirname, cur_path))

    return True


def delete_empty_folders(check_empty_dir, keep_dir=None):
    """
    Walks backwards up the path and deletes any empty folders found.

    check_empty_dir: The path to clean (absolute path to a folder)
    keep_dir: Clean until this path is reached
    """

    # treat check_empty_dir as empty when it only contains these items
    ignore_items = []

    logger.log(u"Trying to clean any empty folders under " + check_empty_dir)

    # as long as the folder exists and doesn't contain any files, delete it
    while ek.ek(os.path.isdir, check_empty_dir) and check_empty_dir != keep_dir:
        check_files = ek.ek(os.listdir, check_empty_dir)

        if not check_files or (len(check_files) <= len(ignore_items) and all(
                [check_file in ignore_items for check_file in check_files])):
            # directory is empty or contains only ignore_items
            try:
                logger.log(u"Deleting empty folder: " + check_empty_dir)
                # need shutil.rmtree when ignore_items is really implemented
                ek.ek(os.rmdir, check_empty_dir)
                # do the library update for synoindex
                notifiers.synoindex_notifier.deleteFolder(check_empty_dir)
            except OSError, e:
                logger.log(u"Unable to delete " + check_empty_dir + ": " + repr(e) + " / " + str(e), logger.WARNING)
                break
            check_empty_dir = ek.ek(os.path.dirname, check_empty_dir)
        else:
            break


def fileBitFilter(mode):
    for bit in [stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH, stat.S_ISUID, stat.S_ISGID]:
        if mode & bit:
            mode -= bit

    return mode


def chmodAsParent(childPath):
    if os.name == 'nt' or os.name == 'ce':
        return

    parentPath = ek.ek(os.path.dirname, childPath)

    if not parentPath:
        logger.log(u"No parent path provided in " + childPath + ", unable to get permissions from it", logger.DEBUG)
        return

    parentPathStat = ek.ek(os.stat, parentPath)
    parentMode = stat.S_IMODE(parentPathStat[stat.ST_MODE])

    childPathStat = ek.ek(os.stat, childPath)
    childPath_mode = stat.S_IMODE(childPathStat[stat.ST_MODE])

    if ek.ek(os.path.isfile, childPath):
        childMode = fileBitFilter(parentMode)
    else:
        childMode = parentMode

    if childPath_mode == childMode:
        return

    childPath_owner = childPathStat.st_uid
    user_id = os.geteuid()  # @UndefinedVariable - only available on UNIX

    if user_id != 0 and user_id != childPath_owner:
        logger.log(u"Not running as root or owner of " + childPath + ", not trying to set permissions", logger.DEBUG)
        return

    try:
        ek.ek(os.chmod, childPath, childMode)
        logger.log(u"Setting permissions for %s to %o as parent directory has %o" % (childPath, childMode, parentMode),
                   logger.DEBUG)
    except OSError:
        logger.log(u"Failed to set permission for %s to %o" % (childPath, childMode), logger.ERROR)


def fixSetGroupID(childPath):
    if os.name == 'nt' or os.name == 'ce':
        return

    parentPath = ek.ek(os.path.dirname, childPath)
    parentStat = ek.ek(os.stat, parentPath)
    parentMode = stat.S_IMODE(parentStat[stat.ST_MODE])

    if parentMode & stat.S_ISGID:
        parentGID = parentStat[stat.ST_GID]
        childStat = ek.ek(os.stat, childPath)
        childGID = childStat[stat.ST_GID]

        if childGID == parentGID:
            return

        childPath_owner = childStat.st_uid
        user_id = os.geteuid()  # @UndefinedVariable - only available on UNIX

        if user_id != 0 and user_id != childPath_owner:
            logger.log(u"Not running as root or owner of " + childPath + ", not trying to set the set-group-ID",
                       logger.DEBUG)
            return

        try:
            ek.ek(os.chown, childPath, -1, parentGID)  # @UndefinedVariable - only available on UNIX
            logger.log(u"Respecting the set-group-ID bit on the parent directory for %s" % (childPath), logger.DEBUG)
        except OSError:
            logger.log(
                u"Failed to respect the set-group-ID bit on the parent directory for %s (setting group ID %i)" % (
                    childPath, parentGID), logger.ERROR)


def get_absolute_number_from_season_and_episode(show, season, episode):
    absolute_number = None

    if season and episode:
        myDB = db.DBConnection()
        sql = "SELECT * FROM tv_episodes WHERE showid = ? and season = ? and episode = ?"
        sqlResults = myDB.select(sql, [show.indexerid, season, episode])

        if len(sqlResults) == 1:
            absolute_number = int(sqlResults[0]["absolute_number"])
            logger.log(
                "Found absolute_number:" + str(absolute_number) + " by " + str(season) + "x" + str(episode),
                logger.DEBUG)
        else:
            logger.log(
                "No entries for absolute number in show: " + show.name + " found using " + str(season) + "x" + str(
                    episode),
                logger.DEBUG)

    return absolute_number


def get_all_episodes_from_absolute_number(show, absolute_numbers, indexer_id=None):
    episodes = []
    season = None

    if len(absolute_numbers):
        if not show and indexer_id:
            show = findCertainShow(sickbeard.showList, indexer_id)

        if show:
            for absolute_number in absolute_numbers:
                ep = show.getEpisode(None, None, absolute_number=absolute_number)
                if ep:
                    episodes.append(ep.episode)
                    season = ep.season  # this will always take the last found seson so eps that cross the season border are not handeled well

    return (season, episodes)


def sanitizeSceneName(name, ezrss=False):
    """
    Takes a show name and returns the "scenified" version of it.

    ezrss: If true the scenified version will follow EZRSS's cracksmoker rules as best as possible

    Returns: A string containing the scene version of the show name given.
    """

    if name:
        if not ezrss:
            bad_chars = u",:()'!?\u2019"
        # ezrss leaves : and ! in their show names as far as I can tell
        else:
            bad_chars = u",()'?\u2019"

        # strip out any bad chars
        for x in bad_chars:
            name = name.replace(x, "")

        # tidy up stuff that doesn't belong in scene names
        name = name.replace("- ", ".").replace(" ", ".").replace("&", "and").replace('/', '.')
        name = re.sub("\.\.*", ".", name)

        if name.endswith('.'):
            name = name[:-1]

        return name
    else:
        return ''


def create_https_certificates(ssl_cert, ssl_key):
    """
    Create self-signed HTTPS certificares and store in paths 'ssl_cert' and 'ssl_key'
    """
    try:
        from OpenSSL import crypto  # @UnresolvedImport
        from lib.certgen import createKeyPair, createCertRequest, createCertificate, TYPE_RSA, \
            serial  # @UnresolvedImport
    except Exception, e:
        logger.log(u"pyopenssl module missing, please install for https access", logger.WARNING)
        return False

    # Create the CA Certificate
    cakey = createKeyPair(TYPE_RSA, 1024)
    careq = createCertRequest(cakey, CN='Certificate Authority')
    cacert = createCertificate(careq, (careq, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    cname = 'SickGear'
    pkey = createKeyPair(TYPE_RSA, 1024)
    req = createCertRequest(pkey, CN=cname)
    cert = createCertificate(req, (cacert, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    # Save the key and certificate to disk
    try:
        open(ssl_key, 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        open(ssl_cert, 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    except:
        logger.log(u"Error creating SSL key and certificate", logger.ERROR)
        return False

    return True


if __name__ == '__main__':
    import doctest

    doctest.testmod()


def parse_xml(data, del_xmlns=False):
    """
    Parse data into an xml elementtree.ElementTree

    data: data string containing xml
    del_xmlns: if True, removes xmlns namesspace from data before parsing

    Returns: parsed data as elementtree or None
    """

    if del_xmlns:
        data = re.sub(' xmlns="[^"]+"', '', data)

    try:
        parsedXML = etree.fromstring(data)
    except Exception, e:
        logger.log(u"Error trying to parse xml data. Error: " + ex(e), logger.DEBUG)
        parsedXML = None

    return parsedXML


def backupVersionedFile(old_file, version):
    numTries = 0

    new_file = old_file + '.' + 'v' + str(version)

    while not ek.ek(os.path.isfile, new_file):
        if not ek.ek(os.path.isfile, old_file):
            logger.log(u"Not creating backup, " + old_file + " doesn't exist", logger.DEBUG)
            break

        try:
            logger.log(u"Trying to back up " + old_file + " to " + new_file, logger.DEBUG)
            shutil.copy(old_file, new_file)
            logger.log(u"Backup done", logger.DEBUG)
            break
        except Exception, e:
            logger.log(u"Error while trying to back up " + old_file + " to " + new_file + " : " + ex(e), logger.WARNING)
            numTries += 1
            time.sleep(1)
            logger.log(u"Trying again.", logger.DEBUG)

        if numTries >= 10:
            logger.log(u"Unable to back up " + old_file + " to " + new_file + " please do it manually.", logger.ERROR)
            return False

    return True


def restoreVersionedFile(backup_file, version):
    numTries = 0

    new_file, backup_version = os.path.splitext(backup_file)
    restore_file = new_file + '.' + 'v' + str(version)

    if not ek.ek(os.path.isfile, new_file):
        logger.log(u"Not restoring, " + new_file + " doesn't exist", logger.DEBUG)
        return False

    try:
        logger.log(
            u"Trying to backup " + new_file + " to " + new_file + "." + "r" + str(version) + " before restoring backup",
            logger.DEBUG)
        shutil.move(new_file, new_file + '.' + 'r' + str(version))
    except Exception, e:
        logger.log(
            u"Error while trying to backup DB file " + restore_file + " before proceeding with restore: " + ex(e),
            logger.WARNING)
        return False

    while not ek.ek(os.path.isfile, new_file):
        if not ek.ek(os.path.isfile, restore_file):
            logger.log(u"Not restoring, " + restore_file + " doesn't exist", logger.DEBUG)
            break

        try:
            logger.log(u"Trying to restore " + restore_file + " to " + new_file, logger.DEBUG)
            shutil.copy(restore_file, new_file)
            logger.log(u"Restore done", logger.DEBUG)
            break
        except Exception, e:
            logger.log(u"Error while trying to restore " + restore_file + ": " + ex(e), logger.WARNING)
            numTries += 1
            time.sleep(1)
            logger.log(u"Trying again.", logger.DEBUG)

        if numTries >= 10:
            logger.log(u"Unable to restore " + restore_file + " to " + new_file + " please do it manually.",
                       logger.ERROR)
            return False

    return True


# try to convert to int, if it fails the default will be returned
def tryInt(s, s_default=0):
    try:
        return int(s)
    except:
        return s_default


# generates a md5 hash of a file
def md5_for_file(filename, block_size=2 ** 16):
    try:
        with open(filename, 'rb') as f:
            md5 = hashlib.md5()
            while True:
                data = f.read(block_size)
                if not data:
                    break
                md5.update(data)
            f.close()
            return md5.hexdigest()
    except Exception:
        return None


def get_lan_ip():
    """
    Simple function to get LAN localhost_ip
    http://stackoverflow.com/questions/11735821/python-get-localhost-ip
    """

    if os.name != "nt":
        import fcntl
        import struct

        def get_interface_ip(ifname):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s',
                                                                                ifname[:15]))[20:24])

    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127.") and os.name != "nt":
        interfaces = [
            "eth0",
            "eth1",
            "eth2",
            "wlan0",
            "wlan1",
            "wifi0",
            "ath0",
            "ath1",
            "ppp0",
        ]
        for ifname in interfaces:
            try:
                ip = get_interface_ip(ifname)
                print ifname, ip
                break
            except IOError:
                pass
    return ip


def check_url(url):
    """
    Check if a URL exists without downloading the whole file.
    We only check the URL header.
    """
    # see also http://stackoverflow.com/questions/2924422
    # http://stackoverflow.com/questions/1140661
    good_codes = [httplib.OK, httplib.FOUND, httplib.MOVED_PERMANENTLY]

    host, path = urlparse.urlparse(url)[1:3]  # elems [1] and [2]
    try:
        conn = httplib.HTTPConnection(host)
        conn.request('HEAD', path)
        return conn.getresponse().status in good_codes
    except StandardError:
        return None


def anon_url(*url):
    """
    Return a URL string consisting of the Anonymous redirect URL and an arbitrary number of values appended.
    """
    return '' if None in url else '%s%s' % (sickbeard.ANON_REDIRECT, ''.join(str(s) for s in url))


def starify(text, verify=False):
    """
    Return text input string with either its latter half or its centre area (if 12 chars or more)
    replaced with asterisks. Useful for securely presenting api keys to a ui.

    If verify is true, return true if text is a star block created text else return false.
    """
    return ((('%s%s' % (text[:len(text) / 2], '*' * (len(text) / 2))),
            ('%s%s%s' % (text[:4], '*' * (len(text) - 8), text[-4:])))[12 <= len(text)],
            set('*') == set((text[len(text) / 2:], text[4:-4])[12 <= len(text)]))[verify]

"""
Encryption
==========
By Pedro Jose Pereira Vieito <pvieito@gmail.com> (@pvieito)

* If encryption_version==0 then return data without encryption
* The keys should be unique for each device

To add a new encryption_version:
  1) Code your new encryption_version
  2) Update the last encryption_version available in webserve.py
  3) Remember to maintain old encryption versions and key generators for retrocompatibility
"""

# Key Generators
unique_key1 = hex(uuid.getnode() ** 2)  # Used in encryption v1


# Encryption Functions
def encrypt(data, encryption_version=0, decrypt=False):
    # Version 1: Simple XOR encryption (this is not very secure, but works)
    if encryption_version == 1:
        if decrypt:
            return ''.join(chr(ord(x) ^ ord(y)) for (x, y) in izip(base64.decodestring(data), cycle(unique_key1)))
        else:
            return base64.encodestring(
                ''.join(chr(ord(x) ^ ord(y)) for (x, y) in izip(data, cycle(unique_key1)))).strip()
    # Version 0: Plain text
    else:
        return data


def decrypt(data, encryption_version=0):
    return encrypt(data, encryption_version, decrypt=True)


def full_sanitizeSceneName(name):
    return re.sub('[. -]', ' ', sanitizeSceneName(name)).lower().lstrip()


def get_show(name, tryIndexers=False):
    if not sickbeard.showList or None is name:
        return

    showObj = None
    fromCache = False

    try:
        # check cache for show
        cache = sickbeard.name_cache.retrieveNameFromCache(name)
        if cache:
            fromCache = True
            showObj = findCertainShow(sickbeard.showList, int(cache))

        if not showObj and tryIndexers:
            showObj = findCertainShow(sickbeard.showList,
                                      searchIndexerForShowID(full_sanitizeSceneName(name), ui=classes.ShowListUI)[2])

        # add show to cache
        if showObj and not fromCache:
            sickbeard.name_cache.addNameToCache(name, showObj.indexerid)
    except Exception as e:
        logger.log(u"Error when attempting to find show: " + name + " in SickGear: " + str(e), logger.DEBUG)

    return showObj


def is_hidden_folder(folder):
    """
    Returns True if folder is hidden.
    On Linux based systems hidden folders start with . (dot)
    folder: Full path of folder to check
    """
    if ek.ek(os.path.isdir, folder):
        if ek.ek(os.path.basename, folder).startswith('.'):
            return True

    return False


def real_path(path):
    """
    Returns: the canonicalized absolute pathname. The resulting path will have no symbolic link, '/./' or '/../' components.
    """
    return ek.ek(os.path.normpath, ek.ek(os.path.normcase, ek.ek(os.path.realpath, path)))


def validateShow(show, season=None, episode=None):
    indexer_lang = show.lang

    try:
        lINDEXER_API_PARMS = sickbeard.indexerApi(show.indexer).api_params.copy()

        if indexer_lang and not indexer_lang == 'en':
            lINDEXER_API_PARMS['language'] = indexer_lang

        t = sickbeard.indexerApi(show.indexer).indexer(**lINDEXER_API_PARMS)
        if season is None and episode is None:
            return t

        return t[show.indexerid][season][episode]
    except (sickbeard.indexer_episodenotfound, sickbeard.indexer_seasonnotfound):
        pass


def set_up_anidb_connection():
    if not sickbeard.USE_ANIDB:
        logger.log(u'Usage of anidb disabled. Skipping', logger.DEBUG)
        return False

    if not sickbeard.ANIDB_USERNAME and not sickbeard.ANIDB_PASSWORD:
        logger.log(u'anidb username and/or password are not set. Aborting anidb lookup.', logger.DEBUG)
        return False

    if not sickbeard.ADBA_CONNECTION:
        anidb_logger = lambda x: logger.log('ANIDB: ' + str(x), logger.DEBUG)
        sickbeard.ADBA_CONNECTION = adba.Connection(keepAlive=True, log=anidb_logger)

    auth = False
    try:
        auth = sickbeard.ADBA_CONNECTION.authed()
    except Exception, e:
        logger.log(u'exception msg: ' + str(e))
        pass

    if not auth:
        try:
            sickbeard.ADBA_CONNECTION.auth(sickbeard.ANIDB_USERNAME, sickbeard.ANIDB_PASSWORD)
        except Exception, e:
            logger.log(u'exception msg: ' + str(e))
            return False
    else:
        return True

    return sickbeard.ADBA_CONNECTION.authed()


def mapIndexersToShow(showObj):
    mapped = {}

    # init mapped indexers object
    for indexer in sickbeard.indexerApi().indexers:
        mapped[indexer] = showObj.indexerid if int(indexer) == int(showObj.indexer) else 0

    myDB = db.DBConnection()
    sqlResults = myDB.select(
        "SELECT * FROM indexer_mapping WHERE indexer_id = ? AND indexer = ?",
        [showObj.indexerid, showObj.indexer])

    # for each mapped entry
    for curResult in sqlResults:
        nlist = [i for i in curResult if None is not i]
        # Check if its mapped with both tvdb and tvrage.
        if 4 <= len(nlist):
            logger.log(u"Found indexer mapping in cache for show: " + showObj.name, logger.DEBUG)
            mapped[int(curResult['mindexer'])] = int(curResult['mindexer_id'])
            break

    else:
        sql_l = []
        for indexer in sickbeard.indexerApi().indexers:
            if indexer == showObj.indexer:
                mapped[indexer] = showObj.indexerid
                continue

            lINDEXER_API_PARMS = sickbeard.indexerApi(indexer).api_params.copy()
            lINDEXER_API_PARMS['custom_ui'] = classes.ShowListUI
            t = sickbeard.indexerApi(indexer).indexer(**lINDEXER_API_PARMS)

            try:
                mapped_show = t[showObj.name]
            except sickbeard.indexer_shownotfound:
                logger.log(u"Unable to map " + sickbeard.indexerApi(showObj.indexer).name + "->" + sickbeard.indexerApi(
                    indexer).name + " for show: " + showObj.name + ", skipping it", logger.DEBUG)
                continue

            if mapped_show and len(mapped_show) == 1:
                logger.log(u"Mapping " + sickbeard.indexerApi(showObj.indexer).name + "->" + sickbeard.indexerApi(
                    indexer).name + " for show: " + showObj.name, logger.DEBUG)

                mapped[indexer] = int(mapped_show[0]['id'])

                logger.log(u"Adding indexer mapping to DB for show: " + showObj.name, logger.DEBUG)

                sql_l.append([
                    "INSERT OR IGNORE INTO indexer_mapping (indexer_id, indexer, mindexer_id, mindexer) VALUES (?,?,?,?)",
                    [showObj.indexerid, showObj.indexer, int(mapped_show[0]['id']), indexer]])

        if len(sql_l) > 0:
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)

    return mapped


def touchFile(fname, atime=None):
    if None != atime:
        try:
            with file(fname, 'a'):
                os.utime(fname, (atime, atime))
                return True
        except:
            logger.log(u"File air date stamping not available on your OS", logger.DEBUG)
            pass

    return False


def _getTempDir():
    """Returns the [system temp dir]/tvdb_api-u501 (or
    tvdb_api-myuser)
    """
    if hasattr(os, 'getuid'):
        uid = "u%d" % (os.getuid())
    else:
        # For Windows
        try:
            uid = getpass.getuser()
        except ImportError:
            return os.path.join(tempfile.gettempdir(), "SickGear")

    return os.path.join(tempfile.gettempdir(), "SickGear-%s" % (uid))


def proxy_setting(proxy_setting, request_url, force=False):
    """
    Returns a list of a) proxy_setting address value or a PAC is fetched and parsed if proxy_setting
    starts with "PAC:" (case-insensitive) and b) True/False if "PAC" is found in the proxy_setting.

    The PAC data parser is crude, javascript is not eval'd. The first "PROXY URL" found is extracted with a list
    of "url_a_part.url_remaining", "url_b_part.url_remaining", "url_n_part.url_remaining" and so on.
    Also, PAC data items are escaped for matching therefore regular expression items will not match a request_url.

    If force is True or request_url contains a PAC parsed data item then the PAC proxy address is returned else False.
    None is returned in the event of an error fetching PAC data.

    """

    # check for "PAC" usage
    match = re.search(r'^\s*PAC:\s*(.*)', proxy_setting, re.I)
    if not match:
        return proxy_setting, False
    pac_url = match.group(1)

    # prevent a recursive test with existing proxy setting when fetching PAC url
    proxy_setting_backup = sickbeard.PROXY_SETTING
    sickbeard.PROXY_SETTING = ''

    resp = ''
    try:
        resp = getURL(pac_url)
    except:
        pass
    sickbeard.PROXY_SETTING = proxy_setting_backup

    if not resp:
        return None, False

    proxy_address = None
    request_url_match = False
    parsed_url = urlparse.urlparse(request_url)
    netloc = (parsed_url.path, parsed_url.netloc)['' != parsed_url.netloc]
    for pac_data in re.finditer(r"""(?:[^'"]*['"])([^\.]+\.[^'"]*)(?:['"])""", resp, re.I):
        data = re.search(r"""PROXY\s+([^'"]+)""", pac_data.group(1), re.I)
        if data:
            if force:
                return data.group(1), True
            proxy_address = (proxy_address, data.group(1))[None is proxy_address]
        elif re.search(re.escape(pac_data.group(1)), netloc, re.I):
            request_url_match = True
            if None is not proxy_address:
                break

    if None is proxy_address:
        return None, True

    return (False, proxy_address)[request_url_match], True


def getURL(url, post_data=None, params=None, headers=None, timeout=30, session=None, json=False):
    """
    Returns a byte-string retrieved from the url provider.
    """

    # request session
    cache_dir = sickbeard.CACHE_DIR or _getTempDir()
    session = CacheControl(sess=session, cache=caches.FileCache(os.path.join(cache_dir, 'sessions')))

    # request session headers
    req_headers = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip,deflate'}
    if headers:
        req_headers.update(headers)
    session.headers.update(req_headers)

    # request session ssl verify
    session.verify = False

    # request session paramaters
    session.params = params

    try:
        # Remove double-slashes from url
        parsed = list(urlparse.urlparse(url))
        parsed[2] = re.sub("/{2,}", "/", parsed[2])  # replace two or more / with one
        url = urlparse.urlunparse(parsed)

        # request session proxies
        if sickbeard.PROXY_SETTING:
            (proxy_address, pac_found) = proxy_setting(sickbeard.PROXY_SETTING, url)
            msg = '%sproxy for url: %s' % (('', 'PAC parsed ')[pac_found], url)
            if None is proxy_address:
                logger.log('Proxy error, aborted the request using %s' % msg, logger.DEBUG)
                return
            elif proxy_address:
                logger.log('Using %s' % msg, logger.DEBUG)
                session.proxies = {
                    'http': proxy_address,
                    'https': proxy_address
                }

        # decide if we get or post data to server
        if post_data:
            resp = session.post(url, data=post_data, timeout=timeout)
        else:
            resp = session.get(url, timeout=timeout)

        if not resp.ok:
            logger.log(u"Requested url " + url + " returned status code is " + str(
                resp.status_code) + ': ' + clients.http_error_code[resp.status_code], logger.DEBUG)
            return

    except requests.exceptions.HTTPError, e:
        logger.log(u"HTTP error " + str(e.errno) + " while loading URL " + url, logger.WARNING)
        return
    except requests.exceptions.ConnectionError, e:
        logger.log(u"Connection error " + str(e.message) + " while loading URL " + url, logger.WARNING)
        return
    except requests.exceptions.Timeout, e:
        logger.log(u"Connection timed out " + str(e.message) + " while loading URL " + url, logger.WARNING)
        return
    except requests.exceptions.ReadTimeout, e:
        logger.log(u'Read timed out ' + str(e.message) + ' while loading URL ' + url, logger.WARNING)
        return
    except Exception:
        logger.log(u"Unknown exception while loading URL " + url + ": " + traceback.format_exc(), logger.WARNING)
        return

    if json:
        return resp.json()

    return resp.content


def download_file(url, filename, session=None):
    # create session
    cache_dir = sickbeard.CACHE_DIR or _getTempDir()
    session = CacheControl(sess=session, cache=caches.FileCache(os.path.join(cache_dir, 'sessions')))

    # request session headers
    session.headers.update({'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip,deflate'})

    # request session ssl verify
    session.verify = False

    # request session streaming
    session.stream = True

    # request session proxies
    if sickbeard.PROXY_SETTING:
        (proxy_address, pac_found) = proxy_setting(sickbeard.PROXY_SETTING, url)
        msg = '%sproxy for url: %s' % (('', 'PAC parsed ')[pac_found], url)
        if None is proxy_address:
            logger.log('Proxy error, aborted the request using %s' % msg, logger.DEBUG)
            return
        elif proxy_address:
            logger.log('Using %s' % msg, logger.DEBUG)
            session.proxies = {
                'http': proxy_address,
                'https': proxy_address
            }

    try:
        resp = session.get(url)
        if not resp.ok:
            logger.log(u"Requested url " + url + " returned status code is " + str(
                resp.status_code) + ': ' + clients.http_error_code[resp.status_code], logger.DEBUG)
            return False

        with open(filename, 'wb') as fp:
            for chunk in resp.iter_content(chunk_size=1024):
                if chunk:
                    fp.write(chunk)
                    fp.flush()

        chmodAsParent(filename)
    except requests.exceptions.HTTPError, e:
        _remove_file_failed(filename)
        logger.log(u"HTTP error " + str(e.errno) + " while loading URL " + url, logger.WARNING)
        return False
    except requests.exceptions.ConnectionError, e:
        _remove_file_failed(filename)
        logger.log(u"Connection error " + str(e.message) + " while loading URL " + url, logger.WARNING)
        return False
    except requests.exceptions.Timeout, e:
        _remove_file_failed(filename)
        logger.log(u"Connection timed out " + str(e.message) + " while loading URL " + url, logger.WARNING)
        return False
    except EnvironmentError, e:
        _remove_file_failed(filename)
        logger.log(u"Unable to save the file: " + ex(e), logger.ERROR)
        return False
    except Exception:
        _remove_file_failed(filename)
        logger.log(u"Unknown exception while loading URL " + url + ": " + traceback.format_exc(), logger.WARNING)
        return False

    return True


def clearCache(force=False):
    update_datetime = datetime.datetime.now()

    # clean out cache directory, remove everything > 12 hours old
    if sickbeard.CACHE_DIR:
        logger.log(u"Trying to clean cache folder " + sickbeard.CACHE_DIR)

        # Does our cache_dir exists
        if not ek.ek(os.path.isdir, sickbeard.CACHE_DIR):
            logger.log(u"Can't clean " + sickbeard.CACHE_DIR + " if it doesn't exist", logger.WARNING)
        else:
            max_age = datetime.timedelta(hours=12)

            # Get all our cache files
            exclude = ['rss', 'images']
            for cache_root, cache_dirs, cache_files in os.walk(sickbeard.CACHE_DIR, topdown=True):
                cache_dirs[:] = [d for d in cache_dirs if d not in exclude]

                for file in cache_files:
                    cache_file = ek.ek(os.path.join, cache_root, file)

                    if ek.ek(os.path.isfile, cache_file):
                        cache_file_modified = datetime.datetime.fromtimestamp(
                            ek.ek(os.path.getmtime, cache_file))

                        if force or (update_datetime - cache_file_modified > max_age):
                            try:
                                ek.ek(os.remove, cache_file)
                            except OSError, e:
                                logger.log(u"Unable to clean " + cache_root + ": " + repr(e) + " / " + str(e),
                                           logger.WARNING)
                                break


def human(size):
    """
    format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
    Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
    e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc
    """
    if size == 1:
        # because I really hate unnecessary plurals
        return "1 byte"

    suffixes_table = [('bytes', 0), ('KB', 0), ('MB', 1), ('GB', 2),('TB', 2), ('PB', 2)]

    num = float(size)
    for suffix, precision in suffixes_table:
        if num < 1024.0:
            break
        num /= 1024.0

    if precision == 0:
        formatted_size = "%d" % num
    else:
        formatted_size = str(round(num, ndigits=precision))

    return "%s %s" % (formatted_size, suffix)


def get_size(start_path='.'):

    total_size = 0
    for dirpath, dirnames, filenames in ek.ek(os.walk, start_path):
        for f in filenames:
            fp = ek.ek(os.path.join, dirpath, f)
            total_size += ek.ek(os.path.getsize, fp)
    return total_size


def remove_article(text=''):
    return re.sub(r'(?i)^(?:(?:A(?!\s+to)n?)|The)\s(\w)', r'\1', text)


def maybe_plural(number=1):
    return ('s', '')[1 == number]


def build_dict(seq, key):
    return dict((d[key], dict(d, index=index)) for (index, d) in enumerate(seq))


def client_host(server_host):
    '''Extracted from cherrypy libs
    Return the host on which a client can connect to the given listener.'''
    if server_host == '0.0.0.0':
        # 0.0.0.0 is INADDR_ANY, which should answer on localhost.
        return '127.0.0.1'
    if server_host in ('::', '::0', '::0.0.0.0'):
        # :: is IN6ADDR_ANY, which should answer on localhost.
        # ::0 and ::0.0.0.0 are non-canonical but common ways to write
        # IN6ADDR_ANY.
        return '::1'
    return server_host


def wait_for_free_port(host, port):
    '''Extracted from cherrypy libs
    Wait for the specified port to become free (drop requests).'''
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    for trial in range(50):
        try:
            # we are expecting a free port, so reduce the timeout
            check_port(host, port, timeout=0.1)
        except IOError:
            # Give the old server thread time to free the port.
            time.sleep(0.1)
        else:
            return

    raise IOError("Port %r is not free on %r" % (port, host))


def check_port(host, port, timeout=1.0):
    '''Extracted from cherrypy libs
    Raise an error if the given port is not free on the given host.'''
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    host = client_host(host)
    port = int(port)

    import socket

    # AF_INET or AF_INET6 socket
    # Get the correct address family for our host (allows IPv6 addresses)
    try:
        info = socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM)
    except socket.gaierror:
        if ':' in host:
            info = [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (host, port, 0, 0))]
        else:
            info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, port))]

    for res in info:
        af, socktype, proto, canonname, sa = res
        s = None
        try:
            s = socket.socket(af, socktype, proto)
            # See http://groups.google.com/group/cherrypy-users/
            #        browse_frm/thread/bbfe5eb39c904fe0
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            raise IOError("Port %s is in use on %s; perhaps the previous "
                          "httpserver did not shut down properly." %
                          (repr(port), repr(host)))
        except socket.error:
            if s:
                s.close()
