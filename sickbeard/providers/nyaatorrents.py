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
import urllib

from . import generic
from sickbeard import logger, show_name_helpers, tvcache
from sickbeard.helpers import tryInt


class NyaaProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'NyaaTorrents', anime_only=True)

        self.url_base = self.url = 'https://www.nyaa.se/'

        self.minseed, self.minleech = 2 * [None]

        self.cache = NyaaCache(self)

    def _search_provider(self, search_string, search_mode='eponly', **kwargs):

        if self.show and not self.show.is_anime:
            return []

        params = urllib.urlencode({'term': search_string.encode('utf-8'),
                  'cats': '1_37',  # Limit to English-translated Anime (for now)
                  # 'sort': '2',     # Sort Descending By Seeders
                                   })

        return self.get_data(getrss_func=self.cache.getRSSFeed,
                             search_url='%s?page=rss&%s' % (self.url, params),
                             mode=('Episode', 'Season')['sponly' == search_mode])

    def get_data(self, getrss_func, search_url, mode='cache'):

        data = getrss_func(search_url)

        results = []
        if data and 'entries' in data:

            rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
                'stats': '(\d+)\W+seed[^\d]+(\d+)\W+leech[^\d]+\d+\W+down[^\d]+([\d.,]+\s\w+)'}.iteritems())

            for cur_item in data.get('entries', []):
                try:
                    seeders, leechers, size = 0, 0, 0
                    stats = rc['stats'].findall(cur_item.get('summary_detail', {'value': ''}).get('value', ''))
                    if len(stats):
                        seeders, leechers, size = (tryInt(n, n) for n in stats[0])
                        if self._peers_fail(mode, seeders, leechers):
                            continue
                    title, download_url = self._title_and_url(cur_item)
                    download_url = self._link(download_url)
                except (AttributeError, TypeError, ValueError, IndexError):
                    continue

                if title and download_url:
                    results.append((title, download_url, seeders, self._bytesizer(size)))

        self._log_search(mode, len(results), search_url)

        return self._sort_seeding(mode, results)

    def _season_strings(self, ep_obj, **kwargs):

        return show_name_helpers.makeSceneShowSearchStrings(self.show)

    def _episode_strings(self, ep_obj, **kwargs):

        return self._season_strings(ep_obj)


class NyaaCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 15

    def _cache_data(self):

        params = urllib.urlencode({'page': 'rss',   # Use RSS page
                  'order': '1',    # Sort Descending By Date
                                   'cats': '1_37'   # Limit to English-translated Anime (for now)
                                   })

        return self.provider.get_data(getrss_func=self.getRSSFeed,
                                      search_url='%s?%s' % (self.provider.url, params))


provider = NyaaProvider()
