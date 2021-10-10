# coding=utf-8
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

from __future__ import division
from __future__ import print_function
from __future__ import with_statement

from itertools import cycle
import datetime
import hashlib
import os
import re
import shutil
import socket
import time
import uuid
import sys

try:
    import json
except ImportError:
    from lib import simplejson as json

import sickbeard
from . import db, logger, notifiers
from .common import cpu_presets, mediaExtensions, Overview, Quality, statusStrings, subtitleExtensions, \
    ARCHIVED, DOWNLOADED, FAILED, IGNORED, SKIPPED, SNATCHED_ANY, SUBTITLED, UNAIRED, UNKNOWN, WANTED
from .sgdatetime import timestamp_near
from lib.tvinfo_base.exceptions import *
# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex, MultipleShowObjectsException

import requests
import requests.exceptions
import subliminal
from lxml_etree import etree, is_lxml

from _23 import b64decodebytes, b64encodebytes, decode_bytes, decode_str, filter_iter, scandir
from six import iteritems, string_types, text_type
# noinspection PyUnresolvedReferences
from six.moves import zip

# the following are imported from elsewhere,
# therefore, they intentionally don't resolve and are unused in this particular file.
# noinspection PyUnresolvedReferences
from sg_helpers import chmod_as_parent, clean_data, copy_file, download_file, fix_set_group_id, get_system_temp_dir, \
    get_url, indent_xml, make_dirs, maybe_plural, md5_for_text, move_file, proxy_setting, remove_file, \
    remove_file_perm, replace_extension, sanitize_filename, scantree, touch_file, try_int, try_ord, write_file

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, Generator, NoReturn, Iterable, Iterator, List, Optional, Set, Tuple, Union
    from .tv import TVShow
    # the following workaround hack resolves a pyc resolution bug
    from .name_cache import retrieveNameFromCache
    from six import integer_types

RE_XML_ENCODING = re.compile(r'^(<\?xml[^>]+)\s+(encoding\s*=\s*[\"\'][^\"\']*[\"\'])(\s*\?>|)', re.U)
RE_IMDB_ID = r'tt\d{7,10}'
RC_IMDB_ID = re.compile(r'(?i)(%s)' % RE_IMDB_ID)


def remove_extension(name):
    """
    Remove download or media extension from name (if any)

    :param name: filename
    :type name: AnyStr
    :return: name without extension
    :rtype: AnyStr
    """

    if name and "." in name:
        base_name, sep, extension = name.rpartition('.')
        if base_name and extension.lower() in ['nzb', 'torrent'] + mediaExtensions:
            name = base_name

    return name


def remove_non_release_groups(name, is_anime=False):
    """
    Remove non release groups from name

    :param name: release name
    :type name: AnyStr
    :param is_anime: is anmie
    :type is_anime: bool
    :return:
    :rtype: AnyStr
    """

    if name:
        rc = [re.compile(r'(?i)' + v) for v in [
              r'([\s\.\-_\[\{\(]*(no-rar|nzbgeek|ripsalot|siklopentan)[\s\.\-_\]\}\)]*)$',
              r'([\s\.\-_\[\{\(]rp[\s\.\-_\]\}\)]*)$',
              r'(?<=\w)([\s\.\-_]*[\[\{\(][\s\.\-_]*(www\.\w+.\w+)[\s\.\-_]*[\]\}\)][\s\.\-_]*)$',
              r'(?<=\w)([\s\.\-_]*[\[\{\(]\s*(rar(bg|tv)|((e[tz]|v)tv))[\s\.\-_]*[\]\}\)][\s\.\-_]*)$'] +
              ([r'(?<=\w)([\s\.\-_]*[\[\{\(][\s\.\-_]*[\w\s\.\-\_]+[\s\.\-_]*[\]\}\)][\s\.\-_]*)$',
                r'^([\s\.\-_]*[\[\{\(][\s\.\-_]*[\w\s\.\-\_]+[\s\.\-_]*[\]\}\)][\s\.\-_]*)(?=\w)'], [])[is_anime]]
        rename = name = remove_extension(name)
        while rename:
            for regex in rc:
                name = regex.sub('', name)
            rename = (name, False)[name == rename]

    return name


def is_sync_file(filename):
    """

    :param filename: filename
    :type filename: AnyStr
    :return:
    :rtype: bool
    """
    extension = filename.rpartition(".")[2].lower()
    return '!sync' == extension or 'lftp-pget-status' == extension


def has_media_ext(filename):
    """
    checks if file has media extension

    :param filename: filename
    :type filename: AnyStr
    :return:
    :rtype: bool
    """
    # ignore samples
    if re.search(r'(^|[\W_])(sample\d*)[\W_]', filename, re.I) \
            or filename.startswith('._'):  # and MAC OS's 'resource fork' files
        return False

    sep_file = filename.rpartition('.')
    return (None is re.search('extras?$', sep_file[0], re.I)) and (sep_file[2].lower() in mediaExtensions)


def has_image_ext(filename):
    """
    checks if file has image extension

    :param filename: filename
    :type filename: AnyStr
    :return:
    :rtype: bool
    """
    try:
        if ek.ek(os.path.splitext, filename)[1].lower() in ['.bmp', '.gif', '.jpeg', '.jpg', '.png', '.webp']:
            return True
    except (BaseException, Exception):
        pass
    return False


def is_first_rar_volume(filename):
    """
    checks if file is part of rar set

    :param filename: filename
    :type filename: AnyStr
    :return:
    :rtype: bool
    """
    return None is not re.search(r'(?P<file>^(?P<base>(?:(?!\.part\d+\.rar$).)*)\.(?:(?:part0*1\.)?rar)$)', filename)


