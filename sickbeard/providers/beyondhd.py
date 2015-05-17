# coding=utf-8
# URL: http://code.google.com/p/sickbeard
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

import requests
import generic
from sickbeard import logger, tvcache, show_name_helpers
from sickbeard.exceptions import AuthException


class BeyondHDProvider(generic.TorrentProvider):
    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BeyondHD', True, False)
        self.api_key = None
        self.ratio = None
        self.cache = BeyondHDCache(self)
        self.urls = {'config_provider_home_uri': 'https://beyondhd.me',
                     'api_search': 'https://beyondhd.me/api_tv.php'}
        self.url = self.urls['config_provider_home_uri']
        self.session = requests.Session()

    def _checkAuth(self):
        if not self.api_key:
            raise AuthException('Your authentication credentials for ' + self.name + ' are missing, check your config.')

        return True

    def _checkAuthFromData(self, data):

        if 'error' in data:
            logger.log(u'Incorrect authentication credentials for ' + self.name + ' : ' + data['error'],
                       logger.DEBUG)
            raise AuthException(
                'Your authentication credentials for ' + self.name + ' are incorrect, check your config.')

        return True

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):
        self._checkAuth()
        results = []
        params = {'passkey': self.api_key}

        if search_params:
            params.update(search_params)

        search_url = self.urls['api_search'] + '?' + urllib.urlencode(params)
        logger.log(u'Search url: %s' % search_url)

        parsedJSON = self.getURL(search_url, json=True)  # do search

        if not parsedJSON:
            logger.log(u'No data returned from ' + self.name, logger.ERROR)
            return results

        if self._checkAuthFromData(parsedJSON):

            try:
                found_torrents = parsedJSON['results']
            except:
                found_torrents = {}

            for result in found_torrents:
                (title, url) = self._get_title_and_url(result)

                if title and url:
                    results.append(result)

        return results

    def _get_title_and_url(self, parsedJSON):
        title = parsedJSON['file']
        url = parsedJSON['get']
        return title, url

    def _get_season_search_strings(self, ep_obj):
        search_strings = []
        for search_name in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj, None, ' '):
            search_strings.append({'search': search_name, 'cats': '89'})
        return search_strings

    def _get_episode_search_strings(self, ep_obj, add_string=''):
        search_strings = []
        for search_name in show_name_helpers.makeSceneSearchString(self.show, ep_obj, ' '):
            search_strings.append({'search': search_name, 'cats': '40,44,48,46,43,45'})
        return search_strings

class BeyondHDCache(tvcache.TVCache):
    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)

        # At least 10 minutes between queries
        self.minTime = 10

    def _getRSSData(self):
        search_params = {'cats': '40,44,48,89,46,43,45', 'search': ''}
        return self.provider._doSearch(search_params)


provider = BeyondHDProvider()
