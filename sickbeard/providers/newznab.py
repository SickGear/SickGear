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

from __future__ import division
# from collections import OrderedDict
from io import BytesIO
from math import ceil

import datetime
import re
import time

import sickbeard
from . import generic
from .. import classes, db, helpers, logger, tvcache
from ..classes import SearchResult
from ..common import NeededQualities, Quality
from ..helpers import remove_non_release_groups
from ..indexers.indexer_config import *
from ..network_timezones import SG_TIMEZONE
from ..sgdatetime import SGDatetime, timestamp_near
from ..search import get_aired_in_season, get_wanted_qualities
from ..show_name_helpers import get_show_names
from ..scene_exceptions import has_season_exceptions
from ..tv import TVEpisode, TVShow

from lib.dateutil import parser
from lib.sg_helpers import md5_for_text, try_int
from exceptions_helper import AuthException, ex, MultipleShowObjectsException
from lxml_etree import etree

from six import iteritems, itervalues, string_types
from _23 import urlencode

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Tuple, Union


class NewznabConstants(object):
    SEARCH_TEXT = -100
    SEARCH_SEASON = -101
    SEARCH_EPISODE = -102

    CAT_SD = -200
    CAT_HD = -201
    CAT_UHD = -202
    CAT_HEVC = -203
    CAT_ANIME = -204
    CAT_SPORT = -205
    CAT_WEBDL = -206

    catSearchStrings = {r'^Anime$': CAT_ANIME,
                        r'^Sport$': CAT_SPORT,
                        r'^SD$': CAT_SD,
                        r'^BoxSD$': CAT_SD,
                        r'^HD$': CAT_HD,
                        r'^BoxHD$': CAT_HD,
                        r'^UHD$': CAT_UHD,
                        r'^4K$': CAT_UHD,
                        # r'^HEVC$': CAT_HEVC,
                        r'^WEB.?DL$': CAT_WEBDL}

    providerToIndexerMapping = {'tvdbid': TVINFO_TVDB,
                                'rageid': TVINFO_TVRAGE,
                                'tvmazeid': TVINFO_TVMAZE,
                                'imdbid': TVINFO_IMDB,
                                'tmdbid': TVINFO_TMDB,
                                'traktid': TVINFO_TRAKT}

    indexer_priority_list = [TVINFO_TVDB, TVINFO_TVMAZE, TVINFO_TVRAGE, TVINFO_TRAKT, TVINFO_TMDB, TVINFO_TMDB]

    searchTypes = {'rid': TVINFO_TVRAGE,
                   'tvdbid': TVINFO_TVDB,
                   'tvmazeid': TVINFO_TVMAZE,
                   'imdbid': TVINFO_IMDB,
                   'tmdbid': TVINFO_TMDB,
                   'traktid': TVINFO_TRAKT,
                   'q': SEARCH_TEXT,
                   'season': SEARCH_SEASON,
                   'ep': SEARCH_EPISODE}

    SERVER_DEFAULT = 0
    SERVER_SPOTWEB = 1
    SERVER_HYDRA1 = 2
    SERVER_HYDRA2 = 3

    server_types = {SERVER_DEFAULT: 'newznab',
                    SERVER_SPOTWEB: 'spotweb',
                    SERVER_HYDRA1: 'NZBHydra',
                    SERVER_HYDRA2: 'NZBHydra 2'}

    # md5_for_text values
    custom_server_types = {SERVER_SPOTWEB: ('720db6d19d02339e9c320dd788291136',)}

    def __init__(self):
        pass


