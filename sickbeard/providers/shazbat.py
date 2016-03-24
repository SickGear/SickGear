# coding=utf-8
#
# Author: SickGear
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

from . import generic
from sickbeard import helpers, logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class ShazbatProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Shazbat', cache_update_freq=20)

        self.url_base = 'https://www.shazbat.tv/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login',
                     'feeds': self.url_base + 'rss_feeds',
                     'browse': self.url_base + 'torrents?portlet=true',
                     'search': self.url_base + 'search?portlet=true&search=%s',
                     'show': self.url_base + 'show?id=%s&show_mode=torrents',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(ShazbatProvider, self)._authorised(
            logged_in=(lambda x=None: '<input type="password"' not in helpers.getURL(
                self.urls['feeds'], session=self.session)),
            post_params={'tv_login': self.username, 'tv_password': self.password,
                         'referer': 'login', 'query': '', 'email': ''})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'show_id': '"show\?id=(\d+)[^>]+>([^<]+)<\/a>',
                                                             'get': 'load_torrent'}.items())
        search_types = sorted([x for x in search_params.items()], key=lambda tup: tup[0], reverse=True)
        maybe_only = search_types[0][0]
        show_detail = '_only' in maybe_only and search_params.pop(maybe_only)[0] or ''
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                if 'Cache' == mode:
                    search_url = self.urls['browse']
                    html = self.get_url(search_url)
                else:
                    search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                    search_string = search_string.replace(show_detail, '').strip()
                    search_url = self.urls['search'] % search_string
                    html = self.get_url(search_url)
                    shows = rc['show_id'].findall(html)
                    if not any(shows):
                        continue
                    html = ''
                    for show in shows:
                        sid, title = show
                        if title not in search_string:
                            continue
                        html and time.sleep(1.1)
                        html += self.get_url(self.urls['show'] % sid)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.tbody.find_all('tr') or soup.table.find_all('tr') or []

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[0:]:
                            try:
                                stats = tr.find_all('td')[3].get_text().strip()
                                seeders, leechers = [(tryInt(x[0], 0), tryInt(x[1], 0)) for x in
                                                     re.findall('(?::(\d+))(?:\W*[/]\W*:(\d+))?', stats) if x[0]][0]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue
                                sizes = [(tryInt(x[0], x[0]), tryInt(x[1], False)) for x in
                                         re.findall('([\d\.]+\w+)?(?:\s*[\(\[](\d+)[\)\]])?', stats) if x[0]][0]
                                size = sizes[(0, 1)[1 < len(sizes)]]

                                for element in [x for x in tr.find_all('td')[2].contents[::-1] if unicode(x).strip()]:
                                    if 'NavigableString' in str(element.__class__):
                                        title = unicode(element).strip()
                                        break

                                link = str(tr.find('a', href=rc['get'])['href']).replace('&amp;', '&').lstrip('/')
                                download_url = self.urls['get'] % link
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, detail_only=True, scene=False)

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, detail_only=True, scene=False, **kwargs)


provider = ShazbatProvider()
