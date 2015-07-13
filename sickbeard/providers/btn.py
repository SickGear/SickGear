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
import time
import math
import socket

from . import generic
from sickbeard import classes, scene_exceptions, logger, tvcache
from sickbeard.helpers import sanitizeSceneName
from sickbeard.exceptions import ex, AuthException
from lib import jsonrpclib


class BTNProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BTN')

        self.url_base = 'https://broadcasthe.net'
        self.url_api = 'http://api.btnapps.net'

        self.url = self.url_base

        self.api_key = None
        self.cache = BTNCache(self)

    def _check_auth_from_data(self, data_json):

        if data_json is None:
            return self._check_auth()

        if 'api-error' not in data_json:
            return True

        logger.log(u'Incorrect authentication credentials for %s : %s' % (self.name, data_json['api-error']),
                   logger.DEBUG)
        raise AuthException('Your authentication credentials for %s are incorrect, check your config.' % self.name)

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        self._check_auth()

        params = {}

        if search_params:
            params.update(search_params)

        if age:
            params['age'] = '<=%i' % age  # age in seconds

        results = []

        data_json = self._api_call(params)
        if not (data_json and self._check_auth_from_data(data_json)):
            self._log_result('rpc search', 0, self.name)
        else:

            found_torrents = {} if 'torrents' not in data_json else data_json['torrents']

            # We got something, we know the API sends max 1000 results at a time.
            # See if there are more than 1000 results for our query, if not we
            # keep requesting until we've got everything.
            # max 150 requests per hour so limit at that. Scan every 15 minutes. 60 / 15 = 4.
            max_pages = 150
            results_per_page = 1000

            if 'results' in data_json and int(data_json['results']) >= results_per_page:
                pages_needed = int(math.ceil(int(data_json['results']) / results_per_page))
                if pages_needed > max_pages:
                    pages_needed = max_pages

                # +1 because range(1,4) = 1, 2, 3
                for page in range(1, pages_needed + 1):
                    data_json = self._api_call(params, results_per_page, page * results_per_page)
                    # Note that this these are individual requests and might time out individually. This would result in 'gaps'
                    # in the results. There is no way to fix this though.
                    if 'torrents' in data_json:
                        found_torrents.update(data_json['torrents'])

            cnt = len(results)
            for torrentid, torrent_info in found_torrents.iteritems():
                title, url = self._get_title_and_url(torrent_info)
                if title and url:
                    results.append(torrent_info)
            self._log_result('search', len(results) - cnt, self.name + ' JSON-RPC API')

        return results

    def _api_call(self, params=None, results_per_page=1000, offset=0):

        if None is params:
            params = {}

        logger.log(u'Searching with parameters: ' + str(params), logger.DEBUG)

        parsed_json = {}
        server = jsonrpclib.Server(self.url_api)
        try:
            parsed_json = server.getTorrents(self.api_key, params, int(results_per_page), int(offset))

        except jsonrpclib.jsonrpc.ProtocolError as error:
            if 'Call Limit' in error.message:
                logger.log(u'Request ignored because the %s 150 calls/hr limit was reached' % self.name, logger.WARNING)
            else:
                logger.log(u'JSON-RPC protocol error while accessing %s: %s' % (self.name, ex(error)), logger.ERROR)
            return {'api-error': ex(error)}

        except socket.timeout:
            logger.log(u'Timeout while accessing ' + self.name, logger.WARNING)

        except socket.error as error:
            # timeouts are sometimes thrown as socket errors
            logger.log(u'Socket error while accessing %s: %s' % (self.name, error[1]), logger.ERROR)

        except Exception as error:
            errorstring = str(error)
            if errorstring.startswith('<') and errorstring.endswith('>'):
                errorstring = errorstring[1:-1]
            logger.log(u'Error while accessing %s: %s' % (self.name, errorstring), logger.ERROR)

        return parsed_json

    def _get_title_and_url(self, data_json):

        # The BTN API gives a lot of information in response,
        # however SickGear is built mostly around Scene or
        # release names, which is why we are using them here.

        if 'ReleaseName' in data_json and data_json['ReleaseName']:
            title = data_json['ReleaseName']

        else:
            # If we don't have a release name we need to get creative
            title = u''
            keys = ['Series', 'GroupName', 'Resolution', 'Source', 'Codec']
            for key in keys:
                if key in data_json:
                    title += ('', '.')[any(title)] + data_json[key]

            if title:
                title = title.replace(' ', '.')

        url = None
        if 'DownloadURL' in data_json:
            url = data_json['DownloadURL']
            if url:
                # unescaped / is valid in JSON, but it can be escaped
                url = url.replace('\\/', '/')

        return title, url

    def _get_season_search_strings(self, ep_obj, **kwargs):

        search_params = []
        current_params = {'category': 'Season'}

        # Search for entire seasons: no need to do special things for air by date or sports shows
        if ep_obj.show.air_by_date or ep_obj.show.sports:
            # Search for the year of the air by date show
            current_params['name'] = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.is_anime:
            current_params['name'] = '%s' % ep_obj.scene_absolute_number
        else:
            current_params['name'] = 'Season ' + str(ep_obj.scene_season)

        # search
        if 1 == ep_obj.show.indexer:
            current_params['tvdb'] = ep_obj.show.indexerid
            search_params.append(current_params)
        elif 2 == ep_obj.show.indexer:
            current_params['tvrage'] = ep_obj.show.indexerid
            search_params.append(current_params)
        else:
            name_exceptions = list(
                set([sanitizeSceneName(a) for a in scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
            for name in name_exceptions:
                # Search by name if we don't have tvdb or tvrage id
                cur_return = current_params.copy()
                cur_return['series'] = name
                search_params.append(cur_return)

        return search_params

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        if not ep_obj:
            return [{}]

        to_return = []
        search_params = {'category': 'Episode'}

        # episode
        if ep_obj.show.air_by_date or ep_obj.show.sports:
            date_str = str(ep_obj.airdate)

            # BTN uses dots in dates, we just search for the date since that
            # combined with the series identifier should result in just one episode
            search_params['name'] = date_str.replace('-', '.')
        elif ep_obj.show.anime:
            search_params['name'] = '%s' % ep_obj.scene_absolute_number
        else:
            # Do a general name search for the episode, formatted like SXXEYY
            search_params['name'] = 'S%02dE%02d' % (ep_obj.scene_season, ep_obj.scene_episode)

        # search
        if 1 == ep_obj.show.indexer:
            search_params['tvdb'] = ep_obj.show.indexerid
            to_return.append(search_params)
        elif 2 == ep_obj.show.indexer:
            search_params['tvrage'] = ep_obj.show.indexerid
            to_return.append(search_params)
        else:
            # add new query string for every exception
            name_exceptions = list(
                set([sanitizeSceneName(a) for a in scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
            for cur_exception in name_exceptions:
                cur_return = search_params.copy()
                cur_return['series'] = cur_exception
                to_return.append(cur_return)

        return to_return

    def find_propers(self, search_date=None):

        results = []

        search_terms = ['%.proper.%', '%.repack.%']

        for term in search_terms:
            for item in self._do_search({'release': term}, age=4 * 24 * 60 * 60):
                if item['Time']:
                    try:
                        result_date = datetime.datetime.fromtimestamp(float(item['Time']))
                    except TypeError:
                        continue

                    if not search_date or result_date > search_date:
                        title, url = self._get_title_and_url(item)
                        results.append(classes.Proper(title, url, result_date, self.show))

        return results

    def get_cache_data(self, **kwargs):

        # Get the torrents uploaded since last check.
        seconds_since_last_update = int(math.ceil(time.time() - time.mktime(kwargs['age'])))

        # default to 15 minutes
        seconds_min_time = kwargs['min_time'] * 60
        if seconds_min_time > seconds_since_last_update:
            seconds_since_last_update = seconds_min_time

        # Set maximum to 24 hours (24 * 60 * 60 = 86400 seconds) of "RSS" data search,
        # older items will be done through backlog
        if 86400 < seconds_since_last_update:
            logger.log(u'Only trying to fetch the last 24 hours even though the last known successful update on %s was over 24 hours'
                       % self.name, logger.WARNING)
            seconds_since_last_update = 86400

        return self._do_search(search_params=None, age=seconds_since_last_update)


class BTNCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 15  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data(age=self._getLastUpdate().timetuple(), min_time=self.minTime)


provider = BTNProvider()
