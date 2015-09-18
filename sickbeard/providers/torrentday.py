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
import time

from . import generic
from sickbeard import tvcache
from sickbeard.helpers import (has_anime, tryInt)


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentDay')

        self.url_base = 'https://torrentday.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'torrents/',
                     'search': self.url_base + 'V3/API/API.php',
                     'get': self.url_base + 'download.php/%s/%s'}

        self.categories = {'Season': {'c31': 1, 'c33': 1, 'c14': 1},
                           'Episode': {'c32': 1, 'c26': 1, 'c7': 1, 'c2': 1},
                           'Cache': {'c31': 1, 'c33': 1, 'c14': 1, 'c32': 1, 'c26': 1, 'c7': 1, 'c2': 1}}

        self.proper_search_terms = None
        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = TorrentDayCache(self)

    def _authorised(self, **kwargs):

        return super(TorrentDayProvider, self)._authorised(
            post_params={'submit.x': 0, 'submit.y': 0},
            failed_msg=(lambda x=None: re.search(r'(?i)tried((<[^>]+>)|\W)*too((<[^>]+>)|\W)*often', x) and
                        u'Abort %s, Too many login attempts. Settings must be checked' or (
                re.search(r'(?i)username((<[^>]+>)|\W)*or((<[^>]+>)|\W)*password', x) and
                u'Invalid username or password for %s. Check settings' or
                u'Failed to authenticate with %s, abort provider')))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict({'/browse.php?': None, 'cata': 'yes', 'jxt': 8, 'jxw': 'b', 'search': search_string},
                                 **self.categories[(mode, 'Episode')['Propers' == mode]])
                if ('Cache' == mode and has_anime()) or (
                        mode in ['Season', 'Episode'] and self.show and self.show.is_anime):
                    post_data.update({'c29': 1})

                if self.freeleech:
                    post_data.update({'free': 'on'})

                data_json = self.get_url(self.urls['search'], post_data=post_data, json=True)

                cnt = len(items[mode])
                try:
                    if not data_json:
                        raise generic.HaltParseException
                    torrents = data_json.get('Fs')[0].get('Cn').get('torrents')

                    for item in torrents:
                        seeders, leechers, size = [tryInt(n, n) for n in [item.get(x) for x in 'seed', 'leech', 'size']]
                        if self._peers_fail(mode, seeders, leechers):
                            continue

                        title = re.sub(r'\[.*=.*\].*\[/.*\]', '', item['name'])

                        download_url = self.urls['get'] % (item['id'], item['fname'])

                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except Exception:
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', date_or=True, **kwargs)


class TorrentDayCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _cache_data(self):

        return self.provider.cache_data()


provider = TorrentDayProvider()
