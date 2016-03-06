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
import traceback

from . import generic
from sickbeard import logger, tvcache
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class TorrentingProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Torrenting')

        self.url_base = 'https://www.torrenting.com/'

        self.api = 'https://ttonline.us/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.api + 'secure.php',
                     'search': self.api + 'browse.php?%s&search=%s',
                     'get': self.api + '%s'}

        self.categories = {'shows': [4, 5]}

        self.url = self.urls['config_provider_home_uri']

        self.digest, self.minseed, self.minleech = 3 * [None]
        self.cache = TorrentingCache(self)

    def _authorised(self, **kwargs):

        return super(TorrentingProvider, self)._authorised(
            logged_in=(lambda x=None: (None is x or 'Other Links' in x) and self.has_all_cookies() and
                       self.session.cookies['uid'] in self.digest and self.session.cookies['pass'] in self.digest),
            failed_msg=(lambda x=None: u'Invalid cookie details for %s. Check settings'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download',
                                                             'cats': 'cat=(?:%s)' % self._categories_string(template='', delimiter='|')
                                                             }.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (self._categories_string(), search_string)

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', id='torrentsTable')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in (-2, -1, -3)]]
                                if None is tr.find('a', href=rc['cats']) or self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = 'title' in info.attrs and info.attrs['title'] or info.get_text().strip()
                                download_url = self.urls['get'] % tr.find('a', href=rc['get']).get('href')
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    @staticmethod
    def ui_string(key):

        return 'torrenting_digest' == key and 'use... \'uid=xx; pass=yy\'' or ''


class TorrentingCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _cache_data(self):

        return self.provider.cache_data()


provider = TorrentingProvider()
