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
import urllib

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class BTSceneProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BTScene')

        self.url_home = ['http://www.btstorrent.cc/', 'http://bittorrentstart.com/',
                         'http://diriri.xyz/', 'http://mytorrentz.tv/']

        self.url_vars = {'search': 'results.php?q=%s&category=series&order=1', 'browse': 'lastdaycat/type/Series/',
                         'get': 'torrentdownload.php?id=%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s',
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
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (urllib.quote_plus(search_string))

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.select('tr[class$="_tr"]')

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows:
                            cells = tr.find_all('td')
                            if 6 > len(cells):
                                continue
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[x].get_text().strip() for x in -4, -3, -5]]
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
        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', **kwargs)


provider = BTSceneProvider()
