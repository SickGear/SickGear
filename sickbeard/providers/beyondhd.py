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
from sickbeard import logger
from sickbeard.exceptions import AuthException
from lib.unidecode import unidecode


class BeyondHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BeyondHD')

        self.url_base = 'https://beyond-hd.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + 'api_tv.php?passkey=%s&cats=%s',
                     'search': '&search=%s'}

        self.categories = {'Season': '89',
                           'Episode': '40,44,48,43,45',
                           'Cache': '40,44,48,89,43,45'}

        self.url = self.urls['config_provider_home_uri']

        self.passkey, self.minseed, self.minleech = 3 * [None]

    def _check_auth_from_data(self, data_json):

        if 'error' not in data_json:
            return True

        logger.log(u'Incorrect authentication credentials for %s : %s' % (self.name, data_json['error']), logger.DEBUG)
        raise AuthException('Authentication credentials for %s are incorrect, check your config' % self.name)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._check_auth():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            if mode in ['Season', 'Episode']:
                show_type = self.show.air_by_date and 'Air By Date' \
                    or self.show.is_sports and 'Sports' or self.show.is_anime and 'Anime' or None
                if show_type:
                    logger.log(u'Provider does not carry shows of type: [%s], skipping' % show_type, logger.DEBUG)
                    return results

            mode_cats = (mode, 'Cache')['Propers' == mode]
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['browse'] % (self.passkey, self.categories[mode_cats])
                if 'Cache' != mode:
                    search_url += self.urls['search'] % re.sub('[.\s]+', ' ', search_string)

                data_json = self.get_url(search_url, json=True)

                cnt = len(items[mode])
                if data_json and 'results' in data_json and self._check_auth_from_data(data_json):
                    for item in data_json['results']:

                        seeders, leechers = item.get('seeders', 0), item.get('leechers', 0)
                        if self._peers_fail(mode, seeders, leechers):
                            continue
                        title, download_url = item.get('file'), self._link(item.get('get'))
                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(item.get('size'))))

                time.sleep(1.1)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, **kwargs)


provider = BeyondHDProvider()
