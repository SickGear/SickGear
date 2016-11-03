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
from sickbeard.helpers import tryInt, anon_url
from lib.unidecode import unidecode


class SceneTimeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneTime', cache_update_freq=15)

        self.url_home = ['https://%s.scenetime.com/' % u for u in 'www', 'uk']

        self.url_vars = {'login': 'support.php', 'browse': 'browse_API.php', 'get': 'download.php/%s.torrent'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'browse': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.categories = {'shows': [2, 43, 9, 63, 77, 79, 83]}

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(SceneTimeProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['staff-support' in y, self.has_all_cookies()] +
                [(self.session.cookies.get(x) or 'sg!no!pw') in self.digest for x in 'uid', 'pass'])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?i)<title[^<]+?(Scenetim)', data))

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

                post_data = {'sec': 'jax', 'cata': 'yes'}
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

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if None is tr.find('a', href=rc['cats'])\
                                        or self.freeleech and None is rc['fl'].search(cells[1].get_text())\
                                        or self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link('%s/%s' % (
                                    re.sub(rc['get'], r'\1', str(info.attrs['href'])), str(title).replace(' ', '.')))
                            except (AttributeError, TypeError, ValueError, KeyError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def ui_string(self, key):
        if 'scenetime_digest' == key and self._valid_home():
            current_url = getattr(self, 'urls', {}).get('config_provider_home_uri')
            return ('use... \'uid=xx; pass=yy\'' +
                    (current_url and (' from a session logged in at <a target="_blank" href="%s">%s</a>' %
                                      (anon_url(current_url), current_url.strip('/'))) or ''))
        return ''


provider = SceneTimeProvider()
