# Author: Nic Wolfe <nic@wolfeden.ca>
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

import time
import urllib

import sickbeard

from . import generic
from sickbeard import helpers, logger, scene_exceptions, tvcache
from sickbeard.exceptions import AuthException


class NewznabProvider(generic.NZBProvider):

    def __init__(self, name, url, key='', cat_ids='5030,5040', search_mode='eponly',
                 search_fallback=False, enable_recentsearch=False, enable_backlog=False):
        generic.NZBProvider.__init__(self, name, True, False)

        self.url = url
        self.key = key
        self.cat_ids = cat_ids
        self.search_mode = search_mode
        self.search_fallback = search_fallback
        self.enable_recentsearch = enable_recentsearch
        self.enable_backlog = enable_backlog
        self.needs_auth = '0' != self.key.strip()  # '0' in the key setting indicates that api_key is not needed
        self.default = False
        self.cache = NewznabCache(self)

    def check_auth_from_data(self, data):

        if data is None:
            return self._check_auth()

        if 'error' in data.feed:
            code = data.feed['error']['code']

            if '100' == code:
                raise AuthException('Your API key for %s is incorrect, check your config.' % self.name)
            elif '101' == code:
                raise AuthException('Your account on %s has been suspended, contact the admin.' % self.name)
            elif '102' == code:
                raise AuthException('Your account isn\'t allowed to use the API on %s, contact the admin.' % self.name)
            elif '910' == code:
                logger.log(u'%s currently has their API disabled, please check with provider.' % self.name,
                           logger.WARNING)
            else:
                logger.log(u'Unknown error given from %s: %s' % (self.name, data.feed['error']['description']),
                           logger.ERROR)
            return False

        return True

    def get_newznab_categories(self):
        """
        Uses the newznab provider url and apikey to get the capabilities.
        Makes use of the default newznab caps param. e.a. http://yournewznab/api?t=caps&apikey=skdfiw7823sdkdsfjsfk
        Returns a tuple with (succes or not, array with dicts [{"id": "5070", "name": "Anime"},
        {"id": "5080", "name": "Documentary"}, {"id": "5020", "name": "Foreign"}...etc}], error message)
        """
        return_categories = []

        api_key = self._check_auth()

        params = {'t': 'caps'}
        if isinstance(api_key, basestring):
            params['apikey'] = api_key

        categories = self.get_url('%s/api' % self.url, params=params, timeout=10)
        if not categories:
            logger.log(u'Error getting html for [%s/api?%s]' %
                       (self.url, '&'.join('%s=%s' % (x, y) for x, y in params.items())), logger.DEBUG)
            return (False, return_categories, 'Error getting html for [%s]' %
                    ('%s/api?%s' % (self.url, '&'.join('%s=%s' % (x, y) for x, y in params.items()))))

        xml_categories = helpers.parse_xml(categories)
        if not xml_categories:
            logger.log(u'Error parsing xml for [%s]' % self.name, logger.DEBUG)
            return False, return_categories, 'Error parsing xml for [%s]' % self.name

        try:
            for category in xml_categories.iter('category'):
                if 'TV' == category.get('name'):
                    for subcat in category.findall('subcat'):
                        return_categories.append(subcat.attrib)
        except:
            logger.log(u'Error parsing result for [%s]' % self.name, logger.DEBUG)
            return False, return_categories, 'Error parsing result for [%s]' % self.name

        return True, return_categories, ''

    def config_str(self):
        return '%s|%s|%s|%s|%i|%s|%i|%i|%i' \
               % (self.name or '', self.url or '', self.maybe_apikey() or '', self.cat_ids or '', self.enabled,
                  self.search_mode or '', self.search_fallback, self.enable_recentsearch, self.enable_backlog)

    def _season_strings(self, ep_obj):

        search_params = []
        base_params = {}

        # season
        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            date_str = str(ep_obj.airdate).split('-')[0]
            base_params['season'] = date_str
            base_params['q'] = date_str.replace('-', '.')
        elif ep_obj.show.is_anime:
            base_params['season'] = '%d' % ep_obj.scene_absolute_number
        else:
            base_params['season'] = str((ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)])

        # search
        ids = helpers.mapIndexersToShow(ep_obj.show)
        if ids[1]:  # or ids[2]:
            params = base_params.copy()
            use_id = False
            if ids[1] and self.supports_tvdbid():
                params['tvdbid'] = ids[1]
                use_id = True
            if ids[2]:
                params['rid'] = ids[2]
                use_id = True
            use_id and search_params.append(params)

        # add new query strings for exceptions
        name_exceptions = list(
            set([helpers.sanitizeSceneName(a) for a in
                 scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
        for cur_exception in name_exceptions:
            params = base_params.copy()
            if 'q' in params:
                params['q'] = '%s.%s' % (cur_exception, params['q'])
            search_params.append(params)

        return [{'Season': search_params}]

    def _episode_strings(self, ep_obj):

        search_params = []
        base_params = {}

        if not ep_obj:
            return [base_params]

        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            date_str = str(ep_obj.airdate)
            base_params['season'] = date_str.partition('-')[0]
            base_params['ep'] = date_str.partition('-')[2].replace('-', '/')
        elif ep_obj.show.is_anime:
            base_params['ep'] = '%i' % int(
                ep_obj.scene_absolute_number if int(ep_obj.scene_absolute_number) > 0 else ep_obj.scene_episode)
        else:
            base_params['season'], base_params['ep'] = (
                (ep_obj.season, ep_obj.episode), (ep_obj.scene_season, ep_obj.scene_episode))[ep_obj.show.is_scene]

        # search
        ids = helpers.mapIndexersToShow(ep_obj.show)
        if ids[1]:  # or ids[2]:
            params = base_params.copy()
            use_id = False
            if ids[1]:
                if self.supports_tvdbid():
                    params['tvdbid'] = ids[1]
                use_id = True
            if ids[2]:
                params['rid'] = ids[2]
                use_id = True
            use_id and search_params.append(params)

        # add new query strings for exceptions
        name_exceptions = list(
            set([helpers.sanitizeSceneName(a) for a in
                 scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))

        for cur_exception in name_exceptions:
            params = base_params.copy()
            params['q'] = cur_exception
            search_params.append(params)

            if ep_obj.show.is_anime:
                # Experimental, add a search string without search explicitly for the episode!
                # Remove the ?ep=e46 parameter and use the episode number to the query parameter.
                # Can be useful for newznab indexers that do not have the episodes 100% parsed.
                # Start with only applying the search string to anime shows
                params = base_params.copy()
                params['q'] = '%s.%02d' % (cur_exception, int(params['ep']))
                if 'ep' in params:
                    params.pop('ep')
                search_params.append(params)

        return [{'Episode': search_params}]

    def supports_tvdbid(self):

        return self.get_id() not in ['sick_beard_index']

    def _search_provider(self, search_params, **kwargs):

        api_key = self._check_auth()

        base_params = {'t': 'tvsearch',
                       'maxage': sickbeard.USENET_RETENTION or 0,
                       'limit': 100,
                       'attrs': 'rageid',
                       'offset': 0}

        if isinstance(api_key, basestring):
            base_params['apikey'] = api_key

        results = []
        total = 0

        for mode in search_params.keys():
            for i, params in enumerate(search_params[mode]):

                # category ids
                cat = []
                cat_anime = ('5070', '6070')['nzbs_org' == self.get_id()]
                cat_sport = '5060'
                if 'Episode' == mode or 'Season' == mode:
                    if not ('rid' in params or 'tvdbid' in params or 'q' in params or not self.supports_tvdbid()):
                        logger.log('Error no rid, tvdbid, or search term available for search.')
                        continue

                    if self.show:
                        if self.show.is_sports:
                            cat = [cat_sport]
                        elif self.show.is_anime:
                            cat = [cat_anime]
                else:
                    cat = [cat_sport, cat_anime]

                if self.cat_ids or len(cat):
                    base_params['cat'] = ','.join(sorted(set(self.cat_ids.split(',') + cat)))

                request_params = base_params.copy()
                request_params.update(params)

                offset = 0
                batch_count = not 0

                # hardcoded to stop after a max of 4 hits (400 items) per query
                while (offset <= total) and (offset < (200, 400)[self.supports_tvdbid()]) and batch_count:
                    cnt = len(results)
                    search_url = '%sapi?%s' % (self.url, urllib.urlencode(request_params))

                    data = self.cache.getRSSFeed(search_url)
                    i and time.sleep(1.1)

                    if not data or not self.check_auth_from_data(data):
                        break

                    for item in data.entries:

                        title, url = self._title_and_url(item)
                        if title and url:
                            results.append(item)
                        else:
                            logger.log(u'The data returned from %s is incomplete, this result is unusable' % self.name,
                                       logger.DEBUG)

                    # get total and offset attribs
                    try:
                        if 0 == total:
                            total = int(data.feed.newznab_response['total'] or 0)
                            hits = (total / 100 + int(0 < (total % 100)))
                            hits += int(0 == hits)
                        offset = int(data.feed.newznab_response['offset'] or 0)
                    except AttributeError:
                        break

                    # No items found or cache mode, prevent from doing another search
                    if 0 == total or 'Cache' == mode:
                        break

                    if offset != request_params['offset']:
                        logger.log('Tell your newznab provider to fix their bloody newznab responses')
                        break

                    request_params['offset'] += request_params['limit']
                    if total <= request_params['offset']:
                        logger.log('%s item%s found that will be used for episode matching' % (total, helpers.maybe_plural(total)),
                                   logger.DEBUG)
                        break

                    # there are more items available than the amount given in one call, grab some more
                    items = total - request_params['offset']
                    logger.log('%s more item%s to fetch from a batch of up to %s items.'
                               % (items, helpers.maybe_plural(items), request_params['limit']), logger.DEBUG)

                    batch_count = len(results) - cnt
                    if batch_count:
                        self._log_search(mode, batch_count, search_url)

                if 'tvdbid' in request_params and len(results):
                    break

        return results


class NewznabCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)

        self.update_freq = 5  # cache update frequency

    def updateCache(self):

        result = []

        if True or self.shouldUpdate():
            try:
                self._checkAuth()
            except Exception:
                return result

            items = self.provider.cache_data()
            if items:

                self._clearCache()
                self.setLastUpdate()

                cl = []
                for item in items:
                    ci = self._parseItem(item)
                    if ci is not None:
                        cl.append(ci)

                if 0 < len(cl):
                    my_db = self.get_db()
                    my_db.mass_action(cl)

        return result

    # overwrite method with that parses the rageid from the newznab feed
    def _parseItem(self, *item):

        title = item[0].title
        url = item[0].link

        attrs = item[0].newznab_attr
        if not isinstance(attrs, list):
            attrs = [item[0].newznab_attr]

        tvrageid = 0
        for attr in attrs:
            if 'tvrageid' == attr['name']:
                tvrageid = int(attr['value'])
                break

        self._checkItemAuth(title, url)

        if not title or not url:
            logger.log(u'The data returned from the %s feed is incomplete, this result is unusable'
                       % self.provider.name, logger.DEBUG)
            return None

        url = self._translateLinkURL(url)

        logger.log(u'Attempting to add item from RSS to cache: ' + title, logger.DEBUG)
        return self.add_cache_entry(title, url, indexer_id=tvrageid)
