# Author: Nic Wolfe <nic@wolfeden.ca>
# Author: Gordon Turner <gordonturner@gordonturner.ca>
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

import datetime
import os

from . import generic
from .. import helpers, logger
from ..indexers.indexer_exceptions import check_exception_type, ExceptionTuples
import sickbeard
# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union


class TIVOMetadata(generic.GenericMetadata):
    """
    Metadata generation class for TIVO

    The following file structure is used:

    show_root/Season ##/filename.ext            (*)
    show_root/Season ##/.meta/filename.ext.txt  (episode metadata)

    This class only generates episode specific metadata files, it does NOT generate a default.txt file.
    """

    def __init__(self,
                 show_metadata=False,  # type: bool
                 episode_metadata=False,  # type: bool
                 use_fanart=False,  # type: bool
                 use_poster=False,  # type: bool
                 use_banner=False,  # type: bool
                 episode_thumbnails=False,  # type: bool
                 season_posters=False,  # type: bool
                 season_banners=False,  # type: bool
                 season_all_poster=False,  # type: bool
                 season_all_banner=False  # type: bool
                 ):

        generic.GenericMetadata.__init__(self,
                                         show_metadata,
                                         episode_metadata,
                                         use_fanart,
                                         use_poster,
                                         use_banner,
                                         episode_thumbnails,
                                         season_posters,
                                         season_banners,
                                         season_all_poster,
                                         season_all_banner)

        self.name = 'TIVO'  # type: AnyStr

        self._ep_nfo_extension = "txt"  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_metadata = "Season##\\.meta\\<i>filename</i>.ext.txt"  # type: AnyStr
        self.eg_fanart = "<i>not supported</i>"  # type: AnyStr
        self.eg_poster = "<i>not supported</i>"  # type: AnyStr
        self.eg_banner = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_thumbnails = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_posters = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_banners = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_poster = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_banner = "<i>not supported</i>"  # type: AnyStr

    # Override with empty methods for unsupported features
    def retrieveShowMetadata(self, folder):
        # type: (AnyStr) -> Tuple[None, None, None]
        # no show metadata generated, we abort this lookup function
        return None, None, None

    def create_show_metadata(self, show_obj, force=False):
        # type: (sickbeard.tv.TVShow, bool) -> None
        pass

    def update_show_indexer_metadata(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_show_file_path(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_fanart(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_poster(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_episode_thumb(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def create_season_posters(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def create_season_banners(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def create_season_all_poster(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_all_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    # Override generic class
    def get_episode_file_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> AnyStr
        """
        Returns a full show dir/.meta/episode.txt path for Tivo
        episode metadata files.

        Note, that pyTivo requires the metadata filename to include the original extention.

        ie If the episode name is foo.avi, the metadata name is foo.avi.txt

        ep_obj: a TVEpisode object to get the path for
        """
        if ek.ek(os.path.isfile, ep_obj.location):
            metadata_file_name = ek.ek(os.path.basename, ep_obj.location) + "." + self._ep_nfo_extension
            metadata_dir_name = ek.ek(os.path.join, ek.ek(os.path.dirname, ep_obj.location), '.meta')
            metadata_file_path = ek.ek(os.path.join, metadata_dir_name, metadata_file_name)
        else:
            logger.log(u"Episode location doesn't exist: " + str(ep_obj.location), logger.DEBUG)
            return ''
        return metadata_file_path

    def _ep_data(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[Union[bool, AnyStr]]
        """
        Creates a key value structure for a Tivo episode metadata file and
        returns the resulting data object.

        ep_obj: a TVEpisode instance to create the metadata file for.

        Lookup the show in http://thetvdb.com/ using the python library:

        https://github.com/dbr/indexer_api/

        The results are saved in the object show_info.

        The key values for the tivo metadata file are from:

        http://pytivo.sourceforge.net/wiki/index.php/Metadata
        """

        data = ''

        ep_obj_list_to_write = [ep_obj] + ep_obj.related_ep_obj

        show_lang = ep_obj.show_obj.lang

        try:
            tvinfo_config = sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).api_params.copy()

            tvinfo_config['actors'] = True

            if show_lang and not 'en' == show_lang:
                tvinfo_config['language'] = show_lang

            if 0 != ep_obj.show_obj.dvdorder:
                tvinfo_config['dvdorder'] = True

            t = sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).setup(**tvinfo_config)
            show_info = t[ep_obj.show_obj.prodid]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_shownotfound):
                raise exceptions_helper.ShowNotFoundException(ex(e))
            elif check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log("Unable to connect to %s while creating meta files - skipping - %s" %
                           (sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name, ex(e)), logger.ERROR)
                return False
            else:
                raise e

        if not self._valid_show(show_info, ep_obj.show_obj):
            return

        for cur_ep_obj in ep_obj_list_to_write:

            try:
                ep_info = show_info[cur_ep_obj.season][cur_ep_obj.episode]
            except (BaseException, Exception):
                logger.log("Unable to find episode %sx%s on %s... has it been removed? Should I delete from db?" %
                           (cur_ep_obj.season, cur_ep_obj.episode, sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name))
                return None

            if None is getattr(ep_info, 'firstaired', None) and 0 == ep_obj.season:
                ep_info["firstaired"] = str(datetime.date.fromordinal(1))

            if None is getattr(ep_info, 'episodename', None) or None is getattr(ep_info, 'firstaired', None):
                return None

            if None is not getattr(show_info, 'seriesname', None):
                data += ("title : " + show_info["seriesname"] + "\n")
                data += ("seriesTitle : " + show_info["seriesname"] + "\n")

            data += ("episodeTitle : " + cur_ep_obj._format_pattern('%Sx%0E %EN') + "\n")

            # This should be entered for episodic shows and omitted for movies. The standard tivo format is to enter
            # the season number followed by the episode number for that season. For example, enter 201 for season 2
            # episode 01.

            # This only shows up if you go into the Details from the Program screen.

            # This seems to disappear once the video is transferred to TiVo.

            # NOTE: May not be correct format, missing season, but based on description from wiki leaving as is.
            data += ("episodeNumber : " + str(cur_ep_obj.episode) + "\n")

            # Must be entered as true or false. If true, the year from originalAirDate will be shown in parentheses
            # after the episode's title and before the description on the Program screen.

            # FIXME: Hardcode isEpisode to true for now, not sure how to handle movies
            data += "isEpisode : true\n"

            # Write the synopsis of the video here
            # Micrsoft Word's smartquotes can die in a fire.
            sanitizedDescription = cur_ep_obj.description
            # Replace double curly quotes
            sanitizedDescription = sanitizedDescription.replace(u"\u201c", "\"").replace(u"\u201d", "\"")
            # Replace single curly quotes
            sanitizedDescription = sanitizedDescription.replace(u"\u2018", "'").replace(u"\u2019", "'").replace(
                u"\u02BC", "'")

            data += ("description : " + sanitizedDescription + "\n")

            # Usually starts with "SH" and followed by 6-8 digits.
            # Tivo uses zap2it for thier data, so the series id is the zap2it_id.
            if None is not getattr(show_info, 'zap2it_id', None):
                data += ("seriesId : " + show_info["zap2it_id"] + "\n")

            # This is the call sign of the channel the episode was recorded from.
            if None is not getattr(show_info, 'network', None):
                data += ("callsign : " + show_info["network"] + "\n")

            # This must be entered as yyyy-mm-ddThh:mm:ssZ (the t is capitalized and never changes, the Z is also
            # capitalized and never changes). This is the original air date of the episode.
            # NOTE: Hard coded the time to T00:00:00Z as we really don't know when during the day the first run happened
            if cur_ep_obj.airdate != datetime.date.fromordinal(1):
                data += ("originalAirDate : " + str(cur_ep_obj.airdate) + "T00:00:00Z\n")

            # This shows up at the beginning of the description on the Program screen and on the Details screen.
            for actor in getattr(show_info, 'actors', []):
                data += ('vActor : %s\n' % actor['character']['name'] and actor['person']['name']
                         and actor['character']['name'] != actor['person']['name']
                         and '%s (%s)' % (actor['character']['name'], actor['person']['name'])
                         or actor['person']['name'] or actor['character']['name'])

            # This is shown on both the Program screen and the Details screen.
            if None is not getattr(ep_info, 'rating', None):
                try:
                    rating = float(ep_info['rating'])
                except ValueError:
                    rating = 0.0
                # convert 10 to 4 star rating. 4 * rating / 10
                # only whole numbers or half numbers work. multiply by 2, round, divide by 2.0
                rating = round(8 * rating / 10) / 2.0
                data += ("starRating : " + str(rating) + "\n")

            # This is shown on both the Program screen and the Details screen.
            # It uses the standard TV rating system of: TV-Y7, TV-Y, TV-G, TV-PG, TV-14, TV-MA and TV-NR.
            if None is not getattr(show_info, 'contentrating', None):
                data += ("tvRating : " + str(show_info["contentrating"]) + "\n")

            # This field can be repeated as many times as necessary or omitted completely.
            if ep_obj.show_obj.genre:
                for genre in ep_obj.show_obj.genre.split('|'):
                    if genre:
                        data += ("vProgramGenre : " + str(genre) + "\n")

                        # NOTE: The following are metadata keywords are not used
                        # displayMajorNumber
                        # showingBits
                        # displayMinorNumber
                        # colorCode
                        # vSeriesGenre
                        # vGuestStar, vDirector, vExecProducer, vProducer, vWriter, vHost, vChoreographer
                        # partCount
                        # partIndex

        return data

    def write_ep_file(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> bool
        """
        Generates and writes ep_obj's metadata under the given path with the
        given filename root. Uses the episode's name with the extension in
        _ep_nfo_extension.

        ep_obj: TVEpisode object for which to create the metadata

        file_name_path: The file name to use for this metadata. Note that the extension
                will be automatically added based on _ep_nfo_extension. This should
                include an absolute path.
        """
        data = self._ep_data(ep_obj)

        if not data:
            return False

        nfo_file_path = self.get_episode_file_path(ep_obj)
        nfo_file_dir = ek.ek(os.path.dirname, nfo_file_path)

        try:
            if not ek.ek(os.path.isdir, nfo_file_dir):
                logger.log(u"Metadata dir didn't exist, creating it at " + nfo_file_dir, logger.DEBUG)
                ek.ek(os.makedirs, nfo_file_dir)
                helpers.chmod_as_parent(nfo_file_dir)

            logger.log(u"Writing episode nfo file to " + nfo_file_path, logger.DEBUG)

            with ek.ek(open, nfo_file_path, 'w') as nfo_file:
                # Calling encode directly, b/c often descriptions have wonky characters.
                nfo_file.write(data.encode("utf-8"))

            helpers.chmod_as_parent(nfo_file_path)

        except EnvironmentError as e:
            logger.log(u"Unable to write file to " + nfo_file_path + " - are you sure the folder is writable? " + ex(e),
                       logger.ERROR)
            return False

        return True


# present a standard "interface" from the module
metadata_class = TIVOMetadata
