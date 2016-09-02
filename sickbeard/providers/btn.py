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

import math
import re
import time

from . import generic
from sickbeard import helpers, logger, scene_exceptions, tvcache
from sickbeard.helpers import tryInt

try:
    import json
except ImportError:
    from lib import simplejson as json
import random


class BTNProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'BTN')

        self.url_base = 'https://broadcasthe.net'
        self.url_api = 'https://api.btnapps.net'

        self.proper_search_terms = ['%.proper.%', '%.repack.%']
        self.url = self.url_base

        self.api_key, self.minseed, self.minleech = 3 * [None]
        self.reject_m2ts = False
        self.session.headers = {'Content-Type': 'application/json-rpc'}
        self.cache = BTNCache(self)

    def _authorised(self, **kwargs):

        return self._check_auth()

    def _search_provider(self, search_params, age=0, **kwargs):

        self._check_auth()

        results = []

        for mode in search_params.keys():
            for search_param in search_params[mode]:

                params = {}
                if 'Propers' == mode:
                    params.update({'release': search_param})
                    age = 4 * 24 * 60 * 60
                else:
                    search_param and params.update(search_param)
                age and params.update(dict(age='<=%i' % age))  # age in seconds

                json_rpc = (lambda param_dct, items_per_page=1000, offset=0:
                            '{"jsonrpc": "2.0", "id": "%s", "method": "getTorrents", "params": ["%s", %s, %s, %s]}' %
                            (''.join(random.sample('abcdefghijklmnopqrstuvwxyz0123456789', 8)),
                             self.api_key, json.dumps(param_dct), items_per_page, offset))

                try:
                    response = helpers.getURL(self.url_api, post_data=json_rpc(params), session=self.session, json=True)
                    error_text = response['error']['message']
                    logger.log(
                        ('Call Limit' in error_text
                         and u'Action aborted because the %(prov)s 150 calls/hr limit was reached'
                         or u'Action prematurely ended. %(prov)s server error response = %(desc)s') %
                        {'prov': self.name, 'desc': error_text}, logger.WARNING)
                    return results
                except (KeyError, Exception):
                    data_json = response and 'result' in response and response['result'] or {}

                if data_json:

                    found_torrents = 'torrents' in data_json and data_json['torrents'] or {}

                    # We got something, we know the API sends max 1000 results at a time.
                    # See if there are more than 1000 results for our query, if not we
                    # keep requesting until we've got everything.
                    # max 150 requests per hour so limit at that. Scan every 15 minutes. 60 / 15 = 4.
                    max_pages = 5  # 150 was the old value and impractical
                    results_per_page = 1000

                    if 'results' in data_json and int(data_json['results']) >= results_per_page:
                        pages_needed = int(math.ceil(int(data_json['results']) / results_per_page))
                        if pages_needed > max_pages:
                            pages_needed = max_pages

                        # +1 because range(1,4) = 1, 2, 3
                        for page in range(1, pages_needed + 1):

                            try:
                                response = helpers.getURL(
                                    self.url_api, json=True, session=self.session,
                                    post_data=json_rpc(params, results_per_page, page * results_per_page))
                                error_text = response['error']['message']
                                logger.log(
                                    ('Call Limit' in error_text
                                     and u'Action prematurely ended because the %(prov)s 150 calls/hr limit was reached'
                                     or u'Action prematurely ended. %(prov)s server error response = %(desc)s') %
                                    {'prov': self.name, 'desc': error_text}, logger.WARNING)
                                return results
                            except (KeyError, Exception):
                                data_json = response and 'result' in response and response['result'] or {}

                            # Note that this these are individual requests and might time out individually.
                            # This would result in 'gaps' in the results. There is no way to fix this though.
                            if 'torrents' in data_json:
                                found_torrents.update(data_json['torrents'])

                    cnt = len(results)
                    for torrentid, torrent_info in found_torrents.iteritems():
                        seeders, leechers, size = (tryInt(n, n) for n in [torrent_info.get(x) for x in
                                                                          'Seeders', 'Leechers', 'Size'])
                        if self._peers_fail(mode, seeders, leechers) or \
                                self.reject_m2ts and re.match(r'(?i)m2?ts', torrent_info.get('Container', '')):
                            continue

                        title, url = self._get_title_and_url(torrent_info)
                        if title and url:
                            results.append((title, url, seeders, self._bytesizer(size)))

                    self._log_search(mode, len(results) - cnt,
                                     ('search_param: ' + str(search_param), self.name)['Cache' == mode])

                    results = self._sort_seeding(mode, results)

        return results

    @staticmethod
    def _get_title_and_url(data_json):

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

    def _season_strings(self, ep_obj, **kwargs):

        search_params = []
        base_params = {'category': 'Season'}

        # Search for entire seasons: no need to do special things for air by date or sports shows
        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            # Search for the year of the air by date show
            base_params['name'] = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.is_anime:
            base_params['name'] = '%s' % ep_obj.scene_absolute_number
        else:
            base_params['name'] = 'Season %s' % (ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)]

        if 1 == ep_obj.show.indexer:
            base_params['tvdb'] = ep_obj.show.indexerid
            search_params.append(base_params)
        # elif 2 == ep_obj.show.indexer:
        #    current_params['tvrage'] = ep_obj.show.indexerid
        #    search_params.append(current_params)
        else:
            name_exceptions = list(
                set([helpers.sanitizeSceneName(a) for a in
                     scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
            for name in name_exceptions:
                series_param = {'series': name}
                series_param.update(base_params)
                search_params.append(series_param)

        return [dict(Season=search_params)]

    def _episode_strings(self, ep_obj, **kwargs):

        if not ep_obj:
            return [{}]

        search_params = []
        base_params = {'category': 'Episode'}

        # episode
        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            date_str = str(ep_obj.airdate)

            # BTN uses dots in dates, we just search for the date since that
            # combined with the series identifier should result in just one episode
            base_params['name'] = date_str.replace('-', '.')
        elif ep_obj.show.is_anime:
            base_params['name'] = '%s' % ep_obj.scene_absolute_number
        else:
            # Do a general name search for the episode, formatted like SXXEYY
            season, episode = ((ep_obj.season, ep_obj.episode),
                               (ep_obj.scene_season, ep_obj.scene_episode))[bool(ep_obj.show.is_scene)]
            base_params['name'] = 'S%02dE%02d' % (season, episode)

        # search
        if 1 == ep_obj.show.indexer:
            base_params['tvdb'] = ep_obj.show.indexerid
            search_params.append(base_params)
        # elif 2 == ep_obj.show.indexer:
        #    search_params['tvrage'] = ep_obj.show.indexerid
        #    to_return.append(search_params)
        else:
            # add new query string for every exception
            name_exceptions = list(
                set([helpers.sanitizeSceneName(a) for a in
                     scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
            for name in name_exceptions:
                series_param = {'series': name}
                series_param.update(base_params)
                search_params.append(series_param)

        return [dict(Episode=search_params)]

    def cache_data(self, **kwargs):

        # Get the torrents uploaded since last check.
        seconds_since_last_update = int(math.ceil(time.time() - time.mktime(kwargs['age'])))

        # default to 15 minutes
        seconds_min_time = kwargs['min_time'] * 60
        if seconds_min_time > seconds_since_last_update:
            seconds_since_last_update = seconds_min_time

        # Set maximum to 24 hours (24 * 60 * 60 = 86400 seconds) of "RSS" data search,
        # older items will be done through backlog
        if 86400 < seconds_since_last_update:
            logger.log(u'Only trying to fetch the last 24 hours even though the last known successful update on ' +
                       '%s was over 24 hours' % self.name, logger.WARNING)
            seconds_since_last_update = 86400

        return self._search_provider(dict(Cache=['']), age=seconds_since_last_update)


class BTNCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 15

    def _cache_data(self):

        return self.provider.cache_data(age=self._getLastUpdate().timetuple(), min_time=self.update_freq)


provider = BTNProvider()
