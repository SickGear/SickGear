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
from . import generic
from sickbeard import helpers
from sickbeard.helpers import tryInt


class StrikeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Strike')

        self.url_base = 'https://getstrike.net/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'api/v2/torrents/search/?category=%s&phrase=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech = 2 * [None]

    def _search_provider(self, search_params, **kwargs):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            search_show = mode in ['Season', 'Episode']
            if not search_show and helpers.has_anime():
                search_params[mode] *= (1, 2)['Cache' == mode]

            for enum, search_string in enumerate(search_params[mode]):
                search_url = self.urls['search'] % \
                    (('tv', 'anime')[(search_show and bool(self.show and self.show.is_anime)) or bool(enum)],
                     (re.sub('[\.\s]+', ' ', search_string), 'x264')['Cache' == mode])

                data_json = self.get_url(search_url, json=True)

                cnt = len(items[mode])
                try:
                    for item in data_json['torrents']:
                        seeders, leechers, title, download_magnet, size = [tryInt(n, n) for n in [item.get(x) for x in [
                            'seeds', 'leeches', 'torrent_title', 'magnet_uri', 'size']]]
                        if self._peers_fail(mode, seeders, leechers):
                            continue

                        if title and download_magnet:
                            items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except Exception:
                    pass
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False)

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, **kwargs)


provider = StrikeProvider()
