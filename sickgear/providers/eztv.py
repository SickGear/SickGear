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
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import b64decodestring, unidecode
from six import iteritems


class EztvProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'EZTV')

        self.url_home = ['https://eztv.ag/'] + \
                        ['https://%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'[v\sz]+', '', x[::-1]) for x in [
                                '0vp XZ', 'uvEj d', 'i5 Wzd', 'j9 vGb', 'kV2v a', '0zdvnL', '==vg Z']],
                            [re.sub(r'[f\sT]+', '', x[::-1]) for x in [
                                '0TpfXZ', 'ufTEjd', 'i5WTTd', 'j9f Gb', 'kV f2a', 'z1mTTL']],
                        ]]]
        self.url_vars = {'search': 'search/%s', 'browse': 'page_%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s',
                         'search': '%(home)s%(vars)s', 'browse': '%(home)s%(vars)s'}

        self.minseed = None

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)(?:EZTV\s[-]\sTV\sTorrents)', data[0:300])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'get': '^magnet:'})])

        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_url = self.urls['browse'] % search_string if 'Cache' == mode else \
                    self.urls['search'] % search_string.replace('.', ' ')

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html) as soup:
                        tbl = soup.findAll('table', attrs={'class': ['table', 'forum_header_border']})[-1]
                        tbl_rows = [] if not tbl else tbl.find_all('tr')
                        for tr in tbl_rows:
                            if 5 > len(tr.find_all('td')):
                                tr.decompose()
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders = try_int(cells[head['seed']].get_text().strip())
                                if self._reject_item(seeders):
                                    continue

                                title = tr.select('a.epinfo')[0].get_text().strip()
                                size = cells[head['size']].get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, KeyError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (generic.HaltParseException, IndexError):
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _cache_data(self, **kwargs):

        return self._search_provider({'Cache': [0, 1]})


provider = EztvProvider()
