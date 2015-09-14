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

import datetime

from . import generic
from sickbeard import tvcache
from sickbeard.rssfeeds import RSSFeeds
from lib.unidecode import unidecode


class PreToMeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PreToMe')

        self.url_base = 'https://pretome.info/'

        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': self.url_base + 'rss.php?cat[]=7&sort=0&type=d&key=%s',
                     'search': '&st=1&tf=all&search=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.passkey = None
        self.cache = PreToMeCache(self)

    def _do_login(self):

        return self._check_auth()

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        self._do_login()
        results = []

        items = {'Season': [], 'Episode': [], 'Cache': []}

        url = self.urls['cache'] % self.passkey
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = (url + self.urls['search'] % search_string, url)['Cache' == mode]
                data = RSSFeeds(self).get_feed(search_url)

                cnt = len(items[mode])
                if data and 'entries' in data:
                    for entry in data['entries']:
                        try:
                            if entry['title'] and 'download' in entry['link']:
                                items[mode].append((entry['title'], entry['link']))
                        except KeyError:
                            continue

                self._log_result(mode, len(items[mode]) - cnt, search_url)

            results += items[mode]

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, use_or=False)


class PreToMeCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 6  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = PreToMeProvider()
