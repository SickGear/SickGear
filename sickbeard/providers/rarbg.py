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
from sickbeard import helpers, logger
from sickbeard.indexers.indexer_config import INDEXER_TVDB


class RarbgProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Rarbg')

        self.url_base = 'https://rarbgmirror.xyz/'
        # api_spec: https://rarbg.com/pubapi/apidocs_v2.txt
        self.url_api = 'https://torrentapi.org/pubapi_v2.php?app_id=SickGear&'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'api_token': self.url_api + 'get_token=get_token',
                     'api_list': self.url_api + 'mode=list',
                     'api_search': self.url_api + 'mode=search'}

        self.params = {'defaults': '&format=json_extended&category=18;41&limit=100&sort=last&ranked=%(r)s&token=%(t)s',
                       'param_iid': '&search_imdb=%(sid)s',
                       'param_tid': '&search_tvdb=%(sid)s',
                       'param_str': '&search_string=%(str)s',
                       'param_seed': '&min_seeders=%(min_seeds)s',
                       'param_peer': '&min_leechers=%(min_peers)s'}

        self.proper_search_terms = '{{.proper.|.repack.}}'
        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech, self.token, self.token_expiry = 4 * [None]
        self.confirmed = False
        self.request_throttle = datetime.datetime.now()

    def _authorised(self, reset=False, **kwargs):

        if not reset and self.token and self.token_expiry and datetime.datetime.now() < self.token_expiry:
            return True

        for r in range(0, 3):
            response = helpers.getURL(self.urls['api_token'], session=self.session, json=True)
            if response and 'token' in response:
                self.token = response['token']
                self.token_expiry = datetime.datetime.now() + datetime.timedelta(minutes=14)
                return True
            time.sleep(1.1)

        logger.log(u'No usable API token returned from: %s' % self.urls['api_token'], logger.ERROR)
        return False

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised(reset=True):
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        id_search = None
        if hasattr(self, 'show') and self.show and self.show.indexer and self.show.indexerid:
            sid, search_with = 2 * [None]
            if 0 < len(self.show.imdb_info):
                sid = self.show.imdb_info['imdb_id']
                search_with = 'param_iid'
            elif INDEXER_TVDB == self.show.indexer:
                sid = self.show.indexerid
                search_with = 'param_tid'

            if sid and search_with:
                id_search = self.params[search_with] % {'sid': sid}

        dedupe = []
        # sort type "_only" as first to process
        search_types = sorted([x for x in search_params.items()], key=lambda tup: tup[0], reverse=True)
        for mode_params in search_types:
            mode_search = mode_params[0]
            mode = mode_search.replace('_only', '')
            for search_string in mode_params[1]:
                searched_url = search_url = ''
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

                cnt = len(items[mode])
                for r in range(0, 3):
                    time_out = 0
                    while(self.request_throttle > datetime.datetime.now()) and 2 >= time_out:
                        time_out += 1
                        time.sleep(1)

                    searched_url = search_url % {'r': int(self.confirmed), 't': self.token}

                    data_json = self.get_url(searched_url, json=True)

                    self.token_expiry = datetime.datetime.now() + datetime.timedelta(minutes=14)
                    self.request_throttle = datetime.datetime.now() + datetime.timedelta(seconds=3)
                    if not data_json:
                        continue

                    if 'error' in data_json:
                        if 5 == data_json['error_code']:  # Too many requests per second.
                            continue

                        elif 2 == data_json['error_code']:  # Invalid token set
                            if self._authorised(reset=True):
                                continue
                            self.log_result(mode, len(items[mode]) - cnt, searched_url)
                            return items[mode]
                    break

                if 'error' not in data_json:
                    for item in data_json['torrent_results']:
                        title, download_magnet, seeders, size = [
                            item.get(x) for x in 'title', 'download', 'seeders', 'size']
                        title = None is title and item.get('filename') or title
                        if not (title and download_magnet) or download_magnet in dedupe:
                            continue
                        dedupe += [download_magnet]

                        items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                self._log_search(mode, len(items[mode]) - cnt, searched_url)

            results = self._sort_seeding(mode, results + items[mode])

            if '_only' in mode_search and len(results):
                break

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, detail_only=True)

    def _episode_strings(self, ep_obj, **kwargs):

        search_params = generic.TorrentProvider._episode_strings(self, ep_obj, detail_only=True, date_or=True, **kwargs)
        if self.show.air_by_date and self.show.is_sports:
            for x, types in enumerate(search_params):
                for y, ep_type in enumerate(types):
                    search_params[x][ep_type][y] = '{{%s}}' % search_params[x][ep_type][y]

        return search_params


provider = RarbgProvider()
