# Author: Mr_Orange
# URL: http://code.google.com/p/sickbeard/
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

import urllib

from . import generic
from sickbeard import logger, tvcache, show_name_helpers


class NyaaProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'NyaaTorrents', anime_only=True)

        self.url = 'http://www.nyaa.se/'

        self.cache = NyaaCache(self)

    def _do_search(self, search_string, search_mode='eponly', epcount=0, age=0):

        results = []
        if self.show and not self.show.is_anime:
            return results

        params = {'term': search_string.encode('utf-8'),
                  'cats': '1_37',  # Limit to English-translated Anime (for now)
                  # 'sort': '2',     # Sort Descending By Seeders
                  }

        search_url = self.url + '?page=rss&' + urllib.urlencode(params)

        logger.log(u'Search string: ' + search_url, logger.DEBUG)

        data = self.cache.getRSSFeed(search_url)
        if data and 'entries' in data:
            items = data.entries
            for curItem in items:

                title, url = self._get_title_and_url(curItem)

                if title and url:
                    results.append(curItem)
                else:
                    logger.log(u'The data returned from ' + self.name + ' is incomplete, this result is unusable',
                               logger.DEBUG)

        return results

    def find_search_results(self, show, episodes, search_mode, manual_search=False):

        return generic.TorrentProvider.find_search_results(self, show, episodes, search_mode, manual_search)

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return show_name_helpers.makeSceneShowSearchStrings(self.show)

    def _get_episode_search_strings(self, ep_obj, **kwargs):

        return self._get_season_search_strings(ep_obj)


class NyaaCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 15  # cache update frequency

    def _getRSSData(self):
        params = {'page': 'rss',   # Use RSS page
                  'order': '1',    # Sort Descending By Date
                  'cats': '1_37'}  # Limit to English-translated Anime (for now)

        url = self.provider.url + '?' + urllib.urlencode(params)
        logger.log(u'NyaaTorrents cache update URL: ' + url, logger.DEBUG)

        data = self.getRSSFeed(url)
        if data and 'entries' in data:
            return data.entries
        return []


provider = NyaaProvider()
