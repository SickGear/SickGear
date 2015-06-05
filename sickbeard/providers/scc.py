# Author: Idan Gutman
# Modified by jkaberg, https://github.com/jkaberg for SceneAccess
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import re
import traceback
import datetime

import sickbeard
import generic
from sickbeard import logger, tvcache, db, classes, helpers, show_name_helpers
from sickbeard.common import Quality
from sickbeard.exceptions import ex
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import sanitizeSceneName
from lib import requests
from lib.requests import exceptions
from lib.unidecode import unidecode


class SCCProvider(generic.TorrentProvider):
    urls = {'base_url': 'https://sceneaccess.eu',
            'login': 'https://sceneaccess.eu/login',
            'detail': 'https://sceneaccess.eu/details?id=%s',
            'search': 'https://sceneaccess.eu/browse?search=%s&method=1&%s',
            'nonscene': 'https://sceneaccess.eu/nonscene?search=%s&method=1&c44=44&c45=44',
            'archive': 'https://sceneaccess.eu/archive?search=%s&method=1&c26=26',
            'download': 'https://sceneaccess.eu/%s'}

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneAccess', True, False)
        self.username = None
        self.password = None
        self.ratio = None
        self.minseed = None
        self.minleech = None
        self.cache = SCCCache(self)
        self.url = self.urls['base_url']
        self.categories = 'c27=27&c17=17&c11=11'

    def getQuality(self, item, anime=False):

        quality = Quality.sceneQuality(item[0], anime)
        return quality

    def _doLogin(self):

        login_params = {'username': self.username,
                        'password': self.password,
                        'submit': 'come on in'}

        self.session = requests.Session()

        try:
            response = self.session.post(self.urls['login'], data=login_params, headers=self.headers, timeout=30, verify=False)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            logger.log(u'Unable to connect to %s provider: %s' % (self.name, ex(e)), logger.ERROR)
            return False

        if re.search('Username or password incorrect', response.text) \
                or re.search('<title>SceneAccess \| Login</title>', response.text) \
                or 401 == response.status_code:
            logger.log(u'Your authentication credentials for %s are incorrect, check your config.' % self.name, logger.ERROR)
            return False

        return True

    def _get_season_search_strings(self, ep_obj):

        search_string = {'Season': []}
        if ep_obj.show.air_by_date or ep_obj.show.sports:
            ep_string = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.anime:
            ep_string = '%d' % ep_obj.scene_absolute_number
        else:
            ep_string = 'S%02d' % int(ep_obj.scene_season)  # 1) showName SXX

        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Season'].append('%s %s' % (show_name, ep_string))

        return [search_string]

    def _get_episode_search_strings(self, ep_obj, add_string=''):

        search_string = {'Episode': []}

        if not ep_obj:
            return []

        airdate = str(ep_obj.airdate).replace('-', '.')
        if self.show.air_by_date:
            ep_detail = airdate
        elif self.show.sports:
            ep_detail = '%s|%s' % (airdate, ep_obj.airdate.strftime('%b'))
        elif self.show.anime:
            ep_detail = ep_obj.scene_absolute_number
        else:
            ep_detail = sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                              'episodenumber': ep_obj.scene_episode}
        if add_string and not self.show.anime:
            ep_detail += ' ' + add_string

        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Episode'].append(re.sub('\s+', ' ', '%s %s' % (sanitizeSceneName(show_name), ep_detail)))

        return [search_string]

    def _isSection(self, section, text):
        title = '<title>.+? \| %s</title>' % section
        if re.search(title, text, re.IGNORECASE):
            return True
        else:
            return False

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin():
            return results

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string, url = self._get_title_and_url([search_string, self.urls['search'], '', '', ''])
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                nonsceneSearchURL = None
                if 'Season' == mode:
                    searchURL = self.urls['archive'] % search_string
                    response = [self.getURL(searchURL)]
                else:
                    searchURL = self.urls['search'] % (search_string, self.categories)
                    nonsceneSearchURL = self.urls['nonscene'] % search_string
                    response = [self.getURL(searchURL),
                                self.getURL(nonsceneSearchURL)]
                    logger.log(u'Search string: ' + nonsceneSearchURL, logger.DEBUG)

                logger.log(u'Search string: ' + searchURL, logger.DEBUG)

                response = [html for html in response if html is not None]
                if not len(response):
                    continue

                try:
                    for markup in response:
                        with BS4Parser(markup, features=['html5lib', 'permissive']) as soup:
                            torrent_table = soup.find('table', attrs={'id': 'torrents-table'})
                            torrent_rows = []
                            if torrent_table:
                                torrent_rows = torrent_table.find_all('tr')

                            # Continue only if at least one Release is found
                            if 2 > len(torrent_rows):
                                if soup.title:
                                    source = '%s (%s)' % (self.name, soup.title.string)
                                else:
                                    source = self.name
                                logger.log(u'The data returned from %s does not contain any torrents' % source, logger.DEBUG)
                                continue

                            for result in torrent_table.find_all('tr')[1:]:

                                try:
                                    link = result.find('td', attrs={'class': 'ttr_name'}).find('a')
                                    all_urls = result.find('td', attrs={'class': 'td_dl'}).find_all('a', limit=2)
                                    url = all_urls[0]

                                    title = link.string
                                    if re.search('\.\.\.', title):
                                        response = self.getURL(self.url + '/' + link['href'])
                                        if response:
                                            with BS4Parser(response) as soup_detail:
                                                title = re.search('(?<=").+(?<!")', soup_detail.title.string).group(0)
                                    download_url = self.urls['download'] % url['href']
                                    id = int(link['href'].replace('details?id=', ''))
                                    seeders = int(result.find('td', attrs={'class': 'ttr_seeders'}).string)
                                    leechers = int(result.find('td', attrs={'class': 'ttr_leechers'}).string)
                                except (AttributeError, TypeError):
                                    continue

                                if 'RSS' != mode and (self.minseed > seeders or self.minleech > leechers):
                                    continue

                                if not title or not download_url:
                                    continue

                                item = title, download_url, id, seeders, leechers

                                if self._isSection('Non-Scene', markup):
                                    logger.log(u'Found result: %s (%s)' % (title, nonsceneSearchURL), logger.DEBUG)
                                else:
                                    logger.log(u'Found result: %s (%s)' % (title, searchURL), logger.DEBUG)

                                items[mode].append(item)

                except Exception as e:
                    logger.log(u'Failed parsing %s Traceback: %s' % (self.name, traceback.format_exc()), logger.ERROR)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def _get_title_and_url(self, item):

        title, url, id, seeders, leechers = item

        if title:
            title += u''
            title = re.sub(r'\s+', '.', title)

        if url:
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
            showid, season, episode = (int(sqlshow['showid']), int(sqlshow['season']), int(sqlshow['episode']))
            self.show = helpers.findCertainShow(sickbeard.showList, showid)
            if not self.show:
                continue
            cur_ep = self.show.getEpisode(season, episode)

            for search in ['.proper.', '.repack.']:
                search_string = self._get_episode_search_strings(cur_ep, add_string=search)

                for item in self._doSearch(search_string[0]):
                    title, url = self._get_title_and_url(item)
                    results.append(classes.Proper(title, url, datetime.datetime.today(), self.show))

        return results

    def seedRatio(self):
        return self.ratio


class SCCCache(tvcache.TVCache):
    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll SCC every 10 minutes max
        self.minTime = 20

    def _getRSSData(self):
        search_params = {'RSS': ['']}
        return self.provider._doSearch(search_params)


provider = SCCProvider()
