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

try:
    from collections import OrderedDict
except ImportError:
    from requests.compat import OrderedDict
import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode

FLTAG = '</a>\s+<img[^>]+%s[^<]+<br'


class FanoProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Fano')

        self.url_base = 'https://www.fano.in/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php', 'get': self.url_base + '%s',
                     'search': self.url_base + 'browse_old.php?search=%s&%s&incldead=0'}

        self.categories = {'Season': [49], 'Episode': [6, 23, 32, 35], 'anime': [27]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.filter = []
        self.may_filter = OrderedDict([
            ('f0', ('not marked', False, '')), ('fx2', ('x2', True, FLTAG % 'x2_up')),
            ('fgx2', ('gold/x2', True, FLTAG % 'free[^<]+<img[^>]+x2_up')), ('fg', ('gold', True, FLTAG % 'free'))])
        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(FanoProvider, self)._authorised()

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'abd': '(\d{4}(?:[.]\d{2}){2})', 'info': 'details', 'get': 'download'}.items())
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            rc['filter'] = re.compile('(?i)(%s)' % '|'.join(
                [self.may_filter[f][2] for f in filters if self.may_filter[f][1]]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join([self.may_filter[f][0] for f in filters]))
        for mode in search_params.keys():
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_string = '+'.join(rc['abd'].sub(r'%22\1%22', search_string).split())
                search_url = self.urls['search'] % (search_string, self._categories_string(mode))

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', id='line')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if (5 > len(cells)
                                or (any(self.filter)
                                    and ((non_marked and rc['filter'].search(str(tr)))
                                         or (not non_marked and not rc['filter'].search(str(tr)))))):
                                continue
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[x].get_text().strip() for x in -2, -1, -4]]
                                if self._peers_fail(mode, seeders, leechers) or not tr.find('a', href=rc['cats']):
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, log + search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = FanoProvider()
