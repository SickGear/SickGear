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
import urllib

from . import generic
from sickbeard import logger, tvcache
from sickbeard.helpers import mapIndexersToShow
from sickbeard.exceptions import AuthException


class ToTVProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'ToTV')

        self.url_base = 'https://titansof.tv/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'api/torrents?%s',
                     'get': self.url_base + 'api/torrents/%s/download?apikey=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.api_key, self.minseed, self.minleech = 3 * [None]
        self.cache = ToTVCache(self)

    def _check_auth_from_data(self, data_json):

        if 'error' not in data_json:
            return True

        logger.log(u'Incorrect authentication credentials for %s : %s' % (self.name, data_json['error']),
                   logger.DEBUG)
        raise AuthException('Your authentication credentials for %s are incorrect, check your config.' % self.name)

    def _do_search(self, search_params, mode='eponly', epcount=0, age=0):

        self._check_auth()
        self.headers.update({'X-Authorization': self.api_key})
        results = []
        params = {'limit': 100}
        mode = ('season' in search_params.keys() and 'Season') or \
               ('episode' in search_params.keys() and 'Episode') or 'Cache'

        if search_params:
            params.update(search_params)

        search_url = self.urls['search'] % urllib.urlencode(params)

        data_json = self.get_url(search_url, json=True)

        cnt = len(results)
        if data_json and 'results' in data_json and self._check_auth_from_data(data_json):
            for result in data_json['results']:
                try:
                    seeders, leechers = result['seeders'], result['leechers']
                    if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                        continue

                    title, download_url = result['release_name'], str(self.urls['get'] % (result['id'], self.api_key))
                except (AttributeError, TypeError):
                    continue

                if title and download_url:
                    results.append((title, download_url))

        self._log_result(mode, len(results) - cnt, search_url)
        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return self._build_search_str(ep_obj, {'season': 'Season %02d' %
                                               int((ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)])})

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        if not ep_obj:
            return [{}]

        # Do a general name search for the episode, formatted like SXXEYY
        season, episode = ((ep_obj.season, ep_obj.episode),
                           (ep_obj.scene_season, ep_obj.scene_episode))[bool(ep_obj.show.is_scene)]
        return self._build_search_str(ep_obj, {'episode': 'S%02dE%02d %s' % (season, episode, add_string)})

    @staticmethod
    def _build_search_str(ep_obj, search_params):

        if 1 == ep_obj.show.indexer:
            search_params['series_id'] = ep_obj.show.indexerid
        elif 2 == ep_obj.show.indexer:
            tvdbid = mapIndexersToShow(ep_obj.show)[1]
            if tvdbid:
                search_params['series_id'] = tvdbid

        return [search_params]

    def get_cache_data(self, *args, **kwargs):

        return self._do_search({})


class ToTVCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = ToTVProvider()
