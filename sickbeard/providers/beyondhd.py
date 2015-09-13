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
from sickbeard import logger, tvcache
from sickbeard.exceptions import AuthException
from lib.unidecode import unidecode


class BeyondHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BeyondHD')

        self.url_base = 'https://beyondhd.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': self.url_base + 'api_tv.php?passkey=%s&cats=%s',
                     'search': '&search=%s',
                     }

        self.categories = {'Season': '89',
                           'Episode': '40,44,48,46,43,45',
                           'Cache': '40,44,48,89,46,43,45'}

        self.url = self.urls['config_provider_home_uri']

        self.passkey, self.minseed, self.minleech = 3 * [None]
        self.cache = BeyondHDCache(self)

    def _check_auth_from_data(self, data_json):

        if 'error' not in data_json:
            return True

        logger.log(u'Incorrect authentication credentials for %s : %s' % (self.name, data_json['error']), logger.DEBUG)
        raise AuthException('Authentication credentials for %s are incorrect, check your config' % self.name)

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._check_auth():
            return results

        for mode in search_params.keys():
            if 'Cache' != mode:
                show_type = self.show.air_by_date and 'Air By Date' \
                    or self.show.is_sports and 'Sports' or self.show.is_anime and 'Anime' or None
                if show_type:
                    logger.log(u'Provider does not carry shows of type: [%s], skipping' % show_type, logger.DEBUG)
                    return results

            for search_string in search_params[mode]:
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['cache'] % (self.passkey, self.categories[mode])
                if 'Cache' != mode:
                    search_url += self.urls['search'] % re.sub('[\.\s]+', ' ', search_string)

                data_json = self.get_url(search_url, json=True)

                cnt = len(results)
                if data_json and 'results' in data_json and self._check_auth_from_data(data_json):
                    for item in data_json['results']:

                        seeders, leechers = item['seeders'], item['leechers']
                        if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                            continue
                        title, download_url = item['file'], item['get']
                        if title and download_url:
                            results.append((title, download_url, seeders))

                self._log_result(mode, len(results) - cnt, search_url)
                time.sleep(1.1)
            # Sort items by seeders
            results.sort(key=lambda tup: tup[2], reverse=True)
        return results

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, scene=False, use_or=False)

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date, ['proper', 'repack'])


class BeyondHDCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 10  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = BeyondHDProvider()
