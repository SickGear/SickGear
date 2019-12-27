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

from _23 import unidecode
from six import iteritems


class MagnetDLProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'MagnetDL')

        self.url_base = 'http://www.magnetdl.com/'

        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + 'download/tv/', 'search': self.url_base + 'search/?m=1&q=%s'}

        self.minseed, self.minleech = 2 * [None]

    def _search_provider(self, search_params, **kwargs):

        results = []

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': '^/file/', 'get': '^magnet:'})])

        for mode in search_params:
            for search_string in search_params[mode]:
                urls = [self.urls['browse'], self.urls['browse'] + '2']
                if 'Cache' != mode:
                    search_string = unidecode(search_string)
                    urls = [self.urls['search'] % re.sub(r'[.\s]+', ' ', search_string)]

                html = ''
                for search_url in urls:
                    html += self.get_url(search_url) or ''
                    if self.should_skip():
                        return results
                search_url = ', '.join(urls)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    if 'Cache' == mode:
                        html = re.sub(r'(?mis)^\s*?<tr><td[^>]+?id="pages">.*?</thead>\s*?<tbody>\r?\n', '', html)

                    with BS4Parser(html, parse_only=dict(table={'class': 'download'})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, KeyError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = MagnetDLProvider()
