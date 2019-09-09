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
import traceback

from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import unidecode
from six import iteritems


class FLProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'FileList')

        self.url_base = 'https://filelist.ro/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'browse.php?search=%s&%s&incldead=0'}

        self.categories = {'Season': [14], 'Episode': [13, 21, 23], 'anime': [24]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(FLProvider, self)._authorised()

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': 'details', 'get': 'download'})])
        for mode in search_params:
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)

                html = self.get_url(self.urls['search'] % ('+'.join(search_string.split()),
                                                           self._categories_string(mode, template='cats[]=%s')))
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html) as soup:
                        tbl_rows = soup.find_all('div', 'torrentrow')

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        for tr in tbl_rows:
                            cells = tr.select('span[style*="cell"]')
                            if 6 > len(cells):
                                continue
                            try:
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[x].get_text().strip() for x in (-3, -2, -5)]]
                                if not tr.find('a', href=rc['cats']) or self._reject_item(seeders, leechers):
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, self.session.response.get('url'))

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = FLProvider()
