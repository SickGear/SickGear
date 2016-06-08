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

import ast
import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class SceneTimeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneTime', cache_update_freq=15)

        self.url_base = 'https://www.scenetime.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'browse': self.url_base + 'browse_API.php',
                     'params': {'sec': 'jax', 'cata': 'yes'},
                     'get': self.url_base + 'download.php/%(id)s/%(title)s.torrent'}

        self.categories = {'shows': [2, 43, 9, 63, 77, 79, 101]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(SceneTimeProvider, self)._authorised(post_params={'submit': 'Log in'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'detail', 'get': '.*id=(\d+).*', 'fl': '\[freeleech\]',
            'cats': 'cat=(?:%s)' % self._categories_string(template='', delimiter='|')}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                post_data = self.urls['params'].copy()
                post_data.update(ast.literal_eval(
                    '{%s}' % self._categories_string(template='"c%s": "1"', delimiter=',')))
                if 'Cache' != mode:
                    search_string = '+'.join(search_string.split())
                    post_data['search'] = search_string

                if self.freeleech:
                    post_data.update({'freeleech': 'on'})

                self.session.headers.update({'Referer': self.url + 'browse.php', 'X-Requested-With': 'XMLHttpRequest'})
                html = self.get_url(self.urls['browse'], post_data=post_data)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'cellpadding': 5})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in (-2, -1, -3)]]
                                if None is tr.find('a', href=rc['cats'])\
                                        or self.freeleech and None is rc['fl'].search(tr.find_all('td')[1].get_text())\
                                        or self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = info.attrs.get('title') or info.get_text().strip()

                                download_url = self.urls['get'] % {
                                    'id': re.sub(rc['get'], r'\1', str(info.attrs['href'])),
                                    'title': str(title).replace(' ', '.')}
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results


provider = SceneTimeProvider()
