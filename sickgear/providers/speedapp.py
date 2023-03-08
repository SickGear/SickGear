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
from ..helpers import try_int

from six import string_types


class SpeedAppProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'SpeedApp')

        self.url_base = 'https://speedapp.io/'

        self.api = self.url_base + 'api/'
        self.urls = dict(
            config_provider_home_uri=self.url_base,
            login=self.api + 'test',
            search=self.api + 'torrent?itemsPerPage=50&search=%s&%s', cats=self.api + 'category',
            get=self.api + 'torrent/%s/download'
        )

        self.perms_needed = self.perms = ('torrent.read', 'torrent.download', 'snatch.read')
        self.api_key, self._authd, self.raise_auth_exception, self.minseed, self.minleech, self.cats = 6 * [None]

    def _authorised(self, **kwargs):

        return super(SpeedAppProvider, self)._authorised(
            logged_in=self.logged_in, parse_json=True, headers=self.auth_header(),
            failed_msg=(lambda y=None: 'Invalid token or permissions for %s. Check settings'))

    def logged_in(self, resp=None):

        self._authd = None
        self.perms_needed = self.perms
        if isinstance(resp, dict) and isinstance(resp.get('scopes'), list):
            self._authd = True
            self.perms_needed = list(filter(lambda x: True is not x,
                                            [p in resp.get('scopes') or p for p in self.perms]))
            if not self.perms_needed:
                self.categories = None
                resp = self.get_url(self.urls['cats'], skip_auth=True, parse_json=True, headers=self.auth_header())
                if isinstance(resp, list):
                    categories = [category['id'] for category in list(filter(
                        lambda c: isinstance(c.get('id'), int) and isinstance(c.get('name'), string_types)
                        and c.get('name').upper() in ('TV PACKS', 'TV HD', 'TV SD'), resp))]
                    self.categories = {'Cache': categories, 'Episode': categories, 'Season': categories}

        return not any(self.perms_needed)

    def auth_header(self):
        return {'X-Client-Id': '328b70a3f869e26de994', 'Authorization': 'Bearer %s' % self.api_key}

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised() or not self.categories:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params:
            for search_string in search_params[mode]:
                search_url = self.urls['search'] % (
                    search_string, self._categories_string(mode, template='categories[]=%s'))

                data_json = self.get_url(search_url, skip_auth=True, parse_json=True, headers=self.auth_header())
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                if isinstance(data_json, list):
                    for tr in data_json or []:
                        seeders, leechers, size, title, tid = (try_int(n, n) for n in [
                            tr.get(x) for x in ('seeders', 'leechers', 'size', 'name', 'id')])
                        if not self._reject_item(seeders, leechers) and title and tid:
                            items[mode].append((title, self._link(tid), seeders, self._bytesizer(size)))

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def ui_string(self, key):
        try:
            not_authd = not self._authd and self._check_auth(True) and self._authorised()
        except (BaseException, Exception):
            not_authd = True

        return ('%s_api_key' % self.get_id()) == key and 'API Token' or \
               ('%s_api_key_tip' % self.get_id()) == key and \
               ((not_authd or self.perms_needed)
                and ('create token at <a href="%sprofile/api-tokens">%s site</a><br>'
                     'with perms %s' % (self.url_base, self.name, list(map(
                           lambda p: 't.read' in p and 'Read torrents'
                                     or 't.down' in p and 'Download torrents'
                                     or 'ch.read' in p and 'Read snatches', self.perms_needed))))
                .replace('[', '').replace(']', '')
                or 'token is valid and required permissions are enabled') \
            or ''


provider = SpeedAppProvider()
