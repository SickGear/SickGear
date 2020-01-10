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

from _23 import unidecode
from six import iteritems


class NcoreProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'nCore')

        self.url_base = 'https://ncore.cc/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'torrents.php?mire=%s&' + '&'.join([
                         'miszerint=fid', 'hogyan=DESC', 'tipus=kivalasztottak_kozott',
                         'kivalasztott_tipus=xvidser,dvdser,hdser', 'miben=name']),
                     'get': self.url_base + '%s&key='}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.chk_td = True

    def _authorised(self, **kwargs):

        return super(NcoreProvider, self)._authorised(
            logged_in=(lambda y='': all([bool(y), 'action="login' not in y, self.has_all_cookies('PHPSESSID')])),
            post_params={'nev': self.username, 'form_tmpl': 'name=[\'"]login[\'"]'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'list': '.*?torrent_all', 'info': 'details', 'key': 'key=([^"]+)">Torrent let'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_url = self.urls['search'] % search_string

                # fetches 15 results by default, and up to 100 if allowed in user profile
                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    parse_only = dict(div={'class': (lambda at: at and rc['list'].search(at))})
                    with BS4Parser(html, parse_only=parse_only) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('div', class_='box_torrent')
                        key = rc['key'].findall(html)[0]

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        for tr in tbl_rows:
                            try:
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    tr.find('div', class_=x).get_text().strip()
                                    for x in ('box_s2', 'box_l2', 'box_meret2')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                anchor = tr.find('a', href=rc['info'])
                                title = (anchor.get('title') or anchor.get_text()).strip()
                                download_url = self._link(anchor.get('href').replace('details', 'download')) + key
                            except (AttributeError, TypeError, ValueError):
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


provider = NcoreProvider()
