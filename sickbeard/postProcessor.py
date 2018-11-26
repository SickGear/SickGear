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
import subprocess
import stat
import threading

import sickbeard

from sickbeard import db
from sickbeard import common
from sickbeard import exceptions
from sickbeard import helpers
from sickbeard import history
from sickbeard import logger
from sickbeard import notifiers
from sickbeard import show_name_helpers
from sickbeard import failed_history
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex

from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException

from lib import adba


class PostProcessor(object):
    """
    A class which will process a media file according to the post processing settings in the config.
    """

    EXISTS_LARGER = 1
    EXISTS_SAME = 2
    EXISTS_SMALLER = 3
    DOESNT_EXIST = 4

    IGNORED_FILESTRINGS = ['/.AppleDouble/', '.DS_Store']

    def __init__(self, file_path, nzb_name=None, process_method=None, force_replace=None, use_trash=None, webhandler=None, showObj=None):
        """
        Creates a new post processor with the given file path and optionally an NZB name.

        file_path: The path to the file to be processed
        nzb_name: The name of the NZB which resulted in this file being downloaded (optional)
        """
        # absolute path to the folder that is being processed
        self.folder_path = ek.ek(os.path.dirname, ek.ek(os.path.abspath, file_path))

        # full path to file
        self.file_path = file_path

        # file name only
        self.file_name = ek.ek(os.path.basename, file_path)

        # the name of the folder only
        self.folder_name = ek.ek(os.path.basename, self.folder_path)

        # name of the NZB that resulted in this folder
        self.nzb_name = nzb_name

        self.force_replace = force_replace

        self.use_trash = use_trash

        self.webhandler = webhandler

        self.showObj = showObj

        self.in_history = False

        self.release_group = None

        self.release_name = None

        self.is_proper = False

        self.log = ''

        self.process_method = process_method if process_method else sickbeard.PROCESS_METHOD

        self.anime_version = None  # anime equivalent of is_proper

        self.anidbEpisode = None

    def _log(self, message, level=logger.MESSAGE):
        """
        A wrapper for the internal logger which also keeps track of messages and saves them to a string for later.

        message: The string to log (unicode)
        level: The log level to use (optional)
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
        For a given file path searches for files with the same name but different extension and returns their absolute paths

        file_path: The file to check for associated files

        base_name_only: False add extra '.' (conservative search) to file_path minus extension

        Returns: A list containing all files which are associated to the given file
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
        base_name = re.sub(r'[\[\]\*\?]', r'[\g<0>]', base_name)

        for meta_ext in ['', '-thumb', '.ext', '.ext.cover', '.metathumb']:
            for associated_file_path in ek.ek(glob.glob, '%s%s.*' % (base_name, meta_ext)):
                # only add associated to list
                if associated_file_path == file_path:
                    continue
                # only list it if the only non-shared part is the extension or if it is a subtitle
                if subtitles_only and not associated_file_path[len(associated_file_path) - 3:] in common.subtitleExtensions:
                    continue

                # Exclude .rar files from associated list
                if re.search('(^.+\.(rar|r\d+)$)', associated_file_path):
                    continue

                if ek.ek(os.path.isfile, associated_file_path):
                    file_path_list.append(associated_file_path)

        return file_path_list

    def _delete(self, file_path, associated_files=False):
        """
        Deletes the file and optionally all associated files.

        file_path: The file to delete
        associated_files: True to delete all files which differ only by extension, False to leave them
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
                        self._log(u'Changed read only permissions to writeable to delete file %s' % cur_file, logger.DEBUG)
                    except:
                        self._log(u'Cannot change permissions to writeable to delete file: %s' % cur_file, logger.WARNING)

                helpers.remove_file(cur_file, log_level=logger.DEBUG)

                if True is not ek.ek(os.path.isfile, cur_file):
                    self._log(u'Deleted file ' + cur_file, logger.DEBUG)

                # do the library update for synoindex
                notifiers.NotifierFactory().get('SYNOINDEX').deleteFile(cur_file)

    def _combined_file_operation(self, file_path, new_path, new_base_name, associated_files=False, action=None,
                                 subtitles=False, action_tmpl=None):
        """
        Performs a generic operation (move or copy) on a file. Can rename the file as well as change its location,
        and optionally move associated files too.

        file_path: The full path of the media file to act on
        new_path: Destination path where we want to move/copy the file to
        new_base_name: The base filename (no extension) to use during the copy. Use None to keep the same name.
        associated_files: Boolean, whether we should copy similarly-named files too
        action: function that takes an old path and new path and does an operation with them (move/copy)
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
                new_file_name = helpers.replaceExtension(cur_file_name, cur_extension)

            if sickbeard.SUBTITLES_DIR and cur_extension in common.subtitleExtensions:
                subs_new_path = ek.ek(os.path.join, new_path, sickbeard.SUBTITLES_DIR)
                dir_exists = helpers.makeDir(subs_new_path)
                if not dir_exists:
                    logger.log(u'Unable to create subtitles folder ' + subs_new_path, logger.ERROR)
                else:
                    helpers.chmodAsParent(subs_new_path)
                new_file_path = ek.ek(os.path.join, subs_new_path, new_file_name)
            else:
                new_file_path = ek.ek(os.path.join, new_path, new_file_name)

            if None is action_tmpl:
                action(cur_file_path, new_file_path)
            else:
                action(cur_file_path, new_file_path, action_tmpl)

    def _move(self, file_path, new_path, new_base_name, associated_files=False, subtitles=False, action_tmpl=None):
        """
        file_path: The full path of the media file to move
        new_path: Destination path where we want to move the file to
        new_base_name: The base filename (no extension) to use during the move. Use None to keep the same name.
        associated_files: Boolean, whether we should move similarly-named files too
        """

        def _int_move(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.moveFile(cur_file_path, new_file_path)
                helpers.chmodAsParent(new_file_path)
                self._log(u'Moved file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to move file %s<br />.. %s' % (success_tmpl % (cur_file_path, new_file_path), str(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_move,
                                      subtitles=subtitles, action_tmpl=action_tmpl)

    def _copy(self, file_path, new_path, new_base_name, associated_files=False, subtitles=False, action_tmpl=None):
        """
        file_path: The full path of the media file to copy
        new_path: Destination path where we want to copy the file to
        new_base_name: The base filename (no extension) to use during the copy. Use None to keep the same name.
        associated_files: Boolean, whether we should copy similarly-named files too
        """

        def _int_copy(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.copyFile(cur_file_path, new_file_path)
                helpers.chmodAsParent(new_file_path)
                self._log(u'Copied file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to copy %s<br />.. %s' % (success_tmpl % (cur_file_path, new_file_path), str(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_copy,
                                      subtitles=subtitles, action_tmpl=action_tmpl)

    def _hardlink(self, file_path, new_path, new_base_name, associated_files=False, action_tmpl=None):
        """
        file_path: The full path of the media file to move
        new_path: Destination path where we want to create a hard linked file
        new_base_name: The base filename (no extension) to use during the link. Use None to keep the same name.
        associated_files: Boolean, whether we should move similarly-named files too
        """

        def _int_hard_link(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.hardlinkFile(cur_file_path, new_file_path)
                helpers.chmodAsParent(new_file_path)
                self._log(u'Hard linked file from' + (success_tmpl % (cur_file_path, new_file_path)), logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to link file %s<br />.. %s' % (success_tmpl % (cur_file_path, new_file_path), str(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_hard_link,
                                      action_tmpl=action_tmpl)

    def _move_and_symlink(self, file_path, new_path, new_base_name, associated_files=False, action_tmpl=None):
        """
        file_path: The full path of the media file to move
        new_path: Destination path where we want to move the file to create a symbolic link to
        new_base_name: The base filename (no extension) to use during the link. Use None to keep the same name.
        associated_files: Boolean, whether we should move similarly-named files too
        """

        def _int_move_and_sym_link(cur_file_path, new_file_path, success_tmpl=u' %s to %s'):

            try:
                helpers.moveAndSymlinkFile(cur_file_path, new_file_path)
                helpers.chmodAsParent(new_file_path)
                self._log(u'Moved then symbolic linked file from' + (success_tmpl % (cur_file_path, new_file_path)),
                          logger.DEBUG)
            except (IOError, OSError) as e:
                self._log(u'Unable to link file %s<br />.. %s' % (success_tmpl % (cur_file_path, new_file_path), str(e)), logger.ERROR)
                raise e

        self._combined_file_operation(file_path, new_path, new_base_name, associated_files, _int_move_and_sym_link,
                                      action_tmpl=action_tmpl)

    def _history_lookup(self):
        """
        Look up the NZB name in the history and see if it contains a record for self.nzb_name

        Returns a (indexer_id, season, [], quality) tuple. indexer_id, season, quality may be None and episodes may be [].
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
            search_name = re.sub('[ \.\-]', '_', curName)
            sql_results = my_db.select('SELECT * FROM history WHERE resource LIKE ?', [search_name])

            if 0 == len(sql_results):
                continue

            indexer_id = int(sql_results[0]['showid'])
            season = int(sql_results[0]['season'])
            quality = int(sql_results[0]['quality'])
            self.anime_version = int(sql_results[0]['version'])

            if common.Quality.UNKNOWN == quality:
                quality = None

            self.in_history = True
            show = helpers.findCertainShow(sickbeard.showList, indexer_id)
            to_return = (show, season, [], quality)
            if not show:
                self._log(u'Unknown show, check availability on ShowList page', logger.DEBUG)
                break
            self._log(u'Found a match in history for %s' % show.name, logger.DEBUG)
            break

        return to_return

    def _analyze_name(self, name, resource=True, show=None, rel_grp=None):
        """
        Takes a name and tries to figure out a show, season, and episode from it.

        name: A string which we want to analyze to determine show info from (unicode)

        Returns a (indexer_id, season, [episodes]) tuple. The first two may be None and episodes may be []
        if none were found.
        """

        logger.log(u'Analyzing name ' + repr(name))

        to_return = (None, None, [], None)

        if not name:
            return to_return

        # parse the name to break it into show name, season, and episode
        np = NameParser(resource, try_scene_exceptions=True, convert=True, showObj=self.showObj or show)
        parse_result = np.parse(name)
        self._log(u'Parsed %s<br />.. from %s' % (str(parse_result).decode('utf-8', 'xmlcharrefreplace'), name), logger.DEBUG)

        if parse_result.is_air_by_date and (None is parse_result.season_number or not parse_result.episode_numbers):
            season = -1
            episodes = [parse_result.air_date]
        else:
            season = parse_result.season_number
            episodes = parse_result.episode_numbers

        # show object
        show = parse_result.show
        if show and rel_grp and not parse_result.release_group:
            parse_result.release_group = rel_grp
        to_return = (show, season, episodes, parse_result.quality)

        self._finalize(parse_result)
        return to_return

    def _finalize(self, parse_result):

        self.release_group = parse_result.release_group

        # remember whether it's a proper
        if parse_result.extra_info_no_name():
            self.is_proper = 0 < common.Quality.get_proper_level(parse_result.extra_info_no_name(), parse_result.version,
                                                                 parse_result.is_anime)

        # if the result is complete then set release name
        if parse_result.series_name and\
                ((None is not parse_result.season_number and parse_result.episode_numbers) or parse_result.air_date)\
                and parse_result.release_group:

            if not self.release_name:
                self.release_name = helpers.remove_extension(ek.ek(os.path.basename, parse_result.original_name))

        else:
            logger.log(u'Parse result not sufficient (all following have to be set). will not save release name', logger.DEBUG)
            logger.log(u'Parse result(series_name): ' + str(parse_result.series_name), logger.DEBUG)
            logger.log(u'Parse result(season_number): ' + str(parse_result.season_number), logger.DEBUG)
            logger.log(u'Parse result(episode_numbers): ' + str(parse_result.episode_numbers), logger.DEBUG)
            logger.log(u' or Parse result(air_date): ' + str(parse_result.air_date), logger.DEBUG)
            logger.log(u'Parse result(release_group): ' + str(parse_result.release_group), logger.DEBUG)

    def _find_info(self):
        """
        For a given file try to find the showid, season, and episode.
        """

        show = season = quality = rel_grp = None
        episodes = []

        # try to look up the nzb in history
        attempt_list = [self._history_lookup,

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

                        # try to analyze file name with previously parsed show
                        lambda: self._analyze_name(self.file_name, show=show, rel_grp=rel_grp)]

        # attempt every possible method to get our info
        for cur_attempt in attempt_list:

            try:
                (cur_show, cur_season, cur_episodes, cur_quality) = cur_attempt()
            except (InvalidNameException, InvalidShowException) as e:
                logger.log(u'Unable to parse, skipping: ' + ex(e), logger.DEBUG)
                continue

            if not cur_show:
                continue

            # if we already did a successful history lookup then keep that show value
            show = cur_show
            if self.release_group:
                rel_grp = self.release_group

            if cur_quality and not (self.in_history and quality):
                quality = cur_quality

            if None is not cur_season:
                season = cur_season

            if cur_episodes:
                episodes = cur_episodes

            # for air-by-date shows we need to look up the season/episode from database
            if -1 == season and show and episodes:
                self._log(
                    u'Looks like this is an air-by-date or sports show, attempting to convert the date to season/episode',
                    logger.DEBUG)
                airdate = episodes[0].toordinal()
                my_db = db.DBConnection()
                sql_result = my_db.select(
                    'SELECT season, episode FROM tv_episodes WHERE showid = ? and indexer = ? and airdate = ?',
                    [show.indexerid, show.indexer, airdate])

                if sql_result:
                    season = int(sql_result[0][0])
                    episodes = [int(sql_result[0][1])]
                else:
                    self._log(u'Unable to find episode with date ' + str(episodes[0]) + u' for show ' + str(
                        show.indexerid) + u', skipping', logger.DEBUG)
                    # we don't want to leave dates in the episode list if we couldn't convert them to real episode numbers
                    episodes = []
                    continue

            # if there's no season then we can hopefully just use 1 automatically
            elif None is season and show:
                my_db = db.DBConnection()
                num_seasons_sql_result = my_db.select(
                    'SELECT COUNT(DISTINCT season) as numseasons FROM tv_episodes WHERE showid = ? and indexer = ? and season != 0',
                    [show.indexerid, show.indexer])
                if 1 == int(num_seasons_sql_result[0][0]) and None is season:
                    self._log(
                        u'No season number found, but this show appears to only have 1 season, setting season number to 1...',
                        logger.DEBUG)
                    season = 1

            if show and season and episodes:
                break

        return show, season, episodes, quality

    def _get_ep_obj(self, show, season, episodes):
        """
        Retrieve the TVEpisode object requested.

        show: The show object belonging to the show we want to process
        season: The season of the episode (int)
        episodes: A list of episodes to find (list of ints)

        If the episode(s) can be found then a TVEpisode object with the correct related eps will
        be instantiated and returned. If the episode can't be found then None will be returned.
        """

        root_ep = None
        for cur_episode in episodes:
            episode = int(cur_episode)

            self._log(u'Retrieving episode object for %sx%s' % (str(season), str(episode)), logger.DEBUG)

            # now that we've figured out which episode this file is just load it manually
            try:
                cur_ep = show.getEpisode(season, episode)
            except exceptions.EpisodeNotFoundException as e:
                self._log(u'Unable to create episode: ' + ex(e), logger.DEBUG)
                raise exceptions.PostProcessingFailed()

            # associate all the episodes together under a single root episode
            if None is root_ep:
                root_ep = cur_ep
                root_ep.relatedEps = []
            elif cur_ep not in root_ep.relatedEps:
                root_ep.relatedEps.append(cur_ep)

        return root_ep

    def _get_quality(self, ep_obj):
        """
        Determines the quality of the file that is being post processed, first by checking if it is directly
        available in the TVEpisode's status or otherwise by parsing through the data available.

        ep_obj: The TVEpisode object related to the file we are post processing

        Returns: A quality value found in common.Quality
        """

        # if there is a quality available in the status then we don't need to bother guessing from the filename
        if ep_obj.status in common.Quality.SNATCHED_ANY:
            old_status, ep_quality = common.Quality.splitCompositeStatus(ep_obj.status)  # @UnusedVariable
            if common.Quality.UNKNOWN != ep_quality:
                self._log(
                    u'Using "%s" quality from the old status' % common.Quality.qualityStrings[ep_quality],
                    logger.DEBUG)
                return ep_quality

        # search all possible names for our new quality, in case the file or dir doesn't have it
        # nzb name is the most reliable if it exists, followed by folder name and lastly file name
        for thing, cur_name in {'nzb name': self.nzb_name, 'folder name': self.folder_name, 'file name': self.file_name}.items():

            # some stuff might be None at this point still
            if not cur_name:
                continue

            ep_quality = common.Quality.nameQuality(cur_name, ep_obj.show.is_anime)
            quality_log = u' "%s" quality parsed from the %s %s' % (common.Quality.qualityStrings[ep_quality], thing, cur_name)

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

    def _run_extra_scripts(self, ep_obj):
        """
        Executes any extra scripts defined in the config.

        ep_obj: The object to use when calling the extra script
        """
        for curScriptName in sickbeard.EXTRA_SCRIPTS:

            # generate a safe command line string to execute the script and provide all the parameters
            script_cmd = [piece for piece in re.split("( |\\\".*?\\\"|'.*?')", curScriptName) if piece.strip()]
            script_cmd[0] = ek.ek(os.path.abspath, script_cmd[0])
            self._log(u'Absolute path to script: ' + script_cmd[0], logger.DEBUG)

            script_cmd = script_cmd + [ep_obj.location.encode(sickbeard.SYS_ENCODING),
                                       self.file_path.encode(sickbeard.SYS_ENCODING),
                                       str(ep_obj.show.indexerid),
                                       str(ep_obj.season),
                                       str(ep_obj.episode),
                                       str(ep_obj.airdate)]

            # use subprocess to run the command and capture output
            self._log(u'Executing command ' + str(script_cmd))
            try:
                p = subprocess.Popen(script_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, cwd=sickbeard.PROG_DIR)
                out, err = p.communicate()  # @UnusedVariable
                self._log(u'Script result: ' + str(out), logger.DEBUG)

            except OSError as e:
                self._log(u'Unable to run extra_script: ' + ex(e))

            except Exception as e:
                self._log(u'Unable to run extra_script: ' + ex(e))

    def _safe_replace(self, ep_obj, new_ep_quality):
        """
        Determines if the new episode can safely replace old episode.
        Episodes which are expected (snatched) or larger than the existing episode are priority, others are not.

        ep_obj: The TVEpisode object in question
        new_ep_quality: The quality of the episode that is being processed

        Returns: True if the episode can safely replace old episode, False otherwise.
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
                self._log(u'Existing episode status is not snatched but the episode to process appears to be better quality than existing episode, marking it safe to replace', logger.DEBUG)
                return True

            else:
                self._log(u'Marking it unsafe to replace because an existing episode exists in the database and the episode to process has unknown quality', logger.DEBUG)
                return False

        # if there's an existing downloaded file with same quality, check filesize to decide
        if new_ep_quality == old_ep_quality:
            np = NameParser(showObj=self.showObj)
            cur_proper_level = 0
            try:
                pr = np.parse(ep_obj.release_name)
                cur_proper_level = common.Quality.get_proper_level(pr.extra_info_no_name(), pr.version, pr.is_anime)
            except (StandardError, Exception):
                pass
            new_name = (('', self.file_name)[isinstance(self.file_name, basestring)], self.nzb_name)[isinstance(
                self.nzb_name, basestring)]
            if new_name:
                try:
                    npr = np.parse(new_name)
                except (StandardError, Exception):
                    npr = None
                if npr:
                    is_repack, new_proper_level = common.Quality.get_proper_level(npr.extra_info_no_name(), npr.version,
                                                                                  npr.is_anime, check_is_repack=True)
                    if new_proper_level > cur_proper_level and \
                            (not is_repack or npr.release_group == ep_obj.release_group):
                        self._log(u'Proper or repack with same quality, marking it safe to replace', logger.DEBUG)
                        return True

            self._log(u'An episode exists in the database with the same quality as the episode to process', logger.DEBUG)

            existing_file_status = self._check_for_existing_file(ep_obj.location)

            # check for an existing file
            if PostProcessor.DOESNT_EXIST == existing_file_status:
                if not ek.ek(os.path.isdir, ep_obj.show.location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
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
                self._log(u'Unknown file status for: %s This should never happen, please log this as a bug.' % ep_obj.location, logger.ERROR)
                return False

        # if there's an existing file with better quality
        if old_ep_quality > new_ep_quality and old_ep_quality != common.Quality.UNKNOWN:
            # Episode already exists in database and processed episode has lower quality, marking it unsafe to replace
            self._log(u'Marking it unsafe to replace the episode that already exists in database with a file of lower quality', logger.DEBUG)
            return False

        if self.in_history:
            self._log(u'SickGear snatched this episode, marking it safe to replace', logger.DEBUG)
            return True

        # None of the conditions were met, marking it unsafe to replace
        self._log(u'Marking it unsafe to replace because no positive condition is met, you may force replace but it would be better to examine the files', logger.DEBUG)
        return False

    def process(self):
        """
        Post-process a given file
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
        (show, season, episodes, quality) = self._find_info()

        # if we don't have it then give up
        if not show:
            self._log(u'Must add show to SickGear before trying to post process an episode', logger.WARNING)
            raise exceptions.PostProcessingFailed()
        elif None is season or not episodes:
            self._log(u'Quitting this post process, could not determine what episode this is', logger.DEBUG)
            return False

        # retrieve/create the corresponding TVEpisode objects
        ep_obj = self._get_ep_obj(show, season, episodes)

        # get the quality of the episode we're processing
        if common.Quality.UNKNOWN == quality:
            new_ep_quality = self._get_quality(ep_obj)
        else:
            new_ep_quality = quality
            self._log(u'Using "%s" quality from the snatch history' % common.Quality.qualityStrings[new_ep_quality], logger.DEBUG)

        # see if it's safe to replace existing episode (is download snatched, PROPER, better quality)
        if not self._safe_replace(ep_obj, new_ep_quality):
            # if it's not safe to replace, stop here
            self._log(u'Quitting this post process', logger.DEBUG)
            return False

        # delete the existing file (and company)
        for cur_ep in [ep_obj] + ep_obj.relatedEps:
            try:
                self._delete(cur_ep.location, associated_files=True)

                # clean up any left over folders
                if cur_ep.location:
                    helpers.delete_empty_folders(ek.ek(os.path.dirname, cur_ep.location),
                                                 keep_dir=ep_obj.show.location)
            except (OSError, IOError):
                raise exceptions.PostProcessingFailed(u'Unable to delete existing files')

            # set the status of the episodes
            # for curEp in [ep_obj] + ep_obj.relatedEps:
            #    curEp.status = common.Quality.compositeStatus(common.SNATCHED, new_ep_quality)

        # if the show directory doesn't exist then make it if allowed
        if not ek.ek(os.path.isdir, ep_obj.show.location) and sickbeard.CREATE_MISSING_SHOW_DIRS:
            self._log(u'Show directory does not exist, creating it', logger.DEBUG)
            try:
                ek.ek(os.mkdir, ep_obj.show.location)
                # do the library update for synoindex
                notifiers.NotifierFactory().get('SYNOINDEX').addFolder(ep_obj.show.location)
            except (OSError, IOError):
                raise exceptions.PostProcessingFailed(u'Unable to create show directory: ' + ep_obj.show.location)

            # get metadata for the show (but not episode because it hasn't been fully processed)
            ep_obj.show.writeMetadata(True)

        # if we're processing an episode of type anime, get the anime version
        anime_version = (-1, self.anime_version)[ep_obj.show.is_anime and None is not self.anime_version]

        # update the ep info before we rename so the quality & release name go into the name properly
        sql_l = []
        for cur_ep in [ep_obj] + ep_obj.relatedEps:
            with cur_ep.lock:

                if self.release_name:
                    self._log(u'Found release name ' + self.release_name, logger.DEBUG)

                cur_ep.release_name = self.release_name or ''

                any_qualities, best_qualities = common.Quality.splitQuality(cur_ep.show.quality)
                cur_status, cur_quality = common.Quality.splitCompositeStatus(cur_ep.status)

                cur_ep.status = common.Quality.compositeStatus(
                    **({'status': common.DOWNLOADED, 'quality': new_ep_quality},
                       {'status': common.ARCHIVED, 'quality': new_ep_quality})
                    [ep_obj.status in common.Quality.SNATCHED_BEST or
                     (cur_ep.show.upgrade_once and
                      (new_ep_quality in best_qualities and
                       (new_ep_quality not in any_qualities or (cur_status in
                        (common.SNATCHED, common.SNATCHED_BEST, common.SNATCHED_PROPER, common.DOWNLOADED) and
                                                                cur_quality != new_ep_quality))))])

                cur_ep.release_group = self.release_group or ''

                cur_ep.is_proper = self.is_proper

                cur_ep.version = anime_version

                cur_ep.subtitles = []

                cur_ep.subtitles_searchcount = 0

                cur_ep.subtitles_lastsearch = '0001-01-01 00:00:00'

                sql = cur_ep.get_sql()
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
            proper_absolute_path = ek.ek(os.path.join, ep_obj.show.location, proper_path)
            dest_path = ek.ek(os.path.dirname, proper_absolute_path)

        except exceptions.ShowDirNotFoundException:
            raise exceptions.PostProcessingFailed(
                u'Unable to post process an episode because the show dir does not exist, quitting')

        self._log(u'Destination folder for this episode is ' + dest_path, logger.DEBUG)

        # create any folders we need
        if not helpers.make_dirs(dest_path):
            raise exceptions.PostProcessingFailed(u'Unable to create destination folder: ' + dest_path)

        # figure out the base name of the resulting episode file
        if sickbeard.RENAME_EPISODES:
            new_base_name = ek.ek(os.path.basename, proper_path)
            new_file_name = new_base_name + '.' + self.file_name.rpartition('.')[-1]

        else:
            # if we're not renaming then there's no new base name, we'll just use the existing name
            new_base_name = None
            new_file_name = self.file_name

        # add to anidb
        if sickbeard.ANIDB_USE_MYLIST and ep_obj.show.is_anime:
            self._add_to_anidb_mylist(self.file_path)

        if self.webhandler:
            def keep_alive(webh, stop_event):
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
            args_cpmv = {'subtitles': sickbeard.USE_SUBTITLES and ep_obj.show.subtitles,
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
                raise exceptions.PostProcessingFailed(u'Unable to move the files to the new location')
        except (OSError, IOError):
            raise exceptions.PostProcessingFailed(u'Unable to move the files to the new location')
        finally:
            if self.webhandler:
                #stop the keep_alive
                keepalive_stop.set()

        # download subtitles
        dosubs = sickbeard.USE_SUBTITLES and ep_obj.show.subtitles

        # put the new location in the database
        sql_l = []
        for cur_ep in [ep_obj] + ep_obj.relatedEps:
            with cur_ep.lock:
                cur_ep.location = ek.ek(os.path.join, dest_path, new_file_name)
                if dosubs:
                    cur_ep.downloadSubtitles(force=True)
                # set file modify stamp to show airdate
                if sickbeard.AIRDATE_EPISODES:
                    cur_ep.airdateModifyStamp()
                sql = cur_ep.get_sql()
                if None is not sql:
                    sql_l.append(sql)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # generate nfo/tbn
        ep_obj.createMetaFiles()

        # log it to history
        history.log_download(ep_obj, self.file_path, new_ep_quality, self.release_group, anime_version)

        # send notifications
        notifiers.notify_download(ep_obj._format_pattern('%SN - %Sx%0E - %EN - %QN'))

        # trigger library updates
        notifiers.notify_update_library(ep_obj=ep_obj)

        self._run_extra_scripts(ep_obj)

        return True

    @staticmethod
    def _build_anidb_episode(connection, filepath):
        ep = adba.Episode(connection, filePath=filepath,
                          paramsF=['quality', 'anidb_file_name', 'crc32'],
                          paramsA=['epno', 'english_name', 'short_name_list', 'other_name', 'synonym_list'])
        return ep

    def _add_to_anidb_mylist(self, filepath):
        if helpers.set_up_anidb_connection():
            if not self.anidbEpisode:  # seams like we could parse the name before, now lets build the anidb object
                self.anidbEpisode = self._build_anidb_episode(sickbeard.ADBA_CONNECTION, filepath)

            self._log(u'Adding the file to the anidb mylist', logger.DEBUG)
            try:
                self.anidbEpisode.add_to_mylist(status=1)  # status = 1 sets the status of the file to "internal HDD"
            except Exception as e:
                self._log(u'exception msg: ' + str(e))