def find_show_by_id(
        show_id,  # type: Union[AnyStr, Dict[int, int], int]
        show_list=None,  # type: Optional[List[TVShow]]
        no_mapped_ids=True,  # type: bool
        check_multishow=False,  # type: bool
        no_exceptions=False  # type: bool
):
    # type: (...) -> Optional[TVShow]
    """
    :param show_id: {indexer: id} or 'tvid_prodid'.
    :param show_list: (optional) TVShow objects list
    :param no_mapped_ids: don't check mapped ids
    :param check_multishow: check for multiple show matches
    :param no_exceptions: suppress the MultipleShowObjectsException and return None instead
    """
    results = []
    if None is show_list:
        show_list = sickbeard.showList

    if show_id and show_list:
        tvid_prodid_obj = None if not isinstance(show_id, string_types) else sickbeard.tv.TVidProdid(show_id)

        if tvid_prodid_obj and no_mapped_ids:
            if None is tvid_prodid_obj.prodid:
                return
            return sickbeard.showDict.get(int(tvid_prodid_obj))
        else:
            if tvid_prodid_obj:
                if None is tvid_prodid_obj.prodid:
                    return None
                show_id = tvid_prodid_obj.dict

            if isinstance(show_id, dict):
                if no_mapped_ids:
                    sid_int_list = [sickbeard.tv.TVShow.create_sid(k, v) for k, v in iteritems(show_id) if k and v and
                                    0 < v and sickbeard.tv.tvid_bitmask >= k]
                    if not check_multishow:
                        return next((sickbeard.showDict.get(_show_sid_id) for _show_sid_id in sid_int_list
                                     if sickbeard.showDict.get(_show_sid_id)), None)
                    results = [sickbeard.showDict.get(_show_sid_id) for _show_sid_id in sid_int_list
                               if sickbeard.showDict.get(_show_sid_id)]
                else:
                    results = [_show_obj for k, v in iteritems(show_id) if k and v and 0 < v
                               for _show_obj in show_list if v == _show_obj.internal_ids.get(k, {'id': 0})['id']]

    num_shows = len(set(results))
    if 1 == num_shows:
        return results[0]
    if 1 < num_shows and not no_exceptions:
        raise MultipleShowObjectsException()


def make_dir(path):
    """
    create given path recursively

    :param path: path
    :type path: AnyStr
    :return: success of creation
    :rtype: bool
    """
    if not ek.ek(os.path.isdir, path):
        try:
            ek.ek(os.makedirs, path)
            # do a Synology library update
            notifiers.NotifierFactory().get('SYNOINDEX').addFolder(path)
        except OSError:
            return False
    return True


def search_infosrc_for_show_id(reg_show_name, tvid=None, prodid=None, ui=None):
    """
    search info source for show

    :param reg_show_name: show name to search
    :type reg_show_name: AnyStr
    :param tvid: tvid
    :type tvid: int or None
    :param prodid: prodid
    :type prodid: int or long or None
    :param ui: ui class
    :type ui: object
    :return: seriesname, tvid, prodid or None, None, None
    :rtype: Tuple[None, None, None] or Tuple[AnyStr, int, int or long]
    """
    show_names = [re.sub('[. -]', ' ', reg_show_name)]

    # Query Indexers for each search term and build the list of results
    for cur_tvid in (sickbeard.TVInfoAPI().sources if not tvid else [int(tvid)]) or []:
        # Query Indexers for each search term and build the list of results
        tvinfo_config = sickbeard.TVInfoAPI(cur_tvid).api_params.copy()
        if ui is not None:
            tvinfo_config['custom_ui'] = ui
        t = sickbeard.TVInfoAPI(cur_tvid).setup(**tvinfo_config)

        for cur_name in show_names:
            logger.debug('Trying to find %s on %s' % (cur_name, sickbeard.TVInfoAPI(cur_tvid).name))

            try:
                show_info_list = t[prodid] if prodid else t[cur_name]
                show_info_list = show_info_list if isinstance(show_info_list, list) else [show_info_list]
            except (BaseException, Exception):
                continue

            seriesname = _prodid = None
            for cur_show_info in show_info_list:  # type: dict
                try:
                    seriesname = cur_show_info['seriesname']
                    _prodid = cur_show_info['id']
                except (BaseException, Exception):
                    _prodid = seriesname = None
                    continue
                if seriesname and _prodid:
                    break

            if not (seriesname and _prodid):
                continue

            if None is prodid and str(cur_name).lower() == str(seriesname).lower():
                return seriesname, cur_tvid, int(_prodid)
            elif None is not prodid and int(prodid) == int(_prodid):
                return seriesname, cur_tvid, int(prodid)

        if tvid:
            break

    return None, None, None


def sizeof_fmt(num):
    """
    format given bytes to human readable string

    :param num: number
    :type num: int or long
    :return: human readable formatted string
    :rtype: AnyStr
    """
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']:
        if 1024.0 > num:
            return "%3.1f %s" % (num, x)
        num /= 1024.0


def list_media_files(path):
    # type: (AnyStr) -> List[AnyStr]
    """
    list all media files in given path

    :param path: path
    :return: list of media files
    """
    result = []
    if path:
        if [direntry for direntry in scantree(path, include=[r'\.sickgearignore'], filter_kind=False, recurse=False)]:
            logger.log('Skipping folder "%s" because it contains ".sickgearignore"' % path, logger.DEBUG)
        else:
            result = [direntry.path for direntry in scantree(path, exclude=['Extras'], filter_kind=False)
                      if has_media_ext(direntry.name)]
    return result


def copyFile(src_file, dest_file):
    """ deprecated_item, remove in 2020, kept here as rollback uses it
    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination file
    :type dest_file: AnyStr
    :return: nothing
    :rtype: None
    """
    return copy_file(src_file, dest_file)


def moveFile(src_file, dest_file):
    """ deprecated_item, remove in 2020, kept here as rollback uses it
    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination file
    :type dest_file: AnyStr
    :return: nothing
    :rtype: None
    """
    return move_file(src_file, dest_file)


def link(src_file, dest_file):
    """

    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination file
    :type dest_file: AnyStr
    """
    if 'nt' == os.name:
        import ctypes

        if 0 == ctypes.windll.kernel32.CreateHardLinkW(text_type(dest_file), text_type(src_file), 0):
            raise ctypes.WinError()
    else:
        ek.ek(os.link, src_file, dest_file)


