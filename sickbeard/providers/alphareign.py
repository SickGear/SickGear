# coding=utf-8
#
# Author: SickGear
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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class AlphaReignProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'AlphaReign')

        self.url_base = 'https://alphareign.se/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base, 'search': self.url_base + '?query=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(AlphaReignProvider, self)._authorised(
            logged_in=(lambda y=None: self.has_all_cookies('token')), post_params={'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'get': 'magnet:'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % search_string

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html) or re.search('<h3>Result.*?&quot;.*?&quot;</h3>', html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find(id='results')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('div', class_='result')

                        for tr in torrent_rows:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr['data-%s' % x].strip() for x in 'seeders', 'leechers', 'size']]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = tr['data-name'].strip()
                                download_magnet = tr.find('a', href=rc['get'])['href']
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_magnet:
                                items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _season_strings(self, ep_obj, **kwargs):
        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False, **kwargs)

    def _episode_strings(self, ep_obj, **kwargs):
        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, **kwargs)

provider = AlphaReignProvider()
