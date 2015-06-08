# Author: SickGear
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

import re
import datetime
import time

import sickbeard
import generic
from sickbeard import logger
from sickbeard import tvcache
from sickbeard import show_name_helpers
from sickbeard import helpers
from sickbeard.indexers.indexer_config import INDEXER_TVDB


class RarbgProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Rarbg')
        self.session = None

        self.request_throttle = datetime.datetime.now()
        self.token = None
        self.token_expiry = None

        self.confirmed = False
        self.ratio = None
        self.minseed = None
        self.minleech = None

        # api_spec: https://rarbg.com/pubapi/apidocs_v2.txt
        self.url_api = 'https://torrentapi.org/pubapi_v2.php?'
        self.urls = {'config_provider_home_uri': 'https://rarbg.com',
                     'api_token': self.url_api + 'get_token=get_token',
                     'api_list': self.url_api + 'mode=list',
                     'api_search': self.url_api + 'mode=search'}

        self.params = {'defaults': '&category=%(cat)s&ranked=%(ranked)s&limit=100&sort=last'
                                   % {'cat': 'tv', 'ranked': int(self.confirmed)} + '&token=%(token)s',
                       'param_iid': '&search_imdb=%(sid)s',
                       'param_tid': '&search_tvdb=%(sid)s',
                       'param_rid': '&search_tvrage=%(sid)s',
                       'param_str': '&search_string=%(str)s',
                       'param_seed': '&min_seeders=%(min_seeds)s',
                       'param_peer': '&min_leechers=%(min_peers)s'}

        self.url = self.urls['config_provider_home_uri']
        self.cache = RarbgCache(self)

    def _doLogin(self, reset=False):

        if not reset and self.token and self.token_expiry and datetime.datetime.now() < self.token_expiry:
            return True

        try:
            data = helpers.getURL(self.urls['api_token'], headers=self.headers, json=True)
            self.token = data['token']
            self.token_expiry = datetime.datetime.now() + datetime.timedelta(minutes=14)
            return True

        except Exception:
            pass

        logger.log(u'No usable API token returned from: %s' % self.urls['api_token'], logger.ERROR)
        return False

    def _get_season_search_strings(self, ep_obj):

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            ep_detail = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.anime:
            ep_detail = '%d' % ep_obj.scene_absolute_number
        else:
            ep_detail = 'S%02d' % int(ep_obj.scene_season)

        search_string = {'Season': []}
        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Season'].append('%s %s' % (show_name, ep_detail))

        if not self.show.sports and not self.show.anime:
            search_string.update({'Season_only': [ep_detail]})

        return [search_string]

    def _get_episode_search_strings(self, ep_obj, add_string=''):

        if not ep_obj:
            return []

        airdate = str(ep_obj.airdate).replace('-', ' ')
        if self.show.air_by_date:
            ep_detail = airdate
        elif self.show.sports:
            ep_detail = '%s|%s' % (airdate, ep_obj.airdate.strftime('%b'))
        elif self.show.anime:
            ep_detail = ep_obj.scene_absolute_number
        else:
            ep_detail = sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                              'episodenumber': ep_obj.scene_episode}
        if add_string and not self.show.anime:
            ep_detail += ' ' + add_string

        search_string = {'Episode': []}
        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Episode'].append(re.sub('\s+', ' ', '%s %s' % (show_name, ep_detail)))

        if not self.show.sports and not self.show.anime:
            search_string.update({'Episode_only': [ep_detail]})

        return [search_string]

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin(reset=True):
            return results

        id_search = None
        if hasattr(self, 'show') and self.show and self.show.indexer and self.show.indexerid:
            if 0 < len(self.show.imdb_info):
                sid = self.show.imdb_info['imdb_id']
                search_with = 'param_iid'
            else:
                sid = self.show.indexerid
                if INDEXER_TVDB == self.show.indexer:
                    search_with = 'param_tid'
                else:  # INDEXER_TVRAGE == self.show.indexer:
                    search_with = 'param_rid'
            id_search = self.params[search_with] % {'sid': sid}

        dedupe = []
        search_types = sorted([x for x in search_params.items()], key=lambda tup: tup[1], reverse=True)  # sort type "_only" as first to process
        for mode_params in search_types:
            mode_search = mode_params[0]
            mode_base = mode_search.replace('_only', '')
            for search_string in mode_params[1]:
                search_url = ''
                if 'RSS' == mode_search:
                    url = 'api_list'
                else:
                    url = 'api_search'

                    if '_only' in mode_search and id_search:
                        search_url = id_search

                    if None is not search_string:
                        search_url += self.params['param_str'] % {'str': search_string}

                search_url = self.urls[url] + self.params['defaults'] + search_url

                if self.minseed:
                    search_url += self.params['param_seed'] % {'min_seeds': self.minseed}

                if self.minleech:
                    search_url += self.params['param_peer'] % {'min_peers': self.minleech}

                logger.log(u'Base search URL: %s' % search_url, logger.DEBUG)

                for r in xrange(0, 3):
                    time_out = 0
                    while(self.request_throttle > datetime.datetime.now()) and 15 >= time_out:
                        time_out += 1
                        time.sleep(1)

                    try:
                        data = self.getURL(search_url % {'token': self.token}, json=True)
                    except Exception:
                        pass

                    self.request_throttle = datetime.datetime.now() + datetime.timedelta(seconds=3)

                    if 'error' in data:
                        if 5 == data['error_code']:  # Too many requests per second.
                            continue

                        elif 2 == data['error_code']:  # Invalid token set!
                            if self._doLogin(reset=True):
                                continue
                            return results
                    break

                if 'error' not in data:
                    for item in data['torrent_results']:
                        try:
                            title = item['filename']
                            get = item['download']
                            if not (title and get) or get in dedupe:
                                continue
                            dedupe += [get]
                            items[mode_base].append((title, get))
                            logger.log(u'Found result: %s' % title, logger.DEBUG)
                        except Exception:
                            pass

                    if 0 < len(items[mode_base]):
                        results += items[mode_base]
                        items[mode_base] = []
                    else:
                        logger.log(u'No results found for: %s' % search_string, logger.DEBUG)

            if '_only' in mode_search and 0 < len(results):
                break

        return results

    def findPropers(self, search_date=datetime.datetime.today()):
        return self._find_propers(search_date, '{{.proper.|.repack.}}')


class RarbgCache(tvcache.TVCache):
    def __init__(self, this_provider):

        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 10  # cache update frequency

    def _getRSSData(self):
        return self.provider.get_cache_data()


provider = RarbgProvider()
