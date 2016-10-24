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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class IPTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'IPTorrents')

        self.url_home = (['https://iptorrents.%s/' % u for u in 'eu', 'com', 'me', 'ru'] +
                         ['http://11111.workisboring.com/', 'https://ipt-update.com'])

        self.url_vars = {'login': 'getrss.php', 'search': 't?%s;q=%s;qf=ti%s%s#torrents', 'get': '%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.categories = {'shows': [4, 5, 22, 23, 24, 25, 26, 55, 65, 66, 78, 79, 99], 'anime': [60]}

        self.proper_search_terms = None

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(IPTorrentsProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['RSS Link' in y, self.has_all_cookies()] +
                [(self.session.cookies.get(x) or 'sg!no!pw') in self.digest for x in 'uid', 'pass'])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?i)<title[^<]+?ipt', data))

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
                search_url = self.urls['search'] % (
                    self._categories_string(mode, '%s', ';'), search_string,
                    (';free', '')[not self.freeleech], (';o=seeders', '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find(id='torrents') or soup.find('table', class_='torrents')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                seeders, leechers = [tryInt(tr.find('td', class_='t_' + x).get_text().strip())
                                                     for x in 'seeders', 'leechers']
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                size = cells[-4].get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
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

    @staticmethod
    def ui_string(key):
        return 'iptorrents_digest' == key and 'use... \'uid=xx; pass=yy\'' or ''


provider = IPTorrentsProvider()
