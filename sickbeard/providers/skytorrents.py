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


class SkytorrentsProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Skytorrents')

        self.url_base = 'https://skytorrents.lol/'

        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + '?category=show&sort=created&query=%s&page=%s'}

        self.minseed, self.minleech = 2 * [None]

    def _search_provider(self, search_params, **kwargs):
        results = []
        self.session.headers['Cache-Control'] = 'max-age=0'
        last_recent_search = self.last_recent_search
        last_recent_search = '' if not last_recent_search else last_recent_search.replace('id-', '')
        for mode in search_params:
            urls = []
            for search_string in search_params[mode]:
                urls += [[]]
                search_string = unidecode(search_string)
                search_string = search_string if 'Cache' == mode else search_string.replace('.', ' ')
                for page in range((3, 5)['Cache' == mode])[1:]:
                    urls[-1] += [self.urls['search'] % (search_string, page)]
            results += self._search_urls(mode, last_recent_search, urls)
            last_recent_search = ''

        return results

    def _search_urls(self, mode, last_recent_search, urls):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': r'(^(info|torrent)/|/[\w+]{40,}\s*$)', 'get': '^magnet:.*?btih:([^&]+)'})])

        lrs_found = False
        lrs_new = True
        for search_urls in urls:  # this intentionally iterates once to preserve indentation
            for search_url in search_urls:
                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                cnt_search = 0
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    parse_only = dict(table={'class': (lambda at: at and 'is-striped' in at)})
                    with BS4Parser(html, parse_only=parse_only, preclean=True) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            cnt_search += 1
                            try:
                                head = head if None is not head else self._header_row(tr)

                                dl = tr.find('a', href=rc['get'])['href']
                                dl_id = rc['get'].findall(dl)[0]
                                lrs_found = dl_id == last_recent_search
                                if lrs_found:
                                    break

                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                info = tr.select_one(
                                    '[alt*="magnet"], [title*="magnet"]') \
                                    or tr.find('a', href=rc['info'])
                                title = re.sub(r'(^www\.\w+\.\w{3}\s[^0-9A-Za-z]\s|\s(using|use|magnet|link))', '', (
                                        info.attrs.get('title') or info.attrs.get('alt'))).strip()
                                download_url = self._link(dl)
                            except (AttributeError, TypeError, ValueError, KeyError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

                if self.is_search_finished(mode, items, cnt_search, rc['get'], last_recent_search, lrs_new, lrs_found):
                    break
                lrs_new = False

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _cache_data(self, **kwargs):
        result_1 = self._search_provider({'Cache': ['x264']})
        lrs_1 = self.last_recent_search

        self.last_recent_search = None
        name_1 = self.name
        self.name += '2'
        result_2 = self._search_provider({'Cache': ['x265']})

        self.name = name_1
        self.last_recent_search = lrs_1

        return result_1 + result_2


provider = SkytorrentsProvider()
