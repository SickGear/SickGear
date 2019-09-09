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
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import unidecode
from six import iteritems


class ZooqleProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Zooqle')

        self.url_base = 'https://zooqle.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'search?q=%s category:%s&s=%s&v=t&sd=d'}

        self.categories = {'Season': ['TV'], 'Episode': ['TV'], 'anime': ['Anime']}
        self.categories['Cache'] = self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech = 2 * [None]

    def _search_provider(self, search_params, **kwargs):

        results = []

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'abd': r'(\d{4}(?:[.]\d{2}){2})', 'peers': r'Seed[^\d]*(\d+)[\w\W]*?Leech[^\d]*(\d+)',
            'info': r'(\w+)[.]html', 'get': r'^magnet:'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_string = '+'.join(rc['abd'].sub(r'%22\1%22', search_string).split())
                search_url = self.urls['search'] % (
                    search_string, self._categories_string(mode, '', ',')
                    + ' %2Blang%3Aen', ('ns', 'dt')['Cache' == mode])

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    html = html.replace('</a> </i>', '</a>').replace('"href=', '" href=').replace('"style', '" style')
                    parse_only = dict(table={'class': (lambda at: at and 'table-torrents' in at)})
                    with BS4Parser(html, parse_only=parse_only) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, {'peers': r'(?:zqf\-clou)', 'size': r'(?:zqf\-file)', 'down': r'(?:zqf\-down)'})
                                stats = rc['peers'].findall(
                                    (cells[head['peers']].find(class_='progress') or {}).get('title', ''))
                                seeders, leechers = any(stats) and [try_int(x) for x in stats[0]] or (0, 0)
                                if self._reject_item(seeders, leechers):
                                    continue
                                for cell in (1, 0):
                                    info = cells[cell].find('a')
                                    if ''.join(re.findall(r'[a-z0-9]+', info.get_text().lower())) in \
                                            re.sub(r'html\?.*', '', ''.join(
                                                re.findall(r'[a-z0-9?]+', info['href'].lower()))):
                                        break
                                else:
                                    info = cells[1].find('a', href=rc['info']) or cells[0].find('a', href=rc['info'])
                                title = info.get_text().strip()
                                size = cells[head['size']].get_text().strip()
                                download_url = cells[head['down']].find('a', href=rc['get'])['href']
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):
        return super(ZooqleProvider, self)._episode_strings(
            ep_obj, sep_date='.', ep_detail_anime=lambda x: '%02i' % x, **kwargs)

    def _cache_data(self, **kwargs):
        return self._search_provider({'Cache': ['*']})


provider = ZooqleProvider()
