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

from . import generic
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class MilkieProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Milkie')

        self.url_base = 'https://milkie.cc/'
        
        self.api = self.url_base + 'api/v1/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.api + 'auth/sessions', 'get': self.api + 'torrents/%s',
                     'search': self.api + 'torrents?pi=0&ps=100&query=%s&categories=2&mode=release'}

        self.username, self.password, self.minseed, self.minleech, self._token = 5 * [None]

    def _authorised(self, **kwargs):

        return super(MilkieProvider, self)._authorised(
            post_params=dict(login=False), post_json=dict(email=self.username, password=self.password),
            json=True, logged_in=self.logged_in)

    def logged_in(self, resp=None):
        
        self._token = resp and resp.get('token')
        return bool(self._token)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % search_string

                data_json = self.get_url(search_url, headers=dict(Authorization='Bearer %s' % self._token), json=True)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                if data_json:
                    for tr in data_json.get('releases'):
                        seeders, leechers, size = (tryInt(n, n) for n in [
                            tr.get(x) for x in ('seeders', 'leechers', 'size')])
                        if not self._reject_item(seeders, leechers):
                            title, download_url = tr.get('releaseName'), self._link(tr.get('shortId'))
                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = MilkieProvider()
