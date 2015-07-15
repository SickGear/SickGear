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
import datetime
import time

from . import generic
from sickbeard import logger, tvcache, helpers


class SpeedCDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Speedcd')

        self.url_base = 'http://speed.cd/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'take_login.php',
                     'search': self.url_base + 'V3/API/API.php',
                     'get': self.url_base + 'download.php?torrent=%s'}

        self.categories = {'Season': {'c14': 1},
                           'Episode': {'c2': 1, 'c49': 1},
                           'Cache': {'c14': 1, 'c2': 1, 'c49': 1}}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = SpeedCDCache(self)

    def _do_login(self):

        logged_in = lambda: 'inSpeed_speedian' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'username': self.username, 'password': self.password}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            msg = u'Failed to authenticate with %s, abort provider'
            if response and re.search('Incorrect username or Password. Please try again.', response):
                msg = u'Invalid username or password for %s. Check settings'
            logger.log(msg % self.name, logger.ERROR)

        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._do_login():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

        remove_tag = re.compile(r'<[^>]*>')
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict({'/browse.php?': None, 'cata': 'yes', 'jxt': 4, 'jxw': 'b', 'search': search_string},
                                 **self.categories[mode])

                data_json = self.get_url(self.urls['search'], post_data=post_data, json=True)
                cnt = len(items[mode])
                try:
                    if not data_json:
                        raise generic.HaltParseException
                    torrents = data_json.get('Fs', [])[0].get('Cn', {}).get('torrents', [])

                    for torrent in torrents:

                        if self.freeleech and not torrent['free']:
                            continue

                        seeders, leechers = int(torrent['seed']), int(torrent['leech'])
                        if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                            continue

                        title = remove_tag.sub('', torrent['name'])
                        url = self.urls['get'] % (torrent['id'])
                        if title and url:
                            items[mode].append((title, url, seeders))

                except Exception:
                    time.sleep(1.1)

                self._log_result(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, sep_date='.', use_or=False)


class SpeedCDCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = SpeedCDProvider()
