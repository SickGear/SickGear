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
import threading
import sickbeard
from sickbeard import db

nameCache = {}
nameCacheLock = threading.Lock()


def addNameToCache(name, indexer_id=0, season=-1):
    """Adds the show & tvdb id to the namecache

    :param name: the show name to cache
    :param indexer_id: the TVDB and TVRAGE id that this show should be cached with (can be None/0 for unknown)
    :param season: the season the the name exception belongs to. -1 for generic exception
    """
    global nameCache

    # standardize the name we're using to account for small differences in providers
    name = sickbeard.helpers.full_sanitizeSceneName(name)
    if name not in nameCache:
        nameCache[name] = [int(indexer_id), season]


def retrieveNameFromCache(name):
    """Looks up the given name in the name cache

    :param name: The show name to look up.
    :return: the TVDB and TVRAGE id that resulted from the cache lookup or None if the show wasn't found in the cache
    """
    global nameCache

    name = sickbeard.helpers.full_sanitizeSceneName(name)
    if name in nameCache:
        return int(nameCache[name][0])


def buildNameCache(show=None):
    """Adds all new name exceptions to the namecache memory and flushes any removed name exceptions

    :param show (optional): Only update namecache for this show object
    """
    global nameCache
    with nameCacheLock:

        if show:
            # search for only the requested show id and flush old show entries from namecache
            indexer_ids = [show.indexerid]
            nameCache = dict((k, v) for k, v in nameCache.items() if v != show.indexerid)

            # add standard indexer name to namecache
            nameCache[sickbeard.helpers.full_sanitizeSceneName(show.name)] = [show.indexerid, -1]
        else:
            # generate list of indexer ids to look up in cache.db
            indexer_ids = [x.indexerid for x in sickbeard.showList if x]

            # add all standard show indexer names to namecache
            nameCache = dict(
                (sickbeard.helpers.full_sanitizeSceneName(x.name), [x.indexerid, -1]) for x in sickbeard.showList if x)

        cacheDB = db.DBConnection()

        cache_results = cacheDB.select(
            'SELECT show_name, indexer_id, season FROM scene_exceptions WHERE indexer_id IN (%s)' % ','.join(
                ['?'] * len(indexer_ids)), indexer_ids)

        if cache_results:
            for cache_result in cache_results:
                indexer_id = int(cache_result['indexer_id'])
                season = int(cache_result['season'])
                name = sickbeard.helpers.full_sanitizeSceneName(cache_result['show_name'])
                nameCache[name] = [indexer_id, season]


def remove_from_namecache(indexer_id):
    """Deletes all entries from the namecache for a particular show

    :param indexer_id: tvdbid or rageid to be removed from the namecache
    """
    global nameCache

    if nameCache:
        nameCache = dict((k, v) for k, v in nameCache.items() if v != indexer_id)