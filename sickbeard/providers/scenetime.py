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


class SceneTimeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneTime')

# https://www.scenetime.com/download.php/860856/Whose.Line.is.it.Anyway.US.S11E13.HDTV.x264-BAJSKORV.torrent
# Whose Line is it Anyway US S11E13 HDTV x264-BAJSKORV
        self.url_base = 'https://www.scenetime.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'takelogin.php',
                     'search': self.url_base + 'browse.php?%ssearch=%s',
                     'get': self.url_base + 'download.php/%(id)s/%(title)s.torrent'}

        self.categories = 'c2=1&c43=1&c9=1&c63=1&c77=1&c79=1&c101=1&cata=yes&'

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.minseed, self.minleech = 4 * [None]
        self.cache = SceneTimeCache(self)

    def _do_login(self):

        logged_in = lambda: 'uid' in self.session.cookies and 'pass' in self.session.cookies
        if logged_in():
            return True

        if self._check_auth():
            login_params = {'username': self.username, 'password': self.password, 'submit': 'Log in'}
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

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': '.*id=(\d+).*',
                                                             'cats': 'cat=(?:2|9|43|63|77|79|101)'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['search'] % (self.categories, search_string)
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('div', id='torrenttable').find('table')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers = [int(tr.find_all('td')[x].get_text().strip()) for x in (-2, -1)]
                                if None is tr.find('a', href=rc['cats'])\
                                        or ('Cache' != mode and (seeders < self.minseed or leechers < self.minleech)):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = 'title' in info.attrs and info.attrs['title'] or info.get_text().strip()

                                download_url = self.urls['get'] % {'id': re.sub(rc['get'], r'\1', str(info.attrs['href'])),
                                                                   'title': str(title).replace(' ', '.')}
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

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date)

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        return generic.TorrentProvider._get_episode_search_strings(self, ep_obj, add_string, use_or=False)


class SceneTimeCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 15  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = SceneTimeProvider()
