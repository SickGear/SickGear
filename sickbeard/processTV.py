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
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

from functools import partial
import datetime
import os
import re
import shutil
import stat
import sys
import time

import sickbeard
from sickbeard import postProcessor, notifiers
from sickbeard import db, helpers, exceptions
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
from sickbeard import logger
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard import common
from sickbeard.common import SNATCHED_ANY
from sickbeard.history import reset_status
from sickbeard.exceptions import MultipleShowObjectsException

from sickbeard import failedProcessor

import lib.rarfile.rarfile as rarfile

try:
    import json
except ImportError:
    from lib import simplejson as json


# noinspection PyArgumentList
class ProcessTVShow(object):
    """ Process a TV Show """

    def __init__(self, webhandler=None, is_basedir=True, skip_failure_processing=False):
        self.files_passed = 0
        self.files_failed = 0
        self.fail_detected = False
        self.skip_failure_processing = skip_failure_processing
        self._output = []
        self.webhandler = webhandler
        self.is_basedir = is_basedir

    @property
    def any_vid_processed(self):
        return 0 < self.files_passed

    @property
    def result(self, pre=True):
        return (('<br />', u'\n')[pre]).join(self._output)

    def _buffer(self, text=None):
        if None is not text:
            self._output.append(text)
            if self.webhandler:
                logger_msg = re.sub(r'(?i)<br(?:[\s/]+)>', '\n', text)
                logger_msg = re.sub('(?i)<a[^>]+>([^<]+)<[/]a>', r'\1', logger_msg)
                self.webhandler('%s%s' % (logger_msg, u'\n'))

    def _log_helper(self, message, log_level=logger.DEBUG):
        logger_msg = re.sub(r'(?i)<br(?:[\s/]+)>\.*', '', message)
        logger_msg = re.sub('(?i)<a[^>]+>([^<]+)<[/]a>', r'\1', logger_msg)
        logger.log(u'%s' % logger_msg, log_level)
        self._buffer(message)
        return

    def _set_process_success(self, state=True, reset=False):
        if state:
            self.files_passed += 1
        else:
            self.files_failed += 1
        if reset:
            self.files_passed = 0
            self.files_failed = 0

    def _delete_folder(self, folder, check_empty=True):

        # check if it's a folder
        if not ek.ek(os.path.isdir, folder):
            return False

        # make sure it isn't TV_DOWNLOAD_DIR
        if sickbeard.TV_DOWNLOAD_DIR and helpers.real_path(sickbeard.TV_DOWNLOAD_DIR) == helpers.real_path(folder):
            return False

        # check if it's empty folder when wanted checked
        if check_empty and ek.ek(os.listdir, folder):
            return False

        # try deleting folder
        try:
            shutil.rmtree(folder)
        except (OSError, IOError) as e:
            logger.log(u'Warning: unable to delete folder: %s: %s' % (folder, ex(e)), logger.WARNING)
            return False

        if ek.ek(os.path.isdir, folder):
            logger.log(u'Warning: unable to delete folder: %s' % folder, logger.WARNING)
            return False

        self._log_helper(u'Deleted folder ' + folder, logger.MESSAGE)
        return True

    def _delete_files(self, process_path, notwanted_files, use_trash=False, force=False):

        if not self.any_vid_processed and not force:
            return

        result = True
        # Delete all file not needed
        for cur_file in notwanted_files:

            cur_file_path = ek.ek(os.path.join, process_path, cur_file)

            if not ek.ek(os.path.isfile, cur_file_path):
                continue  # Prevent error when a notwantedfiles is an associated files

            # check first the read-only attribute
            file_attribute = ek.ek(os.stat, cur_file_path)[0]
            if not file_attribute & stat.S_IWRITE:
                # File is read-only, so make it writeable
                self._log_helper(u'Changing ReadOnly flag for file ' + cur_file)
                try:
                    ek.ek(os.chmod, cur_file_path, stat.S_IWRITE)
                except OSError as e:
                    self._log_helper(u'Cannot change permissions of %s: %s' % (cur_file_path, str(e.strerror)))

            helpers.remove_file(cur_file_path)

            if ek.ek(os.path.isfile, cur_file_path):
                result = False
            else:
                self._log_helper(u'Deleted file ' + cur_file)

        return result

    def check_name(self, name):
        if self.is_basedir:
            return None

        so = None
        my_db = db.DBConnection()
        sql_results = my_db.select(
            'SELECT showid FROM history' +
            ' WHERE resource = ?' +
            ' AND (%s)' % ' OR '.join('action LIKE "%%%02d"' % x for x in SNATCHED_ANY) +
            ' ORDER BY rowid', [name])
        if sql_results:
            try:
                so = helpers.findCertainShow(sickbeard.showList, int(sql_results[-1]['showid']))
                if hasattr(so, 'name'):
                    logger.log('Found Show: %s in snatch history for: %s' % (so.name, name), logger.DEBUG)
            except MultipleShowObjectsException:
                so = None
        return so

    def showObj_helper(self, showObj, base_dir, dir_name, nzb_name, pp_type, alt_showObj=None):
        if None is showObj and base_dir == sickbeard.TV_DOWNLOAD_DIR and not nzb_name or 'manual' == pp_type:
            # Scheduled Post Processing Active
            return self.check_name(dir_name)
        return (showObj, alt_showObj)[None is showObj and None is not alt_showObj]

    def check_video_filenames(self, path, videofiles):
        if self.is_basedir:
            return None

        video_pick = None
        video_size = 0
        for cur_video_file in videofiles:
            try:
                cur_video_size = ek.ek(os.path.getsize, ek.ek(os.path.join, path, cur_video_file))
            except (StandardError, Exception):
                continue

            if 0 == video_size or cur_video_size > video_size:
                video_size = cur_video_size
                video_pick = cur_video_file

        if video_pick:
            vid_filename = ek.ek(os.path.splitext, video_pick)[0]
            # check if filename is garbage, disregard it
            if re.search(r'^[a-zA-Z0-9]+$', vid_filename):
                return None

            return self.check_name(vid_filename)

        return None

    def process_dir(self, dir_name, nzb_name=None, process_method=None, force=False, force_replace=None,
                    failed=False, pp_type='auto', cleanup=False, showObj=None):
        """
        Scans through the files in dir_name and processes whatever media files it finds

        dir_name: The folder name to look in
        nzb_name: The NZB name which resulted in this folder being downloaded
        force: True to postprocess already postprocessed files
        failed: Boolean for whether or not the download failed
        pp_type: Type of postprocessing auto or manual
        """

        # if they passed us a real directory then assume it's the one we want
        if dir_name and ek.ek(os.path.isdir, dir_name):
            dir_name = ek.ek(os.path.realpath, dir_name)

        # if the client and SickGear are not on the same machine translate the directory in a network directory
        elif dir_name and sickbeard.TV_DOWNLOAD_DIR and ek.ek(os.path.isdir, sickbeard.TV_DOWNLOAD_DIR)\
                and ek.ek(os.path.normpath, dir_name) != ek.ek(os.path.normpath, sickbeard.TV_DOWNLOAD_DIR):
            dir_name = ek.ek(os.path.join, sickbeard.TV_DOWNLOAD_DIR,
                             ek.ek(os.path.abspath, dir_name).split(os.path.sep)[-1])
            self._log_helper(u'SickGear PP Config, completed TV downloads folder: ' + sickbeard.TV_DOWNLOAD_DIR)

        if dir_name:
            self._log_helper(u'Checking folder... ' + dir_name)

        # if we didn't find a real directory then process "failed" or just quit
        if not dir_name or not ek.ek(os.path.isdir, dir_name):
            if nzb_name and failed:
                self._process_failed(dir_name, nzb_name, showObj=showObj)
            else:
                self._log_helper(u'Unable to figure out what folder to process. ' +
                                 u'If your downloader and SickGear aren\'t on the same PC then make sure ' +
                                 u'you fill out your completed TV download folder in the PP config.')
            return self.result

        if dir_name == sickbeard.TV_DOWNLOAD_DIR:
            self.is_basedir = True

        if None is showObj:
            if isinstance(nzb_name, basestring):
                showObj = self.check_name(re.sub(r'\.(nzb|torrent)$', '', nzb_name, flags=re.I))

            if None is showObj and dir_name:
                showObj = self.check_name(ek.ek(os.path.basename, dir_name))

        path, dirs, files = self._get_path_dir_files(dir_name, nzb_name, pp_type)

        if sickbeard.POSTPONE_IF_SYNC_FILES and any(filter(helpers.isSyncFile, files)):
            self._log_helper(u'Found temporary sync files, skipping post process', logger.ERROR)
            return self.result

        if not process_method:
            process_method = sickbeard.PROCESS_METHOD

        self._log_helper(u'Processing folder... %s' % path)

        work_files = []
        joined = self.join(path)
        if joined:
            work_files += [joined]

        rar_files, rarfile_history = self.unused_archives(
            path, filter(helpers.is_first_rar_volume, files), pp_type, process_method)
        rar_content = self._unrar(path, rar_files, force)
        if self.fail_detected:
            self._process_failed(dir_name, nzb_name, showObj=showObj)
            return self.result
        rar_content = [x for x in rar_content if not helpers.is_link(ek.ek(os.path.join, path, x))]
        path, dirs, files = self._get_path_dir_files(dir_name, nzb_name, pp_type)
        files = [x for x in files if not helpers.is_link(ek.ek(os.path.join, path, x))]
        video_files = filter(helpers.has_media_ext, files)
        video_in_rar = filter(helpers.has_media_ext, rar_content)
        work_files += [ek.ek(os.path.join, path, item) for item in rar_content]

        if 0 < len(files):
            self._log_helper(u'Process file%s: %s' % (helpers.maybe_plural(files), str(files)))
        if 0 < len(video_files):
            self._log_helper(u'Process video file%s: %s' % (helpers.maybe_plural(video_files), str(video_files)))
        if 0 < len(rar_content):
            self._log_helper(u'Process rar content: ' + str(rar_content))
        if 0 < len(video_in_rar):
            self._log_helper(u'Process video%s in rar: %s' % (helpers.maybe_plural(video_in_rar), str(video_in_rar)))

        # If nzb_name is set and there's more than one videofile in the folder, files will be lost (overwritten).
        nzb_name_original = nzb_name
        if 2 <= len(video_files):
            nzb_name = None

        if None is showObj and 0 < len(video_files):
            showObj = self.check_video_filenames(path, video_files)

        # self._set_process_success()

        # Don't Link media when the media is extracted from a rar in the same path
        if process_method in ('hardlink', 'symlink') and video_in_rar:
            soh = showObj
            if None is showObj:
                soh = self.check_video_filenames(path, video_in_rar)
            self._process_media(path, video_in_rar, nzb_name, 'move', force, force_replace, showObj=soh)
            self._delete_files(path, [ek.ek(os.path.relpath, item, path) for item in work_files], force=True)
            video_batch = set(video_files) - set(video_in_rar)
        else:
            video_batch = video_files

        try:
            while 0 < len(video_batch):
                video_pick = ['']
                video_size = 0
                for cur_video_file in video_batch:
                    cur_video_size = ek.ek(os.path.getsize, ek.ek(os.path.join, path, cur_video_file))
                    if 0 == video_size or cur_video_size > video_size:
                        video_size = cur_video_size
                        video_pick = [cur_video_file]

                video_batch = set(video_batch) - set(video_pick)

                self._process_media(path, video_pick, nzb_name, process_method, force, force_replace,
                                    use_trash=cleanup, showObj=showObj)

        except OSError as e:
            logger.log('Batch skipped, %s%s' %
                       (ex(e), e.filename and (' (file %s)' % e.filename) or ''), logger.WARNING)

        # Process video files in TV subdirectories
        for directory in [x for x in dirs if self._validate_dir(
                path, x, nzb_name_original, failed,
                showObj=self.showObj_helper(showObj, dir_name, x, nzb_name, pp_type))]:

            # self._set_process_success(reset=True)

            for walk_path, walk_dir, files in ek.ek(os.walk, ek.ek(os.path.join, path, directory), topdown=False):

                if sickbeard.POSTPONE_IF_SYNC_FILES and any(filter(helpers.isSyncFile, files)):
                    self._log_helper(u'Found temporary sync files, skipping post process', logger.ERROR)
                    return self.result

                # Ignore any symlinks at this stage to avoid the potential for unraring a symlinked archive
                files = [x for x in files if not helpers.is_link(ek.ek(os.path.join, walk_path, x))]

                rar_files, rarfile_history = self.unused_archives(
                    walk_path, filter(helpers.is_first_rar_volume, files), pp_type, process_method, rarfile_history)
                rar_content = self._unrar(walk_path, rar_files, force)
                work_files += [ek.ek(os.path.join, walk_path, item) for item in rar_content]
                if self.fail_detected:
                    self._process_failed(dir_name, nzb_name, showObj=self.showObj_helper(showObj, directory))
                    continue
                rar_content = [x for x in rar_content if not helpers.is_link(ek.ek(os.path.join, walk_path, x))]
                files = list(set(files + rar_content))
                video_files = filter(helpers.has_media_ext, files)
                video_in_rar = filter(helpers.has_media_ext, rar_content)
                notwanted_files = [x for x in files if x not in video_files]

                # Don't Link media when the media is extracted from a rar in the same path
                if process_method in ('hardlink', 'symlink') and video_in_rar:
                    self._process_media(walk_path, video_in_rar, nzb_name, 'move', force, force_replace,
                                        showObj=self.showObj_helper(showObj, dir_name, directory, nzb_name, pp_type,
                                                                    self.check_video_filenames(walk_dir, video_in_rar)))
                    video_batch = set(video_files) - set(video_in_rar)
                else:
                    video_batch = video_files

                try:
                    while 0 < len(video_batch):
                        video_pick = ['']
                        video_size = 0
                        for cur_video_file in video_batch:
                            cur_video_size = ek.ek(os.path.getsize, ek.ek(os.path.join, walk_path, cur_video_file))

                            if 0 == video_size or cur_video_size > video_size:
                                video_size = cur_video_size
                                video_pick = [cur_video_file]

                        video_batch = set(video_batch) - set(video_pick)

                        self._process_media(
                            walk_path, video_pick, nzb_name, process_method, force, force_replace, use_trash=cleanup,
                            showObj=self.showObj_helper(showObj, dir_name, directory, nzb_name, pp_type,
                                                        self.check_video_filenames(walk_dir, video_pick)))

                except OSError as e:
                    logger.log('Batch skipped, %s%s' %
                               (ex(e), e.filename and (' (file %s)' % e.filename) or ''), logger.WARNING)

                if process_method in ('hardlink', 'symlink') and video_in_rar:
                    self._delete_files(walk_path, rar_content)
                else:
                    # Delete all file not needed
                    if not self.any_vid_processed\
                        or 'move' != process_method\
                            or ('manual' == pp_type and not cleanup):  # Avoid deleting files if Manual Postprocessing
                        continue

                    self._delete_files(walk_path, notwanted_files, use_trash=cleanup)

                    if 'move' == process_method\
                            and ek.ek(os.path.normpath, sickbeard.TV_DOWNLOAD_DIR) != ek.ek(os.path.normpath, walk_path):
                        self._delete_folder(walk_path, check_empty=False)

        if 'copy' == process_method and work_files:
            self._delete_files(path, [ek.ek(os.path.relpath, item, path) for item in work_files], force=True)
            for f in sorted(list(set([ek.ek(os.path.dirname, item) for item in work_files]) - {path}),
                            key=len, reverse=True):
                self._delete_folder(f)

        def _bottom_line(text, log_level=logger.DEBUG):
            self._buffer('-' * len(text))
            self._log_helper(text, log_level)

        notifiers.notify_update_library(ep_obj=None, flush_q=True)

        if self.any_vid_processed:
            if not self.files_failed:
                _bottom_line(u'Successfully processed.', logger.MESSAGE)
            else:
                _bottom_line(u'Successfully processed at least one video file%s.' %
                             (', others were skipped', ' and skipped another')[1 == self.files_failed], logger.MESSAGE)
        else:
            _bottom_line(u'Failed! Did not process any files.', logger.WARNING)

        return self.result

    @staticmethod
    def unused_archives(path, archives, pp_type, process_method, archive_history=None):

        archive_history = (archive_history, {})[not archive_history]
        if ('auto' == pp_type and sickbeard.PROCESS_AUTOMATICALLY
                and 'copy' == process_method and sickbeard.UNPACK):

            archive_history_file = ek.ek(os.path.join, sickbeard.DATA_DIR, 'archive_history.txt')

            if not archive_history:
                try:
                    with open(archive_history_file, 'r') as fh:
                        archive_history = json.loads(fh.read(10 * 1024 * 1024))
                except (IOError, ValueError, Exception):
                    pass

            init_history_cnt = len(archive_history)

            for archive in archive_history.keys():
                if not ek.ek(os.path.isfile, archive):
                    del archive_history[archive]

            unused_files = list(set([ek.ek(os.path.join, path, x) for x in archives]) - set(archive_history.keys()))
            archives = [ek.ek(os.path.basename, x) for x in unused_files]
            if unused_files:
                for f in unused_files:
                    archive_history.setdefault(f, time.mktime(datetime.datetime.utcnow().timetuple()))

            if init_history_cnt != len(archive_history):
                try:
                    with open(archive_history_file, 'w') as fh:
                        fh.write(json.dumps(archive_history))
                except (IOError, Exception):
                    pass

        return archives, archive_history

    def _validate_dir(self, path, dir_name, nzb_name_original, failed, showObj=None):

        self._log_helper(u'Processing sub dir: ' + dir_name)

        if ek.ek(os.path.basename, dir_name).startswith('_FAILED_'):
            self._log_helper(u'The directory name indicates it failed to extract.')
            failed = True
        elif ek.ek(os.path.basename, dir_name).startswith('_UNDERSIZED_'):
            self._log_helper(u'The directory name indicates that it was previously rejected for being undersized.')
            failed = True
        elif ek.ek(os.path.basename, dir_name).upper().startswith('_UNPACK'):
            self._log_helper(u'The directory name indicates that this release is in the process of being unpacked.')
            return False

        if failed:
            self._process_failed(ek.ek(os.path.join, path, dir_name), nzb_name_original, showObj=showObj)
            return False

        if helpers.is_hidden_folder(dir_name):
            self._log_helper(u'Ignoring hidden folder: ' + dir_name)
            return False

        # make sure the directory isn't inside a show directory
        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM tv_shows')

        for sqlShow in sql_results:
            if dir_name.lower().startswith(ek.ek(os.path.realpath, sqlShow['location']).lower() + os.sep)\
                    or dir_name.lower() == ek.ek(os.path.realpath, sqlShow['location']).lower():
                self._log_helper(
                    u'Found an episode that has already been moved to its show dir, skipping',
                    logger.ERROR)
                return False

        # Get the videofile list for the next checks
        all_files = []
        all_dirs = []
        process_path = None
        for process_path, process_dir, fileList in ek.ek(os.walk, ek.ek(os.path.join, path, dir_name), topdown=False):
            all_dirs += process_dir
            all_files += fileList

        video_files = filter(helpers.has_media_ext, all_files)
        all_dirs.append(dir_name)

        # check if the directory have at least one tv video file
        for video in video_files:
            try:
                NameParser(showObj=showObj).parse(video, cache_result=False)
                return True
            except (InvalidNameException, InvalidShowException):
                pass

        for directory in all_dirs:
            try:
                NameParser(showObj=showObj).parse(directory, cache_result=False)
                return True
            except (InvalidNameException, InvalidShowException):
                pass

        if sickbeard.UNPACK and process_path and all_files:
            # Search for packed release
            packed_files = filter(helpers.is_first_rar_volume, all_files)

            for packed in packed_files:
                try:
                    NameParser(showObj=showObj).parse(packed, cache_result=False)
                    return True
                except (InvalidNameException, InvalidShowException):
                    pass

        return False

    def _unrar(self, path, rar_files, force):

        unpacked_files = []

        if 'win32' == sys.platform:
            rarfile.UNRAR_TOOL = ek.ek(os.path.join, sickbeard.PROG_DIR, 'lib', 'rarfile', 'UnRAR.exe')

        if sickbeard.UNPACK and rar_files:

            self._log_helper(u'Packed releases detected: ' + str(rar_files))

            for archive in rar_files:

                self._log_helper(u'Unpacking archive: ' + archive)

                try:
                    rar_handle = rarfile.RarFile(ek.ek(os.path.join, path, archive))
                except (StandardError, Exception):
                    self._log_helper(u'Failed to open archive: %s' % archive, logger.ERROR)
                    self._set_process_success(False)
                    continue
                try:
                    # Skip extraction if any file in archive has previously been extracted
                    skip_file = False
                    for file_in_archive in [ek.ek(os.path.basename, x.filename)
                                            for x in rar_handle.infolist() if not x.isdir()]:
                        if self._already_postprocessed(path, file_in_archive, force):
                            self._log_helper(
                                u'Archive file already processed, extraction skipped: ' + file_in_archive)
                            skip_file = True
                            break

                    if not skip_file:
                        # need to test for password since rar4 doesn't raise PasswordRequired
                        if rar_handle.needs_password():
                            raise rarfile.PasswordRequired

                        rar_handle.extractall(path=path)
                        rar_content = [ek.ek(os.path.normpath, x.filename)
                                       for x in rar_handle.infolist() if not x.isdir()]
                        renamed = self.cleanup_names(path, rar_content)
                        cur_unpacked = rar_content if not renamed else \
                            (list(set(rar_content) - set(renamed.keys())) + renamed.values())
                        self._log_helper(u'Unpacked content: [u\'%s\']' % '\', u\''.join(map(unicode, cur_unpacked)))
                        unpacked_files += cur_unpacked
                except (rarfile.PasswordRequired, rarfile.RarWrongPassword):
                    self._log_helper(u'Failed to unpack archive PasswordRequired: %s' % archive, logger.ERROR)
                    self._set_process_success(False)
                    self.fail_detected = True
                except (StandardError, Exception):
                    self._log_helper(u'Failed to unpack archive: %s' % archive, logger.ERROR)
                    self._set_process_success(False)
                finally:
                    rar_handle.close()
                    del rar_handle

        elif rar_files:
            # check for passworded rar's
            for archive in rar_files:
                try:
                    rar_handle = rarfile.RarFile(ek.ek(os.path.join, path, archive))
                except (StandardError, Exception):
                    self._log_helper(u'Failed to open archive: %s' % archive, logger.ERROR)
                    continue
                try:
                    if rar_handle.needs_password():
                        self._log_helper(u'Failed to unpack archive PasswordRequired: %s' % archive, logger.ERROR)
                        self._set_process_success(False)
                        self.failure_detected = True
                    rar_handle.close()
                    del rar_handle
                except (StandardError, Exception):
                    pass

        return unpacked_files

    @staticmethod
    def cleanup_names(directory, files=None):

        is_renamed = {}
        num_videos = 0
        old_name = None
        new_name = None
        params = {
            'base_name': ek.ek(os.path.basename, directory),
            'reverse_pattern': re.compile('|'.join([
                r'\.\d{2}e\d{2}s\.', r'\.p0(?:63|27|612)\.', r'\.[pi](?:084|675|0801)\.', r'\b[45]62[xh]\.',
                r'\.yarulb\.', r'\.vtd[hp]\.', r'\.(?:ld[.-]?)?bew\.', r'\.pir.?(?:shv|dov|dvd|bew|db|rb)\.',
                r'\brdvd\.', r'\.(?:vts|dcv)\.', r'\b(?:mac|pir)dh\b', r'\.(?:lanretni|reporp|kcaper|reneercs)\.',
                r'\b(?:caa|3ca|3pm)\b', r'\.cstn\.', r'\.5r\.', r'\brcs\b'
            ]), flags=re.IGNORECASE),
            'season_pattern': re.compile(r'(.*\.\d{2}e\d{2}s\.)(.*)', flags=re.IGNORECASE),
            'word_pattern': re.compile(r'([^A-Z0-9]*[A-Z0-9]+)'),
            'char_replace': [[r'(\w)1\.(\w)', r'\1i\2']],
            'garbage_name': re.compile(r'^[a-zA-Z0-9]{3,}$'),
            'media_pattern': re.compile('|'.join([
                r'\.s\d{2}e\d{2}\.', r'\.(?:36|72|216)0p\.', r'\.(?:480|576|1080)[pi]\.', r'\.[xh]26[45]\b',
                r'\.bluray\.', r'\.[hp]dtv\.', r'\.web(?:[.-]?dl)?\.', r'\.(?:vhs|vod|dvd|web|bd|br).?rip\.',
                r'\.dvdr\b', r'\.(?:stv|vcd)\.', r'\bhd(?:cam|rip)\b', r'\.(?:internal|real|proper|repack|screener)\.',
                r'\b(?:aac|ac3|mp3)\b', r'\.(?:ntsc|pal|secam)\.', r'\.r5\.', r'\bscr\b', r'\b(?:divx|xvid)\b'
            ]), flags=re.IGNORECASE)
        }

        def renamer(_dirpath, _filenames, _num_videos, _old_name, _new_name, base_name,
                    reverse_pattern, season_pattern, word_pattern, char_replace, garbage_name, media_pattern):

            for cur_filename in _filenames:

                file_name, file_extension = ek.ek(os.path.splitext, cur_filename)
                file_path = ek.ek(os.path.join, _dirpath, cur_filename)
                dir_name = ek.ek(os.path.dirname, file_path)

                if None is not reverse_pattern.search(file_name):
                    na_parts = season_pattern.search(file_name)
                    if None is not na_parts:
                        word_p = word_pattern.findall(na_parts.group(2))
                        new_words = ''
                        for wp in word_p:
                            if '.' == wp[0]:
                                new_words += '.'
                            new_words += re.sub(r'\W', '', wp)
                        for cr in char_replace:
                            new_words = re.sub(cr[0], cr[1], new_words)
                        new_filename = new_words[::-1] + na_parts.group(1)[::-1]
                    else:
                        new_filename = file_name[::-1]
                    logger.log('Reversing base filename "%s" to "%s"' % (file_name, new_filename))
                    try:
                        ek.ek(os.rename, file_path, ek.ek(os.path.join, _dirpath, new_filename + file_extension))
                        is_renamed[ek.ek(os.path.relpath, file_path, directory)] = ek.ek(
                            os.path.relpath, new_filename + file_extension, directory)
                    except OSError as e:
                        logger.log('Error unable to rename file "%s" because %s' % (cur_filename, ex(e)), logger.ERROR)
                elif helpers.has_media_ext(cur_filename) and \
                        None is not garbage_name.search(file_name) and None is not media_pattern.search(base_name):
                    _num_videos += 1
                    _old_name = file_path
                    _new_name = ek.ek(os.path.join, dir_name, '%s%s' % (base_name, file_extension))
            return is_renamed, _num_videos, _old_name, _new_name

        if files:
            is_renamed, num_videos, old_name, new_name = renamer(
                directory, files, num_videos, old_name, new_name, **params)
        else:
            for cur_dirpath, void, cur_filenames in ek.ek(os.walk, directory):
                is_renamed, num_videos, old_name, new_name = renamer(
                    cur_dirpath, cur_filenames, num_videos, old_name, new_name, **params)

        if all([not is_renamed, 1 == num_videos, old_name, new_name]):
            try_name = ek.ek(os.path.basename, new_name)
            logger.log('Renaming file "%s" using dirname as "%s"' % (ek.ek(os.path.basename, old_name), try_name))
            try:
                ek.ek(os.rename, old_name, new_name)
                is_renamed[ek.ek(os.path.relpath, old_name, directory)] = ek.ek(os.path.relpath, new_name, directory)
            except OSError as e:
                logger.log('Error unable to rename file "%s" because %s' % (old_name, ex(e)), logger.ERROR)

        return is_renamed

    def join(self, directory):

        result = False
        chunks = {}
        matcher = re.compile('\.[0-9]+$')
        for dirpath, void, filenames in ek.ek(os.walk, directory):
            for filename in filenames:
                if None is not matcher.search(filename):
                    maybe_chunk = ek.ek(os.path.join, dirpath, filename)
                    base_filepath, ext = ek.ek(os.path.splitext, maybe_chunk)
                    if base_filepath not in chunks:
                        chunks[base_filepath] = []
                    chunks[base_filepath].append(maybe_chunk)

        if not chunks:
            return

        for base_filepath in chunks:
            chunks[base_filepath].sort()
            chunk_set = chunks[base_filepath]
            if ek.ek(os.path.isfile, base_filepath):
                base_filesize = ek.ek(os.path.getsize, base_filepath)
                chunk_sizes = [ek.ek(os.path.getsize, x) for x in chunk_set]
                largest_chunk = max(chunk_sizes)
                if largest_chunk >= base_filesize:
                    outfile = '%s.001' % base_filepath
                    if outfile not in chunk_set:
                        try:
                            ek.ek(os.rename, base_filepath, outfile)
                        except OSError:
                            logger.log('Error unable to rename file %s' % base_filepath, logger.ERROR)
                            return result
                        chunk_set.append(outfile)
                        chunk_set.sort()
                    else:
                        del_dir, del_file = ek.ek(os.path.split, base_filepath)
                        if not self._delete_files(del_dir, [del_file], force=True):
                            return result
                else:
                    if base_filesize == sum(chunk_sizes):
                        logger.log('Join skipped. Total size of %s input files equal to output.. %s (%s bytes)' % (
                            len(chunk_set), base_filepath, base_filesize))
                    else:
                        logger.log('Join skipped. Found output file larger than input.. %s (%s bytes)' % (
                            base_filepath, base_filesize))
                    return result

            with open(base_filepath, 'ab') as newfile:
                for f in chunk_set:
                    logger.log('Joining file %s' % f)
                    try:
                        with open(f, 'rb') as part:
                            for wdata in iter(partial(part.read, 4096), b''):
                                try:
                                    newfile.write(wdata)
                                except (StandardError, Exception):
                                    logger.log('Failed write to file %s' % f)
                                    return result
                    except (StandardError, Exception):
                        logger.log('Failed read from file %s' % f)
                        return result
            result = base_filepath

        return result

    def _already_postprocessed(self, dir_name, videofile, force):

        if force or not self.any_vid_processed:
            return False

        # Needed for accessing DB with a unicode dir_name
        if not isinstance(dir_name, unicode):
            dir_name = unicode(dir_name, 'utf_8')

        parse_result = None
        try:
            parse_result = NameParser(try_scene_exceptions=True, convert=True).parse(videofile, cache_result=False)
        except (InvalidNameException, InvalidShowException):
            # Does not parse, move on to directory check
            pass
        if None is parse_result:
            try:
                parse_result = NameParser(try_scene_exceptions=True, convert=True).parse(dir_name, cache_result=False)
            except (InvalidNameException, InvalidShowException):
                # If the filename doesn't parse, then return false as last
                # resort. We can assume that unparseable filenames are not
                # processed in the past
                return False

        showlink = ('for "<a href="%s/home/displayShow?show=%s" target="_blank">%s</a>"' % (
            sickbeard.WEB_ROOT, parse_result.show.indexerid, parse_result.show.name),
            parse_result.show.name)[self.any_vid_processed]

        ep_detail_sql = ''
        if parse_result.show.indexerid and 0 < len(parse_result.episode_numbers) and parse_result.season_number:
            ep_detail_sql = " and tv_episodes.showid='%s' and tv_episodes.season='%s' and tv_episodes.episode='%s'"\
                            % (str(parse_result.show.indexerid),
                               str(parse_result.season_number),
                               str(parse_result.episode_numbers[0]))

        # Avoid processing the same directory again if we use a process method <> move
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM tv_episodes WHERE release_name = ?', [dir_name])
        if sql_result:
            self._log_helper(u'Found a release directory %s that has already been processed,<br />.. skipping: %s'
                             % (showlink, dir_name))
            if ep_detail_sql:
                reset_status(parse_result.show.indexerid,
                             parse_result.season_number,
                             parse_result.episode_numbers[0])
            return True

        else:
            # This is needed for video whose name differ from dir_name
            if not isinstance(videofile, unicode):
                videofile = unicode(videofile, 'utf_8')

            sql_result = my_db.select(
                'SELECT * FROM tv_episodes WHERE release_name = ?', [videofile.rpartition('.')[0]])
            if sql_result:
                self._log_helper(u'Found a video, but that release %s was already processed,<br />.. skipping: %s'
                                 % (showlink, videofile))
                if ep_detail_sql:
                    reset_status(parse_result.show.indexerid,
                                 parse_result.season_number,
                                 parse_result.episode_numbers[0])
                return True

            # Needed if we have downloaded the same episode @ different quality
            search_sql = 'SELECT tv_episodes.indexerid, history.resource FROM tv_episodes INNER JOIN history'\
                         + ' ON history.showid=tv_episodes.showid'\
                         + ' WHERE history.season=tv_episodes.season and history.episode=tv_episodes.episode'\
                         + ep_detail_sql\
                         + ' and tv_episodes.status IN (%s)' % ','.join([str(x) for x in common.Quality.DOWNLOADED])\
                         + ' and history.resource LIKE ?'

            sql_result = my_db.select(search_sql, [u'%' + videofile])
            if sql_result:
                self._log_helper(u'Found a video, but the episode %s is already processed,<br />.. skipping: %s'
                                 % (showlink, videofile))
                if ep_detail_sql:
                    reset_status(parse_result.show.indexerid,
                                 parse_result.season_number,
                                 parse_result.episode_numbers[0])
                return True

        return False

    def _process_media(self, process_path, video_files, nzb_name, process_method, force, force_replace,
                       use_trash=False, showObj=None):

        processor = None
        for cur_video_file in video_files:

            if self._already_postprocessed(process_path, cur_video_file, force):
                self._set_process_success(False)
                continue

            cur_video_file_path = ek.ek(os.path.join, process_path, cur_video_file)

            try:
                processor = postProcessor.PostProcessor(
                    cur_video_file_path, nzb_name, process_method, force_replace,
                    use_trash=use_trash, webhandler=self.webhandler, showObj=showObj)

                file_success = processor.process()
                process_fail_message = ''
            except exceptions.PostProcessingFailed:
                file_success = False
                process_fail_message = '<br />.. Post Processing Failed'

            self._set_process_success(file_success)

            if processor:
                self._buffer(processor.log.strip('\n'))

            if file_success:
                self._log_helper(u'Successfully processed ' + cur_video_file, logger.MESSAGE)
            elif self.any_vid_processed:
                self._log_helper(u'Warning fail for %s%s' % (cur_video_file_path, process_fail_message),
                                 logger.WARNING)
            else:
                self._log_helper(u'Did not use file %s%s' % (cur_video_file_path, process_fail_message),
                                 logger.WARNING)

    @staticmethod
    def _get_path_dir_files(dir_name, nzb_name, pp_type):
        path = ''
        dirs = []
        files = []

        if dir_name == sickbeard.TV_DOWNLOAD_DIR and not nzb_name or 'manual' == pp_type:
            # Scheduled Post Processing Active
            # Get at first all the subdir in the dir_name
            for path, dirs, files in ek.ek(os.walk, dir_name):
                files = [x for x in files if not helpers.is_link(ek.ek(os.path.join, path, x))]
                break
        else:
            path, dirs = ek.ek(os.path.split, dir_name)  # Script Post Processing
            if None is not nzb_name and not nzb_name.endswith('.nzb') and \
                    ek.ek(os.path.isfile, ek.ek(os.path.join, dir_name, nzb_name)):
                # For single torrent file without directory
                dirs = []
                files = [ek.ek(os.path.join, dir_name, nzb_name)]
            else:
                dirs = [dirs]
                files = []

        return path, dirs, files

    # noinspection PyArgumentList
    def _process_failed(self, dir_name, nzb_name, showObj=None):
        """ Process a download that did not complete correctly """

        if self.skip_failure_processing:
            self._log_helper('Download was not added by SickGear, ignoring failure', logger.WARNING)
            return

        if sickbeard.USE_FAILED_DOWNLOADS:
            processor = None

            try:
                processor = failedProcessor.FailedProcessor(dir_name, nzb_name, showObj)
                self._set_process_success(processor.process())
                process_fail_message = ''
            except exceptions.FailedProcessingFailed as e:
                self._set_process_success(False)
                process_fail_message = ex(e)

            if processor:
                self._buffer(processor.log.strip('\n'))

            if sickbeard.DELETE_FAILED and self.any_vid_processed:
                self._delete_folder(dir_name, check_empty=False)

            task = u'Failed download processing'
            if self.any_vid_processed:
                self._log_helper(u'Successful %s: (%s, %s)'
                                 % (task.lower(), str(nzb_name), dir_name), logger.MESSAGE)
            else:
                self._log_helper(u'%s failed: (%s, %s): %s'
                                 % (task, str(nzb_name), dir_name, process_fail_message), logger.WARNING)


# backward compatibility prevents the case of this function name from being updated to PEP8
def processDir(dir_name, nzb_name=None, process_method=None, force=False, force_replace=None,
               failed=False, type='auto', cleanup=False, webhandler=None, showObj=None, is_basedir=True,
               skip_failure_processing=False):

    # backward compatibility prevents the case of this function name from being updated to PEP8
    return ProcessTVShow(webhandler, is_basedir, skip_failure_processing=skip_failure_processing).process_dir(
        dir_name, nzb_name, process_method, force, force_replace, failed, type, cleanup, showObj)
