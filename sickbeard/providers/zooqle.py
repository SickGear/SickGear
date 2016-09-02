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


class ZooqleProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Zooqle')

        self.url_base = 'https://zooqle.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'search?q=%s category:%s&s=dt&v=t&sd=d',
                     'get': self.url_base + 'download/%s.torrent'}

        self.categories = {'Season': ['TV'], 'Episode': ['TV'], 'anime': ['Anime']}
        self.categories['Cache'] = self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech = 2 * [None]

    def _search_provider(self, search_params, **kwargs):

        results = []

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'abd': '(\d{4}(?:[.]\d{2}){2})', 'peers': 'Seed[^\d]*(\d+)[\w\W]*?Leech[^\d]*(\d+)',
            'info': '(\w+)[.]html'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_string = '+'.join(rc['abd'].sub(r'%22\1%22', search_string).split())
                search_url = self.urls['search'] % (search_string, self._categories_string(mode, '', ','))

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    html = html.replace('</a> </i>', '</a>').replace('"href=', '" href=').replace('"style', '" style')
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', class_='table-torrents')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                td = tr.find_all('td')
                                stats = rc['peers'].findall((td[-1].find(class_='progress') or {}).get('title', ''))
                                seeders, leechers = any(stats) and [tryInt(x) for x in stats[0]] or (0, 0)
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = td[1].find('a', href=rc['info'])
                                title = info and info.get_text().strip()
                                size = td[-3].get_text().strip()
                                download_url = info and (self.urls['get'] % rc['info'].findall(info['href'])[0])
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

    def _cache_data(self):
        return self._search_provider({'Cache': ['*']})

provider = ZooqleProvider()
