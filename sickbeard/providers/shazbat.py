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
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import unidecode, unquote_plus
from six import iteritems, text_type


class ShazbatProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Shazbat', cache_update_freq=15)

        self.url_base = 'https://www.shazbat.tv/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login',
                     'feeds': self.url_base + 'rss_feeds',
                     'browse': self.url_base + 'torrents?portlet=true',
                     'search': self.url_base + 'search?portlet=true&search=%s',
                     'show': self.url_base + 'show?id=%s&show_mode=torrents'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.scene, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(ShazbatProvider, self)._authorised(
            logged_in=(lambda y=None: '<input type="password"' not in self.get_url(self.urls['feeds'], skip_auth=True)),
            post_params={'tv_login': self.username, 'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'show_id': r'"show\?id=(\d+)[^>]+>([^<]+)<\/a>',
                                                                        'get': 'load_torrent'})])
        search_types = sorted([x for x in iteritems(search_params)], key=lambda tup: tup[0], reverse=True)
        maybe_only = search_types[0][0]
        show_detail = '_only' in maybe_only and search_params.pop(maybe_only)[0] or ''
        for mode in search_params:
            for search_string in search_params[mode]:
                if 'Cache' == mode:
                    search_url = self.urls['browse']
                    html = self.get_url(search_url)
                    if self.should_skip():
                        return results
                else:
                    search_string = unidecode(search_string)
                    search_string = search_string.replace(show_detail, '').strip()
                    search_url = self.urls['search'] % search_string
                    html = self.get_url(search_url)
                    if self.should_skip():
                        return results

                    shows = rc['show_id'].findall(html)
                    if any(shows):
                        html = ''
                        for show in set(shows):
                            sid, title = show
                            if title in unquote_plus(search_string):
                                html and time.sleep(1.1)
                                html += self.get_url(self.urls['show'] % sid)
                                if self.should_skip():
                                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html) as tbl:
                        tbl_rows = tbl.tbody and tbl.tbody.find_all('tr') or tbl.table and tbl.table.find_all('tr')

                        if 2 > len(tbl_rows or []):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[0:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                stats = cells[head['leech']].get_text().strip()
                                seeders, leechers = [(try_int(x[0], 0), try_int(x[1], 0)) for x in
                                                     re.findall(r'(?::(\d+))(?:\W*[/]\W*:(\d+))?', stats) if x[0]][0]
                                if self._reject_item(seeders, leechers):
                                    continue
                                sizes = [(try_int(x[0], x[0]), try_int(x[1], False)) for x in
                                         re.findall(r'([\d.]+\w+)?(?:\s*[(\[](\d+)[)\]])?', stats) if x[0]][0]
                                size = sizes[(0, 1)[1 < len(sizes)]]

                                for element in [x for x in cells[2].contents[::-1] if text_type(x).strip()]:
                                    if 'NavigableString' in str(element.__class__):
                                        title = text_type(element).strip()
                                        break

                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return super(ShazbatProvider, self)._season_strings(ep_obj, detail_only=True)

    def _episode_strings(self, ep_obj, **kwargs):

        return super(ShazbatProvider, self)._episode_strings(ep_obj, detail_only=True, **kwargs)


provider = ShazbatProvider()
