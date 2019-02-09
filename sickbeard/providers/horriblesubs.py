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
import time
import traceback
import urllib

from . import generic
from sickbeard import logger, show_name_helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class HorribleSubsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HorribleSubs', anime_only=True)
        self.url_base = 'http://horriblesubs.info/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + 'rss.php?res=all',
                     'search': self.url_base + 'api.php?method=search&value=%s&_=%s',
                     'get_data': self.url_base + 'api.php?method=getshows&type=show&showid=%s'}
        self.url = self.urls['config_provider_home_uri']

        delattr(self, 'search_mode')
        delattr(self, 'search_fallback')

    def _search_provider(self, search_params, **kwargs):

        results = []
        if self.show and not self.show.is_anime:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'dl-label', 'get': 'magnet:', 'nodots': '[\.\s]+'}.items())

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode else \
                    self.urls['search'] % (rc['nodots'].sub(' ', search_string), str(time.time()).replace('.', '3'))

                data, html = 2 * [None]
                if 'Cache' == mode:
                    data = self.cache.get_rss(search_url)
                else:
                    html = self.get_url(search_url)

                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if None is not data:
                        for cur_item in data.get('entries', []):
                            title, download_url = cur_item.get('title'), self._link(cur_item.get('link'))
                            if title and download_url:
                                items[mode].append((title, download_url, '', ''))
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser('<html><body>%s</body></html>' % html, features=['html5lib', 'permissive']) as soup:
                        for link in soup.find_all('a'):
                            try:
                                variants = map(lambda t: t.get_text().replace('SD', '480p'),
                                               link.find_all('span', class_='badge'))
                                map(lambda t: t.decompose(), link.find_all('span') + link.find_all('div'))
                                title = '[HorribleSubs] ' + re.sub(r'\s*\[HorribleSubs\]\s*', '', link.get_text())
                                download_url = self._link(link.get('href'))
                                if title and download_url:
                                    items[mode] += map(lambda v: (
                                        '%s [%s]' % (title, v), '%s-%s' % (download_url, v), '', ''), variants)
                            except (AttributeError, TypeError, ValueError):
                                continue

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def get_data(self, url):
        result = None
        html = self.get_url(url)
        if self.should_skip():
            return result
        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
            re_showid = re.compile(r'(?i)hs_showid\s*=\s*(\d+)')
            try:
                hs_id = re_showid.findall(
                    filter(lambda s: re_showid.search(s), map(lambda t: t.get_text(), soup.find_all('script')))[0])[0]
            except (Exception, BaseException):
                return result
        html = self.get_url(self.urls['get_data'] % hs_id)
        if self.should_skip():
            return result
        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
            try:
                result = sorted(map(lambda t: t.get('href'),
                                    soup.find(id=re.findall(r'.*#(\d+-\d+\w)$', url)[0])
                                    .find_all('a', href=re.compile('(?i)(torrent$|^magnet:)'))))[0]
            except (Exception, BaseException):
                pass
        return result


provider = HorribleSubsProvider()
