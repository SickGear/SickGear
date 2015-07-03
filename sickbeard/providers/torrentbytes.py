# Author: Idan Gutman
# URL: http://code.google.com/p/sickbeard/
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
import datetime

import sickbeard
import generic
from sickbeard.common import Quality
from sickbeard import logger, tvcache, db, classes, helpers, show_name_helpers
from sickbeard.exceptions import ex
from lib import requests
from lib.requests import exceptions
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode
from sickbeard.helpers import sanitizeSceneName


class TorrentBytesProvider(generic.TorrentProvider):
    urls = {'base_url': 'https://www.torrentbytes.net',
            'login': 'https://www.torrentbytes.net/takelogin.php',
            'detail': 'https://www.torrentbytes.net/details.php?id=%s',
            'search': 'https://www.torrentbytes.net/browse.php?search=%s%s',
            'download': 'https://www.torrentbytes.net/download.php?id=%s&SSL=1&name=%s'}

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentBytes', True, False)
        self.username = None
        self.password = None
        self.ratio = None
        self.minseed = None
        self.minleech = None
        self.cache = TorrentBytesCache(self)
        self.url = self.urls['base_url']
        self.categories = '&c41=1&c33=1&c38=1&c32=1&c37=1'

    def getQuality(self, item, anime=False):

        quality = Quality.sceneQuality(item[0], anime)
        return quality

    def _doLogin(self):

        login_params = {'username': self.username,
                        'password': self.password,
                        'login': 'Log in!'}

        self.session = requests.Session()

        try:
            response = self.session.post(self.urls['login'], data=login_params, timeout=30, verify=False)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            logger.log(u'Unable to connect to ' + self.name + ' provider: ' + ex(e), logger.ERROR)
            return False

        if re.search('Username or password incorrect', response.text):
            logger.log(u'Your authentication credentials for ' + self.name + ' are incorrect, check your config.', logger.ERROR)
            return False

        return True

    def _get_season_search_strings(self, ep_obj):

        search_string = {'Season': []}
        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            if ep_obj.show.air_by_date or ep_obj.show.sports:
                ep_string = show_name + '.' + str(ep_obj.airdate).split('-')[0]
            elif ep_obj.show.anime:
                ep_string = show_name + '.' + '%d' % ep_obj.scene_absolute_number
            else:
                ep_string = show_name + '.S%02d' % int(ep_obj.scene_season)  # 1) showName SXX

            search_string['Season'].append(ep_string)

        return [search_string]

    def _get_episode_search_strings(self, ep_obj, add_string=''):

        search_string = {'Episode': []}

        if not ep_obj:
            return []

        if self.show.air_by_date:
            for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    str(ep_obj.airdate).replace('-', '|')
                search_string['Episode'].append(ep_string)
        elif self.show.sports:
            for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    str(ep_obj.airdate).replace('-', '|') + '|' + \
                    ep_obj.airdate.strftime('%b')
                search_string['Episode'].append(ep_string)
        elif self.show.anime:
            for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    '%i' % int(ep_obj.scene_absolute_number)
                search_string['Episode'].append(ep_string)
        else:
            for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) + ' ' + \
                    sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                          'episodenumber': ep_obj.scene_episode}

                search_string['Episode'].append(re.sub('\s+', ' ', ep_string))

        return [search_string]

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin():
            return []

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string, url = self._get_title_and_url([search_string, self.urls['search'], '', '', ''])
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                search_url = self.urls['search'] % (search_string, self.categories)

                logger.log(u'Search string: ' + search_url, logger.DEBUG)

                html = self.getURL(search_url)
                if not html:
                    continue

                try:
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'border': '1'})
                        torrent_rows = []
                        if torrent_table:
                            torrent_rows = torrent_table.find_all('tr')

                        # Continue only if one Release is found
                        if 2 > len(torrent_rows):
                            logger.log(u'The data returned from ' + self.name + ' does not contain any torrents',
                                       logger.DEBUG)
                            continue

                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')

                            link = cells[1].find('a', attrs={'class': 'index'})

                            full_id = link['href'].replace('details.php?id=', '')
                            torrent_id = full_id.split('&')[0]

                            try:
                                if 'title' in link:
                                    title = cells[1].find('a', {'class': 'index'})['title']
                                else:
                                    title = link.contents[0]
                                download_url = self.urls['download'] % (torrent_id, link.contents[0])
                                tid = int(torrent_id)
                                seeders = int(cells[8].find('span').contents[0])
                                leechers = int(cells[9].find('span').contents[0])
                            except (AttributeError, TypeError):
                                continue

                            # Filter unseeded torrent
                            if 'RSS' != mode and (seeders < self.minseed or leechers < self.minleech):
                                continue

                            if not title or not download_url:
                                continue

                            item = title, download_url, tid, seeders, leechers
                            logger.log(u'Found result: ' + title + '(' + search_url + ')', logger.DEBUG)

                            items[mode].append(item)

                except Exception:
                    logger.log(u'Failed parsing ' + self.name + ' Traceback: ' + traceback.format_exc(), logger.ERROR)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def _get_title_and_url(self, item):

        title, url, tid, seeders, leechers = item

        if title:
            title += u''
            title = re.sub(r'\s+', '.', title)
            title = title.replace(u'\xa0', '')

        if url:
            url = url.replace(u'\xa0', '')
            url = str(url).replace('&amp;', '&')

        return title, url

    def findPropers(self, search_date=datetime.datetime.today()):

        results = []

        my_db = db.DBConnection()
        sql_results = my_db.select(
            'SELECT s.show_name, e.showid, e.season, e.episode, e.status, e.airdate FROM tv_episodes AS e' +
            ' INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id)' +
            ' WHERE e.airdate >= ' + str(search_date.toordinal()) +
            ' AND (e.status IN (' + ','.join([str(x) for x in Quality.DOWNLOADED]) + ')' +
            ' OR (e.status IN (' + ','.join([str(x) for x in Quality.SNATCHED]) + ')))'
        )

        if not sql_results:
            return []

        for sqlshow in sql_results:
            self.show = helpers.findCertainShow(sickbeard.showList, int(sqlshow['showid']))
            if self.show:
                cur_ep = self.show.getEpisode(int(sqlshow['season']), int(sqlshow['episode']))

                search_string = self._get_episode_search_strings(cur_ep, add_string='PROPER|REPACK')

                for item in self._doSearch(search_string[0]):
                    title, url = self._get_title_and_url(item)
                    results.append(classes.Proper(title, url, datetime.datetime.today(), self.show))

        return results

    def seedRatio(self):
        return self.ratio


class TorrentBytesCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        search_params = {'RSS': ['']}
        return self.provider._doSearch(search_params)


provider = TorrentBytesProvider()