def hardlink_file(src_file, dest_file):
    """

    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination file
    :type dest_file: AnyStr
    """
    try:
        ek.ek(link, src_file, dest_file)
        fix_set_group_id(dest_file)
    except (BaseException, Exception) as e:
        logger.log(u"Failed to create hardlink of %s at %s: %s. Copying instead." % (src_file, dest_file, ex(e)),
                   logger.ERROR)
        copy_file(src_file, dest_file)


def symlink(src_file, dest_file):
    """

    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination
    :type dest_file: AnyStr
    """
    if 'nt' == os.name:
        import ctypes

        if ctypes.windll.kernel32.CreateSymbolicLinkW(
                text_type(dest_file), text_type(src_file), 1 if ek.ek(os.path.isdir, src_file) else 0) in [0, 1280]:
            raise ctypes.WinError()
    else:
        ek.ek(os.symlink, src_file, dest_file)


def move_and_symlink_file(src_file, dest_file):
    """

    :param src_file: source file
    :type src_file: AnyStr
    :param dest_file: destination file
    :type dest_file: AnyStr
    """
    try:
        ek.ek(shutil.move, src_file, dest_file)
        fix_set_group_id(dest_file)
        ek.ek(symlink, dest_file, src_file)
    except (BaseException, Exception):
        logger.log(u"Failed to create symlink of %s at %s. Copying instead" % (src_file, dest_file), logger.ERROR)
        copy_file(src_file, dest_file)


def rename_ep_file(cur_path, new_path, old_path_length=0):
    """
    Creates all folders needed to move a file to its new location, renames it, then cleans up any folders
    left that are now empty.

    :param cur_path: The absolute path to the file you want to move/rename
    :type cur_path: AnyStr
    :param new_path: The absolute path to the destination for the file WITHOUT THE EXTENSION
    :type new_path: AnyStr
    :param old_path_length: The length of media file path (old name) WITHOUT THE EXTENSION
    :type old_path_length: int or long
    :return: success
    :rtype: bool
    """

    # new_dest_dir, new_dest_name = ek.ek(os.path.split, new_path)

    if 0 == old_path_length or len(cur_path) < old_path_length:
        # approach from the right
        cur_file_name, cur_file_ext = ek.ek(os.path.splitext, cur_path)
    else:
        # approach from the left
        cur_file_ext = cur_path[old_path_length:]
        cur_file_name = cur_path[:old_path_length]

    if cur_file_ext[1:] in subtitleExtensions:
        # Extract subtitle language from filename
        sublang = ek.ek(os.path.splitext, cur_file_name)[1][1:]

        # Check if the language extracted from filename is a valid language
        try:
            _ = subliminal.language.Language(sublang, strict=True)
            cur_file_ext = '.' + sublang + cur_file_ext
        except ValueError:
            pass

    # put the extension on the incoming file
    new_path += cur_file_ext

    make_dirs(ek.ek(os.path.dirname, new_path), syno=True)

    # move the file
    try:
        logger.log(u'Renaming file from %s to %s' % (cur_path, new_path))
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

    :param check_empty_dir: The path to clean (absolute path to a folder)
    :type check_empty_dir: AnyStr
    :param keep_dir: Clean until this path is reached
    :type keep_dir: bool
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
                # do a Synology library update
                notifiers.NotifierFactory().get('SYNOINDEX').deleteFolder(check_empty_dir)
            except OSError as e:
                logger.log(u"Unable to delete " + check_empty_dir + ": " + repr(e) + " / " + ex(e), logger.WARNING)
                break
            check_empty_dir = ek.ek(os.path.dirname, check_empty_dir)
        else:
            break


def get_absolute_number_from_season_and_episode(show_obj, season, episode):
    """

    :param show_obj: show object
    :type show_obj: TVShow
    :param season: season number
    :type season: int
    :param episode: episode number
    :type episode: int
    :return: absolute number
    :type: int or long
    """
    absolute_number = None

    if season and episode:
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT *'
                                  ' FROM tv_episodes'
                                  ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?',
                                  [show_obj.tvid, show_obj.prodid, season, episode])

        if 1 == len(sql_result):
            absolute_number = int(sql_result[0]["absolute_number"])
            logger.log(
                "Found absolute_number:" + str(absolute_number) + " by " + str(season) + "x" + str(episode),
                logger.DEBUG)
        else:
            logger.debug('No entries for absolute number in show: %s found using %sx%s' %
                       (show_obj.unique_name, str(season), str(episode)))

    return absolute_number


def get_all_episodes_from_absolute_number(show_obj, absolute_numbers):
    # type: (TVShow, List[int]) -> Tuple[int, List[int]]
    """

    :param show_obj: show object
    :param absolute_numbers: absolute numbers
    """
    episode_numbers = []
    season_number = None

    if show_obj and len(absolute_numbers):
        for absolute_number in absolute_numbers:
            ep_obj = show_obj.get_episode(None, None, absolute_number=absolute_number)
            if ep_obj:
                episode_numbers.append(ep_obj.episode)
                season_number = ep_obj.season  # this takes the last found season so eps that cross the season
                # border are not handled well

    return season_number, episode_numbers


def sanitize_scene_name(name):
    """
    Takes a show name and returns the "scenified" version of it.

    :param name: name
    :type name: AnyStr
    :return: A string containing the scene version of the show name given.
    :rtype: AnyStr
    """
    if name:
        bad_chars = u',:()£\'!?\u2019'

        # strip out any bad chars
        name = re.sub(r'[%s]' % bad_chars, '', name, flags=re.U)

        # tidy up stuff that doesn't belong in scene names
        name = re.sub(r'(-?\s|/)', '.', name).replace('&', 'and')
        name = re.sub(r"\.\.*", '.', name).rstrip('.')

        return name
    return ''


