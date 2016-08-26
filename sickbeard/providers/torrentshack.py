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


class TorrentShackProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentShack', cache_update_freq=20)

        self.url_base = 'https://torrentshack.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'torrents.php?searchstr=%s&%s&' + '&'.join(
                         ['release_type=both', 'searchtags=', 'tags_type=0',
                          'order_by=s3', 'order_way=desc', 'torrent_preset=all']),
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [600, 620, 700, 981, 980], 'anime': [850]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentShackProvider, self)._authorised(logged_in=(lambda y=None: self.has_all_cookies('session')),
                                                             post_params={'keeplogged': '1', 'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'view', 'get': 'download', 'title': 'view\s+torrent\s+', 'size': '\s{2,}.*'}.iteritems())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                # fetch 15 results by default, and up to 100 if allowed in user profile
                search_url = self.urls['search'] % (search_string, self._categories_string(mode, 'filter_cat[%s]=1'))

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', class_='torrent_table')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in -2, -1, -4]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                size = rc['size'].sub('', size)
                                info = tr.find('a', title=rc['info'])
                                title = (rc['title'].sub('', info.attrs.get('title', '')) or info.get_text()).strip()
                                download_url = self._link(tr.find('a', title=rc['get'])['href'])
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

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', **kwargs)


provider = TorrentShackProvider()
