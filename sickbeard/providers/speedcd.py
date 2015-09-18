# coding=utf-8
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
import time

from . import generic
from sickbeard import tvcache
from sickbeard.helpers import tryInt


class SpeedCDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SpeedCD')

        self.url_base = 'http://speed.cd/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'V3/API/API.php',
                     'get': self.url_base + 'download.php?torrent=%s'}

        self.categories = {'Season': {'c41': 1, 'c53': 1},
                           'Episode': {'c2': 1, 'c49': 1, 'c50': 1, 'c55': 1},
                           'Cache': {'c41': 1, 'c2': 1, 'c49': 1, 'c50': 1, 'c53': 1, 'c55': 1}}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = SpeedCDCache(self)

    def _authorised(self, **kwargs):

        return super(SpeedCDProvider, self)._authorised(logged_in=(lambda x=None: self.has_all_cookies('inSpeed_speedian')))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        remove_tag = re.compile(r'<[^>]*>')
        for mode in search_params.keys():
            search_mode = (mode, 'Episode')['Propers' == mode]
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict({'/browse.php?': None, 'cata': 'yes', 'jxt': 4, 'jxw': 'b', 'search': search_string},
                                 **self.categories[search_mode])
                if self.freeleech:
                    post_data['freeleech'] = 'on'

                data_json = self.get_url(self.urls['search'], post_data=post_data, json=True)

                cnt = len(items[mode])
                try:
                    if not data_json:
                        raise generic.HaltParseException
                    torrents = data_json.get('Fs', [])[0].get('Cn', {}).get('torrents', [])

                    for item in torrents:

                        if self.freeleech and not item.get('free'):
                            continue

                        seeders, leechers, size = [tryInt(n, n) for n in [item.get(x) for x in 'seed', 'leech', 'size']]
                        if self._peers_fail(mode, seeders, leechers):
                            continue

                        title = remove_tag.sub('', item.get('name'))
                        download_url = self.urls['get'] % item.get('id')
                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except Exception:
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', **kwargs)


class SpeedCDCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 20  # cache update frequency

    def _cache_data(self):

        return self.provider.cache_data()


provider = SpeedCDProvider()
