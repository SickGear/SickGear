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
from sickbeard import logger, show_name_helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class HorribleSubsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HorribleSubs', anime_only=True)

        self.url_base = 'http://horriblesubs.info/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + 'lib/latest.php',
                     'search': self.url_base + 'lib/search.php?value=%s'}
        self.url = self.urls['config_provider_home_uri']

        delattr(self, 'search_mode')
        delattr(self, 'search_fallback')

    def _search_provider(self, search_params, **kwargs):

        results = []
        if self.show and not self.show.is_anime:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'dl-label', 'get': 'magnet:', 'nodots': '[\.\s]+'}.items())

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode else \
                    self.urls['search'] % rc['nodots'].sub(' ', search_string)

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.find_all('table', class_='release-table')

                        if 1 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows:
                            if 4 < len(tr.find_all('td')):
                                try:
                                    title = tr.find('td', class_='dl-label').get_text().strip()
                                    title = title.startswith('[') and title or '[HorribleSubs] %s' % title
                                    download_url = self._link(tr.find('a', href=rc['get'])['href'])
                                    if title and download_url:
                                        items[mode].append((title, download_url, '', ''))
                                except (AttributeError, TypeError, ValueError):
                                    continue

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = HorribleSubsProvider()
