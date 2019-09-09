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
from .. import logger
from ..helpers import try_int

from _23 import unidecode


class MilkieProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Milkie')

        self.url_base = 'https://milkie.cc/'
        
        self.api = self.url_base + 'api/v1/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.api + 'auth/sessions', 'auth': self.api + 'auth',
                     'get': self.api + 'torrents/%s/torrent?key=%s',
                     'search': self.api + 'torrents?pi=0&ps=100&query=%s&categories=2&mode=release&t.o=native'}

        self.username, self.email, self.password, self.minseed, self.minleech, self._token, self._dkey = 7 * [None]

    def _authorised(self, **kwargs):

        return super(MilkieProvider, self)._authorised(
            post_params=dict(login=False), post_json=dict(email=self.username, password=self.password),
            parse_json=True, logged_in=self.logged_in)

    def logged_in(self, resp=None):
        
        self._token = resp and resp.get('token')
        if self._token:
            resp = self.get_url(self.urls['auth'], skip_auth=True,
                                headers=dict(Authorization='Bearer %s' % self._token), parse_json=True)
            self._dkey = isinstance(resp, dict) and resp.get('user', {}).get('downloadKey')
        return bool(self._token)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_url = self.urls['search'] % search_string

                data_json, sess = self.get_url(search_url, headers=dict(Authorization='Bearer %s' % self._token),
                                               resp_sess=True, parse_json=True)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                if isinstance(data_json, dict):
                    for tr in data_json.get('torrents') or data_json.get('releases') or []:
                        seeders, leechers, size = (try_int(n, n) for n in [
                            tr.get(x) for x in ('seeders', 'leechers', 'size')])
                        if not self._reject_item(seeders, leechers):
                            title = tr.get('releaseName')
                            download_id = tr.get('id') or tr.get('shortId')
                            download_url = download_id and self.urls.get('get') % (download_id, self._dkey)
                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))
                elif 200 != getattr(sess, 'response', {}).get('status_code', 0):
                    logger.log('The site search is not working, skipping')
                    break

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = MilkieProvider()
