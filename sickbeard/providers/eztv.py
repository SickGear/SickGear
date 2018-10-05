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

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class EztvProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'EZTV')

        self.url_home = ['https://eztv.ag/'] + \
                        ['https://%s/' % base64.b64decode(x) for x in [''.join(x) for x in [
                            [re.sub('[v\sz]+', '', x[::-1]) for x in [
                                '0vp XZ', 'uvEj d', 'i5 Wzd', 'j9 vGb', 'kV2v a', '0zdvnL', '==vg Z']],
                            [re.sub('[f\sT]+', '', x[::-1]) for x in [
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

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'get': '^magnet:'}.items())

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['browse'] % search_string if 'Cache' == mode else \
                    self.urls['search'] % search_string.replace('.', ' ')

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.findAll('table', attrs={'class': ['table', 'forum_header_border']})[-1]
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')
                        for tr in torrent_rows:
                            if 5 > len(tr.find_all('td')):
                                tr.decompose()
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders = tryInt(cells[head['seed']].get_text().strip())
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
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _cache_data(self, **kwargs):

        return self._search_provider({'Cache': [0, 1]})


provider = EztvProvider()
