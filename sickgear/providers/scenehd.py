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

from six import iteritems


class SceneHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneHD', cache_update_iv=15)

        self.url_home = ['https://scenehd.org/']

        self.url_vars = {'login': 'getrss.php', 'search': 'browse.php?search=%s&cat=%s&sort=5'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s'}

        self.categories = {'shows': [5, 6, 7]}

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]
        self.confirmed = False

    def _authorised(self, **kwargs):

        return super(SceneHDProvider, self)._authorised(
            logged_in=(lambda y='': ['RSS links' in y] and all(
                [(self.session.cookies.get(c, domain='') or 'sg!no!pw') in self.digest for c in ('uid', 'pass')])),
            failed_msg=(lambda y=None: 'Invalid cookie details for %s. Check settings'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': 'detail', 'get': 'download',
                                                                        'nuked': 'nuke', 'filter': 'free'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_url = self.urls['search'] % (search_string, self._categories_string(mode, '%s', ','))

                html = self.get_url(search_url, timeout=90)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, attr='cellpadding="5"') as soup:
                        tbl = soup.find('table', class_='browse')
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                info = tr.find('a', href=rc['info'])
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [n for n in [
                                    cells[head[x]].get_text().strip() for x in ('leech', 'leech', 'size')]]
                                seeders, leechers, size = [try_int(n, n) for n in
                                                           list(re.findall(r'^(\d+)[^\d]+?(\d+)', leechers)[0])
                                                           + re.findall('^[^\n\t]+', size)]
                                if self._reject_item(seeders, leechers,
                                                     self.freeleech and (not tr.find('a', class_=rc['filter'])),
                                                     self.confirmed and (any([tr.find('img', alt=rc['nuked']),
                                                                              tr.find('img', class_=rc['nuked'])]))):
                                    continue

                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, KeyError):
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

    @staticmethod
    def ui_string(key):
        return 'scenehd_confirm' == key and 'not marked as bad/nuked' or \
               'scenehd_digest' == key and 'use... \'uid=xx; pass=yy\'' or ''


provider = SceneHDProvider()
