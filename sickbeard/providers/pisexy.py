# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import re
import traceback

from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import unidecode
from six import iteritems, string_types


class PiSexyProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PiSexy')

        self.url_base = 'https://pisexy.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'search': self.url_base + 'browseall.php?search=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(PiSexyProvider, self)._authorised(
            logged_in=(lambda y=None: self.has_all_cookies(['uid', 'pass', 'pcode'])))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'get': r'info.php\?id', 'cats': 'cat=(?:0|50[12])', 'filter': 'free',
            'title': r'Download\s([^"\']+)', 'seeders': r'(^\d+)', 'leechers': r'(\d+)$'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_url = self.urls['search'] % search_string

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, parse_only=dict(table={'class': 'listor'})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr, {'seed': r'(?:see/lee|seed)'})
                                seeders, leechers = 2 * [cells[head['seed']].get_text().strip()]
                                seeders, leechers = [try_int(n) for n in [
                                    rc['seeders'].findall(seeders)[0], rc['leechers'].findall(leechers)[0]]]
                                if not tr.find('a', href=rc['cats']) or self._reject_item(
                                        seeders, leechers, self.freeleech and not tr.find('img', src=rc['filter'])):
                                    continue

                                info = tr.find('a', href=rc['get'])
                                tag = tr.find('a', alt=rc['title']) or tr.find('a', title=rc['title'])
                                title = tag and rc['title'].findall(str(tag))
                                title = title and title[0]
                                if not isinstance(title, string_types) or 10 > len(title):
                                    title = (rc['title'].sub(r'\1', info.attrs.get('title', ''))
                                             or info.get_text()).strip()
                                if (10 > len(title)) or (4 > len(re.sub(r'[^.\-\s]', '', title))):
                                    continue
                                size = cells[head['size']].get_text().strip()
                                download_url = self._link(info['href'])
                            except (AttributeError, TypeError, ValueError, KeyError, IndexError):
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

    def get_data(self, url):
        result = None
        html = self.get_url(url, timeout=90)
        if self.should_skip():
            return result

        try:
            result = self._link(re.findall(r'(?i)"([^"]*?download\.php[^"]+?&(?!pimp)[^"]*)"', html)[0])
        except IndexError:
            logger.log('Failed no torrent in response', logger.DEBUG)
        return result


provider = PiSexyProvider()
