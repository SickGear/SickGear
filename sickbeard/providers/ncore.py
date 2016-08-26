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


class NcoreProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'nCore')

        self.url_base = 'https://ncore.cc/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'torrents.php?mire=%s&' + '&'.join([
                         'miszerint=fid', 'hogyan=DESC', 'tipus=kivalasztottak_kozott',
                         'kivalasztott_tipus=xvidser,dvdser,hdser', 'miben=name']),
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.chk_td = True

    def _authorised(self, **kwargs):

        return super(NcoreProvider, self)._authorised(
            logged_in=(lambda y='': all([bool(y), 'action="login' not in y, self.has_all_cookies('PHPSESSID')])),
            post_params={'nev': self.username, 'pass': self.password, 'form_tmpl': 'name=[\'"]login[\'"]'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'list': '.*?torrent_all', 'info': 'details'}.iteritems())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % search_string

                # fetches 15 results by default, and up to 100 if allowed in user profile
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('div', class_=rc['list'])
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('div', class_='box_torrent')

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find('div', class_=x).get_text().strip()
                                    for x in 'box_s2', 'box_l2', 'box_meret2']]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                anchor = tr.find('a', href=rc['info'])
                                title = (anchor.get('title') or anchor.get_text()).strip()
                                download_url = self._link(anchor.get('href').replace('details', 'download'))
                            except (AttributeError, TypeError, ValueError):
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


provider = NcoreProvider()
