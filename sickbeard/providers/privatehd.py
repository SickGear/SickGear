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


class PrivateHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PrivateHD')

        self.url_base = 'https://privatehd.to/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'auth/login',
                     'search': self.url_base + 'torrents?%s' % '&'.join(
                         ['in=1', 'tags=', 'type=2', 'language=0', 'subtitle=0', 'rip_type=0',
                          'video_quality=0', 'uploader=', 'search=%s', 'tv_type[]=%s', 'discount[]=%s'])}

        self.categories = {'Season': [2], 'Episode': [1], 'Cache': [0]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(PrivateHDProvider, self)._authorised(
            logged_in=lambda x=None: self.has_all_cookies(['love']),
            post_params={'email_username': self.username})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'info': '.*?details\s*-\s*', 'get': 'download'}.items())
        for mode in search_params.keys():
            if mode in ['Season', 'Episode']:
                show_type = self.show.air_by_date and 'Air By Date' \
                    or self.show.is_sports and 'Sports' or self.show.is_anime and 'Anime' or None
                if show_type:
                    logger.log(u'Provider does not carry shows of type: [%s], skipping' % show_type, logger.DEBUG)
                    return results

            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (
                    '+'.join(search_string.split()), self._categories_string(mode, ''), (1, 0)[not self.freeleech])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'table'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    (tr.find_all('td')[x].get_text().strip()) for x in (-3, -2, -4)]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = rc['info'].sub('', tr.find('a', attrs={'title': rc['info']})['title'])

                                download_url = tr.find('a', href=rc['get'])['href']

                            except (AttributeError, TypeError, ValueError, IndexError):
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


provider = PrivateHDProvider()
