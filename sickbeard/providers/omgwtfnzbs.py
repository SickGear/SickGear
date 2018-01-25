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

import feedparser
import sickbeard

from . import generic
from sickbeard import classes, logger, show_name_helpers, tvcache
from sickbeard.bs4_parser import BS4Parser
from sickbeard.exceptions import AuthException
from sickbeard.common import neededQualities


class OmgwtfnzbsProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'omgwtfnzbs')

        self.url = 'https://omgwtfnzbs.me/'
        self.url_base = 'https://omgwtfnzbs.me/'
        self.url_api = 'https://api.omgwtfnzbs.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': self.url_api + 'xml/?%s',
                     'search': self.url_api + 'json/?%s',
                     'cache_html': self.url_base + 'browse.php?cat=tv%s',
                     'search_html': self.url_base + 'browse.php?cat=tv&search=%s'}

        self.needs_auth = True
        self.username, self.api_key, self.cookies = 3 * [None]
        self.cache = OmgwtfnzbsCache(self)

    cat_sd = ['19']
    cat_hd = ['20']
    cat_uhd = ['30']

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

                if re.search('(?i)(information is incorrect|in(?:valid|correct).*?(?:username|api))',
                             data_json.get('notice')):
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

    @staticmethod
    def _get_cats(needed):
        cats = []
        if needed.need_sd:
            cats.extend(OmgwtfnzbsProvider.cat_sd)
        if needed.need_hd:
            cats.extend(OmgwtfnzbsProvider.cat_hd)
        if needed.need_uhd:
            cats.extend(OmgwtfnzbsProvider.cat_uhd)
        return cats

    def cache_data(self, needed=neededQualities(need_all=True), **kwargs):

        api_key = self._init_api()
        if False is api_key:
            return self.search_html(needed=needed, **kwargs)
        results = []
        cats = self._get_cats(needed=needed)
        if None is not api_key:
            params = {'search': '',
                      'user': self.username,
                      'api': api_key,
                      'eng': 1,
                      'catid': ','.join(cats)}  # SD,HD

            url = self.urls['cache'] % urllib.urlencode(params)

            response = self.get_url(url)

            data = feedparser.parse(response.replace('<xml', '<?xml').replace('>\n<info>', '?>\n<feed>\n<info>')
                                    .replace('<search_req>\n', '').replace('</search_req>\n', '')
                                    .replace('post>\n', 'entry>\n').replace('</xml>', '</feed>'))
            if data and 'entries' in data:
                results = data.entries

            self._log_search('Cache', len(results), url)
        return results

    def _search_provider(self, search, search_mode='eponly', epcount=0, retention=0,
                         needed=neededQualities(need_all=True), **kwargs):

        api_key = self._init_api()
        if False is api_key:
            return self.search_html(search, search_mode, needed=needed, **kwargs)
        results = []
        cats = self._get_cats(needed=needed)
        if None is not api_key:
            params = {'user': self.username,
                      'api': api_key,
                      'eng': 1,
                      'nukes': 1,
                      'catid': ','.join(cats),  # SD,HD
                      'retention': retention or sickbeard.USENET_RETENTION or 0,
                      'search': search}

            search_url = self.urls['search'] % urllib.urlencode(params)

            data_json = self.get_url(search_url, json=True)
            if data_json and self._check_auth_from_data(data_json, is_xml=False):
                for item in data_json:
                    if 'release' in item and 'getnzb' in item:
                        if item.get('nuked', '').startswith('1'):
                            continue
                        results.append(item)

            mode = search_mode
            if 'eponly' == search_mode:
                mode = 'Episode'
            elif 'sponly' == search_mode:
                mode = 'Season'
            self._log_search(mode, len(results), search_url)
        return results

    def search_html(self, search='', search_mode='', needed=neededQualities(need_all=True), **kwargs):

        results = []
        if None is self.cookies:
            return results

        cats = self._get_cats(needed=needed)

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': r'send\?', 'nuked': r'\bnuked',
                                                             'cat': 'cat=(?:%s)' % '|'.join(cats)}.items())
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
                        results.append({'release': title, 'getnzb': self._link(download_url['href']),
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

        search_terms = ['.PROPER.', '.REPACK.', '.REAL.']
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

    def _cache_data(self, **kwargs):

        return self.provider.cache_data(**kwargs)


provider = OmgwtfnzbsProvider()
