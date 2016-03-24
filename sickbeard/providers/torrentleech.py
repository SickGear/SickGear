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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class TorrentLeechProvider(generic.TorrentProvider):
    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentLeech', cache_update_freq=20)

        self.url_base = 'https://torrentleech.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'user/account/login/',
                     'browse': self.url_base + 'torrents/browse/index/categories/%(cats)s',
                     'search': self.url_base + 'torrents/browse/index/query/%(query)s/categories/%(cats)s',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [2, 26, 27, 32], 'anime': [7, 34, 35]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentLeechProvider, self)._authorised(logged_in=(lambda x=None: self.has_all_cookies(pre='tl')),
                                                             post_params={'remember_me': 'on', 'login': 'submit'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_url = self.urls[('search', 'browse')['Cache' == mode]] % {
                    'cats': self._categories_string(mode, '', ','),
                    'query': isinstance(search_string, unicode) and unidecode(search_string) or search_string}

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'id': 'torrenttable'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [int(tr.find('td', attrs={'class': x}).get_text().strip())
                                                     for x in ('seeders', 'leechers')]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('td', {'class': 'name'}).a
                                title = ('title' in info.attrs and info['title']) or info.get_text().strip()
                                size = tr.find_all('td')[-5].get_text().strip()

                                download_url = self.urls['get'] % str(tr.find('a', href=rc['get'])['href']).lstrip('/')
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='|', **kwargs)



provider = TorrentLeechProvider()
