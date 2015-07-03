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

import datetime

from . import generic


class StrikeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Strike')

        self.url_base = 'https://getstrike.net/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'api/v2/torrents/search/?category=TV&phrase=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech = 2 * [None]

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._checkAuth():
            return results

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_url = self.urls['search'] % search_string.replace(' ', '+')
                data_json = self.getURL(search_url, json=True)

                cnt = len(results)
                try:
                    for item in data_json['torrents']:
                        seeders = ('seeds' in item and item['seeds']) or 0
                        leechers = ('leeches' in item and item['leeches']) or 0
                        if seeders < self.minseed or leechers < self.minleech:
                            continue

                        title = ('torrent_title' in item and item['torrent_title']) or ''
                        download_url = ('magnet_uri' in item and item['magnet_uri']) or ''
                        if title and download_url:
                            results.append((title, download_url, seeders))
                except Exception:
                    pass
                self._log_result(mode, len(results) - cnt, search_url)

        # Sort results by seeders
        results.sort(key=lambda tup: tup[2], reverse=True)

        return results

    def findPropers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._get_season_search_strings(self, ep_obj, scene=False)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, scene=False, use_or=False)


provider = StrikeProvider()
