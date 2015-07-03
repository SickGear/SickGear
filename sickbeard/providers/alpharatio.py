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
import datetime
import traceback

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class AlphaRatioProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'AlphaRatio')

        self.url_base = 'https://alpharatio.cc/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'login.php',
                     'search': self.url_base + 'torrents.php?searchstr=%s'
                     + '&tags_type=1&order_by=time&order_way=desc'
                     + '&filter_cat[1]=1&filter_cat[2]=1&filter_cat[3]=1&filter_cat[4]=1&filter_cat[5]=1'
                     + '&action=basic&searchsubmit=1',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.cache = AlphaRatioCache(self)

    def _doLogin(self):

        logged_in = lambda: 'session' in self.session.cookies
        if logged_in():
            return True

        if self._checkAuth():
            login_params = {'username': self.username, 'password': self.password, 'keeplogged': '1', 'login': 'Login'}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            msg = u'Failed to authenticate with %s, abort provider'
            if response and 'Invalid Username/password' in response:
                msg = u'Invalid username or password for %s. Check settings'
            logger.log(msg % self.name, logger.ERROR)

        return False

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._doLogin():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'view', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['search'] % search_string
                html = self.getURL(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'id': 'torrent_table'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [int(tr.find_all('td')[x].get_text().strip()) for x in (-2, -1)]
                                if mode != 'Cache' and (seeders < self.minseed or leechers < self.minleech):
                                    continue

                                title = tr.find('a', title=rc['info']).get_text().strip()

                                link = str(tr.find('a', title=rc['get'])['href']).replace('&amp;', '&').lstrip('/')
                                download_url = self.urls['get'] % link
                            except (AttributeError, TypeError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_result(mode, len(items[mode]) - cnt, search_url)

            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def findPropers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, use_or=False)


class AlphaRatioCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()

provider = AlphaRatioProvider()
