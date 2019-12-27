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


class LimeTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'LimeTorrents')

        self.url_home = ['https://www.limetorrents.cc/'] + \
                        ['https://%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'[F\sp]+', '', x[::-1]) for x in [
                                'XZFtlpGb', 'lJn pcvR', 'nFLpzRnb', 'v xpmYuV', 'CZlt F2Y', '=F QXYs5']],
                            [re.sub(r'[K\sP]+', '', x[::-1]) for x in [
                                'XZKtPlGb', 'lJncPPvR', 'nKLzRnKb', 'vxm Y uV', 'CZlPt2PY', '==wYK2P5']],
                        ]]]

        self.url_vars = {'search': 'search/tv/%s/', 'browse': 'browse-torrents/TV-shows/'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s',
                         'browse': '%(home)s%(vars)s'}

        self.minseed, self.minleech = 2 * [None]

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)LimeTorrents', data[33:1024:])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params:
            for search_string in search_params[mode]:

                search_string = unidecode(search_string)

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (quote_plus(search_string))

                html = self.get_url(search_url, provider=self)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, parse_only=dict(
                            table={'class': (lambda at: at and bool(re.search(r'table[23\d]*', at)))})) as tbl:
                        tbl_rows = [] if not tbl else tbl.select('tr')
                        for x, tr in enumerate(tbl_rows):
                            row_text = tr.get_text().lower()
                            if not('torrent' in row_text and 'size' in row_text):
                                tr.decompose()
                            else:
                                break
                            if 5 < x:
                                break
                        tbl_rows = [] if not tbl else tbl.select('tr')

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n.replace(',', ''), n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                anchors = tr.td.find_all('a')
                                stats = anchors and [len(a.get_text()) for a in anchors]
                                anchor = stats and anchors[stats.index(max(stats))]
                                title = anchor and anchor.get_text().strip()
                                download_url = anchor and self._link(anchor.get('href'))
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

    def get_data(self, url):
        result = None
        html = self.get_url(url)
        if self.should_skip():
            return result

        try:
            result = re.findall('(?i)"(magnet:[^"]+?)"', html)[0]
        except IndexError:
            logger.log('Failed no magnet in response', logger.DEBUG)
        return result


provider = LimeTorrentsProvider()
