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

import re
import time

from . import generic
from sickbeard.helpers import tryInt


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentDay')

        self.url_home = ['https://%s/' % u for u in 'torrentday.eu', 'secure.torrentday.com', 'tdonline.org',
                                                    'torrentday.it', 'www.td.af', 'www.torrentday.com']

        self.url_vars = {'login': 'torrents/', 'search': 'V3/API/API.php', 'get': 'download.php/%s/%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.categories = {'Season': [31, 33, 14], 'Episode': [24, 32, 26, 7, 2], 'Anime': [29]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.proper_search_terms = None

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentDayProvider, self)._authorised(
            post_params={'submit.x': 0, 'submit.y': 0},
            failed_msg=(lambda x=None: re.search(r'(?i)tried((<[^>]+>)|\W)*too((<[^>]+>)|\W)*often', x) and
                        u'Abort %s, Too many login attempts. Settings must be checked' or (
                re.search(r'(?i)username((<[^>]+>)|\W)*or((<[^>]+>)|\W)*password', x) and
                u'Invalid username or password for %s. Check settings' or
                u'Failed to authenticate with %s, abort provider')))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                post_data = dict((x.split('=') for x in self._categories_string(mode).split('&')),
                                 search=search_string, cata='yes', jxt=8, jxw='b')

                if self.freeleech:
                    post_data.update({'free': 'on'})

                data_json = self.get_url(self.urls['search'], post_data=post_data, json=True)

                cnt = len(items[mode])
                try:
                    if not data_json:
                        raise generic.HaltParseException
                    torrents = data_json.get('Fs')[0].get('Cn').get('torrents')

                    for item in torrents:
                        seeders, leechers, size = [tryInt(n, n) for n in [item.get(x) for x in 'seed', 'leech', 'size']]
                        if self._peers_fail(mode, seeders, leechers):
                            continue

                        title = re.sub(r'\[.*=.*\].*\[/.*\]', '', item['name'])

                        download_url = self.urls['get'] % (item['id'], item['fname'])

                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except Exception:
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='.', date_or=True, **kwargs)


provider = TorrentDayProvider()
