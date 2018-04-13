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

import base64
import re
import traceback
import urllib

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class LimeTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'LimeTorrents')

        self.url_home = ['https://www.limetorrents.cc/'] + \
                        ['https://%s/' % base64.b64decode(x) for x in [''.join(x) for x in [
                            [re.sub('[ \sg]+', '', x[::-1]) for x in [
                                'XZtlg Gb', 'lJngcv R', 'nLz R nb', 'v xmYu V', 'CZl t2 Y', '==gwY2g5']],
                            [re.sub('[S\si]+', '', x[::-1]) for x in [
                                'X SZtlGb', 'lJi ncvR', 'nSSLzRnb', 'vxmSYu V', 'CSZilt2Y', '=S= Aet5']],
                            [re.sub('[x\s0]+', '', x[::-1]) for x in [
                                'tlGx b', 'u0ExTZ', 'i5xW d', 'j9 Gxb', 'kV020a', 'zx1m L']],
                            [re.sub('[Y\so]+', '', x[::-1]) for x in [
                                'to lGb', 'uoEYTZ', 'i 5WYd', 'jo 9Gb', 'ko V2a', '0  dnL', '==Y gZ']],
                            [re.sub('[r\sp]+', '', x[::-1]) for x in [
                                'XZt rlGb', 'lJpncpvR', 'n  LzRnb', 'vxmYu  V', 'ic ltp2Y', '=4Wa r35']],
                            [re.sub('[F\so]+', '', x[::-1]) for x in [
                                'lJncvRoX ZtlGb', 'vxFmYuVnLzoRnb', 'pxo2FYj5iclt2Y', '05W ZyJ3b0 VWb',
                                'j9G buVFnct5yc', '=o0WYloJHdz5ya']],
                            [re.sub('[F\sK]+', '', x[::-1]) for x in [
                                'XKZtlGFb', 'lKJncFvR', 'mLzKKRnb', 's 5WFdy1', 'mLrNF2Fb', '=F 8mZul']],
                            [re.sub('[r\sS]+', '', x[::-1]) for x in [
                                'RXZStSlGb', 'nblJ nrcv', 'cvRn LrzR', '6RnSblJ n', '9mScylW b', 'wZyr9mSLy', '=Sr=']],
                            [re.sub('[1\sy]+', '', x[::-1]) for x in [
                                'tylyGb', 'v11RXZ', 'lyJ1nc', 'zRnyyb', 'hxy1mL', 'u8G  d', '=1c Hc']],
                            [re.sub('[w\sy]+', '', x[::-1]) for x in [
                                't wlGb', 'v  RXZ', 'lJ  nc', 'zRnywb', '4pw nL', 'uY3 wY', 'ul2 yd']],
                            [re.sub('[f\s0]+', '', x[::-1]) for x in [
                                'XZtlG0 b', 'lJn fcvR', 'mL0zRn0b', 'zF Gc5fJ', 'mL kV2 c', '= =w0Zy9']],
                            [re.sub('[f\sy]+', '', x[::-1]) for x in [
                                'ZtylGyb', 'ncvyRyX', 'RnbylyJ', '5Jm fLz', 'cy zFGc', 'mLk  V2', '1fyV']],
                            [re.sub('[u\sQ]+', '', x[::-1]) for x in [
                                'ZtlGQub', 'nc  vRX', 'R nb lJ', '5 JQmLz', 'czQuFGc', 'muLkVQ2', '6QuJ']],
                            [re.sub('[p\sk]+', '', x[::-1]) for x in [
                                'XZtlkGpb', 'lJncvkkR', 'nLkzRnpb', 'vxm Y uV', 'Gbhppt2Y', 'n pJ3buw']],

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

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'get': 'dl'}.iteritems())

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (urllib.quote_plus(search_string))

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find_all('table', class_='table2')
                        torrent_rows = [] if not torrent_table else [
                            t.select('tr[bgcolor]') for t in torrent_table if
                            all([x in ' '.join(x.get_text() for x in t.find_all('th')).lower() for x in
                                 ['torrent', 'size']])]

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[0]:  # 0 = all rows
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [tryInt(n.replace(',', ''), n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                anchors = tr.td.find_all('a')
                                stats = anchors and [len(a.get_text()) for a in anchors]
                                title = stats and anchors[stats.index(max(stats))].get_text().strip()
                                download_url = self._link((tr.td.find('a', class_=rc['get']) or {}).get('href'))
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = LimeTorrentsProvider()
