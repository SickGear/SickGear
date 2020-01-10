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


class ETTVProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'ETTV')

        self.url_home = ['https://www.ettv.tv/']
        self.url_vars = {'browse': 'torrents.php?%s&search=%s&sort=id&order=desc',
                         'search': 'torrents-search.php?%s&search=%s&sort=id&order=desc'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s',
                         'browse': '%(home)s%(vars)s', 'search': '%(home)s%(vars)s'}
        self.url_drop = ['http://et']

        self.categories = {'Season': [7], 'Episode': [41, 5, 50, 72, 77]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.minseed, self.minleech = 2 * [None]

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)(?:ettv)', data)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': 'torrent/'})])

        for mode in search_params:
            for search_string in search_params[mode]:

                search_string = unidecode(search_string)

                search_url = self.urls[('browse', 'search')['Cache' != mode]] % (
                    self._categories_string(mode), search_string)

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, parse_only=dict(table={'class': (lambda at: at and 'table' in at)})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 6 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, {'seed': r'seed', 'leech': r'leech', 'size': r'^size'})
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(info.get('href'))
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

                if len(items[mode]):
                    break

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def change_params(params):
        for x, types in enumerate(params):
            for y, ep_type in enumerate(types):
                new_list = []
                for t in params[0].get('Episode') or params[0].get('Season', []):
                    t = t.replace(' ', '.')
                    new_list += ['%2B ' + t, t]
                params[x][ep_type] = new_list
        return params

    def _season_strings(self, ep_obj, **kwargs):
        return self.change_params(super(ETTVProvider, self)._season_strings(ep_obj, **kwargs))

    def _episode_strings(self, ep_obj, **kwargs):
        return self.change_params(super(ETTVProvider, self)._episode_strings(ep_obj, **kwargs))

    def get_data(self, url):
        result = None
        html = self.get_url(url, timeout=90)
        if self.should_skip():
            return result

        try:
            result = re.findall('(?i)"(magnet:[^"]+?)"', html)[0]
        except IndexError:
            logger.log('Failed no magnet in response', logger.DEBUG)
        return result


provider = ETTVProvider()
