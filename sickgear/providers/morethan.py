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
from .. import logger
from ..helpers import try_int

from bs4_parser import BS4Parser

from six import iteritems


class MoreThanProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'MoreThan')

        self.url_base = 'https://www.morethantv.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login',
                     'search': self.url_base + 'torrents.php?searchtext=' + '&'.join([
                         '%s', '%s', 'order_by=time', 'order_way=desc'])}

        self.categories = {'Episode': [3, 4], 'Season': [5, 6]}
        self.categories['Cache'] = self.categories['Episode'] + self.categories['Season']

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.confirmed = False

    def _authorised(self, **kwargs):

        return super(MoreThanProvider, self)._authorised(logged_in=(lambda y=None: self.has_all_cookies('sid')),
                                                         post_params={'keeploggedin': '1', 'form_tmpl': True,
                                                                      'cinfo': '1920|1200|24|0'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v))
                   for (k, v) in iteritems({'info': r'torrents.php\?id', 'get': 'download', 'nuked': 'nuked'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = search_string.replace('.', ' ')
                search_url = self.urls['search'] % (search_string,
                                                    self._categories_string(mode, template='filter_cat[%s]=1'))

                # fetches 50 results by default, and up to 100 if allowed in user profile
                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    parse_only = dict(table={'class': (lambda at: at and 'torrent_table' in at)})
                    with BS4Parser(html, parse_only=parse_only, preclean=True) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells) or tr.find('img', alt=rc['nuked']):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr, {'size': r'by=size'})
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers,
                                                     verified=self.confirmed and not
                                                     any(tr.select('.icon_torrent_okay'))):
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = MoreThanProvider()
