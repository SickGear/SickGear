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


class BTSceneProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BTScene')

        self.url_home = ['https://%s/' % base64.b64decode(x) for x in [''.join(x) for x in [
                            [re.sub('[O\sx]+', '', x[::-1]) for x in [
                                'zRnx Y', 'ux V2Y', '15 S Z', 'sJ Omb', 'r N 2b', 'uxQxWZ', '=MOm d']],
                            [re.sub('[L\sq]+', '', x[::-1]) for x in [
                                'zLRn Y', 'uVqq2Y', '15SqLZ', 'sqJLmb', 'rN L2b', 'uqLQWZ', '=qgX b']],
                            [re.sub('[Q\s0]+', '', x[::-1]) for x in [
                                'zRn  Y', 'uQ V2Y', '1Q5QSZ', 'sJ0mQb', 'rQ0N2b', 'uIX QZ', 'ul200d']],
                            [re.sub('[T\s ]+', '', x[::-1]) for x in [
                                'zR nTY', 'uTVT2Y', '15 STZ', 'sTTJmb', 'r N2 b', 'uTTIXZ', '=TTM2Y']],
                            [re.sub('[i\sw]+', '', x[::-1]) for x in [
                                'zR  nY', 'li52ib', '15i SM', 's Jmwb', 'rN2  b', 'uwQW Z', 's9i Gb']],
                            [re.sub('[X\sV]+', '', x[::-1]) for x in [
                                'z Rn Y', 'lXV52b', '1 5 SM', 'sJ mXb', 'rN2XVb', 'uVQWVZ', 'mRX3Vd']],
                            [re.sub('[p\sF]+', '', x[::-1]) for x in [
                                'zFRFnY', 'l5 F2b', '15SF M', 'sFJmpb', 'rN 2pb', 'upQWpZ', '=MFFXb']],
                            [re.sub('[Q\sp]+', '', x[::-1]) for x in [
                                'z RpnY', 'u V2 Y', 'i5QSQZ', 'hBpQXe', 'lN 3Qc', 'vQ 5CZ', '=cpmpc']],
                            [re.sub('[o\sG]+', '', x[::-1]) for x in [
                                'zo RnY', 'u GV2Y', 'i 5S Z', 'hGBX e', 'loNG3c', 'lG5CGZ', '== Qod']],
                            [re.sub('[q\sW]+', '', x[::-1]) for x in [
                                'zR nqY', 'u V2qY', 'iq5 SZ', 'h BXqe', 'lN3  c', 'i5C WZ', '==gq e']],
                            [re.sub('[q\sg]+', '', x[::-1]) for x in [
                                'c gtQnY', 'mbg lN2', 'M 2Y tU', 'vgJHqcu', 'cz5C qe', 'QqgZjFG', '= g=']],
                            [re.sub('[H\sF]+', '', x[::-1]) for x in [
                                '2YzFRFnY', '0H5SZHuV', 'WZyFFJ3b', 'p1me 0 5', 'iHHcvJnc', '=cFmc v5']],
                            [re.sub('[w\si]+', '', x[::-1]) for x in [
                                'RwnwY', '2 wYz', 'Z u V', 'sii5S', 'RXi Y', 'nL wv', '3i B']],
                            [re.sub('[k\sh]+', '', x[::-1]) for x in [
                                'zRnkhY', 'uV  2Y', '65hSkZ', '2Nk Ge', 'phdn L', '=kk=gb']],
                            [re.sub('[q\sP]+', '', x[::-1]) for x in [
                                'mPblqN2ctQnY', 'vlWduM2 YPtU', 'nYoRXahZPm L', '15PSZuV2 YzR', 'WYrN 2PbsJmb',
                                '==wZ y9mL sx']],
                        ]]]
        self.url_vars = {'search': '?q=%s&order=1', 'browse': 'lastdaycat/type/Series/',
                         'get': 'torrentdownload.php?id=%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(vars)s',
                         'browse': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)(?:btscene|bts[-]official|full\sindex)', data)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': '\w+?(\d+)[.]html', 'verified': 'Verified'}.iteritems())

        url = self.url
        response = self.get_url(url)
        if self.should_skip():
            return results

        form = re.findall('(?is)(<form[^>]+)', response)
        response = any(form) and form[0] or response
        action = re.findall('<form[^>]+action=[\'"]([^\'"]*)', response)[0]
        url = action if action.startswith('http') else \
            url if not action else \
            (url + action) if action.startswith('?') else \
            self.urls['config_provider_home_uri'] + action.lstrip('/')

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else url + self.urls['search'] % (urllib.quote_plus(search_string))

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.select('tr[class$="_tr"]')

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows:
                            cells = tr.find_all('td')
                            if 6 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if self._peers_fail(mode, seeders, leechers) or \
                                        self.confirmed and not (tr.find('img', src=rc['verified'])
                                                                or tr.find('img', title=rc['verified'])):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = info and info.get_text().strip()
                                tid_href = info and rc['info'].findall(info['href'])
                                tid_href = tid_href and tryInt(tid_href[0], 0) or 0
                                tid_tr = tryInt(tr['id'].strip('_'), 0)
                                tid = (tid_tr, tid_href)[tid_href > tid_tr]

                                download_url = info and (self.urls['get'] % tid)
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

    def _episode_strings(self, ep_obj, **kwargs):
        return super(BTSceneProvider, self)._episode_strings(ep_obj, sep_date='.', **kwargs)

    def get_data(self, url):
        result = None
        resp = self.get_url(url, timeout=90)
        if self.should_skip():
            return result

        try:
            result = resp
            if re.search('(?i)\s+html', resp[0:30]):
                result = re.findall('(?i)"(magnet:[^"]+?)"', resp)[0]
        except IndexError:
            pass
        return result


provider = BTSceneProvider()