class NewznabProvider(generic.NZBProvider):

    def __init__(self,
                 name,  # type: AnyStr
                 url,  # type: AnyStr
                 key='',  # type: AnyStr
                 cat_ids=None,  # type: Union[List, AnyStr]
                 search_mode=None,  # type: AnyStr
                 search_fallback=False,  # type: bool
                 enable_recentsearch=False,  # type: bool
                 enable_backlog=False,  # type: bool
                 enable_scheduled_backlog=False,  # type: bool
                 server_type=None  # type: Union[int, None]
                 ):
        """

        :param name: provider name
        :param url: url
        :param key:
        :param cat_ids:
        :param search_mode:
        :param search_fallback:
        :param enable_recentsearch:
        :param enable_backlog:
        :param enable_scheduled_backlog:
        :param server_type:
        """
        generic.NZBProvider.__init__(self, name, True, False)

        self.url = url
        self.key = key
        self.server_type = try_int(server_type, None) or NewznabConstants.SERVER_DEFAULT
        self._exclude = set()
        self.cat_ids = cat_ids or ''
        self.search_mode = search_mode or 'eponly'
        self.search_fallback = bool(try_int(search_fallback))
        self.enable_recentsearch = bool(try_int(enable_recentsearch))
        self.enable_backlog = bool(try_int(enable_backlog))
        self.enable_scheduled_backlog = bool(try_int(enable_scheduled_backlog, 1))
        self.needs_auth = '0' != self.key.strip()  # '0' in the key setting indicates that api_key is not needed
        self.default = False
        self._caps = {}
        self._caps_cats = {}
        self._caps_all_cats = []
        self._caps_need_apikey = {'need': False, 'date': datetime.date.fromordinal(1)}
        self._limits = 100
        self._last_recent_search = None
        self._caps_last_updated = datetime.datetime.fromordinal(1)
        self.cache = NewznabCache(self)
        # filters
        # deprecated; kept here as bookmark for new haspretime:0|1 + nuked:0|1 can be used here instead
        # if super(NewznabProvider, self).get_id() in ('nzbs_org',):
        #     self.filter = []
        #     if 'nzbs_org' == super(NewznabProvider, self).get_id():
        #         self.may_filter = OrderedDict([
        #             ('so', ('scene only', False)), ('snn', ('scene not nuked', False))])

    @property
    def cat_ids(self):
        return self._cat_ids

    @cat_ids.setter
    def cat_ids(self, cats):
        self._cat_ids = self.clean_newznab_categories(cats)

    @property
    def caps(self):
        self.check_cap_update()
        return self._caps

    @property
    def cats(self):
        self.check_cap_update()
        return self._caps_cats

    @property
    def excludes(self):
        self.check_cap_update()
        return self._exclude

    @property
    def all_cats(self):
        self.check_cap_update()
        return self._caps_all_cats

    @property
    def limits(self):
        self.check_cap_update()
        return self._limits

    @property
    def last_recent_search(self):
        if not self._last_recent_search:
            try:
                my_db = db.DBConnection('cache.db')
                res = my_db.select('SELECT' + ' "datetime" FROM "lastrecentsearch" WHERE "name"=?', [self.get_id()])
                if res:
                    self._last_recent_search = SGDatetime.from_timestamp(int(res[0]['datetime']))
            except (BaseException, Exception):
                pass
        return self._last_recent_search

    @last_recent_search.setter
    def last_recent_search(self, value):
        try:
            my_db = db.DBConnection('cache.db')
            if isinstance(value, datetime.datetime):
                save_value = int(timestamp_near(value))
            else:
                save_value = SGDatetime.timestamp_far(value, default=0)
            my_db.action('INSERT OR REPLACE INTO "lastrecentsearch" (name, datetime) VALUES (?,?)',
                         [self.get_id(), save_value])
        except (BaseException, Exception):
            pass
        self._last_recent_search = value

    def image_name(self):
        """
        :rtype: AnyStr
        """
        if self.server_type not in (NewznabConstants.SERVER_DEFAULT, NewznabConstants.SERVER_SPOTWEB):
            return 'warning16.png'
        return generic.GenericProvider.image_name(
            self, ('newznab', 'spotweb')[self.server_type == NewznabConstants.SERVER_SPOTWEB])

    def check_cap_update(self):
        if self.enabled and \
                (not self._caps or (datetime.datetime.now() - self._caps_last_updated) >= datetime.timedelta(days=1)):
            self.get_caps()

    def _get_caps_data(self):
        xml_caps = None
        if self.enabled:
            if datetime.date.today() - self._caps_need_apikey['date'] > datetime.timedelta(days=30) or \
                    not self._caps_need_apikey['need']:
                self._caps_need_apikey['need'] = False
                data = self.get_url('%s/api?t=caps' % self.url)
                if data:
                    xml_caps = helpers.parse_xml(data)
            if None is xml_caps or not hasattr(xml_caps, 'tag') or 'error' == xml_caps.tag or 'caps' != xml_caps.tag:
                api_key = self.maybe_apikey()
                if isinstance(api_key, string_types) and api_key not in ('0', ''):
                    data = self.get_url('%s/api?t=caps&apikey=%s' % (self.url, api_key))
                    if data:
                        xml_caps = helpers.parse_xml(data)
                        if None is not xml_caps and 'caps' == getattr(xml_caps, 'tag', ''):
                            self._caps_need_apikey = {'need': True, 'date': datetime.date.today()}
        return xml_caps

    def _check_excludes(self,
                        cats  # type: Union[Dict, List]
                        ):
        if isinstance(cats, dict):
            c = []
            for v in itervalues(cats):
                c.extend(v)
            self._exclude = set(c)
        else:
            self._exclude = set([v for v in cats])

    def get_caps(self):
        caps = {}
        cats = {}
        all_cats = []
        xml_caps = self._get_caps_data()
        old_api = False
        if None is not xml_caps:
            server_node = xml_caps.find('.//server')
            if None is not server_node:
                if NewznabConstants.server_types.get(NewznabConstants.SERVER_SPOTWEB) in \
                        (server_node.get('type', '') or server_node.get('title', '')).lower() \
                        or (md5_for_text(server_node.get('type', '')) in
                            NewznabConstants.custom_server_types.get(NewznabConstants.SERVER_SPOTWEB)):
                    self.server_type = NewznabConstants.SERVER_SPOTWEB
                elif 'nzbhydra 2' in server_node.get('title', '').lower() or \
                        'nzbhydra2' in server_node.get('url', '').lower():
                    self.server_type = NewznabConstants.SERVER_HYDRA2
                elif 'nzbhydra' == server_node.get('title', '').lower().strip() or \
                        server_node.get('url', '').lower().strip().endswith('nzbhydra'):
                    self.server_type = NewznabConstants.SERVER_HYDRA1
                else:
                    self.server_type = NewznabConstants.SERVER_DEFAULT

            tv_search = xml_caps.find('.//tv-search')
            if None is not tv_search:
                for c in [i for i in tv_search.get('supportedParams', '').split(',')]:
                    k = NewznabConstants.searchTypes.get(c)
                    if k:
                        caps[k] = c
                # for very old newznab, just add text search as only option
                if not tv_search.get('supportedParams'):
                    caps[NewznabConstants.searchTypes['q']] = 'q'
                    old_api = True

            limit = xml_caps.find('.//limits')
            if None is not limit:
                lim = try_int(limit.get('max'), 100)
                self._limits = (100, lim)[100 <= lim]

            try:
                for category in xml_caps.iter('category'):
                    if 'TV' == category.get('name'):
                        for subcat in category.findall('subcat'):
                            try:
                                cat_name = subcat.attrib['name']
                                cat_id = subcat.attrib['id']
                                all_cats.append({'id': cat_id, 'name': cat_name})
                                for s, v in iteritems(NewznabConstants.catSearchStrings):
                                    if None is not re.search(s, cat_name, re.IGNORECASE):
                                        cats.setdefault(v, []).append(cat_id)
                            except (BaseException, Exception):
                                continue
                    elif category.get('name', '').upper() in ['XXX', 'OTHER', 'MISC']:
                        for subcat in category.findall('subcat'):
                            try:
                                if None is not re.search(r'^Anime$', subcat.attrib['name'], re.IGNORECASE):
                                    cats.setdefault(NewznabConstants.CAT_ANIME, []).append(subcat.attrib['id'])
                                    break
                            except (BaseException, Exception):
                                continue
            except (BaseException, Exception):
                logger.log('Error parsing result for [%s]' % self.name, logger.DEBUG)

        if not caps and self._caps and not all_cats and self._caps_all_cats and not cats and self._caps_cats:
            self._check_excludes(cats)
            return

        if self.enabled:
            self._caps_last_updated = datetime.datetime.now()

        if not old_api and (self.url and 'nzbplanet.net' not in self.url.lower()):
            if not caps:
                caps[TVINFO_TVDB] = 'tvdbid'
            if NewznabConstants.SEARCH_SEASON not in caps or not caps.get(NewznabConstants.SEARCH_SEASON):
                caps[NewznabConstants.SEARCH_SEASON] = 'season'
            if NewznabConstants.SEARCH_EPISODE not in caps or not caps.get(NewznabConstants.SEARCH_EPISODE):
                caps[NewznabConstants.SEARCH_TEXT] = 'ep'
            if (TVINFO_TVRAGE not in caps or not caps.get(TVINFO_TVRAGE)):
                caps[TVINFO_TVRAGE] = 'rid'
        if NewznabConstants.SEARCH_TEXT not in caps or not caps.get(NewznabConstants.SEARCH_TEXT):
            caps[NewznabConstants.SEARCH_TEXT] = 'q'

        if NewznabConstants.CAT_HD not in cats or not cats.get(NewznabConstants.CAT_HD):
            cats[NewznabConstants.CAT_HD] = ['5040']  # (['5040'], ['5040', '5090'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_SD not in cats or not cats.get(NewznabConstants.CAT_SD):
            cats[NewznabConstants.CAT_SD] = ['5030']  # (['5030'], ['5030', '5070'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_ANIME not in cats or not cats.get(NewznabConstants.CAT_ANIME):
            cats[NewznabConstants.CAT_ANIME] = ['5070']  # (['5070'], ['6070', '7040'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_SPORT not in cats or not cats.get(NewznabConstants.CAT_SPORT):
            cats[NewznabConstants.CAT_SPORT] = ['5060']

        self._check_excludes(cats)
        self._caps = caps
        self._caps_cats = cats
        self._caps_all_cats = all_cats

    def clean_newznab_categories(self,
                                 cats  # type: Union[List, AnyStr]
                                 ):  # type: (...) -> Union[List, AnyStr]
        """
        Removes automatically mapped categories from the list
        :param cats:
        :return:
        """
        if isinstance(cats, list):
            return [x for x in cats if x['id'] not in self.excludes]
        return ','.join(set(cats.split(',')) - self.excludes)

    def _check_auth(self, is_required=None):
        if self.should_skip():
            return False
        return super(NewznabProvider, self)._check_auth(is_required)

    def _check_auth_from_data(self,
                              data,  # type: etree.Element
                              url  # type: AnyStr
                              ):  # type: (...) -> bool
        """

        :param data:
        :param url:
        :return:
        """
        if None is data or not hasattr(data, 'tag'):
            return False

        if 'error' == data.tag:
            code = try_int(data.get('code'))
            description = data.get('description') or ''
            msg = ('', ': %s' % description)[bool(description)]

            if code not in (100, 101, 102, 401, 429, 500, 910):
                logger.warning('Unknown error given from %s%s' % (self.name, msg))
            else:
                if 100 == code:
                    raise AuthException('API key for %s is incorrect, check your config' % self.name)
                elif 101 == code:
                    raise AuthException('Account suspended on %s, contact the admin' % self.name)
                elif 401 == code:
                    logger.warning('Error code 401 (Unauthorized) from provider%s' % msg)
                    raise AuthException('Account disabled on %s (code 401), contact the admin%s' % (self.name, msg))
                elif code in (102, 429, 500):
                    try:
                        retry_time, unit = re.findall(r'(?i)(?:Try again|Retry) in (\d+)\W+([a-z]+)', description)[0]
                    except IndexError:
                        retry_time, unit = None, None
                    handle_fail = True
                    if 102 == code:
                        handle_fail = ('limit' in description.lower()) or (retry_time and unit)
                        if not handle_fail:
                            raise AuthException(
                                'Your account isn\'t allowed to use the %s API, contact the admin%s' %
                                (self.name, ('', '. Provider message: %s' % description)[bool(description)]))
                    if handle_fail:
                        self.tmr_limit_update(retry_time, unit, description)
                        self.log_failure_url(url)
                elif 910 == code:
                    logger.warning('%s %s, please check with provider' %
                                   (self.name, ('currently has their API disabled', description)[bool(description)]))
            return False

        self.tmr_limit_count = 0
        return True

    def config_str(self):
        # type: (...) -> AnyStr
        return '%s|%s|%s|%s|%i|%s|%i|%i|%i|%i|%i' \
               % (self.name or '', self.url or '', self.maybe_apikey() or '', self.cat_ids or '', self.enabled,
                  self.search_mode or '', self.search_fallback, getattr(self, 'enable_recentsearch', False),
                  getattr(self, 'enable_backlog', False), getattr(self, 'enable_scheduled_backlog', False),
                  self.server_type)

    def _season_strings(self,
                        ep_obj  # type: TVEpisode
                        ):  # type: (...) -> List[Dict[AnyStr, List[AnyStr]]]
        """

        :param ep_obj: episode object
        :return:
        """
        search_params = []
        base_params = {}

        # season
        ep_detail = None
        if ep_obj.show_obj.air_by_date or ep_obj.show_obj.is_sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            base_params['season'] = airdate
            base_params['q'] = airdate
            if ep_obj.show_obj.air_by_date:
                ep_detail = '+"%s"' % airdate
        elif ep_obj.show_obj.is_anime:
            base_params['season'] = '%d' % ep_obj.scene_absolute_number
        else:
            base_params['season'] = str((ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show_obj.is_scene)])
            ep_detail = 'S%02d' % try_int(base_params['season'], 1)

        # id search
        params = base_params.copy()
        use_id = False
        if not has_season_exceptions(ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season):
            for i in sickbeard.TVInfoAPI().all_sources:
                if i in ep_obj.show_obj.ids and 0 < ep_obj.show_obj.ids[i]['id'] and i in self.caps:
                    params[self.caps[i]] = ep_obj.show_obj.ids[i]['id']
                    use_id = True
            use_id and search_params.append(params)

        spacer = 'nzbgeek.info' in self.url.lower() and ' ' or '.'
        # query search and exceptions
        name_exceptions = get_show_names(ep_obj, spacer)
        for cur_exception in name_exceptions:
            params = base_params.copy()
            if 'q' in params:
                params['q'] = '%s%s%s' % (cur_exception, spacer, params['q'])
                search_params.append(params)

            if ep_detail:
                params = base_params.copy()
                params['q'] = '%s%s%s' % (cur_exception, spacer, ep_detail)
                'season' in params and params.pop('season')
                'ep' in params and params.pop('ep')
                search_params.append(params)

        return [{'Season': search_params}]

    def _episode_strings(self,
                         ep_obj  # type: TVEpisode
                         ):  # type: (...) -> List[Dict[AnyStr, List[AnyStr]]]
        """

        :param ep_obj: episode object
        :return:
        """
        search_params = []
        base_params = {}

        if not ep_obj:
            return [base_params]

        ep_detail = None
        if ep_obj.show_obj.air_by_date or ep_obj.show_obj.is_sports:
            airdate = str(ep_obj.airdate).split('-')
            base_params['season'] = airdate[0]
            if ep_obj.show_obj.air_by_date:
                base_params['ep'] = '/'.join(airdate[1:])
                ep_detail = '+"%s.%s"' % (base_params['season'], '.'.join(airdate[1:]))
        elif ep_obj.show_obj.is_anime:
            base_params['ep'] = '%i' % (try_int(ep_obj.scene_absolute_number) or try_int(ep_obj.scene_episode))
            ep_detail = '%02d' % try_int(base_params['ep'])
        else:
            base_params['season'], base_params['ep'] = (
                (ep_obj.season, ep_obj.episode), (ep_obj.scene_season, ep_obj.scene_episode))[ep_obj.show_obj.is_scene]
            ep_detail = sickbeard.config.naming_ep_type[2] % {
                'seasonnumber': try_int(base_params['season'], 1), 'episodenumber': try_int(base_params['ep'], 1)}

        # id search
        params = base_params.copy()
        use_id = False
        if not has_season_exceptions(ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season):
            for i in sickbeard.TVInfoAPI().all_sources:
                if i in ep_obj.show_obj.ids and 0 < ep_obj.show_obj.ids[i]['id'] and i in self.caps:
                    params[self.caps[i]] = ep_obj.show_obj.ids[i]['id']
                    use_id = True
            use_id and search_params.append(params)

        spacer = 'nzbgeek.info' in self.url.lower() and ' ' or '.'
        # query search and exceptions
        name_exceptions = get_show_names(ep_obj, spacer)
        if sickbeard.scene_exceptions.has_abs_episodes(ep_obj):
            search_params.append({'q': '%s%s%s' % (ep_obj.show_obj.name, spacer, base_params['ep'])})
        for cur_exception in name_exceptions:
            params = base_params.copy()
            params['q'] = cur_exception
            search_params.append(params)

            if ep_detail:
                params = base_params.copy()
                params['q'] = '%s%s%s' % (cur_exception, spacer, ep_detail)
                'season' in params and params.pop('season')
                'ep' in params and params.pop('ep')
                search_params.append(params)

        return [{'Episode': search_params}]

    def _title_and_url(self,
                       item  # type: etree.Element
                       ):  # type: (...) -> Union[Tuple[AnyStr, AnyStr], Tuple[None, None]]
        """

        :param item:
        :return:
        :rtype: Tuple[AnyStr, AnyStr] or Tuple[None, None]
        """
        title, url = None, None
        try:
            url = str(item.findtext('link')).replace('&amp;', '&')
            title = ('%s' % item.findtext('title')).strip()
            title = re.sub(r'\s+', '.', title)
            # remove indexer specific release name parts
            r_found = True
            while r_found:
                r_found = False
                for pattern, repl in ((r'(?i)-Scrambled$', ''), (r'(?i)-BUYMORE$', ''), (r'(?i)-Obfuscated$', ''),
                                      (r'(?i)-postbot$', ''), (r'(?i)[-.]English$', '')):
                    if re.search(pattern, title):
                        r_found = True
                        title = re.sub(pattern, repl, title)
            parts = re.findall('(.*(?:(?:h.?|x)26[45]|vp9|av1|hevc|xvid|divx)[^-]*)(.*)', title, re.I)[0]
            title = '%s-%s' % (parts[0], remove_non_release_groups(parts[1].split('-')[1]))
        except (BaseException, Exception):
            pass

        return title, url

    def get_size_uid(self,
                     item,  # type: etree.Element
                     **kwargs
                     ):  # type: (...) -> Tuple[int, Union[AnyStr, None]]
        """

        :param item:
        :param kwargs:
        :return:
        """
        size = -1
        uid = None
        if 'name_space' in kwargs and 'newznab' in kwargs['name_space']:
            size, uid = self._parse_size_uid(item, kwargs['name_space'])
        return size, uid

    def get_show(self,
                 item,  # type: etree.Element
                 **kwargs
                 ):  # type: (...) -> Union[TVShow, None]
        """

        :param item:
        :param kwargs:
        :return:
        """
        show_obj = None
        if 'name_space' in kwargs and 'newznab' in kwargs['name_space']:
            tvid_prodid = self.cache.parse_ids(item, kwargs['name_space'])

            if tvid_prodid:
                try:
                    show_obj = helpers.find_show_by_id(tvid_prodid, no_mapped_ids=False, check_multishow=True)
                except MultipleShowObjectsException:
                    return None
        return show_obj

    def choose_search_mode(self,
                           ep_obj_list,  # type: List[TVEpisode]
                           ep_obj,  # type: TVEpisode
                           hits_per_page=100  # type: int
                           ):  # type: (...) -> Tuple[bool, NeededQualities, int]
        """

        :param ep_obj_list: episode object list
        :param ep_obj: episode object
        :param hits_per_page:
        :return: season search, needed qualities class, max hits
        """
        searches = [eo for eo in ep_obj_list if (not ep_obj.show_obj.is_scene and eo.season == ep_obj.season) or
                    (ep_obj.show_obj.is_scene and eo.scene_season == ep_obj.scene_season)]

        needed = NeededQualities()
        needed.check_needed_types(ep_obj.show_obj)
        for s in searches:
            if needed.all_qualities_needed:
                break
            if not s.show_obj.is_anime and not s.show_obj.is_sports:
                if not getattr(s, 'wanted_quality', None):
                    # this should not happen, the creation is missing for the search in this case
                    logger.log('wanted_quality property was missing for search, creating it', logger.WARNING)
                    ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                    s.wanted_quality = get_wanted_qualities(ep_obj, ep_status, ep_quality, unaired=True)
                needed.check_needed_qualities(s.wanted_quality)

        if not hasattr(ep_obj, 'eps_aired_in_season'):
            # this should not happen, the creation is missing for the search in this case
            logger.log('eps_aired_in_season property was missing for search, creating it', logger.WARNING)
            ep_count, ep_count_scene = get_aired_in_season(ep_obj.show_obj)
            ep_obj.eps_aired_in_season = ep_count.get(ep_obj.season, 0)
            ep_obj.eps_aired_in_scene_season = ep_count_scene.get(ep_obj.scene_season, 0) if ep_obj.show_obj.is_scene \
                else ep_obj.eps_aired_in_season

        per_ep, limit_per_ep = 0, 0
        if needed.need_sd and not needed.need_hd:
            per_ep, limit_per_ep = 10, 25
        if needed.need_hd:
            if not needed.need_sd:
                per_ep, limit_per_ep = 30, 90
            else:
                per_ep, limit_per_ep = 40, 120
        if needed.need_uhd or (needed.need_hd and not self.cats.get(NewznabConstants.CAT_UHD)):
            per_ep += 4
            limit_per_ep += 10
        if ep_obj.show_obj.is_anime or ep_obj.show_obj.is_sports or ep_obj.show_obj.air_by_date:
            rel_per_ep, limit_per_ep = 5, 10
        else:
            rel_per_ep = per_ep
        rel = max(1, int(ceil((ep_obj.eps_aired_in_scene_season if ep_obj.show_obj.is_scene else
                               ep_obj.eps_aired_in_season * rel_per_ep) / hits_per_page)))
        rel_limit = max(1, int(ceil((ep_obj.eps_aired_in_scene_season if ep_obj.show_obj.is_scene else
                                     ep_obj.eps_aired_in_season * limit_per_ep) / hits_per_page)))
        season_search = rel < (len(searches) * 100 // hits_per_page)
        if not season_search:
            needed = NeededQualities()
            needed.check_needed_types(ep_obj.show_obj)
            if not ep_obj.show_obj.is_anime and not ep_obj.show_obj.is_sports:
                if not getattr(ep_obj, 'wanted_quality', None):
                    ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                    ep_obj.wanted_quality = get_wanted_qualities(ep_obj, ep_status, ep_quality, unaired=True)
                needed.check_needed_qualities(ep_obj.wanted_quality)
        else:
            if not ep_obj.show_obj.is_anime and not ep_obj.show_obj.is_sports:
                for cur_ep_obj in ep_obj_list:
                    if not getattr(cur_ep_obj, 'wanted_quality', None):
                        ep_status, ep_quality = Quality.splitCompositeStatus(cur_ep_obj.status)
                        cur_ep_obj.wanted_quality = get_wanted_qualities(cur_ep_obj, ep_status, ep_quality,
                                                                         unaired=True)
                    needed.check_needed_qualities(cur_ep_obj.wanted_quality)
        return (season_search, needed,
                (hits_per_page * 100 // hits_per_page * 2, hits_per_page * int(ceil(rel_limit * 1.5)))[season_search])

    def find_search_results(self,
                            show_obj,  # type: TVShow
                            ep_obj_list,  # type: List[TVEpisode]
                            search_mode,  # type: AnyStr
                            manual_search=False,  # type: bool
                            try_other_searches=False,  # type: bool
                            **kwargs
                            ):  # type: (...) -> Union[Dict[TVEpisode, Dict[TVEpisode, SearchResult]], Dict]
        """

        :param show_obj: show object
        :param ep_obj_list: episode list
        :param search_mode: search mode
        :param manual_search: maunal search
        :param try_other_searches:
        :param kwargs:
        :return:
        """
        check = self._check_auth()
        results = {}  # type: Dict[int, List]
        if (isinstance(check, bool) and not check) or self.should_skip():
            return results

        self.show_obj = show_obj

        item_list = []
        name_space = {}

        searched_scene_season = s_mode = None
        search_list = []
        for ep_obj in ep_obj_list:
            # skip if season already searched
            if (s_mode or 'sponly' == search_mode) and 1 < len(ep_obj_list) \
                    and searched_scene_season == ep_obj.scene_season:
                continue

            # search cache for episode result
            cache_result = self.cache.searchCache(ep_obj, manual_search)
            if cache_result:
                if ep_obj.episode not in results:
                    results[ep_obj.episode] = cache_result
                else:
                    results[ep_obj.episode].extend(cache_result)

                # found result, search next episode
                continue

            s_mode, needed, max_items = self.choose_search_mode(ep_obj_list, ep_obj, hits_per_page=self.limits)
            needed.check_needed_types(self.show_obj)

            if 'sponly' == search_mode:
                searched_scene_season = ep_obj.scene_season

                # get season search params
                search_params = self._season_strings(ep_obj)
            else:
                # get single episode search params
                if s_mode and 1 < len(ep_obj_list):
                    searched_scene_season = ep_obj.scene_season
                    search_params = self._season_strings(ep_obj)
                else:
                    search_params = self._episode_strings(ep_obj)

            search_list += [(search_params, needed, max_items)]

        search_done = []
        for (search_params, needed, max_items) in search_list:
            if self.should_skip(log_warning=False):
                break
            for cur_param in search_params:
                if cur_param in search_done:
                    continue
                search_done += [cur_param]
                items, n_space = self._search_provider(cur_param, search_mode=search_mode, epcount=len(ep_obj_list),
                                                       needed=needed, max_items=max_items,
                                                       try_all_searches=try_other_searches)
                item_list += items
                name_space.update(n_space)
                if self.should_skip():
                    break

        return self.finish_find_search_results(
            show_obj, ep_obj_list, search_mode, manual_search, results, item_list, name_space=name_space)

    @staticmethod
    def _parse_pub_date(item, default=None):
        # type: (etree.Element, Union[int, None]) -> Union[datetime.datetime, None]
        """

        :param item:
        :param default:
        :return:
        """
        parsed_date = default
        try:
            p = item.findtext('pubDate')
            if p:
                p = parser.parse(p, fuzzy=True)
                try:
                    p = p.astimezone(SG_TIMEZONE)
                except (BaseException, Exception):
                    pass
                if isinstance(p, datetime.datetime):
                    parsed_date = p.replace(tzinfo=None)
        except (BaseException, Exception):
            pass

        return parsed_date

    @staticmethod
    def _parse_size_uid(item,  # type: etree.Element
                        ns,  # type: Dict
                        default=-1  # type: int
                        ):  # type: (...) -> Tuple[int, Union[AnyStr, None]]
        """

        :param item:
        :param ns:
        :param default:
        :return:
        """
        parsed_size = default
        uid = None
        try:
            if ns and 'newznab' in ns:
                for attr in item.findall('%sattr' % ns['newznab']):
                    if 'size' == attr.get('name', ''):
                        parsed_size = try_int(attr.get('value'), -1)
                    elif 'guid' == attr.get('name', ''):
                        uid = attr.get('value')
        except (BaseException, Exception):
            pass
        return parsed_size, uid

    def _search_provider(self,
                         search_params,  # type: Dict[AnyStr, List[Dict[AnyStr, List[AnyStr]]]]
                         needed=NeededQualities(need_all=True),  # type: NeededQualities
                         max_items=400,  # type: int
                         try_all_searches=False,   # type: bool
                         **kwargs
                         ):  # type: (...) -> Tuple[List, Dict]
        """

        :param search_params:
        :param needed:
        :param max_items:
        :param try_all_searches:
        :param kwargs:
        :return:
        """
        results, n_spaces = [], {}
        if self.should_skip():
            return results, n_spaces

        api_key = self._check_auth()
        if isinstance(api_key, bool) and not api_key:
            return results, n_spaces

        base_params = {'t': 'tvsearch',
                       'maxage': sickbeard.USENET_RETENTION or 0,
                       'limit': self.limits,
                       'attrs': ','.join([k for k, v in iteritems(NewznabConstants.providerToIndexerMapping)
                                          if v in self.caps]),
                       'offset': 0}
        base_params_rss = {'num': self.limits, 'dl': '1'}
        rss_fallback = False

        if isinstance(api_key, string_types) and api_key not in ('0', ''):
            base_params['apikey'] = api_key
            base_params_rss['r'] = api_key
            args = re.findall(r'.*?([ir])\s*=\s*([^\s&;]*)', api_key)
            if 1 <= len(args):
                for (cur_key, cur_value) in args:
                    base_params_rss[cur_key] = cur_value
                    if 'r' == cur_key:
                        rss_fallback = True
                        base_params['apikey'] = cur_value
                if not rss_fallback:
                    logger.warning('Invalid API key config for API to RSS fallback,'
                                   ' not found: i=num&r=key or i=&r=key or &r=key')
                    return results, n_spaces

        for mode in search_params:
            params = dict(needed=needed, max_items=max_items, try_all_searches=try_all_searches,
                          base_params=base_params, base_params_rss=base_params_rss)
            results, n_spaces = self._search_core(search_params, **params)
            if not self.should_skip() and not results and rss_fallback and 'Cache' == mode:
                results, n_spaces = self._search_core(search_params, use_rss=True, **params)
            break
        return results, n_spaces

    def _search_core(self, search_params, needed=None, max_items=400, try_all_searches=False,
                     use_rss=False, base_params=None, base_params_rss=None):

        results, n_spaces = [], {}
        total, cnt, search_url, exit_log = 0, len(results), '', True

        cat_sport = self.cats.get(NewznabConstants.CAT_SPORT, ['5060'])
        cat_anime = self.cats.get(NewznabConstants.CAT_ANIME, ['5070'])
        cat_hd = self.cats.get(NewznabConstants.CAT_HD, ['5040'])
        cat_sd = self.cats.get(NewznabConstants.CAT_SD, ['5030'])
        cat_uhd = self.cats.get(NewznabConstants.CAT_UHD)
        cat_webdl = self.cats.get(NewznabConstants.CAT_WEBDL)

        for mode in search_params:
            if self.should_skip(log_warning=False):
                break
            for i, params in enumerate(search_params[mode]):  # type: int, List[Dict[AnyStr, List[AnyStr]]]

                if self.should_skip(log_warning=False):
                    break

                # category ids
                cat = []
                if 'Episode' == mode or 'Season' == mode:
                    if not (any([x in params for x in
                                 [v for c, v in iteritems(self.caps)
                                  if c not in [NewznabConstants.SEARCH_EPISODE, NewznabConstants.SEARCH_SEASON]]])):
                        logger.log('Show is missing either an id or search term for search')
                        continue

                if needed.need_anime:
                    cat.extend(cat_anime)
                if needed.need_sports:
                    cat.extend(cat_sport)

                if needed.need_hd:
                    cat.extend(cat_hd)
                if needed.need_sd:
                    cat.extend(cat_sd)
                if needed.need_uhd and None is not cat_uhd:
                    cat.extend(cat_uhd)
                if needed.need_webdl and None is not cat_webdl:
                    cat.extend(cat_webdl)

                if self.cat_ids or len(cat):
                    base_params['cat'] = ','.join(sorted(set((self.cat_ids.split(',') if self.cat_ids else []) + cat)))
                    base_params_rss['t'] = base_params['cat']

                request_params = base_params.copy()
                # if ('Propers' == mode or 'nzbs_org' == self.get_id()) \
                if 'Propers' == mode \
                        and 'q' in params and not (any([x in params for x in ['season', 'ep']])):
                    request_params['t'] = 'search'
                request_params.update(params)

                # deprecated; kept here as bookmark for new haspretime:0|1 + nuked:0|1 can be used here instead
                # if hasattr(self, 'filter'):
                #     if 'nzbs_org' == self.get_id():
                #         request_params['rls'] = ((0, 1)['so' in self.filter], 2)['snn' in self.filter]

                # workaround a strange glitch
                if sum([ord(i) for i in self.get_id()]) in [383] and 5 == 14 - request_params['maxage']:
                    request_params['maxage'] += 1

                offset = 0
                batch_count = not 0
                first_date = last_date = None

                # hardcoded to stop after a max of 4 hits (400 items) per query
                while (offset <= total) and (offset < max_items) and batch_count:
                    cnt = len(results)

                    if 'Cache' == mode and use_rss:
                        search_url = '%srss?%s' % (self.url, urlencode(base_params_rss))
                    else:
                        search_url = '%sapi?%s' % (self.url, urlencode(request_params))
                    i and time.sleep(2.1)

                    data = self.get_url(search_url)

                    if self.should_skip() or not data:
                        break

                    # hack this in until it's fixed server side
                    if not data.startswith('<?xml'):
                        data = '<?xml version="1.0" encoding="ISO-8859-1" ?>%s' % data

                    try:
                        parsed_xml, n_spaces = self.cache.parse_and_get_ns(data)
                        items = parsed_xml.findall('channel/item')
                    except (BaseException, Exception):
                        logger.log('Error trying to load %s RSS feed' % self.name, logger.WARNING)
                        break

                    if not self._check_auth_from_data(parsed_xml, search_url):
                        break

                    if 'rss' != parsed_xml.tag:
                        logger.log('Resulting XML from %s isn\'t RSS, not parsing it' % self.name, logger.WARNING)
                        break

                    i and time.sleep(2.1)

                    for item in items:

                        title, url = self._title_and_url(item)
                        if title and url:
                            results.append(item)
                        else:
                            logger.log('The data returned from %s is incomplete, this result is unusable' % self.name,
                                       logger.DEBUG)

                    # get total and offset attributes
                    try:
                        if 0 == total:
                            total = (try_int(parsed_xml.find(
                                './/%sresponse' % n_spaces['newznab']).get('total', 0)), 1000)['Cache' == mode]
                            hits = (total // self.limits + int(0 < (total % self.limits)))
                            hits += int(0 == hits)
                        offset = try_int(parsed_xml.find('.//%sresponse' % n_spaces['newznab']).get('offset', 0))
                    except (AttributeError, KeyError):
                        if not use_rss:
                            break
                        total = len(items)

                    # No items found, prevent from doing another search
                    if 0 == total:
                        break

                    # Cache mode, prevent from doing another search
                    if 'Cache' == mode:
                        if items and len(items):
                            if not first_date:
                                first_date = self._parse_pub_date(items[0])
                            last_date = self._parse_pub_date(items[-1])
                        if not first_date or not last_date or not self.last_recent_search or \
                                last_date <= self.last_recent_search or use_rss:
                            break

                    if offset != request_params['offset']:
                        logger.log('Ask your newznab provider to fix their newznab responses')
                        break

                    request_params['offset'] += request_params['limit']
                    if total <= request_params['offset']:
                        break

                    # there are more items available than the amount given in one call, grab some more
                    items = total - request_params['offset']
                    logger.log('%s more item%s to fetch from a batch of up to %s items.'
                               % (items, helpers.maybe_plural(items), request_params['limit']), logger.DEBUG)

                    batch_count = self._log_result(results, mode, cnt, search_url)
                    exit_log = False

                if 'Cache' == mode and first_date:
                    self.last_recent_search = first_date

                if exit_log:
                    self._log_search(mode, len(results), search_url)

                if not try_all_searches and any([x in request_params for x in [
                    v for c, v in iteritems(self.caps)
                    if c not in [NewznabConstants.SEARCH_EPISODE, NewznabConstants.SEARCH_SEASON,
                                 NewznabConstants.SEARCH_TEXT]]]) and len(results):
                    break

        return results, n_spaces

    def find_propers(self,
                     search_date=None,  # type: Union[datetime.date, None]
                     shows=None,  # type: Union[List[int, int], None]
                     anime=None,  # type: Union[List[int, int], None]
                     **kwargs
                     ):  # type: (...) -> List[classes.Proper]
        """

        :param search_date:
        :param shows:
        :param anime:
        :param kwargs:
        :return:
        """
        cache_results = self.cache.listPropers(search_date)
        results = [classes.Proper(x['name'], x['url'],
                                  datetime.datetime.fromtimestamp(x['time']), self.show_obj) for x in cache_results]

        check = self._check_auth()
        if isinstance(check, bool) and not check:
            return results

        index = 0
        # alt_search = ('nzbs_org' == self.get_id())
        # do_search_alt = False

        search_terms = []
        regex = []
        if shows:
            search_terms += ['.proper.', '.repack.', '.real.']
            regex += ['proper|repack', Quality.real_check]
            proper_check = re.compile(r'(?i)(\b%s\b)' % '|'.join(regex))
        if anime:
            terms = 'v2|v3|v4|v5|v6|v7|v8|v9'
            search_terms += [terms]
            regex += [terms]
            proper_check = re.compile(r'(?i)(%s)' % '|'.join(regex))

        urls = []
        while index < len(search_terms):
            if self.should_skip(log_warning=False):
                break

            search_params = {'q': search_terms[index], 'maxage': sickbeard.BACKLOG_LIMITED_PERIOD + 2}
            # if alt_search:
            #
            #     if do_search_alt:
            #         search_params['t'] = 'search'
            #         index += 1
            #
            #     do_search_alt = not do_search_alt
            #
            # else:
            #     index += 1
            index += 1

            items, n_space = self._search_provider({'Propers': [search_params]})

            for item in items:

                (title, url) = self._title_and_url(item)

                # noinspection PyUnboundLocalVariable
                if not proper_check.search(title) or url in urls:
                    continue
                urls.append(url)

                result_date = self._parse_pub_date(item)
                if not result_date:
                    logger.log(u'Unable to figure out the date for entry %s, skipping it' % title)
                    continue

                result_size, result_uid = self._parse_size_uid(item, ns=n_space)
                if not search_date or search_date < result_date:
                    show_obj = self.get_show(item, name_space=n_space)
                    search_result = classes.Proper(title, url, result_date, self.show_obj, parsed_show_obj=show_obj,
                                                   size=result_size, puid=result_uid)
                    results.append(search_result)

            time.sleep(0.5)

        return results

    def _log_result(self, results, mode, cnt, url):
        count = len(results) - cnt
        if count:
            self._log_search(mode, count, url)
        return count

    def __str__(self):
        return 'NewznabProvider: %s (%s); server type: %s; enabled searches: %s' % \
               (self.name, ('disabled', 'enabled')[self.enabled in (True, 1)],
                NewznabConstants.server_types.get(self.server_type, 'unknown'),
                ','.join(en[1] for en in
                         ((getattr(self, 'enable_recentsearch', False), 'recent'),
                          (getattr(self, 'enable_backlog', False), 'backlog'),
                          (getattr(self, 'enable_scheduled_backlog', False), 'scheduled')) if en[0]) or 'None')

    def __repr__(self):
        return self.__str__()


class NewznabCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider, interval=5)

    # helper method to read the namespaces from xml
    @staticmethod
    def parse_and_get_ns(data):
        # type: (AnyStr) -> Tuple[etree.Element, Dict]
        """

        :param data:
        :return:
        """
        events = 'start', 'start-ns'
        root = None
        ns = {}
        for event, elem in etree.iterparse(BytesIO(data.encode('utf-8')), events):
            if 'start-ns' == event:
                ns[elem[0]] = '{%s}' % elem[1]
            elif 'start' == event:
                if None is root:
                    root = elem
        return root, ns

    def updateCache(self,
                    needed=NeededQualities(need_all=True),  # type: NeededQualities
                    **kwargs
                    ):
        """

        :param needed: needed qualites class
        :param kwargs:
        """
        if 4489 != sickbeard.RECENTSEARCH_INTERVAL or self.should_update():
            n_spaces = {}
            try:
                check = self._checkAuth()
                if isinstance(check, bool) and not check:
                    items = None
                else:
                    (items, n_spaces) = self.provider.cache_data(needed=needed)
            except (BaseException, Exception) as e:
                logger.log('Error updating Cache: %s' % ex(e), logger.ERROR)
                items = None

            if items:
                self._clearCache()

                # parse data
                cl = []
                for item in items:
                    ci = self._parseItem(n_spaces, item)
                    if None is not ci:
                        cl.append(ci)

                if 0 < len(cl):
                    my_db = self.get_db()
                    my_db.mass_action(cl)

            # set updated as time the attempt to fetch data is
            self.setLastUpdate()

    @staticmethod
    def parse_ids(item, ns):
        # type: (etree.Element, Dict) -> Dict[int, int]
        """

        :param item:
        :param ns:
        :return:
        """
        ids = {}
        if 'newznab' in ns:
            for attr in item.findall('%sattr' % ns['newznab']):
                if attr.get('name', '') in NewznabConstants.providerToIndexerMapping:
                    v = try_int(attr.get('value'))
                    if 0 < v:
                        ids[NewznabConstants.providerToIndexerMapping[attr.get('name')]] = v
        return ids

    # overwrite method with that parses the rageid from the newznab feed
    def _parseItem(self,
                   ns,  # type: Dict
                   item  # type: etree.Element
                   ):  # type: (...) -> Union[List[AnyStr, List[Any]], None]
        """

        :param ns:
        :param item:
        :return:
        """
        title, url = self._title_and_url(item)

        ids = self.parse_ids(item, ns)

        if title and url:
            return self.add_cache_entry(title, url, tvid_prodid=ids)

        logger.log('Data returned from the %s feed is incomplete, this result is unusable' % self.provider.name,
                   logger.DEBUG)
