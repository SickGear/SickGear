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

from . import generic
from sickbeard import logger, tvcache
from sickbeard.helpers import tryInt
from sickbeard.exceptions import ex
from sickbeard.rssfeeds import RSSFeeds
from lib.bencode import bdecode


class TorrentRssProvider(generic.TorrentProvider):

    def __init__(self, name, url, cookies='', search_mode='eponly', search_fallback=False,
                 enable_recentsearch=False, enable_backlog=False, enable_scheduled_backlog=False):
        self.enable_backlog = bool(tryInt(enable_backlog))
        self.enable_scheduled_backlog = bool(tryInt(enable_scheduled_backlog))
        generic.TorrentProvider.__init__(self, name, supports_backlog=self.enable_backlog, cache_update_freq=15)

        self.url = url.rstrip('/')
        self.url_base = self.url
        self.cookies = cookies

        self.enable_recentsearch = bool(tryInt(enable_recentsearch)) or not self.enable_backlog
        self.search_mode = search_mode
        self.search_fallback = bool(tryInt(search_fallback))

        self.feeder = RSSFeeds(self)

    def image_name(self):

        return generic.GenericProvider.image_name(self, 'torrentrss')

    def config_str(self):

        return '%s|%s|%s|%d|%s|%d|%d|%d|%d' % (
            self.name or '', self.url or '', self.cookies or '', self.enabled,
            self.search_mode or '', self.search_fallback, self.enable_recentsearch, self.enable_backlog,
            self.enable_scheduled_backlog)

    def _title_and_url(self, item):

        title, url = None, None

        if item.title:
            title = re.sub(r'\s+', '.', u'' + item.title)

        attempt_list = [lambda: item.torrent_magneturi,
                        lambda: item.enclosures[0].href,
                        lambda: item.link]

        for cur_attempt in attempt_list:
            try:
                url = cur_attempt()
            except (StandardError, Exception):
                continue

            if title and url:
                break

        return title, url

    def validate_feed(self):

        success, err_msg = self._check_cookie()
        if not success:
            return success, err_msg

        try:
            items = self._search_provider({'Validate': ['']})

            for item in items:
                title, url = self._title_and_url(item)
                if not (title and url):
                    continue
                if url.startswith('magnet:'):
                    btih = None
                    try:
                        btih = re.findall('urn:btih:([\w]{32,40})', url)[0]
                        if 32 == len(btih):
                            from base64 import b16encode, b32decode
                            btih = b16encode(b32decode(btih))
                    except (StandardError, Exception):
                        pass
                    if re.search('(?i)[0-9a-f]{32,40}', btih):
                        break
                else:
                    torrent_file = self.get_url(url)
                    try:
                        bdecode(torrent_file)
                        break
                    except (StandardError, Exception):
                        pass
            else:
                return False, '%s fetched RSS feed data: %s' % \
                              (('Fail to validate', 'No items found in the')[0 == len(items)], self.url)

            return True, None

        except Exception as e:
            return False, 'Error when trying to load RSS: ' + ex(e)

    def _search_provider(self, search_params, **kwargs):

        result = []
        for mode in search_params.keys():
            data = self.feeder.get_feed(self.url)

            result += (data and 'entries' in data) and data.entries or []

            self.log_result(mode, count=len(result), url=self.url)

        return result
