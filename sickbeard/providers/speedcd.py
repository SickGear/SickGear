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
import time

from . import generic
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt


class SpeedCDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SpeedCD', cache_update_freq=20)

        self.url_base = 'https://speed.cd/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'V3/API/API.php',
                     'get': self.url_base + '%s'}

        self.categories = {'Season': [41, 53], 'Episode': [2, 49, 50, 55], 'anime': [30]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(SpeedCDProvider, self)._authorised(
            logged_in=(lambda y=None: self.has_all_cookies('inSpeed_speedian')))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'get': 'download', 'fl': '\[freeleech\]'}.items())

        for mode in search_params.keys():
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict((x.split('=') for x in self._categories_string(mode).split('&')), search=search_string,
                                 jxt=2, jxw='b', freeleech=('on', None)[not self.freeleech])

                data_json = self.get_url(self.urls['search'], post_data=post_data, json=True)

                cnt = len(items[mode])
                try:
                    html = data_json.get('Fs')[0].get('Cn')[0].get('d')
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'cellspacing': 0})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[x].get_text().strip() for x in -2, -1, -3]]
                                if None is tr.find('a', href=rc['cats']) \
                                        or self.freeleech and None is rc['fl'].search(cells[1].get_text()) \
                                        or self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', 'torrent')
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (StandardError, Exception):
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', **kwargs)


provider = SpeedCDProvider()
