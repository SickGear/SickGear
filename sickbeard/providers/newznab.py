﻿# Author: Nic Wolfe <nic@wolfeden.ca>
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
from collections import OrderedDict
from math import ceil

import datetime
import re
import time
import urllib

import sickbeard

from io import BytesIO
from lib.dateutil import parser
from . import generic
from sickbeard import classes, db, helpers, logger, tvcache
from sickbeard.common import neededQualities, Quality, DOWNLOADED, SNATCHED, SNATCHED_PROPER, SNATCHED_BEST
from sickbeard.exceptions import AuthException, MultipleShowObjectsException
from sickbeard.helpers import tryInt
from sickbeard.indexers.indexer_config import *
from sickbeard.network_timezones import sb_timezone
from sickbeard.sbdatetime import sbdatetime
from sickbeard.search import get_aired_in_season, get_wanted_qualities
from sickbeard.show_name_helpers import get_show_names

try:
    from lxml import etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        import xml.etree.ElementTree as etree


class NewznabConstants:
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

    providerToIndexerMapping = {'tvdbid': INDEXER_TVDB,
                                'rageid': INDEXER_TVRAGE,
                                'tvmazeid': INDEXER_TVMAZE,
                                'imdbid': INDEXER_IMDB,
                                'tmdbid': INDEXER_TMDB,
                                'traktid': INDEXER_TRAKT}

    indexer_priority_list = [INDEXER_TVDB, INDEXER_TVMAZE, INDEXER_TVRAGE, INDEXER_TRAKT, INDEXER_TMDB, INDEXER_TMDB]

    searchTypes = {'rid': INDEXER_TVRAGE,
                   'tvdbid': INDEXER_TVDB,
                   'tvmazeid': INDEXER_TVMAZE,
                   'imdbid': INDEXER_IMDB,
                   'tmdbid': INDEXER_TMDB,
                   'traktid': INDEXER_TRAKT,
                   'q': SEARCH_TEXT,
                   'season': SEARCH_SEASON,
                   'ep': SEARCH_EPISODE}

    def __init__(self):
        pass


