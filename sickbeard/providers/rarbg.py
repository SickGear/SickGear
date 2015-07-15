# coding=utf-8
#
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

import datetime
import time

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.indexers.indexer_config import INDEXER_TVDB


class RarbgProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Rarbg')

        self.url_base = 'https://rarbg.com/'
        # api_spec: https://rarbg.com/pubapi/apidocs_v2.txt
        self.url_api = 'https://torrentapi.org/pubapi_v2.php?app_id=SickGear&'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'api_token': self.url_api + 'get_token=get_token',
                     'api_list': self.url_api + 'mode=list',
                     'api_search': self.url_api + 'mode=search'}

        self.categories = '18;41'
        self.params = {'defaults': '&category=%(cat)s&limit=100&sort=last' % {'cat': self.categories}
                                   + '&ranked=%(ranked)s&token=%(token)s',
                       'param_iid': '&search_imdb=%(sid)s',
                       'param_tid': '&search_tvdb=%(sid)s',
                       'param_rid': '&search_tvrage=%(sid)s',
                       'param_str': '&search_string=%(str)s',
                       'param_seed': '&min_seeders=%(min_seeds)s',
                       'param_peer': '&min_leechers=%(min_peers)s'}

        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech, self.token, self.token_expiry = 4 * [None]
        self.confirmed = False
        self.request_throttle = datetime.datetime.now()
        self.cache = RarbgCache(self)

    def _do_login(self, reset=False):

        if not reset and self.token and self.token_expiry and datetime.datetime.now() < self.token_expiry:
            return True

        response = helpers.getURL(self.urls['api_token'], session=self.session, json=True)
        if response and 'token' in response:
            self.token = response['token']
            self.token_expiry = datetime.datetime.now() + datetime.timedelta(minutes=14)
            return True

        logger.log(u'No usable API token returned from: %s' % self.urls['api_token'], logger.ERROR)
        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._do_login(reset=True):
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

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
                url = 'api_list'
                if 'Cache' != mode_search:
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

                cnt = len(items[mode_base])
                for r in range(0, 3):
                    time_out = 0
                    while(self.request_throttle > datetime.datetime.now()) and 2 >= time_out:
                        time_out += 1
                        time.sleep(1)

                    data = self.get_url(search_url % {'ranked': int(self.confirmed), 'token': self.token}, json=True)
                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(minutes=14)
                    self.request_throttle = datetime.datetime.now() + datetime.timedelta(seconds=3)

                    if 'error' in data:
                        if 5 == data['error_code']:  # Too many requests per second.
                            continue

                        elif 2 == data['error_code']:  # Invalid token set
                            if self._do_login(reset=True):
                                continue
                            self._log_result(mode_base, len(items[mode_base]) - cnt, search_url)
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
                        except Exception:
                            pass

                    if 0 < len(items[mode_base]):
                        results += items[mode_base]
                        items[mode_base] = []

                self._log_result(mode_base, len(items[mode_base]) - cnt, search_url)

            if '_only' in mode_search and 0 < len(results):
                break

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date, '{{.proper.|.repack.}}')

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._get_season_search_strings(self, ep_obj, detail_only=True)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        search_params = generic.TorrentProvider._get_episode_search_strings(self, ep_obj, detail_only=True)
        if self.show.air_by_date and self.show.sports:
            for x, types in enumerate(search_params):
                for y, ep_type in enumerate(types):
                    search_params[x][ep_type][y] = '{{%s}}' % search_params[x][ep_type][y]

        return search_params


class RarbgCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = RarbgProvider()
