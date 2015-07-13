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
import time
import traceback

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class SCCProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneAccess')

        self.url_base = 'https://sceneaccess.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'login',
                     'search': self.url_base + 'browse?search=%s&method=1&c27=27&c17=17&c11=11',
                     'nonscene': self.url_base + 'nonscene?search=%s&method=1&c44=44&c45=44',
                     'archive': self.url_base + 'archive?search=%s&method=1&c26=26',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.cache = SCCCache(self)

    def _do_login(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'username': self.username, 'password': self.password, 'submit': 'come on in'}

            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            logger.log(u'Failed to authenticate with %s, abort provider.' % self.name, logger.ERROR)

        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'Cache': []}

        if not self._do_login():
            return results

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string, void = self._get_title_and_url((search_string, None))
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                if 'Season' == mode:
                    searches = [self.urls['archive'] % search_string]
                else:
                    searches = [self.urls['search'] % search_string,
                                self.urls['nonscene'] % search_string]

                for search_url in searches:
                    html = self.get_url(search_url)

                    cnt = len(items[mode])
                    try:
                        if not html or self._has_no_results(html):
                            raise generic.HaltParseException

                        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                            torrent_table = soup.find('table', attrs={'id': 'torrents-table'})
                            torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                            if 2 > len(torrent_rows):
                                raise generic.HaltParseException

                            for tr in torrent_table.find_all('tr')[1:]:
                                try:
                                    seeders, leechers = [int(tr.find('td', attrs={'class': x}).get_text().strip())
                                                         for x in ('ttr_seeders', 'ttr_leechers')]
                                    if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                                        continue

                                    info = tr.find('a', href=rc['info'])
                                    title = ('title' in info.attrs and info['title']) or info.get_text().strip()

                                    link = str(tr.find('a', href=rc['get'])['href']).lstrip('/')
                                    download_url = self.urls['get'] % link
                                except (AttributeError, TypeError):
                                    continue

                                if title and download_url:
                                    items[mode].append((title, download_url, seeders))

                    except generic.HaltParseException:
                        time.sleep(1.1)
                    except Exception:
                        logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                    self._log_result(mode, len(items[mode]) - cnt, search_url)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, sep_date='.', use_or=False)


class SCCCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = SCCProvider()
