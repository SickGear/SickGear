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
import datetime

import generic
import sickbeard
from sickbeard import tvcache, classes, logger, show_name_helpers
from sickbeard.helpers import maybe_plural


class OZnzbProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'OZnzb')

        self.url_base = 'https://www.oznzb.com/'

        self.api_url = 'https://api.oznzb.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': '%sapi?o=json%s%s' % (self.api_url, '&apikey=%(apikey)s&t=tvsearch&limit=%(limit)s',
                                                    '&maxage=%(maxage)s&offset=%(offset)s&cat=%(cat)s'),
                     'search': '&q=%(q)s',
                     'get': self.api_url + '%s'}

        self.categories = ['5030', '5040', '5050', '5080']

        self.url = self.urls['config_provider_home_uri']

        self.needs_auth = True
        self.api_key = None
        self.can_edit_url = True
        self.skip_passworded = self.skip_spam = None
        self.cache = OZnzbCache(self)

    def _get_season_search_strings(self, ep_obj):

        return [x for x in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj)]

    def _get_episode_search_strings(self, ep_obj):

        return [x for x in show_name_helpers.makeSceneSearchString(self.show, ep_obj)]

    def get_cache_data(self):

        return self._search_provider('')

    def _search_provider(self, search, search_mode='eponly', epcount=0, retention=0):

        api_key = self._init_api()
        results = []
        if None is not api_key:
            categories = self.categories

            if '' == search:
                mode = 'cache'
                max_reqs = 1
                search_tail = ''
                categories += ['5060', '5070']
            else:
                mode = 'search'
                max_reqs = 4
                search_tail = self.urls['search'] % {'q': search}
                if self.show and (self.show.is_sports or self.show.is_anime):
                    categories += [('5070', '5060')[self.show.is_sports]]

            params = {'apikey': api_key,
                      'cat': '%2C'.join(sorted(categories)),
                      'limit': 100,
                      'maxage': (sickbeard.USENET_RETENTION, retention)[retention or not sickbeard.USENET_RETENTION],
                      'offset': 0}

            offset = total = 0
            while (offset <= total) and max_reqs:

                search_url = (self.urls['cache'] % params) + search_tail
                data_json = self.get_url(search_url, json=True)
                max_reqs -= 1
                cnt = len(results)
                if data_json:
                    try:
                        if 'item' in data_json['channel']:
                            for item in data_json['channel']['item']:
                                if None is not self.skip_passworded or None is not self.skip_spam:
                                    avoid_item = False
                                    scan_attrs = 2
                                    for attr in item['attr']:
                                        if 'passworded_confirmed' in attr['@attributes']['name']:
                                            if self.skip_passworded and 'no' not in attr['@attributes']['value']:
                                                avoid_item = True
                                                break
                                            scan_attrs -= 1
                                        elif 'spam_confirmed' in attr['@attributes']['name']:
                                            if self.skip_spam and 'no' not in attr['@attributes']['value']:
                                                avoid_item = True
                                                break
                                            scan_attrs -= 1
                                        if not scan_attrs:
                                            break
                                    if avoid_item:
                                        continue
                                if 'title' in item and 'link' in item:
                                    results.append((item['title'], item['link']))
                    except:
                        pass

                    # get total and offset attribs
                    try:
                        if 0 == total:
                            total = int(data_json['channel']['response']['@attributes']['total'])
                        offset = int(data_json['channel']['response']['@attributes']['offset'])
                    except (AttributeError, KeyError):
                        total = 0

                self._log_search(mode, len(results) - cnt, search_url)

                if 0 == total:
                    break

                if offset != params['offset']:
                    logger.log('OZnzb response contains an error in offset, aborting', logger.DEBUG)
                    break

                params['offset'] += params['limit']
                if total <= params['offset']:
                    logger.log('%s item%s found that will be used for episode matching' % (total, maybe_plural(total)),
                               logger.DEBUG)
                    break

                items = total - params['offset']
                logger.log('%s item%s found available to fetch in batches of up to %s items.'
                           % (items, maybe_plural(items), params['limit']), logger.DEBUG)

        return results

    def find_propers(self, **kwargs):

        search_terms = ['.proper.', '.repack.']
        results = []

        clean_term = re.compile(r'(?i)[^a-z\|\.]+')
        for term in search_terms:
            proper_check = re.compile(r'(?i)(?:%s)' % clean_term.sub('', term))
            for item in self._search_provider(term, retention=4):
                title, url = self._title_and_url(item)
                if not proper_check.search(title):
                    continue
                results.append(classes.Proper(title, url, datetime.datetime.today(), self.show))

        return results

    def _init_api(self):

        api_key = None
        try:
            api_key = self._check_auth()
        except Exception:
            pass
        return api_key

    def ui_string(self, key=''):
        key = key.replace(self.get_id() + '_skip_', '')
        if re.match('(passworded|spam)', key):
            return 'skip releases confirmed as %(key)s by %(token)s members' % {'key': key, 'token': '%s'}
        raise AttributeError


class OZnzbCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 17

    def _cache_data(self):

        return self.provider.get_cache_data()

provider = OZnzbProvider()
