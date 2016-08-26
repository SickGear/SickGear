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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class PTFProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PTFiles')

        self.url_base = 'https://ptfiles.net/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'loginproc/',
                     'login_base': self.url_base + 'loginproc/',
                     'search': self.url_base + 'browse.php?search=%s&%s&incldead=0&title=0%s',
                     'get': self.url_base + '%s'}

        self.categories = {'Season': [39], 'Episode': [7, 33, 42], 'anime': [23]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(PTFProvider, self)._authorised(logged_in=(lambda y=None: self.has_all_cookies('session_key')),
                                                    post_params={'force_ssl': 'on', 'ssl': '', 'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'details', 'get': 'dl.php', 'snatch': 'snatches',
                                                             'seeders': r'(^\d+)', 'leechers': r'(\d+)$'}.items())
        for mode in search_params.keys():
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['search'] % ('+'.join(search_string.split()), self._categories_string(mode),
                                                    ('&free=1', '')[not self.freeleech])
                html = self.get_url(search_url)
                time.sleep(2)
                if not self.has_all_cookies(['session_key']):
                    if not self._authorised():
                        return results
                    html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', id='tortable')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = 2 * [tr.find_all('td')[-2].get_text().strip()]
                                seeders, leechers = [tryInt(n) for n in [
                                    rc['seeders'].findall(seeders)[0], rc['leechers'].findall(leechers)[0]]]
                                if self._peers_fail(mode, seeders, leechers) or\
                                        not rc['cats'].findall(tr.find('td').get('onclick', ''))[0]:
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                snatches = tr.find('a', href=rc['snatch']).get_text().strip()
                                size = tr.find_all('td')[-3].get_text().strip().replace(snatches, '')
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, self.session.response.get('url'))

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = PTFProvider()
