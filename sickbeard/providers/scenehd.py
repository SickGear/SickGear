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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class SceneHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneHD', cache_update_freq=20)

        self.url_home = ['https://scenehd.org/']

        self.url_vars = {'login_action': 'login.php', 'search': 'browse.php?search=%s&cat=%s&sort=5'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login_action': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s'}

        self.categories = {'shows': [5, 6, 7]}

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]
        self.confirmed = False

    def _authorised(self, **kwargs):

        return super(SceneHDProvider, self)._authorised(post_params={'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download',
                                                             'nuked': 'nuke', 'filter': 'free'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (search_string, self._categories_string(mode, '%s', ','))

                html = self.get_url(search_url, timeout=90)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive'], attr='cellpadding="5"') as soup:
                        torrent_table = soup.find('table', class_='browse')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                info = tr.find('a', href=rc['info'])
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [n for n in [
                                    cells[head[x]].get_text().strip() for x in 'leech', 'leech', 'size']]
                                seeders, leechers, size = [tryInt(n, n) for n in
                                                           list(re.findall('^(\d+)[^\d]+?(\d+)', leechers)[0])
                                                           + re.findall('^[^\n\t]+', size)]
                                if (self.confirmed and
                                        any([tr.find('img', alt=rc['nuked']), tr.find('img', class_=rc['nuked'])])) \
                                        or (self.freeleech and not tr.find('a', class_=rc['filter'])) \
                                        or self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, KeyError):
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

    @staticmethod
    def ui_string(key):
        return 'scenehd_confirm' == key and 'skip releases marked as bad/nuked' or ''


provider = SceneHDProvider()
