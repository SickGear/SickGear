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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class FunFileProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'FunFile', cache_update_freq=15)

        self.url_base = 'https://www.funfile.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'search': self.url_base + 'browse.php?%s&search=%s&incldead=0&showspam=1&',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [7], 'anime': [44]}

        self.url = self.urls['config_provider_home_uri']
        self.url_timeout = 90
        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(FunFileProvider, self)._authorised(
            logged_in=(lambda x=None: None is not self.session.cookies.get('uid', domain='.funfile.org') and
                       None is not self.session.cookies.get('pass', domain='.funfile.org')),
            post_params={'login': 'Login', 'returnto': '/'}, timeout=self.url_timeout)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            rc['cats'] = re.compile('(?i)cat=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (self._categories_string(mode), search_string)

                html = self.get_url(search_url, timeout=self.url_timeout)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('td', attrs={'class': 'colhead'}).find_parent('table')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                info = tr.find('a', href=rc['info'])
                                if not info:
                                    continue

                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    (tr.find_all('td')[x].get_text().strip()) for x in (-2, -1, -4)]]
                                if None is tr.find('a', href=rc['cats']) or self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = info.attrs.get('title') or info.get_text().strip()
                                download_url = self.urls['get'] % str(tr.find('a', href=rc['get'])['href']).lstrip('/')

                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (generic.HaltParseException, AttributeError):
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results


provider = FunFileProvider()
