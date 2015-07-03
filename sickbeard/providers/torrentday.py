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

from . import generic
from sickbeard import logger, tvcache, helpers


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentDay')

        self.url_base = 'https://torrentday.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'torrents/',
                     'search': self.url_base + 'V3/API/API.php',
                     'get': self.url_base + 'download.php/%s/%s'}

        self.categories = {'Season': {'c14': 1},
                           'Episode': {'c2': 1, 'c26': 1, 'c7': 1, 'c24': 1},
                           'Cache': {'c2': 1, 'c26': 1, 'c7': 1, 'c24': 1, 'c14': 1}}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = TorrentDayCache(self)

    def _doLogin(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._checkAuth():
            login_params = {'username': self.username, 'password': self.password, 'submit.x': 0, 'submit.y': 0}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            msg = u'Failed to authenticate'
            if response and 'tried too often' in response:
                msg = u'Too many login attempts'
            logger.log(u'%s, abort provider %s' % (msg, self.name), logger.ERROR)

        return False

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._doLogin():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict({'/browse.php?': None, 'cata': 'yes', 'jxt': 8, 'jxw': 'b', 'search': search_string},
                                 **self.categories[mode])

                if self.freeleech:
                    post_data.update({'free': 'on'})

                data_json = self.getURL(self.urls['search'], post_data=post_data, json=True)
                cnt = len(items[mode])
                try:
                    if not data_json:
                        raise generic.HaltParseException
                    torrents = data_json.get('Fs', [])[0].get('Cn', {}).get('torrents', [])

                    for torrent in torrents:
                        seeders, leechers = int(torrent['seed']), int(torrent['leech'])
                        if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                            continue

                        title = re.sub(r'\[.*=.*\].*\[/.*\]', '', torrent['name'])

                        download_url = self.urls['get'] % (torrent['id'], torrent['fname'])

                        if title and download_url:
                            items[mode].append((title, download_url, seeders))
                except Exception:
                    time.sleep(1.1)

                self._log_result(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def findPropers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date, '')

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, sep_date='.')


class TorrentDayCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = TorrentDayProvider()
