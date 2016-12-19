# coding=utf-8
#
#  This file is part of SickGear.
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
import urllib

from . import generic
from sickbeard import logger
from sickbeard.exceptions import AuthException
from sickbeard.helpers import tryInt
from sickbeard.indexers import indexer_config

try:
    import json
except ImportError:
    from lib import simplejson as json


class HDBitsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HDBits', cache_update_freq=15)

        # api_spec: https://hdbits.org/wiki/API
        self.url_base = 'https://hdbits.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'api/torrents',
                     'get': self.url_base + 'download.php?%s'}

        self.categories = [3, 5, 2]

        self.proper_search_terms = [' proper ', ' repack ']
        self.url = self.urls['config_provider_home_uri']

        self.username, self.passkey, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def check_auth_from_data(self, parsed_json):

        if 'status' in parsed_json and 5 == parsed_json.get('status') and 'message' in parsed_json:
            logger.log(u'Incorrect username or password for %s: %s' % (self.name, parsed_json['message']), logger.DEBUG)
            raise AuthException('Your username or password for %s is incorrect, check your config.' % self.name)

        return True

    def _season_strings(self, ep_obj, **kwargs):

        params = super(HDBitsProvider, self)._season_strings(ep_obj, scene=False)

        show = ep_obj.show
        if indexer_config.INDEXER_TVDB == show.indexer and show.indexerid:
            params[0]['Season'].insert(0, dict(tvdb=dict(
                id=show.indexerid,
                season=(show.air_by_date or show.is_sports) and str(ep_obj.airdate)[:7] or
                (show.is_anime and ('%d' % ep_obj.scene_absolute_number) or
                 (ep_obj.season, ep_obj.scene_season)[bool(show.is_scene)]))))

        return params

    def _episode_strings(self, ep_obj, **kwargs):

        params = super(HDBitsProvider, self)._episode_strings(ep_obj, scene=False, sep_date='|')

        show = ep_obj.show
        if indexer_config.INDEXER_TVDB == show.indexer and show.indexerid:
            id_param = dict(
                id=show.indexerid,
                episode=show.air_by_date and str(ep_obj.airdate).replace('-', ' ') or
                (show.is_sports and ep_obj.airdate.strftime('%b') or
                 (show.is_anime and ('%i' % int(ep_obj.scene_absolute_number)) or
                  (ep_obj.episode, ep_obj.scene_episode)[bool(show.is_scene)])))
            if not(show.air_by_date and show.is_sports and show.is_anime):
                id_param['season'] = (ep_obj.season, ep_obj.scene_season)[bool(show.is_scene)]
            params[0]['Episode'].insert(0, dict(tvdb=id_param))

        return params

    def _search_provider(self, search_params, **kwargs):

        self._check_auth()

        results = []
        api_data = {'username': self.username, 'passkey': self.passkey, 'category': self.categories}

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            for search_param in search_params[mode]:

                post_data = api_data.copy()
                if isinstance(search_param, dict):
                    post_data.update(search_param)
                    id_search = True
                else:
                    post_data['search'] = search_param
                    id_search = False

                post_data = json.dumps(post_data)
                search_url = self.urls['search']

                json_resp = self.get_url(search_url, post_data=post_data, json=True)

                if not (json_resp and self.check_auth_from_data(json_resp) and 'data' in json_resp):
                    logger.log(u'Response from %s does not contain any json data, abort' % self.name, logger.ERROR)
                    return results

                cnt = len(items[mode])
                for item in json_resp['data']:
                    try:
                        seeders, leechers, size = [tryInt(n, n) for n in [item.get(x) for x in
                                                                          'seeders', 'leechers', 'size']]
                        if self._peers_fail(mode, seeders, leechers)\
                                or self.freeleech and re.search('(?i)no', item.get('freeleech', 'no')):
                            continue

                        title = item['name']
                        download_url = self.urls['get'] % urllib.urlencode({'id': item['id'], 'passkey': self.passkey})
                    except (AttributeError, TypeError, ValueError):
                        continue

                    if title and download_url:
                        items[mode].append((title, download_url, item.get('seeders', 0), self._bytesizer(size)))

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search_param: ' + str(search_param), self.name)['Cache' == mode])

                results = self._sort_seeding(mode, results + items[mode])

                if id_search and len(results):
                    return results

        return results


provider = HDBitsProvider()
