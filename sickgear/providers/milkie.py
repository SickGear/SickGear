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

from requests import Request

from . import generic
from .. import logger
from ..helpers import try_int


class MilkieProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Milkie')

        self.url_base = 'https://milkie.cc/'

        self.api = self.url_base + 'api/v1/'
        self.urls = dict(
            config_provider_home_uri=self.url_base,
            login=self.api + 'auth/sessions', auth=self.api + 'auth',
            get=self.api + 'torrents/%s/torrent',
            search=self.api + 'torrents?pi=0&ps=100&categories=2&%s',
            params=('t.f=0', 'mode=release&t.o=native')
        )

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
            user = isinstance(resp, dict) and resp.get('user')
            self._dkey = user and user.get('apiKey') or user.get('downloadKey')
        return bool(self._token) and bool(self._dkey)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params:
            for search_string in search_params[mode]:

                search_url = ''
                data_json, sess = None, None
                for cur_param in self.urls['params']:
                    search_url = getattr(Request(
                        'GET', self.urls['search'] % cur_param,
                        params={'query': search_string}).prepare(), 'url', None)
                    try:
                        data_json, sess = self.get_url(search_url, resp_sess=True, parse_json=True,
                                                       headers=dict(Authorization='Bearer %s' % self._token))
                        if isinstance(data_json, dict):
                            break
                    except(BaseException, Exception):
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
                            download_url = download_id and getattr(Request(
                                'GET', self.urls['get'] % download_id,
                                params={'key': self._dkey}).prepare(), 'url', None)
                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))
                elif 200 != getattr(sess, 'response', {}).get('status_code', 0):
                    logger.log('The site search is not working, skipping')
                    break

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = MilkieProvider()
