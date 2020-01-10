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

from _23 import b64decodestring, quote_plus, unidecode
from six import iteritems


class TorLockProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorLock')

        self.url_home = ['https://www.torlock.com/'] + \
                        ['https://%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'[g\sF]+', '', x[::-1]) for x in [
                                'y9FFGd', 'j9FgGb', '15 Fya', 'sF Jmb', 'rN 2Fb', 'uQW FZ', '0Vmg Y']],
                            [re.sub(r'[O\si]+', '', x[::-1]) for x in [
                                'byO9Gid', 'y aji9G', '02O bj1', 'vJ Hicu', 'cz 5OCe', 'QZij FG', '=  =']],
                        ]]]

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

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': r'torrent.?(\d+)', 'versrc': r'ver\.', 'verified': 'Verified'})])

        for mode in search_params:
            for search_string in search_params[mode]:

                search_string = unidecode(search_string)

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (quote_plus(search_string).replace('+', '-'))

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html.replace('thead', 'tr')) as soup:

                        tbl = soup.find(
                            'div', class_=('panel panel-default', 'table-responsive')['Cache' == mode])
                        if None is tbl:
                            raise generic.HaltParseException
                        tbl = tbl.find(
                            'table', class_='table table-striped table-bordered table-hover table-condensed')
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
                                if self._reject_item(seeders, leechers, verified=self.confirmed and not (
                                        tr.find('img', src=rc['versrc']) or tr.find('img', title=rc['verified']))):
                                    continue

                                info = tr.find('a', href=rc['info']) or {}
                                title = info and info.get_text().strip()
                                tid_href = info and try_int(rc['info'].findall(info['href'])[0])
                                download_url = tid_href and self._link(tid_href)
                            except (AttributeError, TypeError, ValueError, IndexError):
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


provider = TorLockProvider()
