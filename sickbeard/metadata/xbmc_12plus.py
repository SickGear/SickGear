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

from . import generic
from .. import helpers, logger
from ..indexers.indexer_exceptions import check_exception_type, ExceptionTuples
import sickbeard
import exceptions_helper
from exceptions_helper import ex
from lxml_etree import etree

from six import string_types

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, Optional, Union


class XBMC12PlusMetadata(generic.GenericMetadata):
    """
    Metadata generation class for XBMC 12+.

    The following file structure is used:

    show_root/tvshow.nfo                    (show metadata)
    show_root/fanart.jpg                    (fanart)
    show_root/poster.jpg                    (poster)
    show_root/banner.jpg                    (banner)
    show_root/Season ##/filename.ext        (*)
    show_root/Season ##/filename.nfo        (episode metadata)
    show_root/Season ##/filename-thumb.jpg  (episode thumb)
    show_root/season##-poster.jpg           (season posters)
    show_root/season##-banner.jpg           (season banners)
    show_root/season-all-poster.jpg         (season all poster)
    show_root/season-all-banner.jpg         (season all banner)
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

        self.name = 'XBMC 12+'  # type: AnyStr

        self.poster_name = 'poster.jpg'  # type: AnyStr
        self.season_all_poster_name = 'season-all-poster.jpg'  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = 'tvshow.nfo'  # type: AnyStr
        self.eg_episode_metadata = 'Season##\\<i>filename</i>.nfo'  # type: AnyStr
        self.eg_fanart = 'fanart.jpg'  # type: AnyStr
        self.eg_poster = 'poster.jpg'  # type: AnyStr
        self.eg_banner = 'banner.jpg'  # type: AnyStr
        self.eg_episode_thumbnails = 'Season##\\<i>filename</i>-thumb.jpg'  # type: AnyStr
        self.eg_season_posters = 'season##-poster.jpg'  # type: AnyStr
        self.eg_season_banners = 'season##-banner.jpg'  # type: AnyStr
        self.eg_season_all_poster = 'season-all-poster.jpg'  # type: AnyStr
        self.eg_season_all_banner = 'season-all-banner.jpg'  # type: AnyStr

    def _show_data(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for an XBMC-style tvshow.nfo and
        returns the resulting data object.

        show_obj: a TVShow instance to create the NFO for
        """

        show_id = show_obj.prodid

        show_lang = show_obj.lang
        tvinfo_config = sickbeard.TVInfoAPI(show_obj.tvid).api_params.copy()

        tvinfo_config['actors'] = True

        if show_lang and not 'en' == show_lang:
            tvinfo_config['language'] = show_lang

        if 0 != show_obj.dvdorder:
            tvinfo_config['dvdorder'] = True

        t = sickbeard.TVInfoAPI(show_obj.tvid).setup(**tvinfo_config)

        tv_node = etree.Element('tvshow')

        try:
            show_info = t[int(show_id)]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_shownotfound):
                logger.log('Unable to find show with id %s on %s, skipping it' %
                           (show_id, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
                raise

            elif check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log('%s is down, can\'t use its data to add this show' % sickbeard.TVInfoAPI(show_obj.tvid).name,
                           logger.ERROR)
                raise
            else:
                raise e

        if not self._valid_show(show_info, show_obj):
            return

        # check for title and id
        if None is getattr(show_info, 'seriesname', None) or None is getattr(show_info, 'id', None):
            logger.log('Incomplete info for show with id %s on %s, skipping it' %
                       (show_id, sickbeard.TVInfoAPI(show_obj.tvid).name), logger.ERROR)
            return False

        title = etree.SubElement(tv_node, 'title')
        if None is not getattr(show_info, 'seriesname', None):
            title.text = '%s' % show_info['seriesname']

        rating = etree.SubElement(tv_node, 'rating')
        if None is not getattr(show_info, 'rating', None):
            rating.text = '%s' % show_info['rating']

        year = etree.SubElement(tv_node, 'year')
        year_text = self.get_show_year(show_obj, show_info)
        if year_text:
            year.text = '%s' % year_text

        plot = etree.SubElement(tv_node, 'plot')
        if None is not getattr(show_info, 'overview', None):
            plot.text = '%s' % show_info['overview']

        episodeguide = etree.SubElement(tv_node, 'episodeguide')
        episodeguideurl = etree.SubElement(episodeguide, 'url')
        episodeguideurl2 = etree.SubElement(tv_node, 'episodeguideurl')
        if None is not getattr(show_info, 'id', None):
            showurl = sickbeard.TVInfoAPI(show_obj.tvid).config['base_url'] + str(show_info['id']) + '/all/en.zip'
            episodeguideurl.text = '%s' % showurl
            episodeguideurl2.text = '%s' % showurl

        mpaa = etree.SubElement(tv_node, 'mpaa')
        if None is not getattr(show_info, 'contentrating', None):
            mpaa.text = '%s' % show_info['contentrating']

        prodid = etree.SubElement(tv_node, 'id')
        if None is not getattr(show_info, 'id', None):
            prodid.text = str(show_info['id'])

        tvid = etree.SubElement(tv_node, 'indexer')
        if None is not show_obj.tvid:
            tvid.text = str(show_obj.tvid)

        genre = etree.SubElement(tv_node, 'genre')
        if None is not getattr(show_info, 'genre', None):
            if isinstance(show_info['genre'], string_types):
                genre.text = ' / '.join(x.strip() for x in show_info['genre'].split('|') if x.strip())

        premiered = etree.SubElement(tv_node, 'premiered')
        if None is not getattr(show_info, 'firstaired', None):
            premiered.text = '%s' % show_info['firstaired']

        studio = etree.SubElement(tv_node, 'studio')
        if None is not getattr(show_info, 'network', None):
            studio.text = '%s' % show_info['network']

        self.add_actor_element(show_info, etree, tv_node)

        # Make it purdy
        helpers.indent_xml(tv_node)

        data = etree.ElementTree(tv_node)

        return data

    def _ep_data(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[Union[bool, etree.Element]]
        """
        Creates an elementTree XML structure for an XBMC-style episode.nfo and
        returns the resulting data object.
            show_obj: a TVEpisode instance to create the NFO for
        """

        ep_obj_list_to_write = [ep_obj] + ep_obj.related_ep_obj

        show_lang = ep_obj.show_obj.lang

        tvinfo_config = sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).api_params.copy()

        tvinfo_config['actors'] = True

        if show_lang and not 'en' == show_lang:
            tvinfo_config['language'] = show_lang

        if 0 != ep_obj.show_obj.dvdorder:
            tvinfo_config['dvdorder'] = True

        try:
            t = sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).setup(**tvinfo_config)
            show_info = t[ep_obj.show_obj.prodid]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_shownotfound):
                raise exceptions_helper.ShowNotFoundException(ex(e))
            elif check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log('Unable to connect to %s while creating meta files - skipping - %s' %
                           (sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name, ex(e)), logger.ERROR)
                return
            else:
                raise e

        if not self._valid_show(show_info, ep_obj.show_obj):
            return

        if 1 < len(ep_obj_list_to_write):
            rootNode = etree.Element('xbmcmultiepisode')
        else:
            rootNode = etree.Element('episodedetails')

        # write an NFO containing info for all matching episodes
        for cur_ep_obj in ep_obj_list_to_write:

            try:
                ep_info = show_info[cur_ep_obj.season][cur_ep_obj.episode]
            except Exception as e:
                if check_exception_type(e, ExceptionTuples.tvinfo_episodenotfound,
                                        ExceptionTuples.tvinfo_seasonnotfound):
                    logger.log('Unable to find episode %sx%s on %s.. has it been removed? Should I delete from db?' %
                               (cur_ep_obj.season, cur_ep_obj.episode, sickbeard.TVInfoAPI(ep_obj.show_obj.tvid).name))
                    return None
                else:
                    logger.log(u'Not generating nfo because failed to fetched tv info data at this time', logger.DEBUG)
                    return None

            if None is getattr(ep_info, 'firstaired', None):
                ep_info['firstaired'] = str(datetime.date.fromordinal(1))

            if None is getattr(ep_info, 'episodename', None):
                logger.log(u'Not generating nfo because the ep has no title', logger.DEBUG)
                return None

            logger.log(u'Creating metadata for episode ' + str(ep_obj.season) + 'x' + str(ep_obj.episode), logger.DEBUG)

            if 1 < len(ep_obj_list_to_write):
                episode = etree.SubElement(rootNode, 'episodedetails')
            else:
                episode = rootNode

            title = etree.SubElement(episode, 'title')
            if None is not cur_ep_obj.name:
                title.text = '%s' % cur_ep_obj.name

            showtitle = etree.SubElement(episode, 'showtitle')
            if None is not cur_ep_obj.show_obj.name:
                showtitle.text = '%s' % cur_ep_obj.show_obj.name

            season = etree.SubElement(episode, 'season')
            season.text = str(cur_ep_obj.season)

            episodenum = etree.SubElement(episode, 'episode')
            episodenum.text = str(cur_ep_obj.episode)

            uniqueid = etree.SubElement(episode, 'uniqueid')
            uniqueid.text = str(cur_ep_obj.epid)

            aired = etree.SubElement(episode, 'aired')
            if cur_ep_obj.airdate != datetime.date.fromordinal(1):
                aired.text = str(cur_ep_obj.airdate)
            else:
                aired.text = ''

            plot = etree.SubElement(episode, 'plot')
            if None is not cur_ep_obj.description:
                plot.text = '%s' % cur_ep_obj.description

            runtime = etree.SubElement(episode, 'runtime')
            if 0 != cur_ep_obj.season:
                if None is not getattr(show_info, 'runtime', None):
                    runtime.text = '%s' % show_info['runtime']

            displayseason = etree.SubElement(episode, 'displayseason')
            if None is not getattr(ep_info, 'airsbefore_season', None):
                displayseason_text = ep_info['airsbefore_season']
                if None is not displayseason_text:
                    displayseason.text = '%s' % displayseason_text

            displayepisode = etree.SubElement(episode, 'displayepisode')
            if None is not getattr(ep_info, 'airsbefore_episode', None):
                displayepisode_text = ep_info['airsbefore_episode']
                if None is not displayepisode_text:
                    displayepisode.text = '%s' % displayepisode_text

            thumb = etree.SubElement(episode, 'thumb')
            thumb_text = getattr(ep_info, 'filename', None)
            if None is not thumb_text:
                thumb.text = '%s' % thumb_text

            watched = etree.SubElement(episode, 'watched')
            watched.text = 'false'

            credits = etree.SubElement(episode, 'credits')
            credits_text = getattr(ep_info, 'writer', None)
            if None is not credits_text:
                credits.text = '%s' % credits_text

            director = etree.SubElement(episode, 'director')
            director_text = getattr(ep_info, 'director', None)
            if None is not director_text:
                director.text = '%s' % director_text

            rating = etree.SubElement(episode, 'rating')
            rating_text = getattr(ep_info, 'rating', None)
            if None is not rating_text:
                rating.text = '%s' % rating_text

            gueststar_text = getattr(ep_info, 'gueststars', None)
            if isinstance(gueststar_text, string_types):
                for actor in (x.strip() for x in gueststar_text.split('|') if x.strip()):
                    cur_actor = etree.SubElement(episode, 'actor')
                    cur_actor_name = etree.SubElement(cur_actor, 'name')
                    cur_actor_name.text = '%s' % actor

            self.add_actor_element(show_info, etree, episode)

        # Make it purdy
        helpers.indent_xml(rootNode)

        data = etree.ElementTree(rootNode)

        return data

    @staticmethod
    def add_actor_element(show_info, et, node):
        # type: (Dict, etree, etree.Element) -> None
        for actor in getattr(show_info, 'actors', []):
            cur_actor = et.SubElement(node, 'actor')

            cur_actor_name = et.SubElement(cur_actor, 'name')
            cur_actor_name_text = actor['person']['name']
            if cur_actor_name_text:
                cur_actor_name.text = '%s' % cur_actor_name_text

            cur_actor_role = et.SubElement(cur_actor, 'role')
            cur_actor_role_text = actor['character']['name']
            if cur_actor_role_text:
                cur_actor_role.text = '%s' % cur_actor_role_text

            cur_actor_thumb = et.SubElement(cur_actor, 'thumb')
            cur_actor_thumb_text = actor['character']['image']
            if None is not cur_actor_thumb_text:
                cur_actor_thumb.text = '%s' % cur_actor_thumb_text


# present a standard 'interface' from the module
metadata_class = XBMC12PlusMetadata
