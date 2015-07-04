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

import urllib
import time

import sickbeard
import generic

from sickbeard import helpers, scene_exceptions, logger, tvcache
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

    def _checkAuth(self):

        if self.needs_auth and not self.key:
            logger.log(u'Incorrect authentication credentials for %s : API key is missing' % self.name, logger.DEBUG)
            raise AuthException('Your authentication credentials for %s are missing, check your config.' % self.name)

        return True

    def check_auth_from_data(self, data):

        if data is None:
            return self._checkAuth()

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

        self._checkAuth()

        params = {'t': 'caps'}
        if self.needs_auth and self.key:
            params['apikey'] = self.key

        try:
            categories = self.getURL('%s/api' % self.url, params=params, timeout=10)
        except:
            logger.log(u'Error getting html for [%s]' %
                       ('%s/api?%s' % (self.url, '&'.join('%s=%s' % (x, y) for x, y in params.items()))), logger.DEBUG)
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
               % (self.name or '', self.url or '', self.key or '', self.cat_ids or '', self.enabled,
                  self.search_mode or '', self.search_fallback, self.enable_recentsearch, self.enable_backlog)

    def _get_season_search_strings(self, ep_obj):

        to_return = []
        cur_params = {}

        # season
        if ep_obj.show.air_by_date or ep_obj.show.sports:
            date_str = str(ep_obj.airdate).split('-')[0]
            cur_params['season'] = date_str
            cur_params['q'] = date_str.replace('-', '.')
        elif ep_obj.show.is_anime:
            cur_params['season'] = '%d' % ep_obj.scene_absolute_number
        else:
            cur_params['season'] = str(ep_obj.scene_season)

        # search
        rid = helpers.mapIndexersToShow(ep_obj.show)[2]
        if rid:
            cur_return = cur_params.copy()
            cur_return['rid'] = rid
            to_return.append(cur_return)

        # add new query strings for exceptions
        name_exceptions = list(
            set([helpers.sanitizeSceneName(a) for a in
                 scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
        for cur_exception in name_exceptions:
            cur_return = cur_params.copy()
            if 'q' in cur_return:
                cur_return['q'] = cur_exception + '.' + cur_return['q']
            to_return.append(cur_return)

        return to_return

    def _get_episode_search_strings(self, ep_obj, add_string=''):
        to_return = []
        params = {}

        if not ep_obj:
            return [params]

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            date_str = str(ep_obj.airdate)
            params['season'] = date_str.partition('-')[0]
            params['ep'] = date_str.partition('-')[2].replace('-', '/')
        elif ep_obj.show.anime:
            params['ep'] = '%i' % int(
                ep_obj.scene_absolute_number if int(ep_obj.scene_absolute_number) > 0 else ep_obj.scene_episode)
        else:
            params['season'] = ep_obj.scene_season
            params['ep'] = ep_obj.scene_episode

        # search
        rid = helpers.mapIndexersToShow(ep_obj.show)[2]
        if rid:
            cur_return = params.copy()
            cur_return['rid'] = rid
            to_return.append(cur_return)

        # add new query strings for exceptions
        name_exceptions = list(
            set([helpers.sanitizeSceneName(a) for a in
                 scene_exceptions.get_scene_exceptions(ep_obj.show.indexerid) + [ep_obj.show.name]]))
        for cur_exception in name_exceptions:
            cur_return = params.copy()
            cur_return['q'] = cur_exception
            to_return.append(cur_return)

            if ep_obj.show.anime:
                # Experimental, add a searchstring without search explicitly for the episode!
                # Remove the ?ep=e46 paramater and use add the episode number to the query paramater.
                # Can be usefull for newznab indexers that do not have the episodes 100% parsed.
                # Start with only applying the searchstring to anime shows
                params['q'] = cur_exception
                params_no_ep = params.copy()

                params_no_ep['q'] = '%s.%02d' % (params_no_ep['q'], int(params_no_ep['ep']))
                if 'ep' in params_no_ep:
                    params_no_ep.pop('ep')
                to_return.append(params_no_ep)

        return to_return

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        self._checkAuth()

        if 'rid' not in search_params and 'q' not in search_params:
            logger.log('Error no rid or search term given.')
            return []

        params = {'t': 'tvsearch',
                  'maxage': sickbeard.USENET_RETENTION,
                  'limit': 100,
                  'attrs': 'rageid',
                  'offset': 0}

        # category ids
        cat = []
        if self.show:
            if self.show.is_sports:
                cat = ['5060']
            elif self.show.is_anime:
                cat = ['5070']
        params['cat'] = ','.join([self.cat_ids] + cat)

        # if max_age is set, use it, don't allow it to be missing
        if not params['maxage'] or age:
            params['maxage'] = age

        if search_params:
            params.update(search_params)

        if self.needs_auth and self.key:
            params['apikey'] = self.key

        results = []
        offset = total = 0

        # hardcoded to stop after a max of 4 hits (400 items) per query
        while (offset <= total) and (offset < 400):
            search_url = '%sapi?%s' % (self.url, urllib.urlencode(params))
            logger.log(u'Search url: ' + search_url, logger.DEBUG)

            data = self.cache.getRSSFeed(search_url)
            time.sleep(1.1)
            if not data or not self.check_auth_from_data(data):
                break

            for item in data.entries:

                title, url = self._get_title_and_url(item)
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

            # No items found, prevent from doing another search
            if 0 == total:
                break

            if offset != params['offset']:
                logger.log('Tell your newznab provider to fix their bloody newznab responses')
                break

            params['offset'] += params['limit']
            if total <= params['offset']:
                logger.log('%s item%s found that will be used for episode matching' % (total, helpers.maybe_plural(total)),
                           logger.DEBUG)
                break

            # there are more items available than the amount given in one call, grab some more
            items = total - params['offset']
            logger.log('%s more item%s to fetch from a batch of up to %s items.'
                       % (items, helpers.maybe_plural(items), params['limit']), logger.DEBUG)
        return results

    def findPropers(self, search_date=None):
        return self._find_propers(search_date)


class NewznabCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)

        self.minTime = 15  # cache update frequency

    def _getRSSData(self):

        params = {'t': 'tvsearch',
                  'cat': self.provider.cat_ids + ',5060,5070',
                  'attrs': 'rageid'}

        if self.provider.needs_auth and self.provider.key:
            params['apikey'] = self.provider.key

        rss_url = '%sapi?%s' % (self.provider.url, urllib.urlencode(params))

        logger.log(self.provider.name + ' cache update URL: ' + rss_url, logger.DEBUG)

        return self.getRSSFeed(rss_url)

    def _checkAuth(self, *data):

        return self.provider.check_auth_from_data(data[0])

    def updateCache(self):

        if self.shouldUpdate() and self._checkAuth(None):
            data = self._getRSSData()

            # as long as the http request worked we count this as an update
            if not data:
                return []

            # clear cache
            self._clearCache()

            self.setLastUpdate()

            if self._checkAuth(data):
                items = data.entries
                cl = []
                for item in items:
                    ci = self._parseItem(item)
                    if ci is not None:
                        cl.append(ci)

                if 0 < len(cl):
                    my_db = self._getDB()
                    my_db.mass_action(cl)

            else:
                raise AuthException(
                    u'Your authentication credentials for ' + self.provider.name + ' are incorrect, check your config')

        return []

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
        return self._addCacheEntry(title, url, indexer_id=tvrageid)
