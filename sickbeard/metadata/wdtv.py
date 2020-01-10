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

import datetime
import os
import re

from . import generic
from .. import helpers, logger
from ..indexers.indexer_exceptions import check_exception_type, ExceptionTuples
import sickbeard
# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex
from lxml_etree import etree

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union


class WDTVMetadata(generic.GenericMetadata):
    """
    Metadata generation class for WDTV

    The following file structure is used:

    show_root/folder.jpg                    (poster)
    show_root/Season ##/folder.jpg          (season thumb)
    show_root/Season ##/filename.ext        (*)
    show_root/Season ##/filename.metathumb  (episode thumb)
    show_root/Season ##/filename.xml        (episode metadata)
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

        self.name = 'WDTV'  # type: AnyStr

        self._ep_nfo_extension = 'xml'  # type: AnyStr

        self.poster_name = "folder.jpg"  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_metadata = "Season##\\<i>filename</i>.xml"  # type: AnyStr
        self.eg_fanart = "<i>not supported</i>"  # type: AnyStr
        self.eg_poster = "folder.jpg"  # type: AnyStr
        self.eg_banner = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_thumbnails = "Season##\\<i>filename</i>.metathumb"  # type: AnyStr
        self.eg_season_posters = "Season##\\folder.jpg"  # type: AnyStr
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

    def create_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_banners(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_all_poster(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_all_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[AnyStr]
        """
        Returns the path where the episode thumbnail should be stored. Defaults to
        the same path as the episode file but with a .metathumb extension.

        ep_obj: a TVEpisode instance for which to create the thumbnail
        """
        if ek.ek(os.path.isfile, ep_obj.location):
            return helpers.replace_extension(ep_obj.location, 'metathumb')

    def get_season_poster_path(self, show_obj, season):
        # type: (sickbeard.tv.TVShow, int) -> Optional[AnyStr]
        """
        Season thumbs for WDTV go in Show Dir/Season X/folder.jpg

        If no season folder exists, None is returned
        """

        dir_list = [x for x in ek.ek(os.listdir, show_obj.location) if
                    ek.ek(os.path.isdir, ek.ek(os.path.join, show_obj.location, x))]

        season_dir_regex = r'^Season\s+(\d+)$'

        season_dir = None

        for cur_dir in dir_list:
            if 0 == season and "Specials" == cur_dir:
                season_dir = cur_dir
                break

            match = re.match(season_dir_regex, cur_dir, re.I)
            if not match:
                continue

            cur_season = int(match.group(1))

            if cur_season == season:
                season_dir = cur_dir
                break

        if not season_dir:
            logger.log(u"Unable to find a season dir for season " + str(season), logger.DEBUG)
            return None

        logger.log(u"Using " + str(season_dir) + "/folder.jpg as season dir for season " + str(season), logger.DEBUG)

        return ek.ek(os.path.join, show_obj.location, season_dir, 'folder.jpg')

    def _ep_data(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for a WDTV style episode.xml
        and returns the resulting data object.

        ep_obj: a TVShow instance to create the NFO for
        """

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

        rootNode = etree.Element("details")
        data = None

        # write an WDTV XML containing info for all matching episodes
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

            if 1 < len(ep_obj_list_to_write):
                episode = etree.SubElement(rootNode, "details")
            else:
                episode = rootNode

            episodeID = etree.SubElement(episode, "id")
            episodeID.text = str(cur_ep_obj.epid)

            title = etree.SubElement(episode, "title")
            title.text = '%s' % ep_obj.pretty_name()

            seriesName = etree.SubElement(episode, "series_name")
            if None is not getattr(show_info, 'seriesname', None):
                seriesName.text = '%s' % show_info["seriesname"]

            episodeName = etree.SubElement(episode, "episode_name")
            if None is not cur_ep_obj.name:
                episodeName.text = '%s' % cur_ep_obj.name

            seasonNumber = etree.SubElement(episode, "season_number")
            seasonNumber.text = str(cur_ep_obj.season)

            episodeNum = etree.SubElement(episode, "episode_number")
            episodeNum.text = str(cur_ep_obj.episode)

            firstAired = etree.SubElement(episode, "firstaired")

            if cur_ep_obj.airdate != datetime.date.fromordinal(1):
                firstAired.text = str(cur_ep_obj.airdate)

            year = etree.SubElement(episode, "year")
            year_text = self.get_show_year(ep_obj.show_obj, show_info)
            if year_text:
                year.text = '%s' % year_text

            runtime = etree.SubElement(episode, "runtime")
            if 0 != cur_ep_obj.season:
                if None is not getattr(show_info, 'runtime', None):
                    runtime.text = '%s' % show_info["runtime"]

            genre = etree.SubElement(episode, "genre")
            if None is not getattr(show_info, 'genre', None):
                genre.text = " / ".join([x for x in show_info["genre"].split('|') if x])

            director = etree.SubElement(episode, "director")
            director_text = getattr(ep_info, 'director', None)
            if None is not director_text:
                director.text = '%s' % director_text

            for actor in getattr(show_info, 'actors', []):
                cur_actor = etree.SubElement(episode, 'actor')

                cur_actor_name = etree.SubElement(cur_actor, 'name')
                cur_actor_name.text = '%s' % actor['person']['name']

                cur_actor_role = etree.SubElement(cur_actor, 'role')
                cur_actor_role_text = '%s' % actor['character']['name']
                if cur_actor_role_text:
                    cur_actor_role.text = '%s' % cur_actor_role_text

            overview = etree.SubElement(episode, "overview")
            if None is not cur_ep_obj.description:
                overview.text = '%s' % cur_ep_obj.description

            # Make it purdy
            helpers.indent_xml(rootNode)
            data = etree.ElementTree(rootNode)

        return data


# present a standard "interface" from the module
metadata_class = WDTVMetadata
