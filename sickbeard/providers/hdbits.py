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
import datetime
import urllib

from . import generic
from sickbeard import classes, logger, tvcache
from sickbeard.exceptions import AuthException

try:
    import json
except ImportError:
    from lib import simplejson as json


class HDBitsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HDBits')

        # api_spec: https://hdbits.org/wiki/API
        self.url_base = 'https://hdbits.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'api/torrents',
                     'get': self.url_base + 'download.php?%s'}

        self.categories = 2  # TV

        self.url = self.urls['config_provider_home_uri']

        self.username, self.passkey = 2 * [None]
        self.cache = HDBitsCache(self)

    def check_auth_from_data(self, parsed_json):

        if 'status' in parsed_json and 5 == parsed_json.get('status') and 'message' in parsed_json:
            logger.log(u'Incorrect username or password for %s : %s' % (self.name, parsed_json['message']), logger.DEBUG)
            raise AuthException('Your username or password for %s is incorrect, check your config.' % self.name)

        return True

    def _get_season_search_strings(self, ep_obj, **kwargs):

        return [self._build_search_strings(show=ep_obj.show, season=ep_obj)]

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return [self._build_search_strings(show=ep_obj.show, episode=ep_obj)]

    def _get_title_and_url(self, item):

        title = item['name']
        if title:
            title = u'' + title.replace(' ', '.')

        url = self.urls['get'] % urllib.urlencode({'id': item['id'], 'passkey': self.passkey})

        return title, url

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        self._check_auth()

        logger.log(u'Search url: %s search_params: %s' % (self.urls['search'], search_params), logger.DEBUG)

        response_json = self.get_url(self.urls['search'], post_data=search_params, json=True)
        if response_json and 'data' in response_json and self.check_auth_from_data(response_json):
            return response_json['data']

        logger.log(u'Resulting JSON from %s isn\'t correct, not parsing it' % self.name, logger.ERROR)
        return []

    def find_propers(self, search_date=None):

        results = []

        search_terms = [' proper ', ' repack ']

        for term in search_terms:
            for item in self._do_search(self._build_search_strings(search_term=term)):
                if item['utadded']:
                    try:
                        result_date = datetime.datetime.fromtimestamp(int(item['utadded']))
                    except:
                        result_date = None

                    if result_date and (not search_date or result_date > search_date):
                        title, url = self._get_title_and_url(item)
                        if not re.search('(?i)(?:%s)' % term.strip(), title):
                            continue
                        results.append(classes.Proper(title, url, result_date, self.show))
        return results

    def _build_search_strings(self, show=None, episode=None, season=None, search_term=None):

        request_params = {'username': self.username, 'passkey': self.passkey, 'category': [self.categories]}

        if episode or season:
            param = {'id': show.indexerid}

            if episode:
                if show.air_by_date:
                    param['episode'] = str(episode.airdate).replace('-', '|')
                elif show.is_sports:
                    param['episode'] = episode.airdate.strftime('%b')
                elif show.is_anime:
                    param['episode'] = '%i' % int(episode.scene_absolute_number)
                else:
                    param['season'] = episode.scene_season
                    param['episode'] = episode.scene_episode

            if season:
                if show.air_by_date or show.is_sports:
                    param['season'] = str(season.airdate)[:7]
                elif show.is_anime:
                    param['season'] = '%d' % season.scene_absolute_number
                else:
                    param['season'] = season.scene_season

            request_params['tvdb'] = param

        if search_term:
            request_params['search'] = search_term

        return json.dumps(request_params)

    def get_cache_data(self):

        self._check_auth()

        response_json = self.get_url(self.urls['search'], post_data=self._build_search_strings(), json=True)
        if response_json and 'data' in response_json and self.check_auth_from_data(response_json):
            return response_json['data']

        return []


class HDBitsCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 15  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = HDBitsProvider()
