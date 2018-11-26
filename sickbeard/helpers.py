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

from __future__ import print_function
from __future__ import with_statement

import base64
import codecs
import datetime
import getpass
import hashlib
import io
import os
import re
import shutil
import socket
import stat
import tempfile
import time
import traceback
import urlparse
import uuid
import subprocess
import sys

import adba
import requests
import requests.exceptions
from cfscrape import CloudflareScraper
from lib.send2trash import send2trash
import sickbeard
import subliminal

try:
    import json
except ImportError:
    from lib import simplejson as json

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import elementtree.ElementTree as etree

from sickbeard.exceptions import MultipleShowObjectsException, ex
from sickbeard import logger, db, notifiers, clients
from sickbeard.common import USER_AGENT, mediaExtensions, subtitleExtensions, cpu_presets, statusStrings, \
    SNATCHED_ANY, DOWNLOADED, ARCHIVED, IGNORED, WANTED, SKIPPED, UNAIRED, UNKNOWN, SUBTITLED, FAILED, Quality, Overview
from sickbeard import encodingKludge as ek

from lib.cachecontrol import CacheControl, caches
from lib.scandir.scandir import scandir
from itertools import izip, cycle


def indentXML(elem, level=0):
    """
    Does our pretty printing, makes Matt very happy
    """
    i = '\n' + level * '  '
    if len(elem):
        if not elem.text or not ('%s' % elem.text).strip():
            elem.text = i + '  '
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indentXML(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        # Strip out the newlines from text
        if elem.text:
            elem.text = ('%s' % elem.text).replace('\n', ' ')
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


def remove_non_release_groups(name, is_anime=False):
    """
    Remove non release groups from name
    """

    if name:
        rc = [re.compile(r'(?i)' + v) for v in [
              '([\s\.\-_\[\{\(]*(no-rar|nzbgeek|ripsalot|siklopentan)[\s\.\-_\]\}\)]*)$',
              '([\s\.\-_\[\{\(]rp[\s\.\-_\]\}\)]*)$',
              '(?<=\w)([\s\.\-_]*[\[\{\(][\s\.\-_]*(www\.\w+.\w+)[\s\.\-_]*[\]\}\)][\s\.\-_]*)$',
              '(?<=\w)([\s\.\-_]*[\[\{\(]\s*(rar(bg|tv)|((e[tz]|v)tv))[\s\.\-_]*[\]\}\)][\s\.\-_]*)$'] +
              (['(?<=\w)([\s\.\-_]*[\[\{\(][\s\.\-_]*[\w\s\.\-\_]+[\s\.\-_]*[\]\}\)][\s\.\-_]*)$',
                '^([\s\.\-_]*[\[\{\(][\s\.\-_]*[\w\s\.\-\_]+[\s\.\-_]*[\]\}\)][\s\.\-_]*)(?=\w)'], [])[is_anime]]
        rename = name = remove_extension(name)
        while rename:
            for regex in rc:
                name = regex.sub('', name)
            rename = (name, False)[name == rename]

    return name


def replaceExtension(filename, newExt):
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


def has_media_ext(filename):
    # ignore samples
    if re.search('(^|[\W_])(sample\d*)[\W_]', filename, re.I) \
            or filename.startswith('._'):  # and MAC OS's 'resource fork' files
        return False

    sep_file = filename.rpartition('.')
    return (None is re.search('extras?$', sep_file[0], re.I)) and (sep_file[2].lower() in mediaExtensions)


def has_image_ext(filename):
    try:
        if ek.ek(os.path.splitext, filename)[1].lower() in ['.bmp', '.gif', '.jpeg', '.jpg', '.png', '.webp']:
            return True
    except (StandardError, Exception):
        pass
    return False


def is_first_rar_volume(filename):

    return None is not re.search('(?P<file>^(?P<base>(?:(?!\.part\d+\.rar$).)*)\.(?:(?:part0*1\.)?rar)$)', filename)


def sanitizeFileName(name):
    # remove bad chars from the filename
    name = re.sub(r'[\\/\*]', '-', name)
    name = re.sub(r'[:"<>|?]', '', name)

    # remove leading/trailing periods and spaces
    name = name.strip(' .')

    for char in sickbeard.REMOVE_FILENAME_CHARS or []:
        name = name.replace(char, '')

    return name


def remove_file(filepath, tree=False, prefix_failure='', log_level=logger.MESSAGE):
    """
    Remove file based on setting for trash v permanent delete

    :param filepath: Path and file name
    :type filepath: String
    :param tree: Remove file tree
    :type tree: Bool
    :param prefix_failure: Text to prepend to error log, e.g. show id
    :type prefix_failure: String
    :param log_level: Log level to use for error
    :type log_level: Int
    :return: Type of removal ('Deleted' or 'Trashed') if filepath does not exist or None if no removal occurred
    :rtype: String or None
    """
    result = None
    if filepath:
        try:
            result = 'Deleted'
            if sickbeard.TRASH_REMOVE_SHOW:
                result = 'Trashed'
                ek.ek(send2trash, filepath)
            elif tree:
                ek.ek(shutil.rmtree, filepath)
            else:
                ek.ek(os.remove, filepath)
        except OSError as e:
            logger.log(u'%sUnable to %s %s %s: %s' % (prefix_failure, ('delete', 'trash')[sickbeard.TRASH_REMOVE_SHOW],
                                                      ('file', 'dir')[tree], filepath, str(e.strerror)), log_level)

    return (None, result)[filepath and not ek.ek(os.path.exists, filepath)]


def remove_file_failed(filename):
    try:
        ek.ek(os.remove, filename)
    except (StandardError, Exception):
        pass


def findCertainShow(showList, indexerid):
    results = []
    if showList and indexerid:
        results = filter(lambda x: int(x.indexerid) == int(indexerid), showList)

    if len(results) == 1:
        return results[0]
    elif len(results) > 1:
        raise MultipleShowObjectsException()


def find_show_by_id(show_list, id_dict, no_mapped_ids=True):
    """

    :param show_list:
    :type show_list: list
    :param id_dict: {indexer: id}
    :type id_dict: dict
    :param no_mapped_ids:
    :type no_mapped_ids: bool
    :return: showObj or MultipleShowObjectsException
    """
    results = []
    if show_list and id_dict and isinstance(id_dict, dict):
        id_dict = {k: v for k, v in id_dict.items() if v > 0}
        if no_mapped_ids:
            results = list(set([s for k, v in id_dict.iteritems() for s in show_list
                                if k == s.indexer and v == s.indexerid]))
        else:
            results = list(set([s for k, v in id_dict.iteritems() for s in show_list
                                if v == s.ids.get(k, {'id': 0})['id']]))

    if len(results) == 1:
        return results[0]
    elif len(results) > 1:
        raise MultipleShowObjectsException()


def makeDir(path):
    if not ek.ek(os.path.isdir, path):
        try:
            ek.ek(os.makedirs, path)
            # do the library update for synoindex
            notifiers.NotifierFactory().get('SYNOINDEX').addFolder(path)
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
            logger.log('Trying to find %s on %s' % (name, sickbeard.indexerApi(i).name), logger.DEBUG)

            try:
                result = t[indexer_id] if indexer_id else t[name]
            except:
                continue

            seriesname = series_id = None
            for search in result if isinstance(result, list) else [result]:
                try:
                    seriesname = search['seriesname']
                    series_id = search['id']
                except:
                    series_id = seriesname = None
                    continue
                if seriesname and series_id:
                    break

            if not (seriesname and series_id):
                continue

            if None is indexer_id and str(name).lower() == str(seriesname).lower():
                return seriesname, i, int(series_id)
            elif None is not indexer_id and int(indexer_id) == int(series_id):
                return seriesname, i, int(indexer_id)

        if indexer:
            break

    return None, None, None


def sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']:
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

        elif has_media_ext(curFile):
            files.append(fullCurFile)

    return files


def copyFile(srcFile, destFile):
    if os.name.startswith('posix'):
        ek.ek(subprocess.call, ['cp', srcFile, destFile])
    else:
        ek.ek(shutil.copyfile, srcFile, destFile)

    try:
        ek.ek(shutil.copymode, srcFile, destFile)
    except OSError:
        pass


def moveFile(srcFile, destFile):
    try:
        ek.ek(shutil.move, srcFile, destFile)
        fixSetGroupID(destFile)
    except OSError:
        copyFile(srcFile, destFile)
        ek.ek(os.unlink, srcFile)


def link(src, dst):
    if os.name == 'nt':
        import ctypes

        if ctypes.windll.kernel32.CreateHardLinkW(unicode(dst), unicode(src), 0) == 0: raise ctypes.WinError()
    else:
        ek.ek(os.link, src, dst)


def hardlinkFile(srcFile, destFile):
    try:
        ek.ek(link, srcFile, destFile)
        fixSetGroupID(destFile)
    except Exception as e:
        logger.log(u"Failed to create hardlink of " + srcFile + " at " + destFile + ": " + ex(e) + ". Copying instead",
                   logger.ERROR)
        copyFile(srcFile, destFile)


def symlink(src, dst):
    if os.name == 'nt':
        import ctypes

        if ctypes.windll.kernel32.CreateSymbolicLinkW(
                unicode(dst), unicode(src), 1 if ek.ek(os.path.isdir, src) else 0) in [0, 1280]:
            raise ctypes.WinError()
    else:
        ek.ek(os.symlink, src, dst)


def moveAndSymlinkFile(srcFile, destFile):
    try:
        ek.ek(shutil.move, srcFile, destFile)
        fixSetGroupID(destFile)
        ek.ek(symlink, destFile, srcFile)
    except:
        logger.log(u"Failed to create symlink of " + srcFile + " at " + destFile + ". Copying instead", logger.ERROR)
        copyFile(srcFile, destFile)


def make_dirs(path, syno=True):
    """
    Creates any folders that are missing and assigns them the permissions of their
    parents
    """

    if not ek.ek(os.path.isdir, path):
        # Windows, create all missing folders
        if os.name in ('nt', 'ce'):
            try:
                logger.log(u'Path %s doesn\'t exist, creating it' % path, logger.DEBUG)
                ek.ek(os.makedirs, path)
            except (OSError, IOError) as e:
                logger.log(u'Failed creating %s : %s' % (path, ex(e)), logger.ERROR)
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
                    logger.log(u'Path %s doesn\'t exist, creating it' % sofar, logger.DEBUG)
                    ek.ek(os.mkdir, sofar)
                    # use normpath to remove end separator, otherwise checks permissions against itself
                    chmodAsParent(ek.ek(os.path.normpath, sofar))
                    if syno:
                        # do the library update for synoindex
                        notifiers.NotifierFactory().get('SYNOINDEX').addFolder(sofar)
                except (OSError, IOError) as e:
                    logger.log(u'Failed creating %s : %s' % (sofar, ex(e)), logger.ERROR)
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

    new_dest_dir, new_dest_name = ek.ek(os.path.split, new_path)  # @UnusedVariable

    if old_path_length == 0 or old_path_length > len(cur_path):
        # approach from the right
        cur_file_name, cur_file_ext = ek.ek(os.path.splitext, cur_path)  # @UnusedVariable
    else:
        # approach from the left
        cur_file_ext = cur_path[old_path_length:]
        cur_file_name = cur_path[:old_path_length]

    if cur_file_ext[1:] in subtitleExtensions:
        # Extract subtitle language from filename
        sublang = ek.ek(os.path.splitext, cur_file_name)[1][1:]

        # Check if the language extracted from filename is a valid language
        try:
            language = subliminal.language.Language(sublang, strict=True)
            cur_file_ext = '.' + sublang + cur_file_ext
        except ValueError:
            pass

    # put the extension on the incoming file
    new_path += cur_file_ext

    make_dirs(ek.ek(os.path.dirname, new_path))

    # move the file
    try:
        logger.log(u"Renaming file from " + cur_path + " to " + new_path)
        ek.ek(shutil.move, cur_path, new_path)
    except (OSError, IOError) as e:
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
                notifiers.NotifierFactory().get('SYNOINDEX').deleteFolder(check_empty_dir)
            except OSError as e:
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
        sql = 'SELECT * FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ?'
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
                    season = ep.season  # this will always take the last found season so eps that cross the season
                                        # border are not handled well

    return (season, episodes)


def sanitizeSceneName(name):
    """
    Takes a show name and returns the "scenified" version of it.

    Returns: A string containing the scene version of the show name given.
    """

    if name:
        bad_chars = u",:()£'!?\u2019"

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
        from OpenSSL import crypto
        from lib.certgen import createKeyPair, createCertRequest, createCertificate, TYPE_RSA,  serial
    except (StandardError, Exception):
        logger.log(u"pyopenssl module missing, please install for https access", logger.WARNING)
        return False

    # Create the CA Certificate
    cakey = createKeyPair(TYPE_RSA, 4096)
    careq = createCertRequest(cakey, CN='Certificate Authority')
    cacert = createCertificate(careq, (careq, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    pkey = createKeyPair(TYPE_RSA, 4096)
    req = createCertRequest(pkey, CN='SickGear')
    cert = createCertificate(req, (cacert, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    # Save the key and certificate to disk
    try:
        with open(ssl_key, 'w') as file_hd:
            file_hd.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        with open(ssl_cert, 'w') as file_hd:
            file_hd.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    except (StandardError, Exception):
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
    except Exception as e:
        logger.log(u"Error trying to parse xml data. Error: " + ex(e), logger.DEBUG)
        parsedXML = None

    return parsedXML


def backupVersionedFile(old_file, version):
    num_tries = 0

    new_file = '%s.v%s' % (old_file, version)

    while not ek.ek(os.path.isfile, new_file):
        if not ek.ek(os.path.isfile, old_file) or 0 == get_size(old_file):
            logger.log(u'No need to create backup', logger.DEBUG)
            break

        try:
            logger.log(u'Trying to back up %s to %s' % (old_file, new_file), logger.DEBUG)
            shutil.copy(old_file, new_file)
            logger.log(u'Backup done', logger.DEBUG)
            break
        except Exception as e:
            logger.log(u'Error while trying to back up %s to %s : %s' % (old_file, new_file, ex(e)), logger.WARNING)
            num_tries += 1
            time.sleep(3)
            logger.log(u'Trying again.', logger.DEBUG)

        if 3 <= num_tries:
            logger.log(u'Unable to back up %s to %s please do it manually.' % (old_file, new_file), logger.ERROR)
            return False

    return True


def restoreVersionedFile(backup_file, version):
    numTries = 0

    new_file, backup_version = ek.ek(os.path.splitext, backup_file)
    restore_file = new_file + '.' + 'v' + str(version)

    if not ek.ek(os.path.isfile, new_file):
        logger.log(u"Not restoring, " + new_file + " doesn't exist", logger.DEBUG)
        return False

    try:
        logger.log(
            u"Trying to backup " + new_file + " to " + new_file + "." + "r" + str(version) + " before restoring backup",
            logger.DEBUG)
        shutil.move(new_file, new_file + '.' + 'r' + str(version))
    except Exception as e:
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
        except Exception as e:
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


# try to convert to float, return default on failure
def tryFloat(s, s_default=0.0):
    try:
        return float(s)
    except:
        return float(s_default)


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


def md5_for_text(text):
    result = None
    try:
        md5 = hashlib.md5()
        md5.update(str(text))
        raw_md5 = md5.hexdigest()
        result = raw_md5[17:] + raw_md5[9:17] + raw_md5[0:9]
    except (StandardError, Exception):
        pass
    return result


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
                print(ifname, ip)
                break
            except IOError:
                pass
    return ip


def check_url(url):
    """
    Check if a URL exists without downloading the whole file.
    """
    try:
        return requests.head(url).ok
    except:
        return False


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
    return '' if not text\
        else ((('%s%s' % (text[:len(text) / 2], '*' * (len(text) / 2))),
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


def get_show(name, try_scene_exceptions=False, use_cache=True):
    if not sickbeard.showList or None is name:
        return

    show_obj = None
    from_cache = False

    try:
        cache = sickbeard.name_cache.retrieveNameFromCache(name)
        if cache:
            from_cache = True
            show_obj = findCertainShow(sickbeard.showList, cache)

        if not show_obj and try_scene_exceptions:
            indexer_id = sickbeard.scene_exceptions.get_scene_exception_by_name(name)[0]
            if indexer_id:
                show_obj = findCertainShow(sickbeard.showList, indexer_id)

        # add show to cache
        if use_cache and show_obj and not from_cache:
            sickbeard.name_cache.addNameToCache(name, show_obj.indexerid)
    except Exception as e:
        logger.log(u'Error when attempting to find show: ' + name + ' in SickGear: ' + str(e), logger.DEBUG)

    return show_obj


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
        lINDEXER_API_PARMS['dvdorder'] = 0 != show.dvdorder

        if indexer_lang and not indexer_lang == 'en':
            lINDEXER_API_PARMS['language'] = indexer_lang

        t = sickbeard.indexerApi(show.indexer).indexer(**lINDEXER_API_PARMS)
        if season is None and episode is None:
            return t

        return t[show.indexerid][season][episode]
    except (sickbeard.indexer_episodenotfound, sickbeard.indexer_seasonnotfound, TypeError):
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
    except Exception as e:
        logger.log(u'exception msg: ' + str(e))
        pass

    if not auth:
        try:
            sickbeard.ADBA_CONNECTION.auth(sickbeard.ANIDB_USERNAME, sickbeard.ANIDB_PASSWORD)
        except Exception as e:
            logger.log(u'exception msg: ' + str(e))
            return False
    else:
        return True

    return sickbeard.ADBA_CONNECTION.authed()


def touch_file(fname, atime=None):
    if None is not atime:
        try:
            with open(fname, 'a'):
                ek.ek(os.utime, fname, (atime, atime))
            return True
        except (StandardError, Exception):
            logger.log('File air date stamping not available on your OS', logger.DEBUG)

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
            return ek.ek(os.path.join, tempfile.gettempdir(), "SickGear")

    return ek.ek(os.path.join, tempfile.gettempdir(), "SickGear-%s" % (uid))


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


def getURL(url, post_data=None, params=None, headers=None, timeout=30, session=None, json=False,
           raise_status_code=False, raise_exceptions=False, **kwargs):
    """
    Either
    1) Returns a byte-string retrieved from the url provider.
    2) Return True/False if success after using kwargs 'savefile' set to file pathname.
    3) Returns Tuple response, session if success after setting kwargs 'resp_sess' True.
    """

    # selectively mute some errors
    mute = filter(lambda x: kwargs.pop(x, False), ['mute_connect_err', 'mute_read_timeout', 'mute_connect_timeout'])

    # reuse or instantiate request session
    resp_sess = kwargs.pop('resp_sess', None)
    if None is session:
        session = CloudflareScraper.create_scraper()
        session.headers.update({'User-Agent': USER_AGENT})

    # download and save file or simply fetch url
    savename = kwargs.pop('savename', None)
    if savename:
        # session streaming
        session.stream = True

    if not kwargs.pop('nocache', False):
        cache_dir = sickbeard.CACHE_DIR or _getTempDir()
        session = CacheControl(sess=session, cache=caches.FileCache(ek.ek(os.path.join, cache_dir, 'sessions')))

    provider = kwargs.pop('provider', None)

    # session master headers
    req_headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Accept-Encoding': 'gzip,deflate'}
    if headers:
        req_headers.update(headers)
    if hasattr(session, 'reserved') and 'headers' in session.reserved:
        req_headers.update(session.reserved['headers'] or {})
    session.headers.update(req_headers)

    # session paramaters
    session.params = params

    # session ssl verify
    session.verify = False

    response = None
    try:
        # sanitise url
        parsed = list(urlparse.urlparse(url))
        parsed[2] = re.sub('/{2,}', '/', parsed[2])  # replace two or more / with one
        url = urlparse.urlunparse(parsed)

        # session proxies
        if sickbeard.PROXY_SETTING:
            (proxy_address, pac_found) = proxy_setting(sickbeard.PROXY_SETTING, url)
            msg = '%sproxy for url: %s' % (('', 'PAC parsed ')[pac_found], url)
            if None is proxy_address:
                logger.log('Proxy error, aborted the request using %s' % msg, logger.DEBUG)
                return
            elif proxy_address:
                logger.log('Using %s' % msg, logger.DEBUG)
                session.proxies = {'http': proxy_address, 'https': proxy_address}

        # decide if we get or post data to server
        if post_data or 'post_json' in kwargs:
            if True is post_data:
                post_data = None

            if post_data:
                kwargs.setdefault('data', post_data)

            if 'post_json' in kwargs:
                kwargs.setdefault('json', kwargs.pop('post_json'))

            response = session.post(url, timeout=timeout, **kwargs)
        else:
            response = session.get(url, timeout=timeout, **kwargs)
            if response.ok and not response.content and 'url=' in response.headers.get('Refresh', '').lower():
                url = response.headers.get('Refresh').lower().split('url=')[1].strip('/')
                if not url.startswith('http'):
                    parsed[2] = '/%s' % url
                    url = urlparse.urlunparse(parsed)
                response = session.get(url, timeout=timeout, **kwargs)

        # noinspection PyProtectedMember
        if provider and provider._has_signature(response.content):
            return response.content

        if raise_status_code:
            response.raise_for_status()

        if not response.ok:
            http_err_text = 'CloudFlare Ray ID' in response.content and \
                            'CloudFlare reports, "Website is offline"; ' or ''
            if response.status_code in clients.http_error_code:
                http_err_text += clients.http_error_code[response.status_code]
            elif response.status_code in range(520, 527):
                http_err_text += 'Origin server connection failure'
            else:
                http_err_text = 'Custom HTTP error code'
            logger.log(u'Response not ok. %s: %s from requested url %s'
                       % (response.status_code, http_err_text, url), logger.DEBUG)
            return

    except requests.exceptions.HTTPError as e:
        if raise_status_code:
            response.raise_for_status()
        logger.log(u'HTTP error %s while loading URL%s' % (
            e.errno, _maybe_request_url(e)), logger.WARNING)
        return
    except requests.exceptions.ConnectionError as e:
        if 'mute_connect_err' not in mute:
            logger.log(u'Connection error msg:%s while loading URL%s' % (
                e.message, _maybe_request_url(e)), logger.WARNING)
        if raise_exceptions:
            raise e
        return
    except requests.exceptions.ReadTimeout as e:
        if 'mute_read_timeout' not in mute:
            logger.log(u'Read timed out msg:%s while loading URL%s' % (
                e.message, _maybe_request_url(e)), logger.WARNING)
        if raise_exceptions:
            raise e
        return
    except (requests.exceptions.Timeout, socket.timeout) as e:
        if 'mute_connect_timeout' not in mute:
            logger.log(u'Connection timed out msg:%s while loading URL %s' % (
                e.message, _maybe_request_url(e, url)), logger.WARNING)
        if raise_exceptions:
            raise e
        return
    except Exception as e:
        if e.message:
            logger.log(u'Exception caught while loading URL %s\r\nDetail... %s\r\n%s'
                       % (url, e.message, traceback.format_exc()), logger.WARNING)
        else:
            logger.log(u'Unknown exception while loading URL %s\r\nDetail... %s'
                       % (url, traceback.format_exc()), logger.WARNING)
        if raise_exceptions:
            raise e
        return

    if json:
        try:
            data_json = response.json()
            if resp_sess:
                return ({}, data_json)[isinstance(data_json, (dict, list))], session
            return ({}, data_json)[isinstance(data_json, (dict, list))]
        except (TypeError, Exception) as e:
            logger.log(u'JSON data issue from URL %s\r\nDetail... %s' % (url, e.message), logger.WARNING)
            if raise_exceptions:
                raise e
            return None

    if savename:
        try:
            write_file(savename, response, raw=True, raise_exceptions=raise_exceptions)
        except (StandardError, Exception) as e:
            if raise_exceptions:
                raise e
            return
        return True

    if resp_sess:
        return response.content, session

    return response.content


def _maybe_request_url(e, def_url=''):
    return hasattr(e, 'request') and hasattr(e.request, 'url') and ' ' + e.request.url or def_url


def download_file(url, filename, session=None, **kwargs):

    if None is getURL(url, session=session, savename=filename, **kwargs):
        remove_file_failed(filename)
        return False
    return True


def clearCache(force=False):

    # clean out cache directory, remove everything > 12 hours old
    if sickbeard.CACHE_DIR:
        logger.log(u'Trying to clean cache folder %s' % sickbeard.CACHE_DIR)

        # Does our cache_dir exists
        if not ek.ek(os.path.isdir, sickbeard.CACHE_DIR):
            logger.log(u'Skipping clean of non-existing folder: %s' % sickbeard.CACHE_DIR, logger.WARNING)
        else:
            exclude = ['rss', 'images', 'zoneinfo']
            del_time = time.mktime((datetime.datetime.now() - datetime.timedelta(hours=12)).timetuple())
            for f in scantree(sickbeard.CACHE_DIR, exclude, follow_symlinks=True):
                if f.is_file(follow_symlinks=False) and (force or del_time > f.stat(follow_symlinks=False).st_mtime):
                    try:
                        ek.ek(os.remove, f.path)
                    except OSError as e:
                        logger.log('Unable to delete %s: %r / %s' % (f.path, e, str(e)), logger.WARNING)
                elif f.is_dir(follow_symlinks=False) and f.name not in ['cheetah', 'sessions', 'indexers']:
                    try:
                        ek.ek(os.rmdir, f.path)
                    except OSError:
                        pass


def human(size):
    """
    format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
    Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
    e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc
    """
    if size == 1:
        # because I really hate unnecessary plurals
        return "1 byte"

    suffixes_table = [('bytes', 0), ('KB', 0), ('MB', 1), ('GB', 2), ('TB', 2), ('PB', 2)]

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
    if ek.ek(os.path.isfile, start_path):
        return ek.ek(os.path.getsize, start_path)
    try:
        return sum(map((lambda x: x.stat(follow_symlinks=False).st_size), scantree(start_path)))
    except OSError:
        return 0


def remove_article(text=''):
    return re.sub(r'(?i)^(?:(?:A(?!\s+to)n?)|The)\s(\w)', r'\1', text)


def maybe_plural(number=1):
    return ('s', '')[1 == number]


def re_valid_hostname(with_allowed=True):
    this_host = socket.gethostname()
    return re.compile(r'(?i)(%slocalhost|.*\.local|%s%s)$' % (
        (with_allowed
         and '%s|' % (sickbeard.ALLOWED_HOSTS and re.escape(sickbeard.ALLOWED_HOSTS).replace(',', '|') or '.*')
         or ''), bool(this_host) and ('%s|' % this_host) or '', valid_ipaddr_expr()))


def valid_ipaddr_expr():
    """
    Returns a regular expression that will validate an ip address
    :return: Regular expression
    :rtype: String
    """
    return r'(%s)' % '|'.join([re.sub('\s+(#.[^\r\n]+)?', '', x) for x in [
        # IPv4 address (accurate)
        #  Matches 0.0.0.0 through 255.255.255.255
        '''
        (?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])
        '''
        ,
        # IPv6 address (standard and mixed)
        #  8 hexadecimal words, or 6 hexadecimal words followed by 4 decimal bytes All with optional leading zeros
        '''
        (?:(?<![:.\w])\[?                                            # Anchor address
        (?:[A-F0-9]{1,4}:){6}                                        #    6 words
        (?:[A-F0-9]{1,4}:[A-F0-9]{1,4}                               #    2 words
        |  (?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}  #    or 4 bytes
           (?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])
        )(?![:.\w]))                                                 # Anchor address
        '''
        ,
        # IPv6 address (compressed and compressed mixed)
        #  8 hexadecimal words, or 6 hexadecimal words followed by 4 decimal bytes
        #  All with optional leading zeros.  Consecutive zeros may be replaced with ::
        '''
        (?:(?<![:.\w])\[?(?:                                       # Anchor address
         (?:  # Mixed
          (?:[A-F0-9]{1,4}:){6}                                    # Non-compressed
         |(?=(?:[A-F0-9]{0,4}:){2,6}                               # Compressed with 2 to 6 colons
             (?:[0-9]{1,3}\.){3}[0-9]{1,3}                         #    and 4 bytes
             (?![:.\w]))                                           #    and anchored
          (([0-9A-F]{1,4}:){1,5}|:)((:[0-9A-F]{1,4}){1,5}:|:)      #    and at most 1 double colon
         |::(?:[A-F0-9]{1,4}:){5}                                  # Compressed with 7 colons and 5 numbers
         )
         (?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}  # 255.255.255.
         (?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])           # 255
        |     # Standard
         (?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}                        # Standard
        |     # Compressed
         (?=(?:[A-F0-9]{0,4}:){0,7}[A-F0-9]{0,4}                   # Compressed with at most 7 colons
            (?![:.\w]))                                            #    and anchored
         (([0-9A-F]{1,4}:){1,7}|:)((:[0-9A-F]{1,4}){1,7}|:)        #    and at most 1 double colon
        |(?:[A-F0-9]{1,4}:){7}:|:(:[A-F0-9]{1,4}){7}               # Compressed with 8 colons
        )(?![:.\w]))                                               # Anchor address
        '''
    ]])


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


def clear_unused_providers():
    providers = [x.cache.providerID for x in sickbeard.providers.sortedProviderList() if x.is_active()]

    if providers:
        myDB = db.DBConnection('cache.db')
        myDB.action('DELETE FROM provider_cache WHERE provider NOT IN (%s)' % ','.join(['?'] * len(providers)), providers)


def make_search_segment_html_string(segment, max_eps=5):
    seg_str = ''
    if segment and not isinstance(segment, list):
        segment = [segment]
    if segment and len(segment) > max_eps:
        seasons = [x for x in set([x.season for x in segment])]
        seg_str = u'Season' + maybe_plural(len(seasons)) + ': '
        first_run = True
        for x in seasons:
            eps = [str(s.episode) for s in segment if s.season == x]
            ep_c = len(eps)
            seg_str += ('' if first_run else ' ,') + str(x) + ' <span title="Episode' + maybe_plural(ep_c) + ': ' + ', '.join(eps) + '">(' + str(ep_c) + ' Ep' + maybe_plural(ep_c) + ')</span>'
            first_run = False
    elif segment:
        episodes = ['S' + str(x.season).zfill(2) + 'E' + str(x.episode).zfill(2) for x in segment]
        seg_str = u'Episode' + maybe_plural(len(episodes)) + ': ' + ', '.join(episodes)
    return seg_str


def has_anime():
    return False if not sickbeard.showList else any(filter(lambda show: show.is_anime, sickbeard.showList))


def cpu_sleep():
    if cpu_presets[sickbeard.CPU_PRESET]:
        time.sleep(cpu_presets[sickbeard.CPU_PRESET])


def scantree(path, exclude=None, follow_symlinks=False):
    """Recursively yield DirEntry objects for given directory."""
    exclude = (exclude, ([exclude], [])[None is exclude])[not isinstance(exclude, list)]
    for entry in ek.ek(scandir, path):
        if entry.is_dir(follow_symlinks=follow_symlinks):
            if entry.name not in exclude:
                for subentry in scantree(entry.path):
                    yield subentry
                yield entry
        else:
            yield entry


def cleanup_cache():
    """
    Delete old cached files
    """
    delete_not_changed_in([ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', 'browse', 'thumb', x) for x in [
        'anidb', 'imdb', 'trakt', 'tvdb']])


def delete_not_changed_in(paths, days=30, minutes=0):
    """
    Delete files under paths not changed in n days and/or n minutes.
    If a file was modified later than days/and or minutes, then don't delete it.

    :param paths: Path(s) to scan for files to delete
    :type paths: String or List of strings
    :param days: Purge files not modified in this number of days (default: 30 days)
    :param minutes: Purge files not modified in this number of minutes (default: 0 minutes)
    :return: tuple; number of files that qualify for deletion, number of qualifying files that failed to be deleted
    """
    del_time = time.mktime((datetime.datetime.now() - datetime.timedelta(days=days, minutes=minutes)).timetuple())
    errors = 0
    qualified = 0
    for c in (paths, [paths])[not isinstance(paths, list)]:
        try:
            for f in scantree(c):
                if f.is_file(follow_symlinks=False) and del_time > f.stat(follow_symlinks=False).st_mtime:
                    try:
                        ek.ek(os.remove, f.path)
                    except (StandardError, Exception):
                        errors += 1
                    qualified += 1
        except (StandardError, Exception):
                        pass
    return qualified, errors


def set_file_timestamp(filename, min_age=3, new_time=None):
    min_time = time.mktime((datetime.datetime.now() - datetime.timedelta(days=min_age)).timetuple())
    try:
        if ek.ek(os.path.isfile, filename) and ek.ek(os.path.getmtime, filename) < min_time:
            ek.ek(os.utime, filename, new_time)
    except (StandardError, Exception):
        pass


def should_delete_episode(status):
    s = Quality.splitCompositeStatus(status)[0]
    if s not in SNATCHED_ANY + [DOWNLOADED, ARCHIVED, IGNORED]:
        return True
    logger.log('not safe to delete episode from db because of status: %s' % statusStrings[s], logger.DEBUG)
    return False


def is_link(filepath):
    """
    Check if given file/pathname is symbolic link

    :param filepath: file or path to check
    :return: True or False
    """
    if 'win32' == sys.platform:
        if not ek.ek(os.path.exists, filepath):
            return False

        import ctypes
        invalid_file_attributes = 0xFFFFFFFF
        file_attribute_reparse_point = 0x0400

        attr = ctypes.windll.kernel32.GetFileAttributesW(unicode(filepath))
        return invalid_file_attributes != attr and 0 != attr & file_attribute_reparse_point

    return ek.ek(os.path.islink, filepath)


def datetime_to_epoch(dt):
    """ convert a datetime to seconds after (or possibly before) 1970-1-1 """
    """ can raise an error with dates pre 1970-1-1 """
    if not isinstance(getattr(dt, 'tzinfo'), datetime.tzinfo):
        from sickbeard.network_timezones import sb_timezone
        dt = dt.replace(tzinfo=sb_timezone)
    utc_naive = dt.replace(tzinfo=None) - dt.utcoffset()
    return int((utc_naive - datetime.datetime(1970, 1, 1)).total_seconds())


def df():
    """
    Return disk free space at known parent locations

    :return: string path, string value that is formatted size
    :rtype: list of tuples
    """
    result = []
    min_output = True
    if sickbeard.ROOT_DIRS and sickbeard.DISPLAY_FREESPACE:
        targets = []
        for path in sickbeard.ROOT_DIRS.split('|')[1:]:
            location_parts = os.path.splitdrive(path)
            target = location_parts[0]
            if 'win32' == sys.platform:
                if not re.match('(?i)[a-z]:(?:\\\\)?$', target):
                    # simple drive letter not found, fallback to full path
                    target = path
                    min_output = False
            elif sys.platform.startswith(('linux', 'darwin', 'sunos5')) or 'bsd' in sys.platform:
                target = path
                min_output = False
            if target and target not in targets:
                targets += [target]
                free = freespace(path)
                if None is not free:
                    result += [(target, sizeof_fmt(free).replace(' ', ''))]
    return result, min_output


def freespace(path=None):
    """
    Return free space available at path location

    :param path: Example paths (Windows) = '\\\\192.168.0.1\\sharename\\existing_path', 'd:\\existing_path'
                 Untested with mount points under linux
    :type path: basestring
    :return: Size in bytes
    :rtype: long
    """
    result = None

    if 'win32' == sys.platform:
        try:
            import ctypes
            if None is not ctypes:
                max_val = (2 ** 64) - 1
                storage = ctypes.c_ulonglong(max_val)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), None, None, ctypes.pointer(storage))
                result = (storage.value, None)[max_val == storage.value]
        except(StandardError, Exception):
            pass
    elif sys.platform.startswith(('linux', 'darwin', 'sunos5')) or 'bsd' in sys.platform:
        try:
            storage = os.statvfs(path)  # perms errors can result
            result = storage.f_bavail * storage.f_frsize
        except OSError:
            pass

    return result


def path_mapper(search, replace, subject):
    """
    Substitute strings in a path

    :param search: Search text
    :type search: String
    :param replace: Replacement text
    :type replace: String
    :param subject: Path text to search
    :type subject: String
    :return: Subject with or without substitution, True if a change was made otherwise False
    :rtype: Tuple
    """
    delim = '/!~!/'
    search = re.sub(r'[\\]', delim, search)
    replace = re.sub(r'[\\]', delim, replace)
    path = re.sub(r'[\\]', delim, subject)
    result = re.sub('(?i)^%s' % search, replace, path)
    result = ek.ek(os.path.normpath, re.sub(delim, '/', result))

    return result, result != subject


def write_file(filepath, data, raw=False, xmltree=False, utf8=False, raise_exceptions=False):

    result = False

    if make_dirs(ek.ek(os.path.dirname, filepath), False):
        try:
            if raw:
                with io.FileIO(filepath, 'wb') as fh:
                    for chunk in data.iter_content(chunk_size=1024):
                        if chunk:
                            fh.write(chunk)
                            fh.flush()
                    ek.ek(os.fsync, fh.fileno())
            else:
                w_mode = 'w'
                if utf8:
                    w_mode = 'a'
                    with io.FileIO(filepath, 'wb') as fh:
                        fh.write(codecs.BOM_UTF8)

                if xmltree:
                    with io.FileIO(filepath, w_mode) as fh:
                        if utf8:
                            data.write(fh, encoding='utf-8')
                        else:
                            data.write(fh)
                else:
                    with io.FileIO(filepath, w_mode) as fh:
                        fh.write(data)

            chmodAsParent(filepath)

            result = True
        except (EnvironmentError, IOError) as e:
            logger.log('Unable to write file %s : %s' % (filepath, ex(e)), logger.ERROR)
            if raise_exceptions:
                raise e

    return result


def clean_data(data):
    """Cleans up strings, lists, dicts returned

    Issues corrected:
    - Replaces &amp; with &
    - Trailing whitespace
    - Decode html entities
    """

    if isinstance(data, list):
        return [clean_data(d) for d in data]
    if isinstance(data, dict):
        return {k: clean_data(v) for k, v in data.iteritems()}
    if isinstance(data, basestring):
        from lib.six.moves.html_parser import HTMLParser
        return HTMLParser().unescape(data).strip().replace(u'&amp;', u'&')
    return data


def getOverview(epStatus, show_quality, upgrade_once):

    status, quality = Quality.splitCompositeStatus(epStatus)
    if ARCHIVED == status:
        return Overview.GOOD
    if WANTED == status:
        return Overview.WANTED
    if status in (SKIPPED, IGNORED):
        return Overview.SKIPPED
    if status in (UNAIRED, UNKNOWN):
        return Overview.UNAIRED
    if status in [SUBTITLED] + Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.FAILED:

        if FAILED == status:
            return Overview.WANTED
        if status in SNATCHED_ANY:
            return Overview.SNATCHED

        void, best_qualities = Quality.splitQuality(show_quality)
        # if re-downloads aren't wanted then mark it "good" if there is anything
        if not len(best_qualities):
            return Overview.GOOD

        min_best, max_best = min(best_qualities), max(best_qualities)
        if quality >= max_best \
                or (upgrade_once and
                    (quality in best_qualities or (None is not min_best and quality > min_best))):
            return Overview.GOOD
        return Overview.QUAL
