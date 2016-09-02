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
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class FreshOnTVProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'FreshOnTV', cache_update_freq=20)

        self.url_base = 'https://freshon.tv/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'browse.php?incldead=%s&words=0&%s&search=%s',
                     'get': self.url_base + '%s'}

        self.categories = {'shows': 0, 'anime': 235}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(FreshOnTVProvider, self)._authorised(
            post_params={'form_tmpl': True},
            failed_msg=(lambda y=None: 'DDoS protection by CloudFlare' in y and
                                       u'Unable to login to %s due to CloudFlare DDoS javascript check' or
                                       'Username does not exist' in x and
                                       u'Invalid username or password for %s. Check settings' or
                                       u'Failed to authenticate or parse a response from %s, abort provider'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}
        freeleech = (3, 0)[not self.freeleech]

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'info': 'detail', 'get': 'download', 'name': '_name'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string, void = self._title_and_url((
                    isinstance(search_string, unicode) and unidecode(search_string) or search_string, ''))
                void, search_url = self._title_and_url((
                    '', self.urls['search'] % (freeleech, self._categories_string(mode, 'cat=%s'), search_string)))

                # returns top 15 results by default, expandable in user profile to 100
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', class_='frame')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                if tr.find('img', alt='Nuked'):
                                    continue

                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in -2, -1, -4]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'], class_=rc['name'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, sep_date='|', **kwargs)


provider = FreshOnTVProvider()
