# Author: Nic Wolfe <nic@wolfeden.ca>
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

from __future__ import with_statement

import time
import datetime
import sickbeard

from sickbeard import db
from sickbeard import logger
from sickbeard.common import Quality

from sickbeard import helpers, show_name_helpers
from sickbeard.exceptions import AuthException, ex
from name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard.rssfeeds import RSSFeeds
import itertools


class CacheDBConnection(db.DBConnection):
    def __init__(self, providerName):
        db.DBConnection.__init__(self, 'cache.db')

        # Create the table if it's not already there
        try:
            if not self.hasTable('lastUpdate'):
                self.action('CREATE TABLE lastUpdate (provider TEXT, time NUMERIC)')
        except Exception as e:
            if str(e) != 'table lastUpdate already exists':
                raise


class TVCache:
    def __init__(self, provider):

        self.provider = provider
        self.providerID = self.provider.get_id()
        self.providerDB = None
        self.update_freq = 10

    def get_db(self):
        return CacheDBConnection(self.providerID)

    def _clearCache(self):
        if self.should_clear_cache():
            myDB = self.get_db()
            myDB.action('DELETE FROM provider_cache WHERE provider = ?', [self.providerID])

    def _title_and_url(self, item):
        # override this in the provider if recent search has a different data layout to backlog searches
        return self.provider._title_and_url(item)

    def _cache_data(self):
        data = None
        return data

    def _checkAuth(self):
        return self.provider._check_auth()

    def _checkItemAuth(self, title, url):
        return True

    def updateCache(self):
        try:
            self._checkAuth()
        except AuthException as e:
            logger.log(u'Authentication error: ' + ex(e), logger.ERROR)
            return []

        if self.should_update():
            data = self._cache_data()

            # clear cache
            if data:
                self._clearCache()

            # parse data
            cl = []
            for item in data or []:
                title, url = self._title_and_url(item)
                ci = self._parseItem(title, url)
                if ci is not None:
                    cl.append(ci)

            if len(cl) > 0:
                myDB = self.get_db()
                myDB.mass_action(cl)

            # set updated as time the attempt to fetch data is
            self.setLastUpdate()

        return []

    def getRSSFeed(self, url, **kwargs):
        return RSSFeeds(self.provider).get_feed(url, **kwargs)

    def _translateTitle(self, title):
        return u'' + title.replace(' ', '.')

    def _translateLinkURL(self, url):
        return url.replace('&amp;', '&')

    def _parseItem(self, title, url):

        self._checkItemAuth(title, url)

        if title and url:
            title = self._translateTitle(title)
            url = self._translateLinkURL(url)

            logger.log(u'Attempting to add item to cache: ' + title, logger.DEBUG)
            return self.add_cache_entry(title, url)

        else:
            logger.log(
                u'The data returned from the ' + self.provider.name + ' feed is incomplete, this result is unusable',
                logger.DEBUG)
            return None

    def _getLastUpdate(self):
        myDB = self.get_db()
        sqlResults = myDB.select('SELECT time FROM lastUpdate WHERE provider = ?', [self.providerID])

        if sqlResults:
            lastTime = int(sqlResults[0]['time'])
            if lastTime > int(time.mktime(datetime.datetime.today().timetuple())):
                lastTime = 0
        else:
            lastTime = 0

        return datetime.datetime.fromtimestamp(lastTime)

    def _getLastSearch(self):
        myDB = self.get_db()
        sqlResults = myDB.select('SELECT time FROM lastSearch WHERE provider = ?', [self.providerID])

        if sqlResults:
            lastTime = int(sqlResults[0]['time'])
            if lastTime > int(time.mktime(datetime.datetime.today().timetuple())):
                lastTime = 0
        else:
            lastTime = 0

        return datetime.datetime.fromtimestamp(lastTime)

    def setLastUpdate(self, toDate=None):
        if not toDate:
            toDate = datetime.datetime.today()

        myDB = self.get_db()
        myDB.upsert('lastUpdate',
                    {'time': int(time.mktime(toDate.timetuple()))},
                    {'provider': self.providerID})

    def setLastSearch(self, toDate=None):
        if not toDate:
            toDate = datetime.datetime.today()

        myDB = self.get_db()
        myDB.upsert('lastSearch',
                    {'time': int(time.mktime(toDate.timetuple()))},
                    {'provider': self.providerID})

    lastUpdate = property(_getLastUpdate)
    lastSearch = property(_getLastSearch)

    def should_update(self):
        # if we've updated recently then skip the update
        return datetime.datetime.today() - self.lastUpdate >= datetime.timedelta(minutes=self.update_freq)

    def should_clear_cache(self):
        # if recent search hasn't used our previous results yet then don't clear the cache
        return self.lastSearch >= self.lastUpdate

    def add_cache_entry(self, name, url, parse_result=None, indexer_id=0):

        # check if we passed in a parsed result or should we try and create one
        if not parse_result:

            # create showObj from indexer_id if available
            showObj=None
            if indexer_id:
                showObj = helpers.findCertainShow(sickbeard.showList, indexer_id)

            try:
                np = NameParser(showObj=showObj, convert=True)
                parse_result = np.parse(name)
            except InvalidNameException:
                logger.log(u'Unable to parse the filename ' + name + ' into a valid episode', logger.DEBUG)
                return None
            except InvalidShowException:
                logger.log(u'No show in the db matches filename ' + name + ' not cached', logger.DEBUG)
                return None

            if not parse_result or not parse_result.series_name:
                return None

        # if we made it this far then lets add the parsed result to cache for usager later on
        season = parse_result.season_number if parse_result.season_number else 1
        episodes = parse_result.episode_numbers

        if season and episodes:
            # store episodes as a seperated string
            episodeText = '|' + '|'.join(map(str, episodes)) + '|'

            # get the current timestamp
            curTimestamp = int(time.mktime(datetime.datetime.today().timetuple()))

            # get quality of release
            quality = parse_result.quality

            if not isinstance(name, unicode):
                name = unicode(name, 'utf-8', 'replace')

            # get release group
            release_group = parse_result.release_group

            # get version
            version = parse_result.version

            logger.log(u'Added RSS item: [' + name + '] to cache: [' + self.providerID + ']', logger.DEBUG)

            return [
                'INSERT OR IGNORE INTO provider_cache (provider, name, season, episodes, indexerid, url, time, quality, release_group, version) VALUES (?,?,?,?,?,?,?,?,?,?)',
                [self.providerID, name, season, episodeText, parse_result.show.indexerid, url, curTimestamp, quality, release_group, version]]

    def searchCache(self, episode, manualSearch=False):
        neededEps = self.findNeededEpisodes(episode, manualSearch)
        if len(neededEps) > 0:
            return neededEps[episode]
        else:
            return []

    def listPropers(self, date=None):
        myDB = self.get_db()
        sql = "SELECT * FROM provider_cache WHERE name LIKE '%.PROPER.%' OR name LIKE '%.REPACK.%' AND provider = ?"

        if date:
            sql += ' AND time >= ' + str(int(time.mktime(date.timetuple())))

        return filter(lambda x: x['indexerid'] != 0, myDB.select(sql, [self.providerID]))

    def findNeededEpisodes(self, episode, manualSearch=False):
        neededEps = {}
        cl = []

        myDB = self.get_db()
        if type(episode) != list:
            sqlResults = myDB.select(
                'SELECT * FROM provider_cache WHERE provider = ? AND indexerid = ? AND season = ? AND episodes LIKE ?',
                [self.providerID, episode.show.indexerid, episode.season, '%|' + str(episode.episode) + '|%'])
        else:
            for epObj in episode:
                cl.append([
                    'SELECT * FROM provider_cache WHERE provider = ? AND indexerid = ? AND season = ?'
                    + ' AND episodes LIKE ? AND quality IN (' + ','.join([str(x) for x in epObj.wantedQuality]) + ')',
                    [self.providerID, epObj.show.indexerid, epObj.season, '%|' + str(epObj.episode) + '|%']])
            sqlResults = myDB.mass_action(cl)
            if sqlResults:
                sqlResults = list(itertools.chain(*sqlResults))

        if not sqlResults:
            self.setLastSearch()
            return neededEps

        # for each cache entry
        for curResult in sqlResults:

            # skip non-tv crap
            if not show_name_helpers.pass_wordlist_checks(curResult['name'], parse=False):
                continue

            # get the show object, or if it's not one of our shows then ignore it
            showObj = helpers.findCertainShow(sickbeard.showList, int(curResult['indexerid']))
            if not showObj:
                continue

            # skip if provider is anime only and show is not anime
            if self.provider.anime_only and not showObj.is_anime:
                logger.log(u'' + str(showObj.name) + ' is not an anime, skipping', logger.DEBUG)
                continue

            # get season and ep data (ignoring multi-eps for now)
            curSeason = int(curResult['season'])
            if curSeason == -1:
                continue
            curEp = curResult['episodes'].split('|')[1]
            if not curEp:
                continue
            curEp = int(curEp)

            curQuality = int(curResult['quality'])
            curReleaseGroup = curResult['release_group']
            curVersion = curResult['version']

            # if the show says we want that episode then add it to the list
            if not showObj.wantEpisode(curSeason, curEp, curQuality, manualSearch):
                logger.log(u'Skipping ' + curResult['name'] + ' because we don\'t want an episode that\'s ' +
                           Quality.qualityStrings[curQuality], logger.DEBUG)
                continue

            epObj = showObj.getEpisode(curSeason, curEp)

            # build a result object
            title = curResult['name']
            url = curResult['url']

            logger.log(u'Found result ' + title + ' at ' + url)

            result = self.provider.get_result([epObj], url)
            if None is result:
                continue
            result.show = showObj
            result.name = title
            result.quality = curQuality
            result.release_group = curReleaseGroup
            result.version = curVersion
            result.content = None

            # add it to the list
            if epObj not in neededEps:
                neededEps[epObj] = [result]
            else:
                neededEps[epObj].append(result)

        # datetime stamp this search so cache gets cleared
        self.setLastSearch()

        return neededEps
