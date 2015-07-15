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


class TransmithenetProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Transmithe.net')

        self.url_base = 'https://transmithe.net/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'index.php?page=login',
                     'cache': self.url_base + 'index.php?page=torrents&options=0&active=1',
                     'search': '&search=%s',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.cache = TransmithenetCache(self)

    def _do_login(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'uid': self.username, 'pwd': self.password, 'remember_me': 'on', 'login': 'submit'}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            logger.log(u'Failed to authenticate with %s, abort provider.' % self.name, logger.ERROR)

        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._do_login():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'torrent-details', 'get': 'download',
                                                             'peers': 'page=peers', 'nodots': '[\.\s]+'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['cache']
                if 'Cache' != mode:
                    search_url += self.urls['search'] % rc['nodots'].sub(' ', search_string)

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find_all('table', 'lista')[-1]
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            downlink = tr.find('a', href=rc['get'])
                            if None is downlink:
                                continue
                            try:
                                seeders, leechers = [int(x.get_text().strip()) for x in tr.find_all('a', href=rc['peers'])]
                                if mode != 'Cache' and (seeders < self.minseed or leechers < self.minleech):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = ('title' in info.attrs and info['title']) or info.get_text().strip()

                                download_url = self.urls['get'] % str(downlink['href']).lstrip('/')
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

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._get_season_search_strings(self, ep_obj, scene=False)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, scene=False, use_or=False)


class TransmithenetCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 17  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()

provider = TransmithenetProvider()
