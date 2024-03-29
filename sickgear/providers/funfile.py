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
import traceback

from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from six import iteritems


class FunFileProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'FunFile', cache_update_iv=15)

        self.url_base = 'https://www.funfile.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'browse.php?%s&search=%s&incldead=0&showspam=1'}

        self.categories = {'shows': [7], 'anime': [44]}

        self.url = self.urls['config_provider_home_uri']
        self.url_timeout = 90
        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        time.sleep(2.5)
        return super(FunFileProvider, self)._authorised(
            logged_in=(lambda y=None: all(
                [None is not self.session.cookies.get(x, domain='.funfile.org') for x in ('uid', 'pass')])),
            post_params={'form_tmpl': True}, timeout=self.url_timeout)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': 'detail', 'get': 'download'})])
        for mode in search_params:
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_url = self.urls['search'] % (self._categories_string(mode), search_string)

                html = self.get_url(search_url, timeout=self.url_timeout)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html) as soup:
                        tbl = soup.find('td', class_='colhead').find_parent('table')
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            info = tr.find('a', href=rc['info'])
                            if 5 > len(cells) or not info:
                                continue
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, {'seed': r'(?:up\.gif|seed|s/l)', 'leech': r'(?:down\.gif|leech|peers)'})
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if None is tr.find('a', href=rc['cats']) or self._reject_item(seeders, leechers):
                                    continue

                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (generic.HaltParseException, AttributeError):
                    pass
                except (BaseException, Exception):
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = FunFileProvider()
