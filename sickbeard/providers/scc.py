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

import re
import time
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class SCCProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneAccess')

        self.url_home = ['https://sceneaccess.%s/' % u for u in 'eu', 'org']

        self.url_vars = {
            'login_action': 'login', 'search': 'browse?search=%s&method=1&c27=27&c17=17&c11=11', 'get': '%s',
            'nonscene': 'nonscene?search=%s&method=1&c44=44&c45=44', 'archive': 'archive?search=%s&method=1&c26=26'}
        self.url_tmpl = {
            'config_provider_home_uri': '%(home)s', 'login_action': '%(home)s%(vars)s',  'search': '%(home)s%(vars)s',
            'get': '%(home)s%(vars)s', 'nonscene': '%(home)s%(vars)s', 'archive': '%(home)s%(vars)s'}

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(SCCProvider, self)._authorised(post_params={'form_tmpl': 'method'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        if not self._authorised():
            return results

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string, void = self._title_and_url((search_string, None))
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                if 'Season' == mode:
                    searches = [self.urls['archive'] % search_string]
                else:
                    searches = [self.urls['search'] % search_string,
                                self.urls['nonscene'] % search_string]

                for search_url in searches:

                    html = self.get_url(search_url)

                    cnt = len(items[mode])
                    try:
                        if not html or self._has_no_results(html):
                            raise generic.HaltParseException

                        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                            torrent_table = soup.find(id='torrents-table')
                            torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                            if 2 > len(torrent_rows):
                                raise generic.HaltParseException

                            for tr in torrent_table.find_all('tr')[1:]:
                                try:
                                    seeders, leechers, size = [tryInt(n, n) for n in [
                                        tr.find('td', class_='ttr_' + x).get_text().strip()
                                        for x in 'seeders', 'leechers', 'size']]
                                    if self._peers_fail(mode, seeders, leechers):
                                        continue

                                    info = tr.find('a', href=rc['info'])
                                    title = (info.attrs.get('title') or info.get_text()).strip()
                                    download_url = self._link(tr.find('a', href=rc['get'])['href'])
                                except (AttributeError, TypeError, ValueError):
                                    continue

                                if title and download_url:
                                    items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                    except generic.HaltParseException:
                        time.sleep(1.1)
                    except (StandardError, Exception):
                        logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                    self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', **kwargs)


provider = SCCProvider()
