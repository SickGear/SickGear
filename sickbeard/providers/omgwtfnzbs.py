# Author: Jordon Smith <smith@jordon.me.uk>
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear. If not, see <http://www.gnu.org/licenses/>.

from datetime import datetime
import re
import time
import traceback
import urllib

import sickbeard

from . import generic
from sickbeard import classes, logger, show_name_helpers, tvcache
from sickbeard.bs4_parser import BS4Parser
from sickbeard.exceptions import AuthException
from sickbeard.rssfeeds import RSSFeeds


class OmgwtfnzbsProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'omgwtfnzbs')

        self.url = 'https://omgwtfnzbs.me/'

        self.url_base = 'https://omgwtfnzbs.me/'
        self.url_api = 'https://api.omgwtfnzbs.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': 'https://rss.omgwtfnzbs.me/rss-download.php?%s',
                     'search': self.url_api + 'json/?%s',
                     'get': self.url_base + '%s',
                     'cache_html': self.url_base + 'browse.php?cat=tv%s',
                     'search_html': self.url_base + 'browse.php?cat=tv&search=%s'}

        self.needs_auth = True
        self.username, self.api_key, self.cookies = 3 * [None]
        self.cache = OmgwtfnzbsCache(self)

    def _check_auth_from_data(self, parsed_data, is_xml=True):

        if parsed_data is None:
            return self._check_auth()

        if is_xml:
            # provider doesn't return xml on error
            return True
        else:
            data_json = parsed_data

            if 'notice' in data_json:
                description_text = data_json.get('notice')

                if 'information is incorrect' in data_json.get('notice'):
                    logger.log(u'Incorrect authentication credentials for ' + self.name + ' : ' + str(description_text),
                               logger.DEBUG)
                    raise AuthException(
                        'Your authentication credentials for ' + self.name + ' are incorrect, check your config.')

                elif '0 results matched your terms' in data_json.get('notice'):
                    return True

                else:
                    logger.log(u'Unknown error given from ' + self.name + ' : ' + str(description_text), logger.DEBUG)
                    return False

            return True

    def _season_strings(self, ep_obj):

        return [x for x in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj)]

    def _episode_strings(self, ep_obj):

        return [x for x in show_name_helpers.makeSceneSearchString(self.show, ep_obj)]

    def _title_and_url(self, item):

        return item['release'].replace('_', '.'), item['getnzb']

    def get_data(self, url):
        result = None
        if url and False is self._init_api():
            data = self.get_url(url, timeout=90)
            if data:
                if re.search('(?i)limit.*?reached', data):
                    logger.log('Daily Nzb Download limit reached', logger.DEBUG)
                elif '</nzb>' not in data or 'seem to be logged in' in data:
                    logger.log('Failed nzb data response: %s' % data, logger.DEBUG)
                else:
                    result = data
        return result

    def get_result(self, episodes, url):

        result = None
        if url and False is self._init_api():
            result = classes.NZBDataSearchResult(episodes)
            result.get_data_func = self.get_data
            result.url = url

        if None is result:
            result = classes.NZBSearchResult(episodes)
            result.url = url

        result.provider = self

        return result

    def cache_data(self):

        api_key = self._init_api()
        if False is api_key:
            return self.search_html()
        if None is not api_key:
            params = {'user': self.username,
                      'api': api_key,
                      'eng': 1,
                      'catid': '19,20'}  # SD,HD

            rss_url = self.urls['cache'] % urllib.urlencode(params)

            logger.log(self.name + u' cache update URL: ' + rss_url, logger.DEBUG)

            data = RSSFeeds(self).get_feed(rss_url)
            if data and 'entries' in data:
                return data.entries
        return []

    def _search_provider(self, search, search_mode='eponly', epcount=0, retention=0, **kwargs):

        api_key = self._init_api()
        if False is api_key:
            return self.search_html(search, search_mode)
        results = []
        if None is not api_key:
            params = {'user': self.username,
                      'api': api_key,
                      'eng': 1,
                      'nukes': 1,
                      'catid': '19,20',  # SD,HD
                      'retention': (sickbeard.USENET_RETENTION, retention)[retention or not sickbeard.USENET_RETENTION],
                      'search': search}

            search_url = self.urls['search'] % urllib.urlencode(params)
            logger.log(u'Search url: ' + search_url, logger.DEBUG)

            data_json = self.get_url(search_url, json=True)
            if data_json and self._check_auth_from_data(data_json, is_xml=False):
                for item in data_json:
                    if 'release' in item and 'getnzb' in item:
                        if item.get('nuked', '').startswith('1'):
                            continue
                        results.append(item)
        return results

    def search_html(self, search='', search_mode=''):

        results = []
        if None is self.cookies:
            return results

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': r'send\?', 'nuked': r'\bnuked',
                                                             'cat': 'cat=(?:19|20)'}.items())
        mode = ('search', 'cache')['' == search]
        search_url = self.urls[mode + '_html'] % search
        html = self.get_url(search_url)
        cnt = len(results)
        try:
            if not html:
                raise generic.HaltParseException

            with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                torrent_table = soup.find('table', attrs={'id': 'table_table'})
                torrent_rows = []
                if torrent_table:
                    torrent_rows = torrent_table.find('tbody').find_all('tr')

                if 1 > len(torrent_rows):
                    raise generic.HaltParseException

                for tr in torrent_rows:
                    try:
                        if tr.find('img', src=rc['nuked']) or not tr.find('a', href=rc['cat']):
                            continue

                        title = tr.find('a', href=rc['info']).get_text().strip()
                        download_url = tr.find('a', href=rc['get'])
                        age = tr.find_all('td')[-1]['data-sort']
                    except (AttributeError, TypeError, ValueError):
                        continue

                    if title and download_url and age:
                        results.append({'release': title, 'getnzb': self.urls['get'] % download_url['href'].lstrip('/'),
                                        'usenetage': int(age.strip())})

        except generic.HaltParseException:
            time.sleep(1.1)
            pass
        except (StandardError, Exception):
            logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

        mode = (mode, search_mode)['Propers' == search_mode]
        self._log_search(mode, len(results) - cnt, search_url)
        return results

    def find_propers(self, **kwargs):

        search_terms = ['.PROPER.', '.REPACK.']
        results = []

        for term in search_terms:
            for item in self._search_provider(term, search_mode='Propers', retention=4):
                if 'usenetage' in item:

                    title, url = self._title_and_url(item)
                    try:
                        result_date = datetime.fromtimestamp(int(item['usenetage']))
                    except (StandardError, Exception):
                        result_date = None

                    if result_date:
                        results.append(classes.Proper(title, url, result_date, self.show))

        return results

    def _init_api(self):

        try:
            api_key = self._check_auth()
            if not api_key.startswith('cookie:'):
                return api_key
        except (StandardError, Exception):
            return None

        self.cookies = re.sub(r'(?i)([\s\']+|cookie\s*:)', '', api_key)
        success, msg = self._check_cookie()
        if not success:
            logger.log(u'%s: %s' % (msg, self.cookies), logger.WARNING)
            self.cookies = None
            return None
        return False

    @staticmethod
    def ui_string(key):

        return 'omgwtfnzbs_api_key' == key and 'Or use... \'cookie: cookname=xx; cookpass=yy\'' or ''


class OmgwtfnzbsCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 20

    def _cache_data(self):

        return self.provider.cache_data()


provider = OmgwtfnzbsProvider()
