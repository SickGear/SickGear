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
import traceback

from . import generic
from .. import logger
from ..helpers import sanitize_scene_name
from bs4_parser import BS4Parser

from _23 import decode_str, filter_list, html_unescape, list_keys, list_values, unidecode
from six import iteritems, iterkeys


class ShowRSSProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'showRSS')

        self.url_base = 'https://showrss.info/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login',
                     'browse': self.url_base + 'browse/all',
                     'search': self.url_base + 'browse/%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.shows = 3 * [None]

    def _authorised(self, **kwargs):

        return super(ShowRSSProvider, self)._authorised(logged_in=(lambda y=None: self.logged_in(y)))

    def logged_in(self, y):
        if all([None is y or 'logout' in y,
                bool(filter_list(lambda c: 'remember_web_' in c, iterkeys(self.session.cookies)))]):
            if None is not y:
                self.shows = dict(re.findall(r'<option value="(\d+)">(.*?)</option>', y))
                for k, v in iteritems(self.shows):
                    self.shows[k] = sanitize_scene_name(html_unescape(unidecode(decode_str(v))))
            return True
        return False

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'get': 'magnet'})])
        urls = []
        for mode in search_params:
            for search_string in search_params[mode]:
                if 'Cache' == mode:
                    search_url = self.urls['browse']
                else:
                    search_string = unidecode(search_string)
                    show_name = filter_list(lambda x: x.lower() == re.sub(r'\s.*', '', search_string.lower()),
                                            list_values(self.shows))
                    if not show_name:
                        continue
                    search_url = self.urls['search'] % list_keys(self.shows)[
                        list_values(self.shows).index(show_name[0])]

                if search_url in urls:
                    continue
                urls += [search_url]

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html) as soup:
                        tbl_rows = soup.select('ul.user-timeline > li')

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        for tr in tbl_rows:
                            try:
                                anchor = tr.find('a', href=rc['get'])
                                title = self.regulate_title(anchor)
                                download_url = self._link(anchor['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, None, None))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def regulate_title(anchor):
        title = ''
        t1 = anchor.attrs.get('title').strip()
        t2 = anchor.get_text().strip()
        diff, x, offset = 0, 0, 0
        for x, c in enumerate(t2):
            if c.lower() == t1[x-offset].lower():
                title += t1[x-offset]
                diff = 0
            elif ' ' != c and ' ' == t1[x-offset]:
                title += c
                diff = 0
                if ' ' == t2[x+1]:
                    offset += 1
            else:
                diff += 1
                if 1 < diff:
                    break
        return '%s%s' % (title, re.sub(r'(?i)(xvid|divx|[hx].?26[45])\s(\w+)$', r'\1-\2',
                                       ''.join(t1[x - (offset + diff)::]).strip()))

    @staticmethod
    def ui_string(key):

        return ('showrss_tip' == key
                and 'lists are not needed, the SickGear list is used as usual' or '')


provider = ShowRSSProvider()
