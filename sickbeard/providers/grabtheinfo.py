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
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class GrabTheInfoProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'GrabTheInfo', cache_update_freq=20)

        self.url_base = 'http://grabthe.info/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'browse': self.url_base + 'browse.php?%s&incldead=%s&blah=0%s',
                     'search': '&search=%s',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': [36, 32, 43, 56, 8, 10, 61]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['browse'] % (self._categories_string(), ('3', '0')[not self.freeleech],
                                                    (self.urls['search'] % search_string, '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    html = html.replace('<?xml version="1.0" encoding="iso-8859-1"?>', '')
                    html = re.sub(r'(</td>)[^<]*</td>', r'\1', html)
                    html = re.sub(r'(<a[^<]*)<a[^<]*?href=details[^<]*', r'\1', html)
                    with BS4Parser(html, 'html.parser') as soup:
                        shows_found = False
                        torrent_rows = soup.find_all('tr')
                        for index, row in enumerate(torrent_rows):
                            if 'type' == row.find_all('td')[0].get_text().strip().lower():
                                shows_found = index
                                break

                        if not shows_found or 2 > (len(torrent_rows) - shows_found):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1 + shows_found:]:
                            try:
                                info = tr.find('a', href=rc['info'])
                                if None is info:
                                    continue
                                title = (('title' in info.attrs.keys() and info['title']) or info.get_text()).strip()

                                download_url = tr.find('a', href=rc['get'])
                                if None is download_url:
                                    continue

                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    (tr.find_all('td')[x].get_text().strip()) for x in (-2, -1, -3)]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue
                            except (AttributeError, TypeError, ValueError, KeyError):
                                continue

                            if title:
                                items[mode].append((title, self.urls['get'] % str(download_url['href'].lstrip('/')),
                                                    seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='|', **kwargs)


provider = GrabTheInfoProvider()
