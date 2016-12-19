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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import time

from . import generic
from sickbeard.helpers import tryInt


class HD4FreeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HD4Free')

        self.url_base = 'https://hd4free.xyz/'

        self.urls = {'search': self.url_base + 'searchapi.php',
                     'get': self.url_base + 'download.php?torrent=%s&torrent_pass=%s'}

        self.url = self.url_base

        self.username, self.api_key, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return self._check_auth()

    def _search_provider(self, search_params, age=0, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        params = {'username': self.username, 'apikey': self.api_key,
                  'tv': 'true', 'fl': ('true', None)[not self.freeleech]}
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                params['search'] = '+'.join(search_string.split())
                json_resp = self.get_url(self.urls['search'], params=params, json=True)

                cnt = len(items[mode])
                for k, item in json_resp.items():
                    if 'error' == k or not item.get('total_results'):
                        break
                    seeders, leechers, size = [tryInt(n, n) for n in [
                        item.get(x) for x in 'seeders', 'leechers', 'size']]
                    if self._peers_fail(mode, seeders, leechers):
                        continue
                    title = item.get('release_name')
                    tid, tpass = [item.get('torrent' + x) for x in 'id', 'pass']
                    download_url = all([tid, tpass]) and (self.urls['get'] % (tid, tpass))
                    if title and download_url:
                        items[mode].append((title, download_url, seeders, self._bytesizer('%smb' % size)))

                self._log_search(mode, len(items[mode]) - cnt, self.session.response['url'])
                time.sleep(1.1)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = HD4FreeProvider()
