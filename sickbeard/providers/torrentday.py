# Author: Mr_Orange <mr_orange@hotmail.it>
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

import sickbeard
import generic
from sickbeard.common import Quality
from sickbeard import logger, tvcache, db, classes, helpers, show_name_helpers
from sickbeard.exceptions import ex
from lib import requests
from lib.requests import exceptions
from sickbeard.helpers import sanitizeSceneName


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'TorrentDay', True, False)
        self.username = None
        self.password = None
        self._uid = None
        self._hash = None
        self.cookies = None

        self.minseed = None
        self.minleech = None
        self.freeleech = False
        self.ratio = None

        self.urls = {'base_url': 'https://torrentday.eu',
                     'login': 'https://torrentday.eu/torrents/',
                     'search': 'https://torrentday.eu/V3/API/API.php',
                     'download': 'https://torrentday.eu/download.php/%s/%s'}

        self.url = self.urls['base_url']

        self.categories = {'Season': {'c14': 1}, 'Episode': {'c2': 1, 'c26': 1, 'c7': 1, 'c24': 1},
                           'RSS': {'c2': 1, 'c26': 1, 'c7': 1, 'c24': 1, 'c14': 1}}

        self.cache = TorrentDayCache(self)

    def getQuality(self, item, anime=False):

        quality = Quality.sceneQuality(item[0], anime)
        return quality

    def _doLogin(self):

        if any(requests.utils.dict_from_cookiejar(self.session.cookies).values()):
            return True

        if self._uid and self._hash:

            requests.utils.add_dict_to_cookiejar(self.session.cookies, self.cookies)

        else:

            login_params = {'username': self.username, 'password': self.password, 'submit.x': 0, 'submit.y': 0}

            try:
                response = self.session.post(self.urls['login'], data=login_params, timeout=30, verify=False)
            except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                logger.log(u'Unable to connect to ' + self.name + ' provider: ' + ex(e), logger.ERROR)
                return False

            if re.search('You tried too often', response.text):
                logger.log(u'Too many login attempts for ' + self.name + ', can\'t retrive any data', logger.ERROR)
                return False

            if 401 == response.status_code:
                logger.log(u'Your authentication credentials for ' + self.name + ' are incorrect, check your config.', logger.ERROR)
                return False

            if requests.utils.dict_from_cookiejar(self.session.cookies)['uid'] and requests.utils.dict_from_cookiejar(self.session.cookies)['pass']:
                self._uid = requests.utils.dict_from_cookiejar(self.session.cookies)['uid']
                self._hash = requests.utils.dict_from_cookiejar(self.session.cookies)['pass']
                self.cookies = {'uid': self._uid, 'pass': self._hash}
                return True

            else:
                logger.log(u'Unable to obtain a cookie for TorrentDay', logger.ERROR)
                return False

    def _get_season_search_strings(self, ep_obj):

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            ep_string = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.anime:
            ep_string = '%d' % ep_obj.scene_absolute_number
        else:
            ep_string = 'S%02d' % int(ep_obj.scene_season)  # 1) showName SXX

        search_string = {'Season': []}
        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Season'].append('%s %s' % (show_name, ep_string))

        return [search_string]

    def _get_episode_search_strings(self, ep_obj, add_string=''):

        if not ep_obj:
            return []

        if self.show.air_by_date or self.show.sports:
            ep_detail = str(ep_obj.airdate).replace('-', '.')
            if self.show.sports:
                ep_detail += '|' + ep_obj.airdate.strftime('%b')
        elif self.show.anime:
            ep_detail = ep_obj.scene_absolute_number
        else:
            ep_detail = sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                              'episodenumber': ep_obj.scene_episode}

        if add_string and not self.show.anime:
            ep_detail += ' ' + add_string

        search_string = {'Episode': []}
        for show_name in set(show_name_helpers.allPossibleShowNames(self.show)):
            search_string['Episode'].append(re.sub('\s+', ' ', '%s %s' % (sanitizeSceneName(show_name), ep_detail)))

        return [search_string]

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin():
            return []

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                logger.log(u'Search string: ' + search_string, logger.DEBUG)

                search_string = '+'.join(search_string.split())

                post_data = dict({'/browse.php?': None, 'cata': 'yes', 'jxt': 8, 'jxw': 'b', 'search': search_string},
                                 **self.categories[mode])

                if self.freeleech:
                    post_data.update({'free': 'on'})

                data_json = self.getURL(self.urls['search'], post_data=post_data, json=True)
                if not data_json:
                    continue

                try:
                    torrents = data_json.get('Fs', [])[0].get('Cn', {}).get('torrents', [])
                except Exception:
                    continue

                for torrent in torrents:

                    seeders = int(torrent['seed'])
                    leechers = int(torrent['leech'])
                    if 'RSS' != mode and (seeders < self.minseed or leechers < self.minleech):
                        continue

                    title = re.sub(r'\[.*=.*\].*\[/.*\]', '', torrent['name'])
                    url = self.urls['download'] % (torrent['id'], torrent['fname'])
                    if title and url:
                        items[mode].append((title, url, seeders, leechers))

            results += items[mode]

        return results

    def _get_title_and_url(self, item):

        title, url = item[0], item[1]

        if title:
            title = u'' + title.replace(' ', '.')

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


class TorrentDayCache(tvcache.TVCache):
    def __init__(self, this_provider):

        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 10

    def _getRSSData(self):
        search_params = {'RSS': ['']}
        return self.provider._doSearch(search_params)


provider = TorrentDayProvider()
