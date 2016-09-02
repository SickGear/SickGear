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

from . import generic
from sickbeard.rssfeeds import RSSFeeds
from lib.unidecode import unidecode


class PreToMeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PreToMe', cache_update_freq=6)

        self.url_base = 'https://pretome.info/'

        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + 'rss.php?cat[]=7&sort=0&type=d&key=%s',
                     'search': '&st=1&tf=all&search=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.passkey = None

    def _authorised(self, **kwargs):

        return self._check_auth()

    def _search_provider(self, search_params, **kwargs):

        self._authorised()
        results = []

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        url = self.urls['browse'] % self.passkey
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = url + (self.urls['search'] % search_string, '')['Cache' == mode]

                xml_data = RSSFeeds(self).get_feed(search_url)

                cnt = len(items[mode])
                if xml_data and 'entries' in xml_data:
                    for entry in xml_data['entries']:
                        try:
                            if entry['title'] and 'download' in entry['link']:
                                items[mode].append((entry['title'], entry['link'], None, None))
                        except KeyError:
                            continue

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = list(set(results + items[mode]))

        return results


provider = PreToMeProvider()
