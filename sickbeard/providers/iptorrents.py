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
import datetime
import traceback

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class IPTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'IPTorrents')

        self.url_base = 'https://iptorrents.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'torrents/',
                     'search': self.url_base + 't?l73=1&l78=1&l66=1&l65=1&l79=1&l5=1&l4=1&qf=ti%s&q=%s#torrents',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = IPTorrentsCache(self)

    def _do_login(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'username': self.username, 'password': self.password, 'login': 'submit'}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            logger.log(u'Failed to authenticate with %s, abort provider' % self.name, logger.ERROR)

        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._do_login():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}
        freeleech = self.freeleech and '&free=on' or ''

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                # URL with 50 tv-show results, or max 150 if adjusted in IPTorrents profile
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)
                search_url = '%s%s' % (self.urls['search'] % (freeleech, search_string),
                                       (';o=seeders', '')['Cache' == mode])
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'torrents'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [int(tr.find('td', attrs={'class': x}).get_text().strip())
                                                     for x in ('t_seeders', 't_leechers')]
                                if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = ('title' in info.attrs and info['title']) or info.get_text().strip()

                                download_url = self.urls['get'] % str(tr.find('a', href=rc['get'])['href']).lstrip('/')
                            except (AttributeError, TypeError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_result(mode, len(items[mode]) - cnt, search_url)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date, '')


class IPTorrentsCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = IPTorrentsProvider()
