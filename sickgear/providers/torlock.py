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
from _23 import quote_plus


class TorLockProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorLock')

        self.url_home = ['https://www.torlock.com/']

        self.url_vars = {'search': 'television/torrents/%s.html?sort=added&order=desc',
                         'browse': 'television/1/added/desc.html', 'get': 'tor/%s.torrent'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s',
                         'browse': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)TorLock', data[33:1024:])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        # a release links to /torrent/<id>/ on the site, a row linking to another site (e.g. *.t0r.store) is an advert
        rc = dict([(k, re.compile(f'(?i){v}')) for (k, v) in {'info': r'^/torrent/(\d+)'}.items()])

        for mode in search_params:
            for search_string in search_params[mode]:

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (quote_plus(search_string).replace('+', '-'))

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html) or re.search(r'<b>Error:\sNot\sFound</b>', html):
                        raise generic.HaltParseException
                    with BS4Parser(html) as soup:

                        tbl = soup.find('table', class_='tl-list')
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        for tr in tbl_rows[1:]:
                            try:
                                info = tr.find('a', class_='tl-name', href=rc['info'])
                                if not info:
                                    continue
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    tr.find('td', class_=x).get_text().strip() for x in ('tul', 'tdl', 'ts')]]
                                if self._reject_item(seeders, leechers,
                                                     verified=self.confirmed and not tr.find(class_='tl-ver')):
                                    continue

                                title = info.get_text().strip()
                                download_url = self._link(try_int(rc['info'].findall(info['href'])[0]))
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = TorLockProvider()