def create_https_certificates(ssl_cert, ssl_key):
    """
    Create self-signed HTTPS certificares and store in paths 'ssl_cert' and 'ssl_key'
    """

    try:
        from lib.certgen import generate_key, generate_local_cert
    except (BaseException, Exception):
        return False

    private_key = generate_key(key_size=4096, output_file=ssl_key)
    cert = generate_local_cert(private_key, days_valid=3650, output_file=ssl_cert)
    return bool(cert)


if '__main__' == __name__:
    import doctest

    doctest.testmod()


def parse_xml(data, del_xmlns=False):
    # type: (AnyStr, bool) -> Optional[etree.ElementTree]
    """
    Parse data into an xml elementtree.ElementTree

    data: data string containing xml
    del_xmlns: if True, removes xmlns namesspace from data before parsing

    Returns: parsed data as elementtree or None
    """

    if del_xmlns:
        data = re.sub(' xmlns="[^"]+"', '', data)

    if isinstance(data, text_type) and is_lxml:
        data = RE_XML_ENCODING.sub(r'\1\3', data, count=1)

    try:
        parsed_xml = etree.fromstring(data)
    except (BaseException, Exception) as e:
        logger.log(u"Error trying to parse xml data. Error: " + ex(e), logger.DEBUG)
        parsed_xml = None

    return parsed_xml


def backup_versioned_file(old_file, version):
    """

    :param old_file: old filename
    :type old_file: AnyStr
    :param version: version number
    :type version: int
    :return: success
    :rtype: bool
    """
    num_tries = 0

    new_file = '%s.v%s' % (old_file, version)

    if ek.ek(os.path.isfile, new_file):
        changed_old_db = False
        for back_nr in range(1, 10000):
            alt_name = '%s.r%s' % (new_file, back_nr)
            if not ek.ek(os.path.isfile, alt_name):
                try:
                    shutil.move(new_file, alt_name)
                    changed_old_db = True
                    break
                except (BaseException, Exception):
                    if ek.ek(os.path.isfile, new_file):
                        continue
                    logger.log('could not rename old backup db file', logger.WARNING)
        if not changed_old_db:
            raise Exception('can\'t create a backup of db')

    while not ek.ek(os.path.isfile, new_file):
        if not ek.ek(os.path.isfile, old_file) or 0 == get_size(old_file):
            logger.log(u'No need to create backup', logger.DEBUG)
            break

        try:
            logger.log(u'Trying to back up %s to %s' % (old_file, new_file), logger.DEBUG)
            shutil.copy(old_file, new_file)
            logger.log(u'Backup done', logger.DEBUG)
            break
        except (BaseException, Exception) as e:
            logger.log(u'Error while trying to back up %s to %s : %s' % (old_file, new_file, ex(e)), logger.WARNING)
            num_tries += 1
            time.sleep(3)
            logger.log(u'Trying again.', logger.DEBUG)

        if 3 <= num_tries:
            logger.log(u'Unable to back up %s to %s please do it manually.' % (old_file, new_file), logger.ERROR)
            return False

    return True


def restore_versioned_file(backup_file, version):
    """

    :param backup_file: filename
    :type backup_file: AnyStr
    :param version: version number
    :type version: int
    :return: success
    :rtype: bool
    """
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
    except (BaseException, Exception) as e:
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
        except (BaseException, Exception) as e:
            logger.log(u"Error while trying to restore " + restore_file + ": " + ex(e), logger.WARNING)
            numTries += 1
            time.sleep(1)
            logger.log(u"Trying again.", logger.DEBUG)

        if 10 <= numTries:
            logger.log(u"Unable to restore " + restore_file + " to " + new_file + " please do it manually.",
                       logger.ERROR)
            return False

    return True


# one legacy custom provider is keeping this signature here,
# a monkey patch could fix that so that this can be removed
def tryInt(s, s_default=0):
    return try_int(s, s_default)


# try to convert to float, return default on failure
def try_float(s, s_default=0.0):
    try:
        return float(s)
    except (BaseException, Exception):
        return float(s_default)


# generates a md5 hash of a file
def md5_for_file(filename, block_size=2 ** 16):
    """

    :param filename: filename
    :type filename: AnyStr
    :param block_size: block size
    :type block_size: int or long
    :return:
    :rtype: AnyStr or None
    """
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
    except (BaseException, Exception):
        return None


def get_lan_ip():
    """
    Simple function to get LAN localhost_ip
    http://stackoverflow.com/questions/11735821/python-get-localhost-ip
    """

    if 'nt' != os.name:
        # noinspection PyUnresolvedReferences
        import fcntl
        import struct

        def get_interface_ip(if_name):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', if_name[:15]))[20:24])

    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127.") and "nt" != os.name:
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
                # noinspection PyUnboundLocalVariable
                ip = get_interface_ip(ifname)
                print(ifname, ip)
                break
            except IOError:
                pass
    return ip


def check_url(url):
    """
    Check if a URL exists without downloading the whole file.
    :param url: url
    :type url: AnyStr
    :return:
    :rtype: bool
    """
    try:
        return requests.head(url).ok
    except (BaseException, Exception):
        return False


def anon_url(*url):
    """

    :param url: url
    :type url:
    :return: a URL string consisting of the Anonymous redirect URL and an arbitrary number of values appended
    :rtype: AnyStr
    """
    return '' if None in url else '%s%s' % (sickbeard.ANON_REDIRECT, ''.join([str(s) for s in url]))