class NewznabProvider(generic.NZBProvider):

    def __init__(self, name, url, key='', cat_ids=None, search_mode=None, search_fallback=False,
                 enable_recentsearch=False, enable_backlog=False, enable_scheduled_backlog=False):
        generic.NZBProvider.__init__(self, name, True, False)

        self.url = url
        self.key = key
        self._exclude = set()
        self.cat_ids = cat_ids or ''
        self._cat_ids = None
        self.search_mode = search_mode or 'eponly'
        self.search_fallback = bool(tryInt(search_fallback))
        self.enable_recentsearch = bool(tryInt(enable_recentsearch))
        self.enable_backlog = bool(tryInt(enable_backlog))
        self.enable_scheduled_backlog = bool(tryInt(enable_scheduled_backlog, 1))
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
                    self._last_recent_search = datetime.datetime.fromtimestamp(int(res[0]['datetime']))
            except (StandardError, Exception):
                pass
        return self._last_recent_search

    @last_recent_search.setter
    def last_recent_search(self, value):
        try:
            my_db = db.DBConnection('cache.db')
            my_db.action('INSERT OR REPLACE INTO "lastrecentsearch" (name, datetime) VALUES (?,?)',
                         [self.get_id(), sbdatetime.totimestamp(value, default=0)])
        except (StandardError, Exception):
            pass
        self._last_recent_search = value

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
            if xml_caps is None or not hasattr(xml_caps, 'tag') or xml_caps.tag == 'error' or xml_caps.tag != 'caps':
                api_key = self.maybe_apikey()
                if isinstance(api_key, basestring) and api_key not in ('0', ''):
                    data = self.get_url('%s/api?t=caps&apikey=%s' % (self.url, api_key))
                    if data:
                        xml_caps = helpers.parse_xml(data)
                        if xml_caps and hasattr(xml_caps, 'tag') and xml_caps.tag == 'caps':
                            self._caps_need_apikey = {'need': True, 'date': datetime.date.today()}
        return xml_caps

    def _check_excludes(self, cats):
        if isinstance(cats, dict):
            c = []
            for v in cats.itervalues():
                c.extend(v)
            self._exclude = set(c)
        else:
            self._exclude = set(v for v in cats)

    def get_caps(self):
        caps = {}
        cats = {}
        all_cats = []
        xml_caps = self._get_caps_data()
        if None is not xml_caps:
            tv_search = xml_caps.find('.//tv-search')
            if None is not tv_search:
                for c in [i for i in tv_search.get('supportedParams', '').split(',')]:
                    k = NewznabConstants.searchTypes.get(c)
                    if k:
                        caps[k] = c

            limit = xml_caps.find('.//limits')
            if None is not limit:
                lim = helpers.tryInt(limit.get('max'), 100)
                self._limits = (100, lim)[lim >= 100]

            try:
                for category in xml_caps.iter('category'):
                    if 'TV' == category.get('name'):
                        for subcat in category.findall('subcat'):
                            try:
                                cat_name = subcat.attrib['name']
                                cat_id = subcat.attrib['id']
                                all_cats.append({'id': cat_id, 'name': cat_name})
                                for s, v in NewznabConstants.catSearchStrings.iteritems():
                                    if None is not re.search(s, cat_name, re.IGNORECASE):
                                        cats.setdefault(v, []).append(cat_id)
                            except (StandardError, Exception):
                                continue
                    elif category.get('name', '').upper() in ['XXX', 'OTHER', 'MISC']:
                        for subcat in category.findall('subcat'):
                            try:
                                if None is not re.search(r'^Anime$', subcat.attrib['name'], re.IGNORECASE):
                                    cats.setdefault(NewznabConstants.CAT_ANIME, []).append(subcat.attrib['id'])
                                    break
                            except (StandardError, Exception):
                                continue
            except (StandardError, Exception):
                logger.log('Error parsing result for [%s]' % self.name, logger.DEBUG)

        if not caps and self._caps and not all_cats and self._caps_all_cats and not cats and self._caps_cats:
            self._check_excludes(cats)
            return

        if self.enabled:
            self._caps_last_updated = datetime.datetime.now()

        if not caps and self.get_id() not in ['sick_beard_index']:
            caps[INDEXER_TVDB] = 'tvdbid'
        if NewznabConstants.SEARCH_TEXT not in caps or not caps.get(NewznabConstants.SEARCH_TEXT):
            caps[NewznabConstants.SEARCH_TEXT] = 'q'
        if NewznabConstants.SEARCH_SEASON not in caps or not caps.get(NewznabConstants.SEARCH_SEASON):
            caps[NewznabConstants.SEARCH_SEASON] = 'season'
        if NewznabConstants.SEARCH_EPISODE not in caps or not caps.get(NewznabConstants.SEARCH_EPISODE):
            caps[NewznabConstants.SEARCH_TEXT] = 'ep'
        if (INDEXER_TVRAGE not in caps or not caps.get(INDEXER_TVRAGE)) and self.get_id() not in ['sick_beard_index']:
            caps[INDEXER_TVRAGE] = 'rid'

        if NewznabConstants.CAT_HD not in cats or not cats.get(NewznabConstants.CAT_HD):
            cats[NewznabConstants.CAT_HD] = (['5040'], ['5040', '5090'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_SD not in cats or not cats.get(NewznabConstants.CAT_SD):
            cats[NewznabConstants.CAT_SD] = (['5030'], ['5030', '5070'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_ANIME not in cats or not cats.get(NewznabConstants.CAT_ANIME):
            cats[NewznabConstants.CAT_ANIME] = (['5070'], ['6070', '7040'])['nzbs_org' == self.get_id()]
        if NewznabConstants.CAT_SPORT not in cats or not cats.get(NewznabConstants.CAT_SPORT):
            cats[NewznabConstants.CAT_SPORT] = ['5060']

        self._check_excludes(cats)
        self._caps = caps
        self._caps_cats = cats
        self._caps_all_cats = all_cats

    def clean_newznab_categories(self, cats):
        """
        Removes automatically mapped categories from the list
        """
        if isinstance(cats, list):
            return [x for x in cats if x['id'] not in self.excludes]
        return ','.join(set(cats.split(',')) - self.excludes)

    def _check_auth(self, is_required=None):
        if self.should_skip():
            return False
        return super(NewznabProvider, self)._check_auth(is_required)

    def _check_auth_from_data(self, data, url):

        if data is None or not hasattr(data, 'tag'):
            return False

        if 'error' == data.tag:
            code = data.get('code', '')
            description = data.get('description', '')

            if '100' == code:
                raise AuthException('Your API key for %s is incorrect, check your config.' % self.name)
            elif '101' == code:
                raise AuthException('Your account on %s has been suspended, contact the admin.' % self.name)
            elif '102' == code:
                raise AuthException('Your account isn\'t allowed to use the API on %s, contact the admin.' % self.name)
            elif '500' == code:
                try:
                    retry_time, unit = re.findall(r'Retry in (\d+)\W+([a-z]+)', description, flags=re.I)[0]
                except IndexError:
                    retry_time, unit = None, None
                self.tmr_limit_update(retry_time, unit, description)
                self.log_failure_url(url)
            elif '910' == code:
                logger.log(
                    '%s %s, please check with provider.' %
                    (self.name, ('currently has their API disabled', description)[description not in (None, '')]),
                    logger.WARNING)
            else:
                logger.log('Unknown error given from %s: %s' % (self.name, data.get('description', '')),
                           logger.WARNING)
            return False

        self.tmr_limit_count = 0
        return True

    def config_str(self):
        return '%s|%s|%s|%s|%i|%s|%i|%i|%i|%i' \
               % (self.name or '', self.url or '', self.maybe_apikey() or '', self.cat_ids or '', self.enabled,
                  self.search_mode or '', self.search_fallback, self.enable_recentsearch, self.enable_backlog,
                  self.enable_scheduled_backlog)

    def _season_strings(self, ep_obj):

        search_params = []
        base_params = {}

        # season
        ep_detail = None
        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            base_params['season'] = airdate
            base_params['q'] = airdate
            if ep_obj.show.air_by_date:
                ep_detail = '+"%s"' % airdate
        elif ep_obj.show.is_anime:
            base_params['season'] = '%d' % ep_obj.scene_absolute_number
        else:
            base_params['season'] = str((ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)])
            ep_detail = 'S%02d' % helpers.tryInt(base_params['season'], 1)

        # id search
        params = base_params.copy()
        use_id = False
        for i in sickbeard.indexerApi().all_indexers:
            if i in ep_obj.show.ids and 0 < ep_obj.show.ids[i]['id'] and i in self.caps:
                params[self.caps[i]] = ep_obj.show.ids[i]['id']
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

    def _episode_strings(self, ep_obj):

        search_params = []
        base_params = {}

        if not ep_obj:
            return [base_params]

        ep_detail = None
        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            airdate = str(ep_obj.airdate).split('-')
            base_params['season'] = airdate[0]
            if ep_obj.show.air_by_date:
                base_params['ep'] = '/'.join(airdate[1:])
                ep_detail = '+"%s.%s"' % (base_params['season'], '.'.join(airdate[1:]))
        elif ep_obj.show.is_anime:
            base_params['ep'] = '%i' % (helpers.tryInt(ep_obj.scene_absolute_number) or
                                        helpers.tryInt(ep_obj.scene_episode))
            ep_detail = '%02d' % helpers.tryInt(base_params['ep'])
        else:
            base_params['season'], base_params['ep'] = (
                (ep_obj.season, ep_obj.episode), (ep_obj.scene_season, ep_obj.scene_episode))[ep_obj.show.is_scene]
            ep_detail = sickbeard.config.naming_ep_type[2] % {
                'seasonnumber': helpers.tryInt(base_params['season'], 1),
                'episodenumber': helpers.tryInt(base_params['ep'], 1)}

        # id search
        params = base_params.copy()
        use_id = False
        for i in sickbeard.indexerApi().all_indexers:
            if i in ep_obj.show.ids and 0 < ep_obj.show.ids[i]['id'] and i in self.caps:
                params[self.caps[i]] = ep_obj.show.ids[i]['id']
                use_id = True
        use_id and search_params.append(params)

        spacer = 'nzbgeek.info' in self.url.lower() and ' ' or '.'
        # query search and exceptions
        name_exceptions = get_show_names(ep_obj, spacer)
        if sickbeard.scene_exceptions.has_abs_episodes(ep_obj):
            search_params.append({'q': '%s%s%s' % (ep_obj.show.name, spacer, base_params['ep'])})
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

    def supports_tvdbid(self):

        return self.get_id() not in ['sick_beard_index']

    def _title_and_url(self, item):
        title, url = None, None
        try:
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
            url = str(item.findtext('link')).replace('&amp;', '&')
        except (StandardError, Exception):
            pass

        return title, url

    def get_size_uid(self, item, **kwargs):
        size = -1
        uid = None
        if 'name_space' in kwargs and 'newznab' in kwargs['name_space']:
            size, uid = self._parse_size_uid(item, kwargs['name_space'])
        return size, uid

    def get_show(self, item, **kwargs):
        show_obj = None
        if 'name_space' in kwargs and 'newznab' in kwargs['name_space']:
            ids = self.cache.parse_ids(item, kwargs['name_space'])

            if ids:
                try:
                    show_obj = helpers.find_show_by_id(sickbeard.showList, id_dict=ids, no_mapped_ids=False)
                except MultipleShowObjectsException:
                    return None
        return show_obj

    def choose_search_mode(self, episodes, ep_obj, hits_per_page=100):
        searches = [e for e in episodes if (not ep_obj.show.is_scene and e.season == ep_obj.season) or
                    (ep_obj.show.is_scene and e.scene_season == ep_obj.scene_season)]

        needed = neededQualities()
        needed.check_needed_types(ep_obj.show)
        for s in searches:
            if needed.all_qualities_needed:
                break
            if not s.show.is_anime and not s.show.is_sports:
                if not getattr(s, 'wantedQuality', None):
                    # this should not happen, the creation is missing for the search in this case
                    logger.log('wantedQuality property was missing for search, creating it', logger.WARNING)
                    ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                    s.wantedQuality = get_wanted_qualities(ep_obj, ep_status, ep_quality, unaired=True)
                needed.check_needed_qualities(s.wantedQuality)

        if not hasattr(ep_obj, 'eps_aired_in_season'):
            # this should not happen, the creation is missing for the search in this case
            logger.log('eps_aired_in_season property was missing for search, creating it', logger.WARNING)
            ep_count, ep_count_scene = get_aired_in_season(ep_obj.show)
            ep_obj.eps_aired_in_season = ep_count.get(ep_obj.season, 0)
            ep_obj.eps_aired_in_scene_season = ep_count_scene.get(ep_obj.scene_season, 0) if ep_obj.show.is_scene else \
                ep_obj.eps_aired_in_season

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
        if ep_obj.show.is_anime or ep_obj.show.is_sports or ep_obj.show.air_by_date:
            rel_per_ep, limit_per_ep = 5, 10
        else:
            rel_per_ep = per_ep
        rel = max(1, int(ceil((ep_obj.eps_aired_in_scene_season if ep_obj.show.is_scene else
                               ep_obj.eps_aired_in_season * rel_per_ep) / hits_per_page)))
        rel_limit = max(1, int(ceil((ep_obj.eps_aired_in_scene_season if ep_obj.show.is_scene else
                                     ep_obj.eps_aired_in_season * limit_per_ep) / hits_per_page)))
        season_search = rel < (len(searches) * 100 // hits_per_page)
        if not season_search:
            needed = neededQualities()
            needed.check_needed_types(ep_obj.show)
            if not ep_obj.show.is_anime and not ep_obj.show.is_sports:
                if not getattr(ep_obj, 'wantedQuality', None):
                    ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                    ep_obj.wantedQuality = get_wanted_qualities(ep_obj, ep_status, ep_quality, unaired=True)
                needed.check_needed_qualities(ep_obj.wantedQuality)
        else:
            if not ep_obj.show.is_anime and not ep_obj.show.is_sports:
                for ep in episodes:
                    if not getattr(ep, 'wantedQuality', None):
                        ep_status, ep_quality = Quality.splitCompositeStatus(ep.status)
                        ep.wantedQuality = get_wanted_qualities(ep, ep_status, ep_quality, unaired=True)
                    needed.check_needed_qualities(ep.wantedQuality)
        return (season_search, needed,
                (hits_per_page * 100 // hits_per_page * 2, hits_per_page * int(ceil(rel_limit * 1.5)))[season_search])

    def find_search_results(self, show, episodes, search_mode, manual_search=False, try_other_searches=False, **kwargs):
        check = self._check_auth()
        results = {}
        if (isinstance(check, bool) and not check) or self.should_skip():
            return results

        self.show = show

        item_list = []
        name_space = {}

        searched_scene_season = s_mode = None
        search_list = []
        for ep_obj in episodes:
            # skip if season already searched
            if (s_mode or 'sponly' == search_mode) and 1 < len(episodes) \
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

            s_mode, needed, max_items = self.choose_search_mode(episodes, ep_obj, hits_per_page=self.limits)
            needed.check_needed_types(self.show)

            if 'sponly' == search_mode:
                searched_scene_season = ep_obj.scene_season

                # get season search params
                search_params = self._season_strings(ep_obj)
            else:
                # get single episode search params
                if s_mode and 1 < len(episodes):
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
                items, n_space = self._search_provider(cur_param, search_mode=search_mode, epcount=len(episodes),
                                                       needed=needed, max_items=max_items,
                                                       try_all_searches=try_other_searches)
                item_list += items
                name_space.update(n_space)
                if self.should_skip():
                    break

        return self.finish_find_search_results(
            show, episodes, search_mode, manual_search, results, item_list, name_space=name_space)

    @staticmethod
    def _parse_pub_date(item, default=None):
        parsed_date = default
        try:
            p = item.findtext('pubDate')
            if p:
                p = parser.parse(p, fuzzy=True)
                try:
                    p = p.astimezone(sb_timezone)
                except (StandardError, Exception):
                    pass
                if isinstance(p, datetime.datetime):
                    parsed_date = p.replace(tzinfo=None)
        except (StandardError, Exception):
            pass

        return parsed_date

    @staticmethod
    def _parse_size_uid(item, ns, default=-1):
        parsed_size = default
        uid = None
        try:
            if ns and 'newznab' in ns:
                for attr in item.findall('%sattr' % ns['newznab']):
                    if 'size' == attr.get('name', ''):
                        parsed_size = helpers.tryInt(attr.get('value'), -1)
                    elif 'guid' == attr.get('name', ''):
                        uid = attr.get('value')
        except (StandardError, Exception):
            pass
        return parsed_size, uid

    def _search_provider(self, search_params, needed=neededQualities(need_all=True), max_items=400,
                         try_all_searches=False, **kwargs):

        results, n_spaces = [], {}
        if self.should_skip():
            return results, n_spaces

        api_key = self._check_auth()
        if isinstance(api_key, bool) and not api_key:
            return results, n_spaces

        base_params = {'t': 'tvsearch',
                       'maxage': sickbeard.USENET_RETENTION or 0,
                       'limit': self.limits,
                       'attrs': ','.join([k for k, v in NewznabConstants.providerToIndexerMapping.iteritems()
                                          if v in self.caps]),
                       'offset': 0}

        uc_only = all([re.search('(?i)usenet_crawler', self.get_id())])
        base_params_uc = {'num': self.limits, 'dl': '1', 'i': '64660'}

        if isinstance(api_key, basestring) and api_key not in ('0', ''):
            base_params['apikey'] = api_key
            base_params_uc['r'] = api_key

        results, n_spaces = [], {}
        total, cnt, search_url, exit_log = 0, len(results), '', True

        cat_sport = self.cats.get(NewznabConstants.CAT_SPORT, ['5060'])
        cat_anime = self.cats.get(NewznabConstants.CAT_ANIME, ['5070'])
        cat_hd = self.cats.get(NewznabConstants.CAT_HD, ['5040'])
        cat_sd = self.cats.get(NewznabConstants.CAT_SD, ['5030'])
        cat_uhd = self.cats.get(NewznabConstants.CAT_UHD)
        cat_webdl = self.cats.get(NewznabConstants.CAT_WEBDL)

        for mode in search_params.keys():
            if self.should_skip(log_warning=False):
                break
            for i, params in enumerate(search_params[mode]):

                if self.should_skip(log_warning=False):
                    break

                # category ids
                cat = []
                if 'Episode' == mode or 'Season' == mode:
                    if not (any(x in params for x in [v for c, v in self.caps.iteritems()
                                if c not in [NewznabConstants.SEARCH_EPISODE, NewznabConstants.SEARCH_SEASON]])
                            or not self.supports_tvdbid()):
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
                if needed.need_uhd and cat_uhd is not None:
                    cat.extend(cat_uhd)
                if needed.need_webdl and cat_webdl is not None:
                    cat.extend(cat_webdl)

                if self.cat_ids or len(cat):
                    base_params['cat'] = ','.join(sorted(set((self.cat_ids.split(',') if self.cat_ids else []) + cat)))
                    base_params_uc['t'] = base_params['cat']

                request_params = base_params.copy()
                if ('Propers' == mode or 'nzbs_org' == self.get_id()) \
                        and 'q' in params and not (any(x in params for x in ['season', 'ep'])):
                    request_params['t'] = 'search'
                request_params.update(params)

                # deprecated; kept here as bookmark for new haspretime:0|1 + nuked:0|1 can be used here instead
                # if hasattr(self, 'filter'):
                #     if 'nzbs_org' == self.get_id():
                #         request_params['rls'] = ((0, 1)['so' in self.filter], 2)['snn' in self.filter]

                # workaround a strange glitch
                if sum(ord(i) for i in self.get_id()) in [383] and 5 == 14 - request_params['maxage']:
                    request_params['maxage'] += 1

                offset = 0
                batch_count = not 0
                first_date = last_date = None

                # hardcoded to stop after a max of 4 hits (400 items) per query
                while (offset <= total) and (offset < max_items) and batch_count:
                    cnt = len(results)

                    if 'Cache' == mode and uc_only:
                        search_url = '%srss?%s' % (self.url, urllib.urlencode(base_params_uc))
                    else:
                        search_url = '%sapi?%s' % (self.url, urllib.urlencode(request_params))
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
                    except (StandardError, Exception):
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
                            total = (helpers.tryInt(parsed_xml.find(
                                './/%sresponse' % n_spaces['newznab']).get('total', 0)), 1000)['Cache' == mode]
                            hits = (total // self.limits + int(0 < (total % self.limits)))
                            hits += int(0 == hits)
                        offset = helpers.tryInt(parsed_xml.find('.//%sresponse' % n_spaces['newznab']).get('offset', 0))
                    except (AttributeError, KeyError):
                        if not uc_only:
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
                        if not first_date or not last_date or not self._last_recent_search or \
                                last_date <= self.last_recent_search or uc_only:
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
                    self._log_search(mode, total, search_url)

                if not try_all_searches and any(x in request_params for x in [
                    v for c, v in self.caps.iteritems()
                    if c not in [NewznabConstants.SEARCH_EPISODE, NewznabConstants.SEARCH_SEASON,
                                 NewznabConstants.SEARCH_TEXT]]) and len(results):
                    break

        return results, n_spaces

    def find_propers(self, search_date=None, shows=None, anime=None, **kwargs):
        cache_results = self.cache.listPropers(search_date)
        results = [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show) for x in
                   cache_results]

        check = self._check_auth()
        if isinstance(check, bool) and not check:
            return results

        index = 0
        alt_search = ('nzbs_org' == self.get_id())
        do_search_alt = False

        search_terms = []
        regex = []
        if shows:
            search_terms += ['.proper.', '.repack.', '.real.']
            regex += ['proper|repack', Quality.real_check]
            proper_check = re.compile(r'(?i)(\b%s\b)' % '|'.join(regex))
        if anime:
            terms = 'v1|v2|v3|v4|v5'
            search_terms += [terms]
            regex += [terms]
            proper_check = re.compile(r'(?i)(%s)' % '|'.join(regex))

        urls = []
        while index < len(search_terms):
            if self.should_skip(log_warning=False):
                break

            search_params = {'q': search_terms[index], 'maxage': sickbeard.BACKLOG_DAYS + 2}
            if alt_search:

                if do_search_alt:
                    search_params['t'] = 'search'
                    index += 1

                do_search_alt = not do_search_alt

            else:
                index += 1

            items, n_space = self._search_provider({'Propers': [search_params]})

            for item in items:

                (title, url) = self._title_and_url(item)

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
                    search_result = classes.Proper(title, url, result_date, self.show, parsed_show=show_obj,
                                                   size=result_size, puid=result_uid)
                    results.append(search_result)

            time.sleep(0.5)

        return results

    def _log_result(self, results, mode, cnt, url):
        count = len(results) - cnt
        if count:
            self._log_search(mode, count, url)
        return count


class NewznabCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)

        self.update_freq = 5

    # helper method to read the namespaces from xml
    @staticmethod
    def parse_and_get_ns(data):
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

    def updateCache(self, needed=neededQualities(need_all=True), **kwargs):

        result = []

        if 4489 != sickbeard.RECENTSEARCH_FREQUENCY or self.should_update():
            n_spaces = {}
            try:
                check = self._checkAuth()
                if isinstance(check, bool) and not check:
                    items = None
                else:
                    (items, n_spaces) = self.provider.cache_data(needed=needed)
            except (StandardError, Exception):
                items = None

            if items:
                self._clearCache()

                # parse data
                cl = []
                for item in items:
                    ci = self._parseItem(n_spaces, item)
                    if ci is not None:
                        cl.append(ci)

                if 0 < len(cl):
                    my_db = self.get_db()
                    my_db.mass_action(cl)

            # set updated as time the attempt to fetch data is
            self.setLastUpdate()

        return result

    @staticmethod
    def parse_ids(item, ns):
        ids = {}
        if 'newznab' in ns:
            for attr in item.findall('%sattr' % ns['newznab']):
                if attr.get('name', '') in NewznabConstants.providerToIndexerMapping:
                    v = helpers.tryInt(attr.get('value'))
                    if v > 0:
                        ids[NewznabConstants.providerToIndexerMapping[attr.get('name')]] = v
        return ids

    # overwrite method with that parses the rageid from the newznab feed
    def _parseItem(self, ns, item):

        title, url = self._title_and_url(item)

        ids = self.parse_ids(item, ns)

        if title and url:
            return self.add_cache_entry(title, url, id_dict=ids)

        logger.log('Data returned from the %s feed is incomplete, this result is unusable' % self.provider.name,
                   logger.DEBUG)
