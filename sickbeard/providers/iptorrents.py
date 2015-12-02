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
from sickbeard import logger, tvcache
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class IPTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'IPTorrents')

        self.url_base = 'https://iptorrents.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'torrents/',
                     'search': self.url_base + 't?%s;q=%s;qf=ti%s%s#torrents',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [4, 5, 22, 23, 24, 25, 26, 55, 65, 66, 73, 78, 79], 'anime': [60]}

        self.proper_search_terms = None
        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = IPTorrentsCache(self)

    def _authorised(self, **kwargs):

        return super(IPTorrentsProvider, self)._authorised(post_params={'php': ''})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                # URL with 50 tv-show results, or max 150 if adjusted in IPTorrents profile
                search_url = self.urls['search'] % (self._categories_string(mode, '%s', ';'), search_string,
                                                    ('', ';free')[self.freeleech], (';o=seeders', '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'torrents'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [int(tr.find('td', attrs={'class': x}).get_text().strip())
                                                     for x in ('t_seeders', 't_leechers')]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = ('title' in info.attrs and info['title']) or info.get_text().strip()
                                size = tr.find_all('td')[-4].get_text().strip()

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


class IPTorrentsCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _cache_data(self):

        return self.provider.cache_data()


provider = IPTorrentsProvider()
