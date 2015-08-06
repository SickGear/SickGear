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
import datetime
import traceback

from . import generic
from sickbeard import logger, tvcache, helpers
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class GrabTheInfoProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'GrabTheInfo')

        self.url_base = 'http://grabthe.info/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'cache': self.url_base + 'browse.php?%s',
                     'search': '&search=%s',
                     'get': self.url_base + '%s'}

        self.categories = 'c56=1&c8=1&c61=1&c10=1&incldead=0&blah=0'

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.cache = GrabTheInfoCache(self)

    def _do_login(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'username': self.username, 'password': self.password}
            response = helpers.getURL(self.urls['login'], post_data=login_params, session=self.session)
            if response and logged_in():
                return True

            msg = u'Failed to authenticate with %s, abort provider'
            if response and 'Username or password incorrect' in response:
                msg = u'Invalid username or password for %s. Check settings'
            logger.log(msg % self.name, logger.ERROR)

        return False

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        if not self._do_login():
            return results

        items = {'Season': [], 'Episode': [], 'Cache': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['cache'] % self.categories
                if 'cache' != mode.lower():
                    search_url += self.urls['search'] % search_string
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

                                seeders, leechers = [int(tr.find_all('td')[x].get_text().strip()) for x in (-2, -1)]
                                if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                                    continue
                            except (AttributeError, TypeError, KeyError):
                                continue

                            if title:
                                items[mode].append((title, self.urls['get']
                                                    % str(download_url['href'].lstrip('/')), seeders))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_result(mode, len(items[mode]) - cnt, search_url)

            # for each search mode sort all the items by seeders
            'Cache' != mode and items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, sep_date='|', use_or=False)


class GrabTheInfoCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = GrabTheInfoProvider()
