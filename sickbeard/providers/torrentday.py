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

from . import generic
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt, anon_url


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentDay')

        self.url_home = ['https://%s/' % u for u in 'torrentday.eu', 'secure.torrentday.com', 'tdonline.org',
                                                    'torrentday.it', 'www.td.af', 'www.torrentday.com']

        self.url_vars = {'login': 'rss.php', 'search': 't?%s%s;q=%s%s', 'get': '%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.categories = {'Season': [31, 33, 14], 'Episode': [24, 32, 26, 7, 2], 'Anime': [29]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.proper_search_terms = None

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentDayProvider, self)._authorised(
            logged_in=(lambda x=None: (None is x or 'RSS URL' in x) and self.has_all_cookies() and
                       self.session.cookies['uid'] in self.digest and self.session.cookies['pass'] in self.digest),
            failed_msg=(lambda x=None: u'Invalid cookie details for %s. Check settings'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())

                search_url = self.urls['search'] % (
                    self._categories_string(mode, '%s', ';'), (';free', '')[not self.freeleech],
                    search_string, (';o=seeders', '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', id='torrentTable')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [tryInt(tr.find('td', attrs={'class': x}).get_text().strip())
                                                     for x in ('seedersInfo', 'leechersInfo')]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                size = tr.find_all('td')[-3].get_text().strip()

                                download_url = self.urls['get'] % str(tr.find('a', href=rc['get'])['href']).lstrip('/')
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', date_or=True, **kwargs)

    def ui_string(self, key):
        current_url = self.urls['config_provider_home_uri']
        return ('torrentday_digest' == key and
                ('use... \'uid=xx; pass=yy\' from a session logged in at <a target="_blank" href="%s">%s</a>' %
                 (anon_url(current_url), current_url.strip('/'))) or '')


provider = TorrentDayProvider()
