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

from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union


class MediaBrowserMetadata(generic.GenericMetadata):
    """
    Metadata generation class for Media Browser 2.x/3.x - Standard Mode.

    The following file structure is used:

    show_root/series.xml                       (show metadata)
    show_root/folder.jpg                       (poster)
    show_root/backdrop.jpg                     (fanart)
    show_root/Season ##/folder.jpg             (season thumb)
    show_root/Season ##/filename.ext           (*)
    show_root/Season ##/metadata/filename.xml  (episode metadata)
    show_root/Season ##/metadata/filename.jpg  (episode thumb)
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

        self.name = 'MediaBrowser'  # type: AnyStr

        self._ep_nfo_extension = 'xml'  # type: AnyStr
        self._show_metadata_filename = 'series.xml'  # type: AnyStr

        self.fanart_name = "backdrop.jpg"  # type: AnyStr
        self.poster_name = "folder.jpg"  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = "series.xml"  # type: AnyStr
        self.eg_episode_metadata = "Season##\\metadata\\<i>filename</i>.xml"  # type: AnyStr
        self.eg_fanart = "backdrop.jpg"  # type: AnyStr
        self.eg_poster = "folder.jpg"  # type: AnyStr
        self.eg_banner = "banner.jpg"  # type: AnyStr
        self.eg_episode_thumbnails = "Season##\\metadata\\<i>filename</i>.jpg"  # type: AnyStr
        self.eg_season_posters = "Season##\\folder.jpg"  # type: AnyStr
        self.eg_season_banners = "Season##\\banner.jpg"  # type: AnyStr
        self.eg_season_all_poster = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_banner = "<i>not supported</i>"  # type: AnyStr

    # Override with empty methods for unsupported features
    def retrieveShowMetadata(self, folder):
        # type: (AnyStr) -> Tuple[None, None, None]
        # while show metadata is generated, it is not supported for our lookup
        return None, None, None

    def create_season_all_poster(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_all_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_episode_file_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> AnyStr
        """
        Returns a full show dir/metadata/episode.xml path for MediaBrowser
        episode metadata files

        ep_obj: a TVEpisode object to get the path for
        """

        if ek.ek(os.path.isfile, ep_obj.location):
            xml_file_name = helpers.replace_extension(ek.ek(os.path.basename, ep_obj.location), self._ep_nfo_extension)
            metadata_dir_name = ek.ek(os.path.join, ek.ek(os.path.dirname, ep_obj.location), 'metadata')
            xml_file_path = ek.ek(os.path.join, metadata_dir_name, xml_file_name)
        else:
            logger.log(u"Episode location doesn't exist: " + str(ep_obj.location), logger.DEBUG)
            return ''

        return xml_file_path

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> AnyStr
        """
        Returns a full show dir/metadata/episode.jpg path for MediaBrowser
        episode thumbs.

        ep_obj: a TVEpisode object to get the path from
        """

        if ek.ek(os.path.isfile, ep_obj.location):
            metadata_dir_name = ek.ek(os.path.join, ek.ek(os.path.dirname, ep_obj.location), 'metadata')
            tbn_file_name = helpers.replace_extension(ek.ek(os.path.basename, ep_obj.location), 'jpg')
            return ek.ek(os.path.join, metadata_dir_name, tbn_file_name)

    def get_season_poster_path(self, show_obj, season):
        # type: (sickbeard.tv.TVShow, int) -> Optional[AnyStr]
        """
        Season thumbs for MediaBrowser go in Show Dir/Season X/folder.jpg

        If no season folder exists, None is returned
        """

        dir_list = [x for x in ek.ek(os.listdir, show_obj.location) if
                    ek.ek(os.path.isdir, ek.ek(os.path.join, show_obj.location, x))]

        season_dir_regex = r'^Season\s+(\d+)$'

        season_dir = None

        for cur_dir in dir_list:
            # MediaBrowser 1.x only supports 'Specials'
            # MediaBrowser 2.x looks to only support 'Season 0'
            # MediaBrowser 3.x looks to mimic XBMC/Plex support
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

    def get_season_banner_path(self, show_obj, season):
        # type: (sickbeard.tv.TVShow, int) -> Optional[AnyStr]
        """
        Season thumbs for MediaBrowser go in Show Dir/Season X/banner.jpg

        If no season folder exists, None is returned
        """

        dir_list = [x for x in ek.ek(os.listdir, show_obj.location) if
                    ek.ek(os.path.isdir, ek.ek(os.path.join, show_obj.location, x))]

        season_dir_regex = r'^Season\s+(\d+)$'

        season_dir = None

        for cur_dir in dir_list:
            # MediaBrowser 1.x only supports 'Specials'
            # MediaBrowser 2.x looks to only support 'Season 0'
            # MediaBrowser 3.x looks to mimic XBMC/Plex support
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

        logger.log(u"Using " + str(season_dir) + "/banner.jpg as season dir for season " + str(season), logger.DEBUG)

        return ek.ek(os.path.join, show_obj.location, season_dir, 'banner.jpg')

    def _show_data(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for a MediaBrowser-style series.xml
        returns the resulting data object.

        show_obj: a TVShow instance to create the NFO for
        """

        show_lang = show_obj.lang

        # There's gotta be a better way of doing this but we don't wanna
        # change the language value elsewhere
        tvinfo_config = sickbeard.TVInfoAPI(show_obj.tvid).api_params.copy()

        tvinfo_config['actors'] = True

        if show_lang and not 'en' == show_lang:
            tvinfo_config['language'] = show_lang

        if 0 != show_obj.dvdorder:
            tvinfo_config['dvdorder'] = True

        t = sickbeard.TVInfoAPI(show_obj.tvid).setup(**tvinfo_config)

        tv_node = etree.Element("Series")

        try:
            show_info = t[int(show_obj.prodid)]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_shownotfound):
                logger.log("Unable to find show with id %s on %s, skipping it" %
                           (show_obj.prodid, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
                raise

            elif check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log("%s is down, can't use its data to make the NFO" % sickbeard.TVInfoAPI(show_obj.tvid).name,
                           logger.ERROR)
                raise
            else:
                raise e

        if not self._valid_show(show_info, show_obj):
            return

        # check for title and id
        if None is getattr(show_info, 'seriesname', None) or None is getattr(show_info, 'id', None):
            logger.log("Incomplete info for show with id %s on %s, skipping it" %
                       (show_obj.prodid, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
            return False

        prodid = etree.SubElement(tv_node, "id")
        if None is not getattr(show_info, 'id', None):
            prodid.text = str(show_info['id'])

        tvid = etree.SubElement(tv_node, "indexer")
        if None is not show_obj.tvid:
            tvid.text = str(show_obj.tvid)

        SeriesName = etree.SubElement(tv_node, "SeriesName")
        if None is not getattr(show_info, 'seriesname', None):
            SeriesName.text = '%s' % show_info['seriesname']

        Status = etree.SubElement(tv_node, "Status")
        if None is not getattr(show_info, 'status', None):
            Status.text = '%s' % show_info['status']

        Network = etree.SubElement(tv_node, "Network")
        if None is not getattr(show_info, 'network', None):
            Network.text = '%s' % show_info['network']

        Airs_Time = etree.SubElement(tv_node, "Airs_Time")
        if None is not getattr(show_info, 'airs_time', None):
            Airs_Time.text = '%s' % show_info['airs_time']

        Airs_DayOfWeek = etree.SubElement(tv_node, "Airs_DayOfWeek")
        if None is not getattr(show_info, 'airs_dayofweek', None):
            Airs_DayOfWeek.text = '%s' % show_info['airs_dayofweek']

        FirstAired = etree.SubElement(tv_node, "FirstAired")
        if None is not getattr(show_info, 'firstaired', None):
            FirstAired.text = '%s' % show_info['firstaired']

        ContentRating = etree.SubElement(tv_node, "ContentRating")
        MPAARating = etree.SubElement(tv_node, "MPAARating")
        certification = etree.SubElement(tv_node, "certification")
        if None is not getattr(show_info, 'contentrating', None):
            ContentRating.text = '%s' % show_info['contentrating']
            MPAARating.text = '%s' % show_info['contentrating']
            certification.text = '%s' % show_info['contentrating']

        MetadataType = etree.SubElement(tv_node, "Type")
        MetadataType.text = "Series"

        Overview = etree.SubElement(tv_node, "Overview")
        if None is not getattr(show_info, 'overview', None):
            Overview.text = '%s' % show_info['overview']

        PremiereDate = etree.SubElement(tv_node, "PremiereDate")
        if None is not getattr(show_info, 'firstaired', None):
            PremiereDate.text = '%s' % show_info['firstaired']

        Rating = etree.SubElement(tv_node, "Rating")
        if None is not getattr(show_info, 'rating', None):
            Rating.text = '%s' % show_info['rating']

        ProductionYear = etree.SubElement(tv_node, "ProductionYear")
        year_text = self.get_show_year(show_obj, show_info)
        if year_text:
            ProductionYear.text = '%s' % year_text

        RunningTime = etree.SubElement(tv_node, "RunningTime")
        Runtime = etree.SubElement(tv_node, "Runtime")
        if None is not getattr(show_info, 'runtime', None):
            RunningTime.text = '%s' % show_info['runtime']
            Runtime.text = '%s' % show_info['runtime']

        IMDB_ID = etree.SubElement(tv_node, "IMDB_ID")
        IMDB = etree.SubElement(tv_node, "IMDB")
        IMDbId = etree.SubElement(tv_node, "IMDbId")
        if None is not getattr(show_info, 'imdb_id', None):
            IMDB_ID.text = '%s' % show_info['imdb_id']
            IMDB.text = '%s' % show_info['imdb_id']
            IMDbId.text = '%s' % show_info['imdb_id']

        Zap2ItId = etree.SubElement(tv_node, "Zap2ItId")
        if None is not getattr(show_info, 'zap2it_id', None):
            Zap2ItId.text = '%s' % show_info['zap2it_id']

        Genres = etree.SubElement(tv_node, "Genres")
        for genre in show_info['genre'].split('|'):
            if genre:
                cur_genre = etree.SubElement(Genres, "Genre")
                cur_genre.text = '%s' % genre

        Genre = etree.SubElement(tv_node, "Genre")
        if None is not getattr(show_info, 'genre', None):
            Genre.text = "|".join([x for x in show_info["genre"].split('|') if x])

        Studios = etree.SubElement(tv_node, "Studios")
        Studio = etree.SubElement(Studios, "Studio")
        if None is not getattr(show_info, 'network', None):
            Studio.text = '%s' % show_info['network']

        Persons = etree.SubElement(tv_node, 'Persons')
        for actor in getattr(show_info, 'actors', []):
            cur_actor = etree.SubElement(Persons, 'Person')

            cur_actor_name = etree.SubElement(cur_actor, 'Name')
            cur_actor_name.text = '%s' % actor['person']['name']

            cur_actor_type = etree.SubElement(cur_actor, 'Type')
            cur_actor_type.text = 'Actor'

            cur_actor_role = etree.SubElement(cur_actor, 'Role')
            cur_actor_role_text = '%s' % actor['character']['name']
            if cur_actor_role_text:
                cur_actor_role.text = '%s' % cur_actor_role_text

        helpers.indent_xml(tv_node)

        data = etree.ElementTree(tv_node)

        return data

    def _ep_data(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for a MediaBrowser style episode.xml
        and returns the resulting data object.

        show_obj: a TVShow instance to create the NFO for
        """

        ep_obj_list_to_write = [ep_obj] + ep_obj.related_ep_obj

        persons_dict = {'Director': [], 'GuestStar': [], 'Writer': []}

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

        rootNode = etree.Element("Item")

        # write an MediaBrowser XML containing info for all matching episodes
        for cur_ep_obj in ep_obj_list_to_write:

            try:
                ep_info = show_info[cur_ep_obj.season][cur_ep_obj.episode]
            except (BaseException, Exception):
                logger.log("Unable to find episode %sx%s on %s.. has it been removed? Should I delete from db?" %
                           (cur_ep_obj.season, cur_ep_obj.episode, sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name))
                return None

            if cur_ep_obj == ep_obj:
                # root (or single) episode

                # default to today's date for specials if firstaired is not set
                if None is getattr(ep_info, 'firstaired', None) and 0 == ep_obj.season:
                    ep_info['firstaired'] = str(datetime.date.fromordinal(1))

                if None is getattr(ep_info, 'episodename', None) or None is getattr(ep_info, 'firstaired', None):
                    return None

                episode = rootNode

                EpisodeName = etree.SubElement(episode, "EpisodeName")
                if None is not cur_ep_obj.name:
                    EpisodeName.text = '%s' % cur_ep_obj.name
                else:
                    EpisodeName.text = ""

                EpisodeNumber = etree.SubElement(episode, "EpisodeNumber")
                EpisodeNumber.text = str(ep_obj.episode)

                if ep_obj.related_ep_obj:
                    EpisodeNumberEnd = etree.SubElement(episode, "EpisodeNumberEnd")
                    EpisodeNumberEnd.text = str(cur_ep_obj.episode)

                SeasonNumber = etree.SubElement(episode, "SeasonNumber")
                SeasonNumber.text = str(cur_ep_obj.season)

                if not ep_obj.related_ep_obj:
                    absolute_number = etree.SubElement(episode, "absolute_number")
                    if None is not getattr(ep_info, 'absolute_number', None):
                        absolute_number.text = '%s' % ep_info['absolute_number']

                FirstAired = etree.SubElement(episode, "FirstAired")
                if cur_ep_obj.airdate != datetime.date.fromordinal(1):
                    FirstAired.text = str(cur_ep_obj.airdate)
                else:
                    FirstAired.text = ""

                MetadataType = etree.SubElement(episode, "Type")
                MetadataType.text = "Episode"

                Overview = etree.SubElement(episode, "Overview")
                if None is not cur_ep_obj.description:
                    Overview.text = '%s' % cur_ep_obj.description
                else:
                    Overview.text = ""

                if not ep_obj.related_ep_obj:
                    Rating = etree.SubElement(episode, "Rating")
                    if None is not getattr(ep_info, 'rating', None):
                        Rating.text = '%s' % ep_info['rating']

                    IMDB_ID = etree.SubElement(episode, "IMDB_ID")
                    IMDB = etree.SubElement(episode, "IMDB")
                    IMDbId = etree.SubElement(episode, "IMDbId")
                    if None is not getattr(show_info, 'imdb_id', None):
                        IMDB_ID.text = '%s' % show_info['imdb_id']
                        IMDB.text = '%s' % show_info['imdb_id']
                        IMDbId.text = '%s' % show_info['imdb_id']

                prodid = etree.SubElement(episode, "id")
                prodid.text = str(cur_ep_obj.show_obj.prodid)

                tvid = etree.SubElement(episode, "indexer")
                tvid.text = str(cur_ep_obj.show_obj.tvid)

                Persons = etree.SubElement(episode, "Persons")

                Language = etree.SubElement(episode, "Language")
                try:
                    Language.text = '%s' % cur_ep_obj.show_obj.lang
                except (BaseException, Exception):
                    Language.text = 'en'  # tvrage api doesn't provide language so we must assume a value here

                thumb = etree.SubElement(episode, "filename")
                # TODO: See what this is needed for.. if its still needed
                # just write this to the NFO regardless of whether it actually exists or not
                # note: renaming files after nfo generation will break this, tough luck
                thumb_text = self.get_episode_thumb_path(ep_obj)
                if thumb_text:
                    thumb.text = '%s' % thumb_text

            else:
                # append data from (if any) related episodes
                EpisodeNumberEnd.text = str(cur_ep_obj.episode)

                if cur_ep_obj.name:
                    if not EpisodeName.text:
                        EpisodeName.text = '%s' % cur_ep_obj.name
                    else:
                        EpisodeName.text = '%s, %s' % (EpisodeName.text, cur_ep_obj.name)

                if cur_ep_obj.description:
                    if not Overview.text:
                        Overview.text = '%s' % cur_ep_obj.description
                    else:
                        Overview.text = '%s\r%s' % (Overview.text, cur_ep_obj.description)

            # collect all directors, guest stars and writers
            if None is not getattr(ep_info, 'director', None):
                persons_dict['Director'] += [x.strip() for x in ep_info['director'].split('|') if x]
            if None is not getattr(ep_info, 'gueststars', None):
                persons_dict['GuestStar'] += [x.strip() for x in ep_info['gueststars'].split('|') if x]
            if None is not getattr(ep_info, 'writer', None):
                persons_dict['Writer'] += [x.strip() for x in ep_info['writer'].split('|') if x]

        # fill in Persons section with collected directors, guest starts and writers
        for person_type, names in iteritems(persons_dict):
            # remove doubles
            names = list(set(names))
            for cur_name in names:
                Person = etree.SubElement(Persons, "Person")
                cur_person_name = etree.SubElement(Person, "Name")
                cur_person_name.text = '%s' % cur_name
                cur_person_type = etree.SubElement(Person, "Type")
                cur_person_type.text = '%s' % person_type

        helpers.indent_xml(rootNode)
        data = etree.ElementTree(rootNode)

        return data


# present a standard "interface" from the module
metadata_class = MediaBrowserMetadata