def starify(text, verify=False):
    """
    If verify is true, return true if text is a star block created text else return false.

    :param text: text
    :type text: AnyStr
    :param verify:
    :type verify: bool
    :return: Return text input string with either its latter half or its centre area (if 12 chars or more)
             replaced with asterisks. Useful for securely presenting api keys to a ui.
    """
    return '' if not text\
        else ((('%s%s' % (text[:len(text) // 2], '*' * (len(text) // 2))),
               ('%s%s%s' % (text[:4], '*' * (len(text) - 8), text[-4:])))[12 <= len(text)],
              set('*') == set((text[len(text) // 2:], text[4:-4])[12 <= len(text)]))[verify]


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
def encrypt(data, encryption_version=0, do_decrypt=False):
    # Version 1: Simple XOR encryption (this is not very secure, but works)
    if 1 == encryption_version:
        if do_decrypt:
            return ''.join([chr(try_ord(x) ^ try_ord(y)) for (x, y) in
                            zip(b64decodebytes(decode_bytes(data)), cycle(unique_key1))])

        return decode_str(b64encodebytes(decode_bytes(
            ''.join([chr(try_ord(x) ^ try_ord(y)) for (x, y) in zip(data, cycle(unique_key1))])))).strip()

    # Version 0: Plain text
    return data


def decrypt(data, encryption_version=0):
    return encrypt(data, encryption_version, do_decrypt=True)


def full_sanitize_scene_name(name):
    """
    sanitize scene name

    :param name: name
    :type name: AnyStr
    :return: sanitized name
    :rtype: AnyStr
    """
    return re.sub('[. -]', ' ', sanitize_scene_name(name)).lower().lstrip()


def get_show(name, try_scene_exceptions=False):
    # type: (AnyStr, bool) -> Optional[TVShow]
    """
    get show object for show with given name

    :param name: name of show
    :type name: AnyStr
    :param try_scene_exceptions: check scene exceptions
    :type try_scene_exceptions: bool
    :return: None or show object
    :type: TVShow or None
    """
    if not sickbeard.showList or None is name:
        return

    show_obj = None

    try:
        tvid, prodid = sickbeard.name_cache.retrieveNameFromCache(name)
        if tvid and prodid:
            show_obj = find_show_by_id({tvid: prodid})

        if not show_obj and try_scene_exceptions:
            tvid, prodid, season = sickbeard.scene_exceptions.get_scene_exception_by_name(name)
            if tvid and prodid:
                show_obj = find_show_by_id({tvid: prodid})
    except (BaseException, Exception) as e:
        logger.log(u'Error when attempting to find show: ' + name + ' in SickGear: ' + ex(e), logger.DEBUG)

    return show_obj


def is_hidden_folder(folder):
    """
    On Linux based systems hidden folders start with . (dot)

    :param folder: Full path of folder to check
    :type folder: AnyStr
    :return: Returns True if folder is hidden
    :rtype: bool
    """
    if ek.ek(os.path.isdir, folder):
        if ek.ek(os.path.basename, folder).startswith('.'):
            return True

    return False


def real_path(path):
    """
    The resulting path will have no symbolic link, '/./' or '/../' components.

    :param path: path
    :type path: AnyStr
    :return: the canonicalized absolute pathname
    :rtype: AnyStr
    """
    return ek.ek(os.path.normpath, ek.ek(os.path.normcase, ek.ek(os.path.realpath, ek.ek(os.path.expanduser, path))))


def validate_show(show_obj, season=None, episode=None):
    """

    :param show_obj: show object
    :type show_obj: TVShow
    :param season: optional season
    :type season: int or None
    :param episode: opitonal episode
    :type episode: int or None
    :return: TVInfoAPI source
    :rtype: object
    """
    show_lang = show_obj.lang

    try:
        tvinfo_config = sickbeard.TVInfoAPI(show_obj.tvid).api_params.copy()
        tvinfo_config['dvdorder'] = 0 != show_obj.dvdorder

        if show_lang and not 'en' == show_lang:
            tvinfo_config['language'] = show_lang

        t = sickbeard.TVInfoAPI(show_obj.tvid).setup(**tvinfo_config)
        if season is None and episode is None:
            return t

        return t[show_obj.prodid][season][episode]
    except (BaseTVinfoEpisodenotfound, BaseTVinfoSeasonnotfound, TypeError):
        pass


def _maybe_request_url(e, def_url=''):
    return hasattr(e, 'request') and hasattr(e.request, 'url') and ' ' + e.request.url or def_url


def clear_cache(force=False):
    """
    clear sickgear cache folder

    :param force: force clearing
    :type force: bool
    """
    # clean out cache directory, remove everything > 12 hours old
    dirty = None
    del_time = int(timestamp_near((datetime.datetime.now() - datetime.timedelta(hours=12))))
    direntry_args = dict(follow_symlinks=False)
    for direntry in scantree(sickbeard.CACHE_DIR, ['images|rss|zoneinfo'], follow_symlinks=True):
        if direntry.is_file(**direntry_args) and (force or del_time > direntry.stat(**direntry_args).st_mtime):
            dirty = dirty or False if remove_file_perm(direntry.path) else True
        elif direntry.is_dir(**direntry_args) and direntry.name not in ['cheetah', 'sessions', 'indexers']:
            dirty = dirty or False
            try:
                ek.ek(os.rmdir, direntry.path)
            except OSError:
                dirty = True

    logger.log(u'%s from cache folder %s' % ((('Found items not removed', 'Found items removed')[not dirty],
                                              'No items found to remove')[None is dirty], sickbeard.CACHE_DIR))


def human(size):
    """
    format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
    Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
    e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc

    :param size: numerical value to be converted
    :type size: int or long or float
    :return: human readable string
    :rtype: AnyStr
    """
    if 1 == size:
        # because I really hate unnecessary plurals
        return "1 byte"

    suffixes_table = [('bytes', 0), ('KB', 0), ('MB', 1), ('GB', 2), ('TB', 2), ('PB', 2)]

    num = float(size)
    for suffix, precision in suffixes_table:
        if 1024.0 > num:
            break
        num /= 1024.0

    # noinspection PyUnboundLocalVariable
    if 0 == precision:
        formatted_size = '%d' % num
    else:
        formatted_size = str(round(num, ndigits=precision))

    # noinspection PyUnboundLocalVariable
    return '%s %s' % (formatted_size, suffix)


def get_size(start_path='.'):
    """
    return combined size of data in given path

    :param start_path: start path
    :type start_path: AnyStr
    :return: size in bytes
    :rtype: int or long
    """
    if ek.ek(os.path.isfile, start_path):
        return ek.ek(os.path.getsize, start_path)
    try:
        return sum(map((lambda x: x.stat(follow_symlinks=False).st_size), scantree(start_path)))
    except OSError:
        return 0


def get_media_stats(start_path='.'):
    # type: (AnyStr) -> Tuple[int, int, int, int]
    """
    return recognised media stats for a folder as...

    number of media files, smallest size in bytes, largest size in bytes, average size in bytes

    :param start_path: path to scan
    """
    if ek.ek(os.path.isdir, start_path):
        sizes = sorted(map(lambda y: y.stat(follow_symlinks=False).st_size,
                           filter(lambda x: has_media_ext(x.name), scantree(start_path))))
        if sizes:
            return len(sizes), sizes[0], sizes[-1], int(sum(sizes) / len(sizes))

    elif ek.ek(os.path.isfile, start_path):
        size = ek.ek(os.path.getsize, start_path)
        return 1, size, size, size

    return 0, 0, 0, 0


def remove_article(text=''):
    """
    remove articles from text

    :param text: input text
    :type text: AnyStr
    :return: text without articles
    :rtype: AnyStr
    """
    return re.sub(r'(?i)^(?:(?:A(?!\s+to)n?)|The)\s(\w)', r'\1', text)


def re_valid_hostname(with_allowed=True):
    this_host = socket.gethostname()
    return re.compile(r'(?i)(%slocalhost|.*\.local%s%s)$' % (
        (with_allowed
         and '%s|' % (sickbeard.ALLOWED_HOSTS
                      and '|'.join(re.escape(x.strip()) for x in sickbeard.ALLOWED_HOSTS.split(','))
                      or '.*')
         or ''),
        bool(this_host) and ('|%s' % this_host) or '',
        sickbeard.ALLOW_ANYIP and ('|%s' % valid_ipaddr_expr()) or ''))


def valid_ipaddr_expr():
    """
    Returns a regular expression that will validate an ip address
    :return: Regular expression
    :rtype: String
    """
    return r'(%s)' % '|'.join([re.sub(r'\s+(#.[^\r\n]+)?', '', x) for x in [
        # IPv4 address (accurate)
        #  Matches 0.0.0.0 through 255.255.255.255
        r'''
        (?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])
        ''',
        # IPv6 address (standard and mixed)
        #  8 hexadecimal words, or 6 hexadecimal words followed by 4 decimal bytes All with optional leading zeros
        r'''
        (?:(?<![:.\w])\[?                                            # Anchor address
        (?:[A-F0-9]{1,4}:){6}                                        #    6 words
        (?:[A-F0-9]{1,4}:[A-F0-9]{1,4}                               #    2 words
        |  (?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}  #    or 4 bytes
           (?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])
        )(?![:.\w]))                                                 # Anchor address
        ''',
        # IPv6 address (compressed and compressed mixed)
        #  8 hexadecimal words, or 6 hexadecimal words followed by 4 decimal bytes
        #  All with optional leading zeros.  Consecutive zeros may be replaced with ::
        r'''
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
    """

    :param seq: Iterable sequence
    :type seq: Iterable
    :param key: key
    :type key: AnyStr
    :return: returns dict
    :rtype: Dict
    """
    return dict([(d[key], dict(d, index=index)) for (index, d) in enumerate(seq)])


def client_host(server_host):
    """Extracted from cherrypy libs
    Return the host on which a client can connect to the given listener."""
    if '0.0.0.0' == server_host:
        # 0.0.0.0 is INADDR_ANY, which should answer on localhost.
        return '127.0.0.1'
    if server_host in ('::', '::0', '::0.0.0.0'):
        # :: is IN6ADDR_ANY, which should answer on localhost.
        # ::0 and ::0.0.0.0 are non-canonical but common ways to write
        # IN6ADDR_ANY.
        return '::1'
    return server_host


def wait_for_free_port(host, port):
    """Extracted from cherrypy libs
    Wait for the specified port to become free (drop requests)."""
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
    """Extracted from cherrypy libs
    Raise an error if the given port is not free on the given host."""
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
            # See http://groups.google.com/group/cherrypy-users/browse_frm/thread/bbfe5eb39c904fe0
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
        my_db = db.DBConnection('cache.db')
        my_db.action('DELETE FROM provider_cache WHERE provider NOT IN (%s)' % ','.join(['?'] * len(providers)),
                     providers)


def make_search_segment_html_string(segment, max_eps=5):
    seg_str = ''
    if segment and not isinstance(segment, list):
        segment = [segment]
    if segment and len(segment) > max_eps:
        seasons = [x for x in set([x.season for x in segment])]
        seg_str = u'Season%s: ' % maybe_plural(len(seasons))
        divider = ''
        for x in seasons:
            eps = [str(s.episode) for s in segment if x == s.season]
            ep_c = len(eps)
            seg_str += '%s%s <span title="Episode%s: %s">(%s Ep%s)</span>' \
                       % (divider, x, maybe_plural(ep_c), ', '.join(eps), ep_c, maybe_plural(ep_c))
            divider = ', '
    elif segment:
        episode_numbers = ['S%sE%s' % (str(x.season).zfill(2), str(x.episode).zfill(2)) for x in segment]
        seg_str = u'Episode%s: %s' % (maybe_plural(len(episode_numbers)), ', '.join(episode_numbers))
    return seg_str


def has_anime():
    """
    :return: if there are any anime shows in show list
    :rtype: bool
    """
    # noinspection PyTypeChecker
    return False if not sickbeard.showList else any(filter_iter(lambda show: show.is_anime, sickbeard.showList))


def cpu_sleep():
    if cpu_presets[sickbeard.CPU_PRESET]:
        time.sleep(cpu_presets[sickbeard.CPU_PRESET])


def cleanup_cache():
    """
    Delete old cached files
    """
    delete_not_changed_in(
        [ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', 'browse', 'thumb', x)
         for x in ['anidb', 'imdb', 'trakt', 'tvdb']] +
        [ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', x)
         for x in ['characters', 'person']] +
        [ek.ek(os.path.join, sickbeard.CACHE_DIR, 'tvinfo_cache')])


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
    del_time = int(timestamp_near((datetime.datetime.now() - datetime.timedelta(days=days, minutes=minutes))))
    errors = 0
    qualified = 0
    for cur_path in (paths, [paths])[not isinstance(paths, list)]:
        try:
            for direntry in scantree(cur_path, filter_kind=False):
                if del_time > direntry.stat(follow_symlinks=False).st_mtime:
                    if not remove_file_perm(direntry.path):
                        errors += 1
                    qualified += 1
        except (BaseException, Exception):
            pass
    return qualified, errors


def set_file_timestamp(filename, min_age=3, new_time=None):
    """

    :param filename: filename
    :type filename: AnyStr
    :param min_age: minimum age in days
    :type min_age: int
    :param new_time:
    :type new_time: None or int
    """
    min_time = int(timestamp_near((datetime.datetime.now() - datetime.timedelta(days=min_age))))
    try:
        if ek.ek(os.path.isfile, filename) and ek.ek(os.path.getmtime, filename) < min_time:
            ek.ek(os.utime, filename, new_time)
    except (BaseException, Exception):
        pass


def should_delete_episode(status):
    """
    check if episode should be deleted from db

    :param status: episode status
    :type status: int
    :return: should be deleted
    :rtype: bool
    """
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

        attr = ctypes.windll.kernel32.GetFileAttributesW(text_type(filepath))
        return invalid_file_attributes != attr and 0 != attr & file_attribute_reparse_point

    return ek.ek(os.path.islink, filepath)


def df():
    """
    Return disk free space at known parent locations

    :return: string path, string value that is formatted size
    :rtype: Tuple[List[Tuple[AnyStr, AnyStr]], bool]
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
    :type path: AnyStr
    :return: Size in bytes
    :rtype: long or None
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
        except (BaseException, Exception):
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
    :type search: AnyStr
    :param replace: Replacement text
    :type replace: AnyStr
    :param subject: Path text to search
    :type subject: AnyStr
    :return: Subject with or without substitution, True if a change was made otherwise False
    :rtype: Tuple[AnyStr, bool]
    """
    delim = '/!~!/'
    search = re.sub(r'[\\]', delim, search)
    replace = re.sub(r'[\\]', delim, replace)
    path = re.sub(r'[\\]', delim, subject)
    result = re.sub('(?i)^%s' % search, replace, path)
    result = ek.ek(os.path.normpath, re.sub(delim, '/', result))

    return result, result != subject


def get_overview(ep_status, show_quality, upgrade_once, split_snatch=False):
    # type: (integer_types, integer_types, Union[integer_types, bool], bool) -> integer_types
    """

    :param ep_status: episode status
    :param show_quality: show quality
    :param upgrade_once: upgrade once
    :param split_snatch:
    :type split_snatch: bool
    :return: constant from classes Overview
    """
    status, quality = Quality.splitCompositeStatus(ep_status)
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
        if not split_snatch and status in SNATCHED_ANY:
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
        return (Overview.QUAL, Overview.SNATCHED_QUAL)[status in SNATCHED_ANY]


def generate_show_dir_name(root_dir, show_name):
    # type: (Optional[AnyStr], AnyStr) -> AnyStr
    """
    generate show dir name

    :param root_dir: root dir
    :param show_name: show name
    :return: show dir name
    """
    san_show_name = sanitize_filename(show_name)
    if sickbeard.SHOW_DIRS_WITH_DOTS:
        san_show_name = san_show_name.replace(' ', '.')
    if None is root_dir:
        return san_show_name
    return ek.ek(os.path.join, root_dir, san_show_name)


def count_files_dirs(base_dir):
    """

    :param base_dir: path
    :type base_dir: AnyStr
    :return: tuple of count of files, dirs
    :rtype: Tuple[int, int]
    """
    f = d = 0
    try:
        files = ek.ek(scandir, base_dir)
    except OSError as e:
        logger.log('Unable to count files %s / %s' % (repr(e), ex(e)), logger.WARNING)
    else:
        for e in files:
            if e.is_file():
                f += 1
            elif e.is_dir():
                d += 1

    return f, d


def upgrade_new_naming():
    my_db = db.DBConnection()
    sql_result = my_db.select('SELECT indexer AS tv_id, indexer_id AS prod_id FROM tv_shows')
    show_list = {}
    for cur_result in sql_result:
        show_list[int(cur_result['prod_id'])] = int(cur_result['tv_id'])

    if sickbeard.FANART_RATINGS:
        from sickbeard.tv import TVidProdid
        ne = {}
        for k, v in iteritems(sickbeard.FANART_RATINGS):
            nk = show_list.get(try_int(k))
            if nk:
                ne[TVidProdid({nk: int(k)})()] = sickbeard.FANART_RATINGS[k]
        sickbeard.FANART_RATINGS = ne
        sickbeard.CFG.setdefault('GUI', {})['fanart_ratings'] = '%s' % ne
        sickbeard.CFG.write()

    image_cache_dir = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images')
    bp_match = re.compile(r'(\d+)\.((?:banner|poster|(?:(?:\d+(?:\.\w*)?\.(?:\w{5,8}))\.)?fanart)\.jpg)', flags=re.I)

    def _set_progress(p_msg, c, s):
        ps = None
        if 0 == s:
            ps = 0
        elif 1 == s and 0 == c:
            ps = 100
        elif 1 > c % s:
            ps = c / s
        if None is not ps:
            sickbeard.classes.loading_msg.set_msg_progress(p_msg, '{:6.2f}%'.format(ps))

    for d in ['', 'thumbnails']:
        bd = ek.ek(os.path.join, image_cache_dir, d)
        if ek.ek(os.path.isdir, bd):
            fc, dc = count_files_dirs(bd)
            step = fc / float(100)
            cf = 0
            p_text = 'Upgrading %s' % (d, 'banner/poster')[not d]
            _set_progress(p_text, 0, 0)
            for entry in ek.ek(scandir, bd):
                if entry.is_file():
                    cf += 1
                    _set_progress(p_text, cf, step)
                    b_s = bp_match.search(entry.name)
                    if b_s:
                        old_id = int(b_s.group(1))
                        tvid = show_list.get(old_id)
                        if tvid:
                            nb_dir = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', 'shows',
                                           '%s-%s' % (tvid, old_id), d)
                            if not ek.ek(os.path.isdir, nb_dir):
                                try:
                                    ek.ek(os.makedirs, nb_dir)
                                except (BaseException, Exception):
                                    pass
                            new_name = ek.ek(os.path.join, nb_dir, bp_match.sub(r'\2', entry.name))
                            try:
                                move_file(entry.path, new_name)
                            except (BaseException, Exception) as e:
                                logger.log('Unable to rename %s to %s: %s / %s'
                                           % (entry.path, new_name, repr(e), ex(e)), logger.WARNING)
                        else:
                            # clean up files without reference in db
                            try:
                                ek.ek(os.remove, entry.path)
                            except (BaseException, Exception):
                                pass
                elif entry.is_dir():
                    if entry.name in ['shows', 'browse']:
                        continue
                    elif 'fanart' == entry.name:
                        _set_progress(p_text, 0, 1)
                        fc_fan, dc_fan = count_files_dirs(entry.path)
                        step_fan = dc_fan / float(100)
                        cf_fan = 0
                        p_text = 'Upgrading fanart'
                        _set_progress(p_text, 0, 0)
                        try:
                            entries = ek.ek(scandir, entry.path)
                        except OSError as e:
                            logger.log('Unable to stat dirs %s / %s' % (repr(e), ex(e)), logger.WARNING)
                            continue
                        for d_entry in entries:
                            if d_entry.is_dir():
                                cf_fan += 1
                                _set_progress(p_text, cf_fan, step_fan)
                                old_id = try_int(d_entry.name)
                                if old_id:
                                    new_id = show_list.get(old_id)
                                    if new_id:
                                        new_dir_name = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', 'shows',
                                                             '%s-%s' % (new_id, old_id), 'fanart')
                                        try:
                                            move_file(d_entry.path, new_dir_name)
                                        except (BaseException, Exception) as e:
                                            logger.log('Unable to rename %s to %s: %s / %s' %
                                                       (d_entry.path, new_dir_name, repr(e), ex(e)), logger.WARNING)
                                        if ek.ek(os.path.isdir, new_dir_name):
                                            try:
                                                f_n = filter_iter(lambda fn: fn.is_file(),
                                                                  ek.ek(scandir, new_dir_name))
                                            except OSError as e:
                                                logger.log('Unable to rename %s / %s' % (repr(e), ex(e)),
                                                           logger.WARNING)
                                            else:
                                                rename_args = []
                                                # noinspection PyTypeChecker
                                                for f_entry in f_n:
                                                    rename_args += [(f_entry.path, bp_match.sub(r'\2', f_entry.path))]

                                                for args in rename_args:
                                                    try:
                                                        move_file(*args)
                                                    except (BaseException, Exception) as e:
                                                        logger.log('Unable to rename %s to %s: %s / %s' %
                                                                   (args[0], args[1], repr(e), ex(e)), logger.WARNING)
                                    else:
                                        try:
                                            ek.ek(shutil.rmtree, d_entry.path)
                                        except (BaseException, Exception):
                                            pass
                                try:
                                    ek.ek(shutil.rmtree, d_entry.path)
                                except (BaseException, Exception):
                                    pass
                    try:
                        ek.ek(os.rmdir, entry.path)
                    except (BaseException, Exception):
                        pass
            if 'thumbnails' == d:
                try:
                    ek.ek(os.rmdir, bd)
                except (BaseException, Exception):
                    pass
            _set_progress(p_text, 0, 1)


def xhtml_escape(text, br=True):
    """
    Escapes a string so it is valid within HTML or XML using the function from Tornado.

    :param text: Text to convert entities from for example '"' to '&quot;'
    :type text: AnyStr
    :param br: True, replace newline with html `<br>`
    :type br: bool
    :return: Text with entities replaced
    :rtype: AnyStr
    """
    from tornado import escape
    if br:
        text = re.sub(r'\r?\n', '<br>', text)
    return escape.xhtml_escape(text)


def parse_imdb_id(string):
    # type: (AnyStr) -> Optional[AnyStr]
    """ Parse an IMDB ID from a string

    :param string: string to parse
    :return: parsed ID of the form char, char, number of digits or None if no match
    """
    result = None
    try:
        result = RC_IMDB_ID.findall(string)[0]
    except(BaseException, Exception):
        pass

    return result


def generate_word_str(words, regex=False, join_chr=','):
    # type: (Set[AnyStr], bool, AnyStr) -> AnyStr
    """
    combine a list or set to a string with optional prefix 'regex:'

    :param words: list or set of words
    :type words: set
    :param regex: prefix regex: ?
    :type regex: bool
    :param join_chr: character(s) used for join words
    :type join_chr: basestring
    :return: combined string
    :rtype: basestring
    """
    return '%s%s' % (('', 'regex:')[True is regex], join_chr.join(words))


def split_word_str(word_list):
    # type: (AnyStr) -> Tuple[Set[AnyStr], bool]
    """
    split string into set and boolean regex

    :param word_list: string with words
    :type word_list: basestring
    :return: set of words, is it regex
    :rtype: (set, bool)
    """
    try:
        if word_list.startswith('regex:'):
            rx = True
            word_list = word_list.replace('regex:', '')
        else:
            rx = False
        s = set(w.strip() for w in word_list.split(',') if w.strip())
    except (BaseException, Exception):
        rx = False
        s = set()
    return s, rx
