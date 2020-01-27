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

import glob
import os
import re
import stat
import threading

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex

import sickbeard
from . import common, db, failed_history, helpers, history, logger, notifiers, show_name_helpers

from .anime import push_anidb_mylist
from .indexers.indexer_config import TVINFO_TVDB
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser

from _23 import decode_str
from six import iteritems, PY2, string_types
from sg_helpers import long_path

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Optional, Tuple, Union


class PostProcessor(object):
    """
    A class which will process a media file according to the post processing settings in the config.
    """

    EXISTS_LARGER = 1
    EXISTS_SAME = 2
    EXISTS_SMALLER = 3
    DOESNT_EXIST = 4

    IGNORED_FILESTRINGS = ['/.AppleDouble/', '.DS_Store']

    def __init__(self, file_path, nzb_name=None, process_method=None, force_replace=None,
                 use_trash=None, webhandler=None, show_obj=None):
        """
        Creates a new post processor with the given file path and optionally an NZB name.

        file_path: The path to the file to be processed
        nzb_name: The name of the NZB which resulted in this file being downloaded (optional)
        """
        # absolute path to the folder that is being processed
        self.folder_path = long_path(ek.ek(os.path.dirname, long_path(
            ek.ek(os.path.abspath, long_path(file_path)))))  # type: AnyStr

        # full path to file
        self.file_path = long_path(file_path)  # type: AnyStr

        # file name only
        self.file_name = ek.ek(os.path.basename, long_path(file_path))  # type: AnyStr

        # the name of the folder only
        self.folder_name = ek.ek(os.path.basename, self.folder_path)  # type: AnyStr

        # name of the NZB that resulted in this folder
        self.nzb_name = nzb_name  # type: AnyStr or None

        self.force_replace = force_replace  # type: None or bool

        self.use_trash = use_trash  # type: None or bool

        self.webhandler = webhandler

        self.show_obj = show_obj  # type: sickbeard.tv.TVShow

        self.in_history = False  # type: bool

        self.release_group = None  # type: None or AnyStr

        self.release_name = None  # type: None or AnyStr

        self.is_proper = False  # type: bool

        self.log = ''  # type: AnyStr

        self.process_method = process_method if process_method else sickbeard.PROCESS_METHOD

        self.anime_version = None  # anime equivalent of is_proper

        self.anidbEpisode = None

    def _log(self, message, level=logger.MESSAGE):
        """
        A wrapper for the internal logger which also keeps track of messages and saves them to a string for later.

        :param message: The string to log (unicode)
        :type message: AnyStr
        :param level: The log level to use (optional)
        :type level: int
        """
        logger_msg = re.sub(r'(?i)<br(?:[\s/]+)>\.*', '', message)
        logger_msg = re.sub('(?i)<a[^>]+>([^<]+)<[/]a>', r'\1', logger_msg)
        logger.log(u'%s' % logger_msg, level)
        self.log += message + '\n'

    def _check_for_existing_file(self, existing_file):
        """
        Checks if a file exists already and if it does whether it's bigger or smaller than
        the file we are post processing

        existing_file: The file to compare to

        Returns:
            DOESNT_EXIST if the file doesn't exist
            EXISTS_LARGER if the file exists and is larger than the file we are post processing
            EXISTS_SMALLER if the file exists and is smaller than the file we are post processing
            EXISTS_SAME if the file exists and is the same size as the file we are post processing
        """

        if not existing_file:
            self._log(u'There is no existing file', logger.DEBUG)
            return PostProcessor.DOESNT_EXIST

        # if the new file exists, return the appropriate code depending on the size
        if ek.ek(os.path.isfile, existing_file):
            new_file = u'New file %s<br />.. is ' % self.file_path
            if ek.ek(os.path.getsize, self.file_path) == ek.ek(os.path.getsize, existing_file):
                self._log(u'%sthe same size as %s' % (new_file, existing_file), logger.DEBUG)
                return PostProcessor.EXISTS_SAME
            elif ek.ek(os.path.getsize, self.file_path) < ek.ek(os.path.getsize, existing_file):
                self._log(u'%ssmaller than %s' % (new_file, existing_file), logger.DEBUG)
                return PostProcessor.EXISTS_LARGER
            else:
                self._log(u'%slarger than %s' % (new_file, existing_file), logger.DEBUG)
                return PostProcessor.EXISTS_SMALLER

        else:
            self._log(u'File doesn\'t exist %s' % existing_file,
                      logger.DEBUG)
            return PostProcessor.DOESNT_EXIST

    @staticmethod
    def list_associated_files(file_path, base_name_only=False, subtitles_only=False):
        """
        For a given file path searches for files with the same name but different extension
        and returns their absolute paths

        Returns: A list containing all files which are associated to the given file
        :param file_path: The file to check for associated files
        :type file_path: AnyStr
        :param base_name_only: False add extra '.' (conservative search) to file_path minus extension
        :type base_name_only: bool
        :param subtitles_only:
        :type subtitles_only: bool
        :return: list of associated files
        :rtype: List[AnyStr]
        """

        if not file_path:
            return []

        file_path_list = []

        tmp_base = base_name = file_path.rpartition('.')[0]

        if not base_name_only:
            tmp_base += '.'

        # don't strip it all and use cwd by accident
        if not tmp_base:
            return []

        # don't confuse glob with chars we didn't mean to use
        base_name = re.sub(r'[\[\]*?]', r'[\g<0>]', base_name)

        for meta_ext in ['', '-thumb', '.ext', '.ext.cover', '.metathumb']:
            for associated_file_path in ek.ek(glob.glob, '%s%s.*' % (base_name, meta_ext)):
                # only add associated to list
                if associated_file_path == file_path:
                    continue
                # only list it if the only non-shared part is the extension or if it is a subtitle
                if subtitles_only and not associated_file_path[len(associated_file_path) - 3:] \
                        in common.subtitleExtensions:
                    continue

                # Exclude .rar files from associated list
                if re.search(r'(^.+\.(rar|r\d+)$)', associated_file_path):
                    continue

                if ek.ek(os.path.isfile, associated_file_path):
                    file_path_list.append(associated_file_path)

        return file_path_list

    def _delete(self, file_path, associated_files=False):
        """
        Deletes the file and optionally all associated files.

        :param file_path: The file to delete
        :type file_path: AnyStr
        :param associated_files: True to delete all files which differ only by extension, False to leave them
        :type associated_files: bool
        """

        if not file_path:
            return

        # figure out which files we want to delete
        file_list = [file_path]
        if associated_files:
            file_list = file_list + self.list_associated_files(file_path)

        if not file_list:
            self._log(u'Not deleting anything because there are no files associated with %s' % file_path, logger.DEBUG)
            return

        # delete the file and any other files which we want to delete
        for cur_file in file_list:
            if ek.ek(os.path.isfile, cur_file):
                # check first the read-only attribute
                file_attribute = ek.ek(os.stat, cur_file)[0]
                if not file_attribute & stat.S_IWRITE:
                    # File is read-only, so make it writeable
                    try:
                        ek.ek(os.chmod, cur_file, stat.S_IWRITE)
                        self._log(u'Changed read only permissions to writeable to delete file %s'
                                  % cur_file, logger.DEBUG)
                    except (BaseException, Exception):
                        self._log(u'Cannot change permissions to writeable to delete file: %s'
                                  % cur_file, logger.WARNING)

                removal_type = helpers.remove_file(cur_file, log_level=logger.DEBUG)

                if True is not ek.ek(os.path.isfile, cur_file):
                    self._log(u'%s file %s' % (removal_type, cur_file), logger.DEBUG)

                # do the library update for synoindex
                notifiers.NotifierFactory().get('SYNOINDEX').deleteFile(cur_file)

    def _combined_file_operation(self, file_path, new_path, new_base_name, associated_files=False, action=None,
                                 subtitles=False, action_tmpl=None):
        """
        Performs a generic operation (move or copy) on a file. Can rename the file as well as change its location,
        and optionally move associated files too.

        :param file_path: The full path of the media file to act on
        :type file_path: AnyStr
        :param new_path: Destination path where we want to move/copy the file to
        :type new_path: AnyStr
        :param new_base_name: The base filename (no extension) to use during the copy. Use None to keep the same name.
        :type new_base_name: AnyStr
        :param associated_files: Boolean, whether we should copy similarly-named files too
        :type associated_files: bool
        :param action: function that takes an old path and new path and does an operation with them (move/copy)
        :type action:
        :param subtitles:
        :type subtitles: bool
        :param action_tmpl:
        :type action_tmpl:
        """

        if not action:
            self._log(u'Must provide an action for the combined file operation', logger.ERROR)
            return

        file_list = [file_path]
        if associated_files:
            file_list = file_list + self.list_associated_files(file_path)
        elif subtitles:
            file_list = file_list + self.list_associated_files(file_path, subtitles_only=True)

        if not file_list:
            self._log(u'Not moving anything because there are no files associated with %s' % file_path, logger.DEBUG)
            return

        # create base name with file_path (media_file without .extension)
        old_base_name = file_path.rpartition('.')[0]
        old_base_name_length = len(old_base_name)

        # deal with all files
        for cur_file_path in file_list:

            cur_file_name = ek.ek(os.path.basename, cur_file_path)

            # get the extension without .
            cur_extension = cur_file_path[old_base_name_length + 1:]

            # replace .nfo with .nfo-orig to avoid conflicts
            if 'nfo' == cur_extension and True is sickbeard.NFO_RENAME:
                cur_extension = 'nfo-orig'

            # check if file have subtitles language
            if ek.ek(os.path.splitext, cur_extension)[1][1:] in common.subtitleExtensions:
                cur_lang = ek.ek(os.path.splitext, cur_extension)[0]
                if cur_lang in sickbeard.SUBTITLES_LANGUAGES:
                    cur_extension = cur_lang + ek.ek(os.path.splitext, cur_extension)[1]

            # If new base name then convert name
            if new_base_name:
                new_file_name = new_base_name + '.' + cur_extension
            # if we're not renaming we still want to change extensions sometimes
            else:
                new_file_name = helpers.replace_extension(cur_file_name, cur_extension)

            if sickbeard.SUBTITLES_DIR and cur_extension in common.subtitleExtensions:
                subs_new_path = ek.ek(os.path.join, new_path, sickbeard.SUBTITLES_DIR)
                dir_exists = helpers.make_dir(subs_new_path)
                if not dir_exists:
                    logger.log(u'Unable to create subtitles folder ' + subs_new_path, logger.ERROR)
                else:
                    helpers.chmod_as_parent(subs_new_path)
                new_file_path = ek.ek(os.path.join, subs_new_path, new_file_name)
            else:
                new_file_path = ek.ek(os.path.join, new_path, new_file_name)

            if None is action_tmpl:
                action(cur_file_path, new_file_path)
            else:
                action(cur_file_path, new_file_path, action_tmpl)

    def _move(self, file_path, new_path, new_base_name, associated_files=False, subtitles=False, action_tmpl=None):
        """
        :param file_path: The full path of the media file to move
        :type file_path: AnyStr
        :param new_path: Destination path where we want to move the file to
        :type new_path: AnyStr
        :param new_base_name: The base filename (no extension) to use during the move. Use None to keep the same name.
        :type new_base_name: AnyStr
        :param associated_files: Boolean, whether we should move similarly-named files too
        :type associated_files: bool
        :param subtitles:
        :type subtitles: bool
        :param action_tmpl:
        :type action_tmpl:
        """

        def _int_move(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.move_file(cur_file_path, new_file_path)
                helpers.chmod_as_parent(new_file_path)
                self._log(u'Moved file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to move file %s<br />.. %s'
                          % (success_tmpl % (cur_file_path, new_file_path), ex(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_move,
                                      subtitles=subtitles, action_tmpl=action_tmpl)

    def _copy(self, file_path, new_path, new_base_name, associated_files=False, subtitles=False, action_tmpl=None):
        """
        :param file_path: The full path of the media file to copy
        :type file_path: AnyStr
        :param new_path: Destination path where we want to copy the file to
        :type new_path: AnyStr
        :param new_base_name: The base filename (no extension) to use during the copy. Use None to keep the same name.
        :type new_base_name: AnyStr
        :param associated_files: Boolean, whether we should copy similarly-named files too
        :type associated_files: bool
        :param subtitles:
        :type subtitles: bool
        :param action_tmpl:
        :type action_tmpl:
        """

        def _int_copy(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.copy_file(cur_file_path, new_file_path)
                helpers.chmod_as_parent(new_file_path)
                self._log(u'Copied file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to copy %s<br />.. %s'
                          % (success_tmpl % (cur_file_path, new_file_path), ex(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_copy,
                                      subtitles=subtitles, action_tmpl=action_tmpl)

    def _hardlink(self, file_path, new_path, new_base_name, associated_files=False, action_tmpl=None):
        """
        :param file_path: The full path of the media file to move
        :type file_path: AnyStr
        :param new_path: Destination path where we want to create a hard linked file
        :type new_path: AnyStr
        :param new_base_name: The base filename (no extension) to use during the link. Use None to keep the same name.
        :type new_base_name: AnyStr
        :param associated_files: Boolean, whether we should move similarly-named files too
        :type associated_files: bool
        :param action_tmpl:
        :type action_tmpl:
        """

        def _int_hard_link(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.hardlink_file(cur_file_path, new_file_path)
                helpers.chmod_as_parent(new_file_path)
                self._log(u'Hard linked file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to link file %s<br />.. %s'
                          % (success_tmpl % (cur_file_path, new_file_path), ex(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_hard_link,
                                      action_tmpl=action_tmpl)

    def _move_and_symlink(self, file_path, new_path, new_base_name, associated_files=False, action_tmpl=None):
        """
        :param file_path: The full path of the media file to move
        :type file_path: AnyStr
        :param new_path: Destination path where we want to move the file to create a symbolic link to
        :type new_path: AnyStr
        :param new_base_name: The base filename (no extension) to use during the link. Use None to keep the same name.
        :type new_base_name: AnyStr
        :param associated_files: Boolean, whether we should move similarly-named files too
        :type associated_files: bool
        :param action_tmpl:
        :type action_tmpl:
        """

        def _int_move_and_sym_link(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.move_and_symlink_file(cur_file_path, new_file_path)
                helpers.chmod_as_parent(new_file_path)
                self._log(u'Moved then symbolic linked file from' + (success_tmpl % (cur_file_path, new_file_path)),
                          logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to link file %s<br />.. %s'
                          % (success_tmpl % (cur_file_path, new_file_path), ex(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_move_and_sym_link,
                                      action_tmpl=action_tmpl)

    def _history_lookup(self):
        # type: (...) -> Union[Tuple[None, None, List, None], Tuple[sickbeard.tv.TVShow, int, List[int], int]]
        """
        Look up the NZB name in the history and see if it contains a record for self.nzb_name

        :return: (show_obj, season, [], quality) tuple.
        :rtype: Tuple[sickbeard.tv.TVShow, int, List, int]
        """

        to_return = (None, None, [], None)
        self.in_history = False

        # if we don't have either of these then there's nothing to use to search the history for anyway
        if not self.nzb_name and not self.file_name and not self.folder_name:
            return to_return

        # make a list of possible names to use in the search
        names = []
        if self.nzb_name:
            names.append(self.nzb_name)
            if '.' in self.nzb_name:
                names.append(self.nzb_name.rpartition('.')[0])
        if self.file_name:
            names.append(self.file_name)
            if '.' in self.file_name:
                names.append(self.file_name.rpartition('.')[0])
        if self.folder_name:
            names.append(self.folder_name)

        my_db = db.DBConnection()

        # search the database for a possible match and return immediately if we find one
        for curName in names:
            # The underscore character ( _ ) represents a single character to match a pattern from a word or string
            search_name = re.sub(r'[ .\-]', '_', curName)
            # noinspection SqlResolve
            sql_result = my_db.select('SELECT * FROM history WHERE (%s) AND resource LIKE ? ORDER BY date DESC'
                                      ' LIMIT 1' % ' OR '.join(['action LIKE "%%%02d"' % x for x in
                                                                common.Quality.SNATCHED_ANY]),
                                      [search_name])

            if 0 == len(sql_result):
                continue

            tvid = int(sql_result[0]['indexer'])
            prodid = int(sql_result[0]['showid'])
            season_number = int(sql_result[0]['season'])
            episode_numbers = []
            quality = int(sql_result[0]['quality'])
            self.anime_version = int(sql_result[0]['version'])
            show_obj = helpers.find_show_by_id({tvid: prodid})

            if show_obj:
                try:
                    parsed_show, season, episodes, quality = \
                        self._analyze_name(sql_result[0]['resource'], show_obj=show_obj)
                    # validate that the history ep number is in parsed result
                    if parsed_show and season and season_number == season and \
                            episodes and int(sql_result[0]['episode']) in episodes:
                        episode_numbers = episodes
                except (BaseException, Exception):
                    continue

            if common.Quality.UNKNOWN == quality:
                quality = None

            self.in_history = True
            to_return = (show_obj, season_number, episode_numbers, quality)
            if not show_obj:
                self._log(u'Unknown show, check availability on ShowList page', logger.DEBUG)
                break
            self._log(u'Found a match in history for %s' % show_obj.name, logger.DEBUG)
            break

        return to_return

    def _analyze_name(self,
                      name,  # type: AnyStr
                      resource=True,  # type: bool
                      show_obj=None,  # type: Optional[sickbeard.tv.TVShow]
                      rel_grp=None  # type: Optional[AnyStr]
                      ):
        # type: (...) -> Union[Tuple[None, None, List, None], Tuple[sickbeard.tv.TVShow, int, List[int], int]]
        """
        Takes a name and tries to figure out a show, season, and episode from it.

        Returns a (show_obj, season_number, [episode_numbers], quality) tuple. Episodes may be [], the others, None.
        if none were found.
        :param name: A string which we want to analyze to determine show info from (unicode)
        :type name: AnyStr
        :param resource:
        :type resource: bool
        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param rel_grp: release group
        :type rel_grp: None or AnyStr
        :return: tuple of show_object, season number, list of episode numbers, quality or None, None, [], None
        :rtype: Tuple[None, None, List, None] or Tuple[sickbeard.tv.TVShow, int, List[int], int]
        """

        logger.log(u'Analyzing name ' + repr(name))

        to_return = (None, None, [], None)

        if not name:
            return to_return

        # parse the name to break it into show name, season, and episode
        np = NameParser(resource, try_scene_exceptions=True, convert=True, show_obj=self.show_obj or show_obj)
        parse_result = np.parse(name)
        self._log(u'Parsed %s<br />.. from %s'
                  % (decode_str(str(parse_result), errors='xmlcharrefreplace'), name), logger.DEBUG)

        if parse_result.is_air_by_date and (None is parse_result.season_number or not parse_result.episode_numbers):
            season_number = -1
            episode_numbers = [parse_result.air_date]
        else:
            season_number = parse_result.season_number
            episode_numbers = parse_result.episode_numbers

        # show object
        show_obj = parse_result.show_obj
        if show_obj and rel_grp and not parse_result.release_group:
            parse_result.release_group = rel_grp
        to_return = (show_obj, season_number, episode_numbers, parse_result.quality)

        self._finalize(parse_result)
        return to_return

    def _finalize(self, parse_result):
        """

        :param parse_result: parse result
        :type parse_result: sickbeard.parser.ParseResult
        """
        self.release_group = parse_result.release_group

        # remember whether it's a proper
        if parse_result.extra_info_no_name():
            self.is_proper = 0 < common.Quality.get_proper_level(parse_result.extra_info_no_name(),
                                                                 parse_result.version,
                                                                 parse_result.is_anime)

        # if the result is complete then set release name
        if parse_result.series_name and\
                ((None is not parse_result.season_number and parse_result.episode_numbers) or parse_result.air_date)\
                and parse_result.release_group:

            if not self.release_name:
                self.release_name = helpers.remove_extension(ek.ek(os.path.basename, parse_result.original_name))

        else:
            logger.log(u'Parse result not sufficient (all following have to be set). will not save release name',
                       logger.DEBUG)
            logger.log(u'Parse result(series_name): ' + str(parse_result.series_name), logger.DEBUG)
            logger.log(u'Parse result(season_number): ' + str(parse_result.season_number), logger.DEBUG)
            logger.log(u'Parse result(episode_numbers): ' + str(parse_result.episode_numbers), logger.DEBUG)
            logger.log(u' or Parse result(air_date): ' + str(parse_result.air_date), logger.DEBUG)
            logger.log(u'Parse result(release_group): ' + str(parse_result.release_group), logger.DEBUG)

    def _find_info(self):
        """
        For a given file try to find the show_obj, season, and episode.
        :return: tuple of tv show object, season number, list of episode numbers, quality or None, None, [], None
        :rtype: Tuple[sickbeard.tv.TVShow, int, List[int], int] or Tuple[None, None, List, None]
        """

        show_obj = season_number = quality = rel_grp = None
        episode_numbers = []

        # try to look up the nzb in history
        try_list = [self._history_lookup,

                    # try to analyze the nzb name
                    lambda: self._analyze_name(self.nzb_name),

                    # try to analyze the file name
                    lambda: self._analyze_name(self.file_name),

                    # try to analyze the dir name
                    lambda: self._analyze_name(self.folder_name),

                    # try to analyze the file + dir names together
                    lambda: self._analyze_name(self.file_path),

                    # try to analyze the dir + file name together as one name
                    lambda: self._analyze_name(self.folder_name + u' ' + self.file_name),

                    # try to analyze file name with previously parsed show_obj
                    lambda: self._analyze_name(self.file_name, show_obj=show_obj, rel_grp=rel_grp)]

        # attempt every possible method to get our info
        for cur_try in try_list:

            try:
                (try_show_obj, try_season, try_episodes, try_quality) = cur_try()
            except (InvalidNameException, InvalidShowException) as e:
                logger.log(u'Unable to parse, skipping: ' + ex(e), logger.DEBUG)
                continue

            if not try_show_obj:
                continue

            # if we already did a successful history lookup then keep that show object
            show_obj = try_show_obj
            if self.release_group:
                rel_grp = self.release_group

            if try_quality and not (self.in_history and quality):
                quality = try_quality

            if None is not try_season:
                season_number = try_season

            if try_episodes:
                episode_numbers = try_episodes

            # for air-by-date shows we need to look up the season/episode from database
            if -1 == season_number and show_obj and episode_numbers:
                self._log(u'Looks like this is an air-by-date or sports show,'
                          u' attempting to convert the date to season/episode', logger.DEBUG)
                airdate = episode_numbers[0].toordinal()
                my_db = db.DBConnection()
                sql_result = my_db.select(
                    'SELECT season, episode'
                    ' FROM tv_episodes'
                    ' WHERE indexer = ? AND showid = ? AND airdate = ?',
                    [show_obj.tvid, show_obj.prodid, airdate])

                if sql_result:
                    season_number = int(sql_result[0][0])
                    episode_numbers = [int(sql_result[0][1])]
                else:
                    self._log(u'Unable to find episode with date %s for show %s, skipping' %
                              (episode_numbers[0], show_obj.tvid_prodid), logger.DEBUG)
                    # don't leave dates in the episode list if we can't convert them to real episode numbers
                    episode_numbers = []
                    continue

            # if there's no season then we can hopefully just use 1 automatically
            elif None is season_number and show_obj:
                my_db = db.DBConnection()
                num_seasons_sql_result = my_db.select(
                    'SELECT COUNT(DISTINCT season) AS numseasons'
                    ' FROM tv_episodes'
                    ' WHERE indexer = ? AND showid = ? AND season != 0',
                    [show_obj.tvid, show_obj.prodid])
                if 1 == int(num_seasons_sql_result[0][0]) and None is season_number:
                    self._log(
                        u'No season number found, but this show appears to only have 1 season,'
                        u' setting season number to 1...', logger.DEBUG)
                    season_number = 1

            if show_obj and season_number and episode_numbers:
                break

        return show_obj, season_number, episode_numbers, quality

    def _get_ep_obj(self, show_obj, season_number, episode_numbers):
        """
        Retrieve the TVEpisode object requested.

        show_obj: The TVShow object belonging to the show we want to process
        season_number: The season of the episode (int)
        episode_numbers: A list of episode numbers to find (list of ints)

        If the episode(s) can be found then a TVEpisode object with the correct related eps will
        be instantiated and returned. If the episode can't be found then None will be returned.
        
        :param show_obj:
        :type show_obj: sickbeard.tv.TVShow
        :param season_number:
        :type season_number: int
        :param episode_numbers:
        :type episode_numbers: int list
        :return: TVEpisode
        :rtype: sickbeard.tv.TVEpisode
        """

        root_ep_obj = None
        for cur_episode_number in episode_numbers:
            cur_episode_number = int(cur_episode_number)

            self._log(u'Retrieving episode object for %sx%s' % (season_number, cur_episode_number), logger.DEBUG)

            # now that we've figured out which episode this file is just load it manually
            try:
                ep_obj = show_obj.get_episode(season_number, cur_episode_number)
            except exceptions_helper.EpisodeNotFoundException as e:
                self._log(u'Unable to create episode: ' + ex(e), logger.DEBUG)
                raise exceptions_helper.PostProcessingFailed()

            # associate all the episodes together under a single root episode
            if None is root_ep_obj:
                root_ep_obj = ep_obj
                root_ep_obj.related_ep_obj = []
            elif ep_obj not in root_ep_obj.related_ep_obj:
                root_ep_obj.related_ep_obj.append(ep_obj)

        return root_ep_obj

    def _get_quality(self, ep_obj):
        """
        Determines the quality of the file that is being post processed, first by checking if it is directly
        available in the TVEpisode's status or otherwise by parsing through the data available.

        :param ep_obj: The TVEpisode object related to the file we are post processing
        :type ep_obj: sickbeard.tv.TVEpisode
        :return: A quality value found in common.Quality
        :rtype: int
        """

        # if there is a quality available in the status then we don't need to bother guessing from the filename
        if ep_obj.status in common.Quality.SNATCHED_ANY:
            old_status, ep_quality = common.Quality.splitCompositeStatus(ep_obj.status)
            if common.Quality.UNKNOWN != ep_quality:
                self._log(
                    u'Using "%s" quality from the old status' % common.Quality.qualityStrings[ep_quality],
                    logger.DEBUG)
                return ep_quality

        # search all possible names for our new quality, in case the file or dir doesn't have it
        # nzb name is the most reliable if it exists, followed by folder name and lastly file name
        for thing, cur_name in iteritems({'nzb name': self.nzb_name,
                                          'folder name': self.folder_name,
                                          'file name': self.file_name}):

            # some stuff might be None at this point still
            if not cur_name:
                continue

            ep_quality = common.Quality.nameQuality(cur_name, ep_obj.show_obj.is_anime)
            quality_log = u' "%s" quality parsed from the %s %s'\
                          % (common.Quality.qualityStrings[ep_quality], thing, cur_name)

            # if we find a good one then use it
            if common.Quality.UNKNOWN != ep_quality:
                self._log(u'Using' + quality_log, logger.DEBUG)
                return ep_quality
            else:
                self._log(u'Found' + quality_log, logger.DEBUG)

        ep_quality = common.Quality.fileQuality(self.file_path)
        if common.Quality.UNKNOWN != ep_quality:
            self._log(u'Using "%s" quality parsed from the metadata file content of %s'
                      % (common.Quality.qualityStrings[ep_quality], self.file_name), logger.DEBUG)
            return ep_quality

        # Try guessing quality from the file name
        ep_quality = common.Quality.assumeQuality(self.file_name)
        self._log(u'Using guessed "%s" quality from the file name %s'
                  % (common.Quality.qualityStrings[ep_quality], self.file_name), logger.DEBUG)

        return ep_quality

    def _execute_extra_scripts(self, script_name, ep_obj, new_call=False):
        """

        :param script_name: script name
        :type script_name: AnyStr
        :param ep_obj: episode object
        :type ep_obj: sickbeard.tv.TVEpisode
        :param new_call:
        :type new_call: bool
        """
        # generate a safe command line string to execute the script and provide all the parameters
        if not new_call and TVINFO_TVDB != ep_obj.show_obj.tvid:
            self._log('Can\'t execute old script [%s] for show from new TV info source: %s' %
                      (script_name, sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name), logger.ERROR)
            return

        try:
            script_cmd = [piece for piece in re.split("( |\\\".*?\\\"|'.*?')", script_name) if piece.strip()]
            script_cmd[0] = ek.ek(os.path.abspath, script_cmd[0])
            self._log(u'Absolute path to script: ' + script_cmd[0], logger.DEBUG)

            if PY2:
                script_cmd += [ep_obj.location.encode(sickbeard.SYS_ENCODING),
                               self.file_path.encode(sickbeard.SYS_ENCODING)
                               ]
            else:
                script_cmd += [ep_obj.location, self.file_path]

            script_cmd += ([], [str(ep_obj.show_obj.tvid)])[new_call] + [
                str(ep_obj.show_obj.prodid),
                str(ep_obj.season),
                str(ep_obj.episode),
                str(ep_obj.airdate)]

            self._log(u'Executing command ' + str(script_cmd))
        except (BaseException, Exception) as e:
            self._log('Error creating extra script command: %s' % ex(e), logger.ERROR)
            return

        try:
            # run the command and capture output
            output, err, exit_status = helpers.cmdline_runner(script_cmd)
            self._log('Script result: %s' % output, logger.DEBUG)

        except OSError as e:
            self._log(u'Unable to run extra_script: ' + ex(e), logger.ERROR)

        except (BaseException, Exception) as e:
            self._log(u'Unable to run extra_script: ' + ex(e), logger.ERROR)

    def _run_extra_scripts(self, ep_obj):
        """
        Executes any extra scripts defined in the config.

        :param ep_obj: The object to use when calling the extra script
        :type ep_obj: sickbeard.tv.TVEpisode
        """
        for curScriptName in sickbeard.EXTRA_SCRIPTS:
            self._execute_extra_scripts(curScriptName, ep_obj)

        for curScriptName in sickbeard.SG_EXTRA_SCRIPTS:
            self._execute_extra_scripts(curScriptName, ep_obj, new_call=True)

    def _safe_replace(self, ep_obj, new_ep_quality):
        """
        Determines if the new episode can safely replace old episode.
        Episodes which are expected (snatched) or larger than the existing episode are priority, others are not.

        :param ep_obj: The TVEpisode object in question
        :type ep_obj: sickbeard.tv.TVEpisode
        :param new_ep_quality: The quality of the episode that is being processed
        :type new_ep_quality: int
        :return: True if the episode can safely replace old episode, False otherwise.
        :rtype: bool
        """

        # if SickGear snatched this then assume it's safe
        if ep_obj.status in common.Quality.SNATCHED_ANY:
            self._log(u'SickGear snatched this episode, marking it safe to replace', logger.DEBUG)
            return True

        old_ep_status, old_ep_quality = common.Quality.splitCompositeStatus(ep_obj.status)

        # if old episode is not downloaded/archived then it's safe
        if common.DOWNLOADED != old_ep_status and common.ARCHIVED != old_ep_status:
            self._log(u'Existing episode status is not downloaded/archived, marking it safe to replace', logger.DEBUG)
            return True

        if common.ARCHIVED == old_ep_status and common.Quality.NONE == old_ep_quality:
            self._log(u'Marking it unsafe to replace because the existing episode status is archived', logger.DEBUG)
            return False

        # Status downloaded. Quality/ size checks

        # if manual post process option is set to force_replace then it's safe
        if self.force_replace:
            self._log(u'Force replace existing episode option is enabled, marking it safe to replace', logger.DEBUG)
            return True

        # if the file processed is higher quality than the existing episode then it's safe
        if new_ep_quality > old_ep_quality:
            if common.Quality.UNKNOWN != new_ep_quality:
                self._log(u'Existing episode status is not snatched but the episode to process appears to be better'
                          u' quality than existing episode, marking it safe to replace', logger.DEBUG)
                return True

            else:
                self._log(u'Marking it unsafe to replace because an existing episode exists in the database and'
                          u' the episode to process has unknown quality', logger.DEBUG)
                return False

        # if there's an existing downloaded file with same quality, check filesize to decide
        if new_ep_quality == old_ep_quality:
            np = NameParser(show_obj=self.show_obj)
            cur_proper_level = 0
            try:
                pr = np.parse(ep_obj.release_name)
                cur_proper_level = common.Quality.get_proper_level(pr.extra_info_no_name(), pr.version, pr.is_anime)
            except (BaseException, Exception):
                pass
            new_name = (('', self.file_name)[isinstance(self.file_name, string_types)], self.nzb_name)[isinstance(
                self.nzb_name, string_types)]
            if new_name:
                try:
                    npr = np.parse(new_name)
                except (BaseException, Exception):
                    npr = None
                if npr:
                    is_repack, new_proper_level = common.Quality.get_proper_level(npr.extra_info_no_name(), npr.version,
                                                                                  npr.is_anime, check_is_repack=True)
                    if new_proper_level > cur_proper_level and \
                            (not is_repack or npr.release_group == ep_obj.release_group):
                        self._log(u'Proper or repack with same quality, marking it safe to replace', logger.DEBUG)
                        return True

            self._log(u'An episode exists in the database with the same quality as the episode to process',
                      logger.DEBUG)

            existing_file_status = self._check_for_existing_file(ep_obj.location)

            # check for an existing file
            if PostProcessor.DOESNT_EXIST == existing_file_status:
                if not ek.ek(os.path.isdir, ep_obj.show_obj.location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
                    # File and show location does not exist, marking it unsafe to replace
                    self._log(u'.. marking it unsafe to replace because show location does not exist', logger.DEBUG)
                    return False
                else:
                    # File does not exist, marking it safe to replace
                    self._log(u'.. there is no file to replace, marking it safe to continue', logger.DEBUG)
                    return True

            self._log(u'Checking size of existing file ' + ep_obj.location, logger.DEBUG)

            if PostProcessor.EXISTS_SMALLER == existing_file_status:
                # File exists and new file is larger, marking it safe to replace
                self._log(u'.. the existing smaller file will be replaced', logger.DEBUG)
                return True

            elif PostProcessor.EXISTS_LARGER == existing_file_status:
                # File exists and new file is smaller, marking it unsafe to replace
                self._log(u'.. marking it unsafe to replace the existing larger file', logger.DEBUG)
                return False

            elif PostProcessor.EXISTS_SAME == existing_file_status:
                # File exists and new file is same size, marking it unsafe to replace
                self._log(u'.. marking it unsafe to replace the existing same size file', logger.DEBUG)
                return False

            else:
                self._log(u'Unknown file status for: %s This should never happen, please log this as a bug.'
                          % ep_obj.location, logger.ERROR)
                return False

        # if there's an existing file with better quality
        if old_ep_quality > new_ep_quality and old_ep_quality != common.Quality.UNKNOWN:
            # Episode already exists in database and processed episode has lower quality, marking it unsafe to replace
            self._log(u'Marking it unsafe to replace the episode that already exists in database with a file of lower'
                      u' quality', logger.DEBUG)
            return False

        if self.in_history:
            self._log(u'SickGear snatched this episode, marking it safe to replace', logger.DEBUG)
            return True

        # None of the conditions were met, marking it unsafe to replace
        self._log(u'Marking it unsafe to replace because no positive condition is met, you may force replace but it'
                  u' would be better to examine the files', logger.DEBUG)
        return False

    def process(self):
        """
        Post-process a given file
        :return:
        :rtype: bool
        """

        self._log(u'Processing... %s%s' % (ek.ek(os.path.relpath, self.file_path, self.folder_path),
                                           (u'<br />.. from nzb %s' % self.nzb_name, u'')[None is self.nzb_name]))

        if ek.ek(os.path.isdir, self.file_path):
            self._log(u'Expecting file %s<br />.. is actually a directory, skipping' % self.file_path)
            return False

        for ignore_file in self.IGNORED_FILESTRINGS:
            if ignore_file in self.file_path:
                self._log(u'File %s<br />.. is ignored type, skipping' % self.file_path)
                return False

        # reset per-file stuff
        self.in_history = False
        self.anidbEpisode = None

        # try to find the file info
        (show_obj, season_number, episode_numbers, quality) = self._find_info()

        # if we don't have it then give up
        if not show_obj:
            self._log(u'Must add show to SickGear before trying to post process an episode', logger.WARNING)
            raise exceptions_helper.PostProcessingFailed()
        elif None is season_number or not episode_numbers:
            self._log(u'Quitting this post process, could not determine what episode this is', logger.DEBUG)
            return False

        # retrieve/create the corresponding TVEpisode objects
        ep_obj = self._get_ep_obj(show_obj, season_number, episode_numbers)

        # get the quality of the episode we're processing
        if quality in (None, common.Quality.UNKNOWN):
            new_ep_quality = self._get_quality(ep_obj)
        else:
            new_ep_quality = quality
            self._log(u'Using "%s" quality' % common.Quality.qualityStrings[new_ep_quality], logger.DEBUG)

        # see if it's safe to replace existing episode (is download snatched, PROPER, better quality)
        if not self._safe_replace(ep_obj, new_ep_quality):
            # if it's not safe to replace, stop here
            self._log(u'Quitting this post process', logger.DEBUG)
            return False

        # delete the existing file (and company)
        for cur_ep_obj in [ep_obj] + ep_obj.related_ep_obj:
            try:
                self._delete(cur_ep_obj.location, associated_files=True)

                # clean up any left over folders
                if cur_ep_obj.location:
                    helpers.delete_empty_folders(ek.ek(os.path.dirname, cur_ep_obj.location),
                                                 keep_dir=ep_obj.show_obj.location)
            except (OSError, IOError):
                raise exceptions_helper.PostProcessingFailed(u'Unable to delete existing files')

            # set the status of the episodes
            # for cur_ep_obj in [ep_obj] + ep_obj.related_ep_obj:
            #    cur_ep_obj.status = common.Quality.compositeStatus(common.SNATCHED, new_ep_quality)

        # if the show directory doesn't exist then make it if allowed
        if not ek.ek(os.path.isdir, ep_obj.show_obj.location) and sickbeard.CREATE_MISSING_SHOW_DIRS:
            self._log(u'Show directory does not exist, creating it', logger.DEBUG)
            try:
                ek.ek(os.mkdir, ep_obj.show_obj.location)
                # do the library update for synoindex
                notifiers.NotifierFactory().get('SYNOINDEX').addFolder(ep_obj.show_obj.location)
            except (OSError, IOError):
                raise exceptions_helper.PostProcessingFailed(u'Unable to create show directory: '
                                                             + ep_obj.show_obj.location)

            # get metadata for the show (but not episode because it hasn't been fully processed)
            ep_obj.show_obj.write_metadata(True)

        # if we're processing an episode of type anime, get the anime version
        anime_version = (-1, self.anime_version)[ep_obj.show_obj.is_anime and None is not self.anime_version]

        # update the ep info before we rename so the quality & release name go into the name properly
        sql_l = []
        for cur_ep_obj in [ep_obj] + ep_obj.related_ep_obj:
            with cur_ep_obj.lock:

                if self.release_name:
                    self._log(u'Found release name ' + self.release_name, logger.DEBUG)

                cur_ep_obj.release_name = self.release_name or ''

                any_qualities, best_qualities = common.Quality.splitQuality(cur_ep_obj.show_obj.quality)
                cur_status, cur_quality = common.Quality.splitCompositeStatus(cur_ep_obj.status)

                cur_ep_obj.status = common.Quality.compositeStatus(
                    **({'status': common.DOWNLOADED, 'quality': new_ep_quality},
                       {'status': common.ARCHIVED, 'quality': new_ep_quality})
                    [ep_obj.status in common.Quality.SNATCHED_BEST or
                     (cur_ep_obj.show_obj.upgrade_once and
                      (new_ep_quality in best_qualities and
                       (new_ep_quality not in any_qualities or (cur_status in
                        (common.SNATCHED, common.SNATCHED_BEST, common.SNATCHED_PROPER, common.DOWNLOADED) and
                                                                cur_quality != new_ep_quality))))])

                cur_ep_obj.release_group = self.release_group or ''

                cur_ep_obj.is_proper = self.is_proper

                cur_ep_obj.version = anime_version

                cur_ep_obj.subtitles = []

                cur_ep_obj.subtitles_searchcount = 0

                cur_ep_obj.subtitles_lastsearch = '0001-01-01 00:00:00'

                sql = cur_ep_obj.get_sql()
                if None is not sql:
                    sql_l.append(sql)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # Just want to keep this consistent for failed handling right now
        release_name = show_name_helpers.determineReleaseName(self.folder_path, self.nzb_name)
        if None is release_name:
            self._log(u'No snatched release found in history', logger.WARNING)
        elif sickbeard.USE_FAILED_DOWNLOADS:
            failed_history.remove_failed(release_name)

        # find the destination folder
        try:
            proper_path = ep_obj.proper_path()
            proper_absolute_path = ek.ek(os.path.join, ep_obj.show_obj.location, proper_path)
            dest_path = ek.ek(os.path.dirname, proper_absolute_path)

        except exceptions_helper.ShowDirNotFoundException:
            raise exceptions_helper.PostProcessingFailed(
                u'Unable to post process an episode because the show dir does not exist, quitting')

        self._log(u'Destination folder for this episode is ' + dest_path, logger.DEBUG)

        # create any folders we need
        if not helpers.make_dirs(dest_path):
            raise exceptions_helper.PostProcessingFailed(u'Unable to create destination folder: ' + dest_path)

        # figure out the base name of the resulting episode file
        if sickbeard.RENAME_EPISODES:
            new_base_name = ek.ek(os.path.basename, proper_path)
            new_file_name = new_base_name + '.' + self.file_name.rpartition('.')[-1]

        else:
            # if we're not renaming then there's no new base name, we'll just use the existing name
            new_base_name = None
            new_file_name = self.file_name

        # add to anidb
        if sickbeard.ANIDB_USE_MYLIST and ep_obj.show_obj.is_anime:
            self._add_to_anidb_mylist(self.file_path)

        keepalive = keepalive_stop = None
        if self.webhandler:
            def keep_alive(webh, stop_event):
                if not PY2:
                    import asyncio
                    asyncio.set_event_loop(asyncio.new_event_loop())
                while not stop_event.is_set():
                    stop_event.wait(60)
                    webh('.')
                webh(u'\n')

            keepalive_stop = threading.Event()
            keepalive = threading.Thread(target=keep_alive,  args=(self.webhandler, keepalive_stop))

        try:
            # move the episode and associated files to the show dir
            args_link = {'file_path': self.file_path, 'new_path': dest_path,
                         'new_base_name': new_base_name,
                         'associated_files': sickbeard.MOVE_ASSOCIATED_FILES}
            args_cpmv = {'subtitles': sickbeard.USE_SUBTITLES and ep_obj.show_obj.subtitles,
                         'action_tmpl': u' %s<br />.. to %s'}
            args_cpmv.update(args_link)
            if self.webhandler:
                self.webhandler('Processing method is "%s"' % self.process_method)
                keepalive.start()
            if 'copy' == self.process_method:
                self._copy(**args_cpmv)
            elif 'move' == self.process_method:
                self._move(**args_cpmv)
            elif 'hardlink' == self.process_method:
                self._hardlink(**args_link)
            elif 'symlink' == self.process_method:
                self._move_and_symlink(**args_link)
            else:
                logger.log(u'Unknown process method: ' + str(self.process_method), logger.ERROR)
                raise exceptions_helper.PostProcessingFailed(u'Unable to move the files to the new location')
        except (OSError, IOError):
            raise exceptions_helper.PostProcessingFailed(u'Unable to move the files to the new location')
        finally:
            if self.webhandler:
                # stop the keep_alive
                keepalive_stop.set()

        # download subtitles
        dosubs = sickbeard.USE_SUBTITLES and ep_obj.show_obj.subtitles

        # put the new location in the database
        sql_l = []
        for cur_ep_obj in [ep_obj] + ep_obj.related_ep_obj:
            with cur_ep_obj.lock:
                cur_ep_obj.location = ek.ek(os.path.join, dest_path, new_file_name)
                if dosubs:
                    cur_ep_obj.download_subtitles(force=True)
                # set file modify stamp to show airdate
                if sickbeard.AIRDATE_EPISODES:
                    cur_ep_obj.airdate_modify_stamp()
                sql = cur_ep_obj.get_sql()
                if None is not sql:
                    sql_l.append(sql)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # generate nfo/tbn
        ep_obj.create_meta_files()

        # log it to history
        history.log_download(ep_obj, self.file_path, new_ep_quality, self.release_group, anime_version)

        # send notifications
        # noinspection PyProtectedMember
        notifiers.notify_download(ep_obj._format_pattern('%SN - %Sx%0E - %EN - %QN'))

        # trigger library updates
        notifiers.notify_update_library(ep_obj=ep_obj)

        self._run_extra_scripts(ep_obj)

        return True

    def _add_to_anidb_mylist(self, filepath):
        """
        :param filepath: file path
        :type filepath: AnyStr
        """
        anidb_episode, log_args = push_anidb_mylist(filepath, self.anidbEpisode)
        if None is not anidb_episode:
            self.anidbEpisode = anidb_episode
        if None is not log_args:
            self._log(*log_args)
