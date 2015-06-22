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
import datetime
import traceback

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class FreshOnTVProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'FreshOnTV')

        self.url_base = 'https://freshon.tv/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'login.php?action=makelogin',
                     'search': self.url_base + 'browse.php?incldead=%s&words=0&cat=0&search=%s',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.freeleech = False
        self.cache = FreshOnTVCache(self)

    def _doLogin(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._checkAuth():
            login_params = {'username': self.username, 'password': self.password, 'login': 'Do it!'}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            msg = u'Failed to authenticate with %s, abort provider'
            if response:
                if 'Username does not exist in the userbase or the account is not confirmed' in response:
                    msg = u'Invalid username or password for %s, check your config'
                if 'DDoS protection by CloudFlare' in response:
                    msg = u'Unable to login to %s due to CloudFlare DDoS javascript check'
            logger.log(msg % self.name, logger.ERROR)

        return False

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._doLogin():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}
        freeleech = '3' if self.freeleech else '0'

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'info': 'detail', 'get': 'download', 'name': '_name'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string, url = self._get_title_and_url((search_string, self.urls['search']))
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                # returns top 15 results by default, expandable in user profile to 100
                search_url = self.urls['search'] % (freeleech, search_string)
                html = self.getURL(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'frame'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                if tr.find('img', alt='Nuked'):
                                    continue

                                seeders, leechers = [int(tr.find_all('td')[x].get_text().strip()) for x in (-2, -1)]
                                if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                                    continue

                                info = tr.find('a', href=rc['info'], attrs={'class': rc['name']})
                                title = 'title' in info.attrs and info.attrs['title'] or info.get_text().strip()

                                download_url = self.urls['get'] % str(tr.find('a', href=rc['get'])['href']).lstrip('/')
                            except (AttributeError, TypeError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_result(mode, len(items[mode]) - cnt, search_url)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def findPropers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, sep_date='|', use_or=False)


class FreshOnTVCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = FreshOnTVProvider()
