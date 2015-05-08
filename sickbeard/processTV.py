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

import os
import shutil
import stat
import re

import sickbeard
from sickbeard import postProcessor
from sickbeard import db, helpers, exceptions
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
from sickbeard import logger
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard import common

from sickbeard import failedProcessor

from lib.unrar2 import RarFile

try:
    from lib.send2trash import send2trash
except ImportError:
    pass


# noinspection PyArgumentList
class ProcessTVShow(object):
    """ Process a TV Show """

    def __init__(self):
        self.files_passed = 0
        self.files_failed = 0
        self._output = []

    @property
    def any_vid_processed(self):
        return 0 < self.files_passed

    @property
    def result(self, pre=True):
        return (('<br />', u'\n')[pre]).join(self._output)

    def _buffer(self, text=None):
        if None is not text:
            self._output.append(text)

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
        except (OSError, IOError), e:
            logger.log(u'Warning: unable to delete folder: %s: %s' % (folder, ex(e)), logger.WARNING)
            return False

        if ek.ek(os.path.isdir, folder):
            logger.log(u'Warning: unable to delete folder: %s' % folder, logger.WARNING)
            return False

        self._log_helper(u'Deleted folder ' + folder, logger.MESSAGE)
        return True

    def _delete_files(self, process_path, notwanted_files, use_trash=False):

        if not self.any_vid_processed:
            return

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
                except OSError, e:
                    self._log_helper(u'Cannot change permissions of %s: %s' % (cur_file_path, str(e.strerror)))
            try:
                if use_trash:
                    ek.ek(send2trash, cur_file_path)
                else:
                    ek.ek(os.remove, cur_file_path)
            except OSError, e:
                self._log_helper(u'Unable to delete file %s: %s' % (cur_file, str(e.strerror)))

            if True is not ek.ek(os.path.isfile, cur_file_path):
                self._log_helper(u'Deleted file ' + cur_file)

    def process_dir(self, dir_name, nzb_name=None, process_method=None, force=False, force_replace=None, failed=False, pp_type='auto', cleanup=False):
        """
        Scans through the files in dir_name and processes whatever media files it finds

        dir_name: The folder name to look in
        nzb_name: The NZB name which resulted in this folder being downloaded
        force: True to postprocess already postprocessed files
        failed: Boolean for whether or not the download failed
        pp_type: Type of postprocessing auto or manual
        """

        # if they passed us a real directory then assume it's the one we want
        if ek.ek(os.path.isdir, dir_name):
            self._log_helper(u'Processing folder... ' + dir_name)
            dir_name = ek.ek(os.path.realpath, dir_name)

        # if the client and SickGear are not on the same machine translate the directory in a network directory
        elif sickbeard.TV_DOWNLOAD_DIR and ek.ek(os.path.isdir, sickbeard.TV_DOWNLOAD_DIR)\
                and ek.ek(os.path.normpath, dir_name) != ek.ek(os.path.normpath, sickbeard.TV_DOWNLOAD_DIR):
            dir_name = ek.ek(os.path.join, sickbeard.TV_DOWNLOAD_DIR, ek.ek(os.path.abspath, dir_name).split(os.path.sep)[-1])
            self._log_helper(u'SickGear PP Config, completed TV downloads folder: ' + sickbeard.TV_DOWNLOAD_DIR)
            self._log_helper(u'Trying to use folder... ' + dir_name)

        # if we didn't find a real directory then quit
        if not ek.ek(os.path.isdir, dir_name):
            self._log_helper(
                u'Unable to figure out what folder to process. If your downloader and SickGear aren\'t on the same PC then make sure you fill out your completed TV download folder in the PP config.')
            return self.result

        path, dirs, files = self._get_path_dir_files(dir_name, nzb_name, pp_type)

        sync_files = filter(helpers.isSyncFile, files)

        # Don't post process if files are still being synced and option is activated
        if sync_files and sickbeard.POSTPONE_IF_SYNC_FILES:
            self._log_helper(u'Found temporary sync files, skipping post process', logger.ERROR)
            return self.result

        self._log_helper(u'Process path: ' + path)
        if 0 < len(dirs):
            self._log_helper(u'Process dir%s: %s' % (('', 's')[1 < len(dirs)], str(dirs)))

        rar_files = filter(helpers.isRarFile, files)
        rar_content = self._unrar(path, rar_files, force)
        files += rar_content
        video_files = filter(helpers.isMediaFile, files)
        video_in_rar = filter(helpers.isMediaFile, rar_content)

        if 0 < len(files):
            self._log_helper(u'Process file%s: %s' % (('', 's')[1 < len(files)], str(files)))
        if 0 < len(video_files):
            self._log_helper(u'Process video file%s: %s' % (('', 's')[1 < len(video_files)], str(video_files)))
        if 0 < len(rar_content):
            self._log_helper(u'Process rar content: ' + str(rar_content))
        if 0 < len(video_in_rar):
            self._log_helper(u'Process video in rar: ' + str(video_in_rar))

        # If nzb_name is set and there's more than one videofile in the folder, files will be lost (overwritten).
        nzb_name_original = nzb_name
        if 2 <= len(video_files):
            nzb_name = None

        if not process_method:
            process_method = sickbeard.PROCESS_METHOD

        # self._set_process_success()

        # Don't Link media when the media is extracted from a rar in the same path
        if process_method in ('hardlink', 'symlink') and video_in_rar:
            self._process_media(path, video_in_rar, nzb_name, 'move', force, force_replace)
            self._delete_files(path, rar_content)
            video_batch = set(video_files) - set(video_in_rar)
        else:
            video_batch = video_files

        while 0 < len(video_batch):
            video_pick = ['']
            video_size = 0
            for cur_video_file in video_batch:
                cur_video_size = ek.ek(os.path.getsize, ek.ek(os.path.join, path, cur_video_file))
                if 0 == video_size or cur_video_size > video_size:
                    video_size = cur_video_size
                    video_pick = [cur_video_file]

            video_batch = set(video_batch) - set(video_pick)

            self._process_media(path, video_pick, nzb_name, process_method, force, force_replace, use_trash=cleanup)

        # Process video files in TV subdirectories
        for directory in [x for x in dirs if self._validate_dir(path, x, nzb_name_original, failed)]:

            self._set_process_success(reset=True)

            for process_path, process_dir, file_list in ek.ek(os.walk, ek.ek(os.path.join, path, directory), topdown=False):

                sync_files = filter(helpers.isSyncFile, file_list)

                # Don't post process if files are still being synced and option is activated
                if sync_files and sickbeard.POSTPONE_IF_SYNC_FILES:
                    self._log_helper(u'Found temporary sync files, skipping post process', logger.ERROR)
                    return self.result

                rar_files = filter(helpers.isRarFile, file_list)
                rar_content = self._unrar(process_path, rar_files, force)
                file_list = set(file_list + rar_content)
                video_files = filter(helpers.isMediaFile, file_list)
                video_in_rar = filter(helpers.isMediaFile, rar_content)
                notwanted_files = [x for x in file_list if x not in video_files]

                # Don't Link media when the media is extracted from a rar in the same path
                if process_method in ('hardlink', 'symlink') and video_in_rar:
                    self._process_media(process_path, video_in_rar, nzb_name, 'move', force, force_replace)
                    video_batch = set(video_files) - set(video_in_rar)
                else:
                    video_batch = video_files

                while 0 < len(video_batch):
                    video_pick = ['']
                    video_size = 0
                    for cur_video_file in video_batch:
                        cur_video_size = ek.ek(os.path.getsize, ek.ek(os.path.join, process_path, cur_video_file))
                        if 0 == video_size or cur_video_size > video_size:
                            video_size = cur_video_size
                            video_pick = [cur_video_file]

                    video_batch = set(video_batch) - set(video_pick)

                    self._process_media(process_path, video_pick, nzb_name, process_method, force, force_replace, use_trash=cleanup)

                if process_method in ('hardlink', 'symlink') and video_in_rar:
                    self._delete_files(process_path, rar_content)
                else:
                    # Delete all file not needed
                    if not self.any_vid_processed\
                        or 'move' != process_method\
                            or ('manual' == pp_type and not cleanup):  # Avoid deleting files if Manual Postprocessing
                        continue

                    self._delete_files(process_path, notwanted_files, use_trash=cleanup)

                    if 'move' == process_method\
                            and ek.ek(os.path.normpath, sickbeard.TV_DOWNLOAD_DIR) != ek.ek(os.path.normpath, process_path):
                        self._delete_folder(process_path, check_empty=False)

        def _bottom_line(text, log_level=logger.DEBUG):
            self._buffer('-' * len(text))
            self._log_helper(text, log_level)

        if self.any_vid_processed:
            if not self.files_failed:
                _bottom_line(u'Successfully processed.', logger.MESSAGE)
            else:
                _bottom_line(u'Successfully processed at least one video file %s.' % (', others were skipped', 'and skipped another')[1 == self.files_failed], logger.MESSAGE)
        else:
            _bottom_line(u'Failed! Did not process any files.', logger.WARNING)

        return self.result

    def _validate_dir(self, path, dir_name, nzb_name_original, failed):

        self._log_helper(u'Processing dir: ' + dir_name)

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
            self._process_failed(os.path.join(path, dir_name), nzb_name_original)
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
        for process_path, process_dir, fileList in ek.ek(os.walk, ek.ek(os.path.join, path, dir_name), topdown=False):
            all_dirs += process_dir
            all_files += fileList

        video_files = filter(helpers.isMediaFile, all_files)
        all_dirs.append(dir_name)

        # check if the directory have at least one tv video file
        for video in video_files:
            try:
                NameParser().parse(video, cache_result=False)
                return True
            except (InvalidNameException, InvalidShowException):
                pass

        for directory in all_dirs:
            try:
                NameParser().parse(directory, cache_result=False)
                return True
            except (InvalidNameException, InvalidShowException):
                pass

        if sickbeard.UNPACK:
            # Search for packed release
            packed_files = filter(helpers.isRarFile, all_files)

            for packed in packed_files:
                try:
                    NameParser().parse(packed, cache_result=False)
                    return True
                except (InvalidNameException, InvalidShowException):
                    pass

        return False

    def _unrar(self, path, rar_files, force):

        unpacked_files = []

        if sickbeard.UNPACK and rar_files:

            self._log_helper(u'Packed releases detected: ' + str(rar_files))

            for archive in rar_files:

                self._log_helper(u'Unpacking archive: ' + archive)

                try:
                    rar_handle = RarFile(os.path.join(path, archive))

                    # Skip extraction if any file in archive has previously been extracted
                    skip_file = False
                    for file_in_archive in [os.path.basename(x.filename) for x in rar_handle.infolist() if not x.isdir]:
                        if self._already_postprocessed(path, file_in_archive, force):
                            self._log_helper(
                                u'Archive file already processed, extraction skipped: ' + file_in_archive)
                            skip_file = True
                            break

                    if skip_file:
                        continue

                    rar_handle.extract(path=path, withSubpath=False, overwrite=False)
                    unpacked_files += [os.path.basename(x.filename) for x in rar_handle.infolist() if not x.isdir]
                    del rar_handle
                except Exception, e:
                    self._log_helper(u'Failed to unpack archive %s: %s' % (archive, ex(e)), logger.ERROR)
                    self._set_process_success(False)
                    continue

            self._log_helper(u'Unpacked content: ' + str(unpacked_files))

        return unpacked_files

    def _already_postprocessed(self, dir_name, videofile, force):

        if force and not self.any_vid_processed:
            return False

        # Needed for accessing DB with a unicode dir_name
        if not isinstance(dir_name, unicode):
            dir_name = unicode(dir_name, 'utf_8')

        parse_result = None
        try:
            parse_result = NameParser(try_indexers=True, try_scene_exceptions=True, convert=True).parse(videofile, cache_result=False)
        except (InvalidNameException, InvalidShowException):
            pass
        if None is parse_result:
            try:
                parse_result = NameParser(try_indexers=True, try_scene_exceptions=True, convert=True).parse(dir_name, cache_result=False)
            except (InvalidNameException, InvalidShowException):
                pass

        showlink = ''
        ep_detail_sql = ''
        undo_status = None
        if parse_result:
            showlink = (' for "<a href="/home/displayShow?show=%s" target="_blank">%s</a>"' % (parse_result.show.indexerid, parse_result.show.name),
                        parse_result.show.name)[self.any_vid_processed]

            if parse_result.show.indexerid and parse_result.episode_numbers and parse_result.season_number:
                ep_detail_sql = " and tv_episodes.showid='%s' and tv_episodes.season='%s' and tv_episodes.episode='%s'"\
                                % (str(parse_result.show.indexerid),
                                   str(parse_result.season_number),
                                   str(parse_result.episode_numbers[0]))
                undo_status = "UPDATE `tv_episodes` SET status="\
                              + "(SELECT h.action FROM `history` as h INNER JOIN `tv_episodes` as t on h.showid=t.showid"\
                              + " where  t.showid='%s' and t.season='%s' and t.episode='%s'"\
                                % (str(parse_result.show.indexerid), str(parse_result.season_number), str(parse_result.episode_numbers[0]))\
                              + " and (h.action is not t.status) group by h.action order by h.date DESC LIMIT 1)"\
                              + " where showid='%s' and season='%s' and episode='%s'"\
                                % (str(parse_result.show.indexerid), str(parse_result.season_number), str(parse_result.episode_numbers[0]))

        # Avoid processing the same directory again if we use a process method <> move
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM tv_episodes WHERE release_name = ?', [dir_name])
        if sql_result:
            self._log_helper(u'Found a release directory%s that has already been processed,<br />.. skipping: %s'
                             % (showlink, dir_name))
            my_db.action(undo_status)
            return True

        else:
            # This is needed for video whose name differ from dir_name
            if not isinstance(videofile, unicode):
                videofile = unicode(videofile, 'utf_8')

            sql_result = my_db.select('SELECT * FROM tv_episodes WHERE release_name = ?', [videofile.rpartition('.')[0]])
            if sql_result:
                self._log_helper(u'Found a video, but that release%s was already processed,<br />.. skipping: %s'
                                 % (showlink, videofile))
                my_db.action(undo_status)
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
                self._log_helper(u'Found a video, but the episode%s is already processed,<br />.. skipping: %s'
                                 % (showlink, videofile))
                my_db.action(undo_status)
                return True

        return False

    def _process_media(self, process_path, video_files, nzb_name, process_method, force, force_replace, use_trash=False):

        processor = None
        for cur_video_file in video_files:

            if self._already_postprocessed(process_path, cur_video_file, force):
                self._set_process_success(False)
                continue

            cur_video_file_path = ek.ek(os.path.join, process_path, cur_video_file)

            try:
                processor = postProcessor.PostProcessor(cur_video_file_path, nzb_name, process_method, force_replace, use_trash=use_trash)
                file_success = processor.process()
                process_fail_message = ''
            except exceptions.PostProcessingFailed, e:
                file_success = False
                process_fail_message = '<br />.. ' + ex(e)

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

        if dir_name == sickbeard.TV_DOWNLOAD_DIR and not nzb_name or 'manual' == pp_type:  # Scheduled Post Processing Active
            # Get at first all the subdir in the dir_name
            for path, dirs, files in ek.ek(os.walk, dir_name):
                break
        else:
            path, dirs = ek.ek(os.path.split, dir_name)  # Script Post Processing
            if None is not nzb_name and not nzb_name.endswith('.nzb') and os.path.isfile(
                    os.path.join(dir_name, nzb_name)):  # For single torrent file without directory
                dirs = []
                files = [os.path.join(dir_name, nzb_name)]
            else:
                dirs = [dirs]
                files = []

        return path, dirs, files

    # noinspection PyArgumentList
    def _process_failed(self, dir_name, nzb_name):
        """ Process a download that did not complete correctly """

        if sickbeard.USE_FAILED_DOWNLOADS:
            processor = None

            try:
                processor = failedProcessor.FailedProcessor(dir_name, nzb_name)
                self._set_process_success(processor.process())
                process_fail_message = ''
            except exceptions.FailedProcessingFailed, e:
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
def processDir(dir_name, nzb_name=None, process_method=None, force=False, force_replace=None, failed=False, type='auto', cleanup=False):
    # backward compatibility prevents the case of this function name from being updated to PEP8
    return ProcessTVShow().process_dir(dir_name, nzb_name, process_method, force, force_replace, failed, type, cleanup)
