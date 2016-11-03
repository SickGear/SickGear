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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

try:
    from collections import OrderedDict
except ImportError:
    from requests.compat import OrderedDict
import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class HDSpaceProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HDSpace', cache_update_freq=17)

        self.url_base = 'https://hd-space.org/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'index.php?page=login',
                     'browse': self.url_base + 'index.php?page=torrents&' + '&'.join(
                         ['options=0', 'active=1', 'category=']),
                     'search': '&search=%s',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [21, 22, 24, 25, 27, 28]}

        self.url = self.urls['config_provider_home_uri']

        self.filter = []
        self.may_filter = OrderedDict([
            ('f0', ('not marked', False, '')), ('f25', ('FL', True, 'gold|sf')), ('f50', ('F/L', True, 'silver|sf'))])
        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(HDSpaceProvider, self)._authorised(
            post_params={'uid': self.username, 'form_tmpl': 'name=[\'"]login[\'"]'})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'torrent-details', 'get': 'download', 'peers': 'page=peers', 'nodots': '[\.\s]+'}.items())
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            rc['filter'] = re.compile('(?i)(%s).png' % '|'.join(
                [self.may_filter[f][2] for f in filters if self.may_filter[f][1]]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join([self.may_filter[f][0] for f in filters]))
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] + self._categories_string(template='', delimiter=';')
                if 'Cache' != mode:
                    search_url += self.urls['search'] % rc['nodots'].sub(' ', search_string)

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive'],
                                   attr='width="100%"\Wclass="lista"') as soup:
                        torrent_table = soup.find_all('table', class_='lista')[-1]
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if (6 > len(cells) or tr.find('td', class_='header')
                                or (any(self.filter)
                                    and ((non_marked and tr.find('img', src=rc['filter']))
                                         or (not non_marked and not tr.find('img', src=rc['filter']))))):
                                continue
                            downlink = tr.find('a', href=rc['get'])
                            if None is downlink:
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers = [tryInt(x.get_text().strip())
                                                     for x in tr.find_all('a', href=rc['peers'])]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                size = cells[head['size']].get_text().strip()
                                download_url = self._link(downlink['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, log + search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False)

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, **kwargs)


provider = HDSpaceProvider()
