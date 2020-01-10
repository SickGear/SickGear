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

from . import mediabrowser
from .. import helpers, logger
from ..indexers.indexer_exceptions import check_exception_type, ExceptionTuples
import sickbeard
import exceptions_helper
from exceptions_helper import ex
from lxml_etree import etree

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, Optional, Union


class Mede8erMetadata(mediabrowser.MediaBrowserMetadata):
    """
    Metadata generation class for Mede8er based on the MediaBrowser.

    The following file structure is used:

    show_root/series.xml                    (show metadata)
    show_root/folder.jpg                    (poster)
    show_root/fanart.jpg                    (fanart)
    show_root/Season ##/folder.jpg          (season thumb)
    show_root/Season ##/filename.ext        (*)
    show_root/Season ##/filename.xml        (episode metadata)
    show_root/Season ##/filename.jpg        (episode thumb)
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

        mediabrowser.MediaBrowserMetadata.__init__(
            self,
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

        self.name = 'Mede8er'  # type: AnyStr

        self.fanart_name = 'fanart.jpg'  # type: AnyStr

        # web-ui metadata template
        # self.eg_show_metadata = 'series.xml'
        self.eg_episode_metadata = 'Season##\\<i>filename</i>.xml'  # type: AnyStr
        self.eg_fanart = 'fanart.jpg'  # type: AnyStr
        # self.eg_poster = 'folder.jpg'
        # self.eg_banner = 'banner.jpg'
        self.eg_episode_thumbnails = 'Season##\\<i>filename</i>.jpg'  # type: AnyStr
        # self.eg_season_posters = 'Season##\\folder.jpg'
        # self.eg_season_banners = 'Season##\\banner.jpg'
        # self.eg_season_all_poster = '<i>not supported</i>'
        # self.eg_season_all_banner = '<i>not supported</i>'

    def get_episode_file_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> AnyStr
        return helpers.replace_extension(ep_obj.location, self._ep_nfo_extension)

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> AnyStr
        return helpers.replace_extension(ep_obj.location, 'jpg')

    def _show_data(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for a MediaBrowser-style series.xml
        returns the resulting data object.

        show_obj: a TVShow instance to create the NFO for
        """

        show_lang = show_obj.lang
        tvinfo_config = sickbeard.TVInfoAPI(show_obj.tvid).api_params.copy()

        tvinfo_config['actors'] = True

        if show_lang and not 'en' == show_lang:
            tvinfo_config['language'] = show_lang

        if 0 != show_obj.dvdorder:
            tvinfo_config['dvdorder'] = True

        t = sickbeard.TVInfoAPI(show_obj.tvid).setup(**tvinfo_config)

        rootNode = etree.Element('details')
        tv_node = etree.SubElement(rootNode, 'movie')
        tv_node.attrib['isExtra'] = 'false'
        tv_node.attrib['isSet'] = 'false'
        tv_node.attrib['isTV'] = 'true'

        try:
            show_info = t[int(show_obj.prodid)]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_shownotfound):
                logger.log(u'Unable to find show with id ' + str(show_obj.prodid) + ' on tvdb, skipping it', logger.ERROR)
                raise

            elif check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log(u'TVDB is down, can\'t use its data to make the NFO', logger.ERROR)
                raise
            else:
                raise e

        if not self._valid_show(show_info, show_obj):
            return

        # check for title and id
        try:
            if None is show_info['seriesname'] \
                    or '' == show_info['seriesname'] \
                    or None is show_info['id'] \
                    or '' == show_info['id']:
                logger.log('Incomplete info for show with id %s on %s, skipping it' %
                           (show_obj.prodid, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
                return False
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_attributenotfound):
                logger.log('Incomplete info for show with id %s on %s, skipping it' %
                           (show_obj.prodid, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
                return False
            else:
                raise e

        SeriesName = etree.SubElement(tv_node, 'title')
        if None is not show_info['seriesname']:
            SeriesName.text = '%s' % show_info['seriesname']
        else:
            SeriesName.text = ''

        Genres = etree.SubElement(tv_node, 'genres')
        if None is not show_info['genre']:
            for genre in show_info['genre'].split('|'):
                if genre and genre.strip():
                    cur_genre = etree.SubElement(Genres, 'Genre')
                    cur_genre.text = '%s' % genre.strip()

        FirstAired = etree.SubElement(tv_node, 'premiered')
        if None is not show_info['firstaired']:
            FirstAired.text = '%s' % show_info['firstaired']

        year = etree.SubElement(tv_node, 'year')
        year_text = self.get_show_year(show_obj, show_info)
        if year_text:
            year.text = '%s' % year_text

        if None is not show_info['rating']:
            try:
                rating = int((float(show_info['rating']) * 10))
            except ValueError:
                rating = 0
            Rating = etree.SubElement(tv_node, 'rating')
            rating_text = str(rating)
            if None is not rating_text:
                Rating.text = '%s' % rating_text

        Status = etree.SubElement(tv_node, 'status')
        if None is not show_info['status']:
            Status.text = '%s' % show_info['status']

        mpaa = etree.SubElement(tv_node, 'mpaa')
        if None is not show_info['contentrating']:
            mpaa.text = '%s' % show_info['contentrating']

        IMDB_ID = etree.SubElement(tv_node, 'id')
        if None is not show_info['imdb_id']:
            IMDB_ID.attrib['moviedb'] = 'imdb'
            IMDB_ID.text = '%s' % show_info['imdb_id']

        prodid = etree.SubElement(tv_node, 'indexerid')
        if None is not show_info['id']:
            prodid.text = '%s' % show_info['id']

        Runtime = etree.SubElement(tv_node, 'runtime')
        if None is not show_info['runtime']:
            Runtime.text = '%s' % show_info['runtime']

        cast = etree.SubElement(tv_node, 'cast')
        self.add_actor_element(show_info, etree, cast)

        helpers.indent_xml(rootNode)

        data = etree.ElementTree(rootNode)

        return data

    def _ep_data(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for a MediaBrowser style episode.xml
        and returns the resulting data object.

        show_obj: a TVShow instance to create the NFO for
        """

        ep_obj_list_to_write = [ep_obj] + ep_obj.related_ep_obj

        show_lang = ep_obj.show_obj.lang

        try:
            # There's gotta be a better way of doing this but we don't wanna
            # change the language value elsewhere
            tvinfo_config = sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).api_params.copy()

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
                logger.log('Unable to connect to %s while creating meta files - skipping - %s' %
                           (sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name, ex(e)), logger.ERROR)
                return False
            else:
                raise e

        if not self._valid_show(show_info, ep_obj.show_obj):
            return

        rootNode = etree.Element('details')
        movie = etree.SubElement(rootNode, 'movie')

        movie.attrib['isExtra'] = 'false'
        movie.attrib['isSet'] = 'false'
        movie.attrib['isTV'] = 'true'

        # write an MediaBrowser XML containing info for all matching episodes
        for cur_ep_obj in ep_obj_list_to_write:

            try:
                ep_info = show_info[cur_ep_obj.season][cur_ep_obj.episode]
            except (BaseException, Exception):
                logger.log(u'Unable to find episode %sx%s on tvdb... has it been removed? Should I delete from db?' %
                           (cur_ep_obj.season, cur_ep_obj.episode))
                return None

            if cur_ep_obj == ep_obj:
                # root (or single) episode

                # default to today's date for specials if firstaired is not set
                if None is ep_info['firstaired'] and 0 == ep_obj.season:
                    ep_info['firstaired'] = str(datetime.date.fromordinal(1))

                if None is ep_info['episodename'] or None is ep_info['firstaired']:
                    return None

                episode = movie

                EpisodeName = etree.SubElement(episode, 'title')
                if None is not cur_ep_obj.name:
                    EpisodeName.text = '%s' % cur_ep_obj.name
                else:
                    EpisodeName.text = ''

                SeasonNumber = etree.SubElement(episode, 'season')
                SeasonNumber.text = str(cur_ep_obj.season)

                EpisodeNumber = etree.SubElement(episode, 'episode')
                EpisodeNumber.text = str(ep_obj.episode)

                year = etree.SubElement(episode, 'year')
                year_text = self.get_show_year(ep_obj.show_obj, show_info)
                if year_text:
                    year.text = '%s' % year_text

                plot = etree.SubElement(episode, 'plot')
                if None is not show_info['overview']:
                    plot.text = '%s' % show_info['overview']

                Overview = etree.SubElement(episode, 'episodeplot')
                if None is not cur_ep_obj.description:
                    Overview.text = '%s' % cur_ep_obj.description
                else:
                    Overview.text = ''

                mpaa = etree.SubElement(episode, 'mpaa')
                if None is not show_info['contentrating']:
                    mpaa.text = '%s' % show_info['contentrating']

                if not ep_obj.related_ep_obj:
                    if None is not ep_info['rating']:
                        try:
                            rating = int((float(ep_info['rating']) * 10))
                        except ValueError:
                            rating = 0
                        Rating = etree.SubElement(episode, 'rating')
                        rating_text = str(rating)
                        if None is not rating_text:
                            Rating.text = '%s' % rating_text

                director = etree.SubElement(episode, 'director')
                director_text = ep_info['director']
                if None is not director_text:
                    director.text = '%s' % director_text

                credits = etree.SubElement(episode, 'credits')
                credits_text = ep_info['writer']
                if None is not credits_text:
                    credits.text = '%s' % credits_text

                cast = etree.SubElement(episode, 'cast')
                self.add_actor_element(show_info, etree, cast)

            else:
                # append data from (if any) related episodes

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

        helpers.indent_xml(rootNode)
        data = etree.ElementTree(rootNode)

        return data

    @staticmethod
    def add_actor_element(show_info, et, node):
        # type: (Dict, etree, etree.Element) -> None
        for actor in getattr(show_info, 'actors', []):
            cur_actor_name_text = actor['character']['name'] and actor['person']['name'] \
                                  and actor['character']['name'] != actor['person']['name'] \
                                  and '%s (%s)' % (actor['character']['name'], actor['person']['name']) \
                                  or actor['person']['name'] or actor['character']['name']
            if cur_actor_name_text:
                cur_actor = et.SubElement(node, 'actor')
                cur_actor.text = '%s' % cur_actor_name_text


# present a standard "interface" from the module
metadata_class = Mede8erMetadata
