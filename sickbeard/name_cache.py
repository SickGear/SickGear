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
from . import db
from .helpers import try_int

from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union
    from .tv import TVShow, TVShowBase

nameCache = {}
nameCacheLock = threading.Lock()


def addNameToCache(name, tvid=0, prodid=0, season=-1):
    """Adds the show & tvdb id to the namecache

    :param name: the show name to cache
    :type name: AnyStr
    :param tvid: the tvinfo source id that this show should be cached with (can be None/0 for unknown)
    :type tvid: int
    :param prodid: the production id that this show should be cached with (can be None/0 for unknown)
    :type prodid: int or long
    :param season: the season the the name exception belongs to. -1 for generic exception
    :type season: int
    """
    global nameCache

    with nameCacheLock:
        # standardize the name we're using to account for small differences in providers
        name = sickbeard.helpers.full_sanitize_scene_name(name)
        if name not in nameCache:
            nameCache[name] = [int(tvid), int(prodid), season]


def retrieveNameFromCache(name):
    # type: (AnyStr) -> Union[Tuple[int, int], Tuple[None, None]]
    """Looks up the given name in the name cache

    :param name: The show name to look up.
    :return: the tuple of (tvid, prodid) id resulting from a cache lookup or None if the show wasn't found
    """
    global nameCache

    name = sickbeard.helpers.full_sanitize_scene_name(name)
    try:
        if name in nameCache:
            return int(nameCache[name][0]), int(nameCache[name][1])
    except (BaseException, Exception):
        pass
    return None, None


def buildNameCache(show_obj=None):
    # type: (Optional[Union[TVShow, TVShowBase]]) -> None
    """Adds all new name exceptions to the namecache memory and flushes any removed name exceptions

    :param show_obj : Only update name cache for this show object, otherwise update all
    """
    global nameCache
    with nameCacheLock:

        if show_obj:
            # search for only the requested show id and flush old show entries from namecache
            show_ids = {show_obj.tvid: [show_obj.prodid]}
            nameCache = dict([(k, v) for k, v in iteritems(nameCache)
                              if not (v[0] == show_obj.tvid and v[1] == show_obj.prodid)])

            # add standard indexer name to namecache
            nameCache[sickbeard.helpers.full_sanitize_scene_name(show_obj.name)] = [show_obj.tvid, show_obj.prodid, -1]
        else:
            # generate list of production ids to look up in cache.db
            show_ids = {}
            for cur_show_obj in sickbeard.showList:
                show_ids.setdefault(cur_show_obj.tvid, []).append(cur_show_obj.prodid)

            # add all standard show indexer names to namecache
            nameCache = dict(
                [(sickbeard.helpers.full_sanitize_scene_name(cur_so.name), [cur_so.tvid, cur_so.prodid, -1])
                 for cur_so in sickbeard.showList if cur_so])

        cacheDB = db.DBConnection()

        cache_results = []
        for t, s in iteritems(show_ids):
            cache_results += cacheDB.select(
                'SELECT show_name, indexer AS tv_id, indexer_id AS prod_id, season'
                ' FROM scene_exceptions'
                ' WHERE indexer = %s AND indexer_id IN (%s)' % (t, ','.join(['%s' % i for i in s])))

        if cache_results:
            for cache_result in cache_results:
                tvid = int(cache_result['tv_id'])
                prodid = int(cache_result['prod_id'])
                season = try_int(cache_result['season'], -1)
                name = sickbeard.helpers.full_sanitize_scene_name(cache_result['show_name'])
                nameCache[name] = [tvid, prodid, season]


def remove_from_namecache(tvid, prodid):
    """Deletes all entries from the namecache for a particular show

    :param tvid: TV info source to be removed from the namecache
    :type tvid: int
    :param prodid: tvdbid or rageid to be removed from the namecache
    :type prodid: int or long
    """
    global nameCache

    with nameCacheLock:
        if nameCache:
            nameCache = dict([(k, v) for k, v in iteritems(nameCache) if not (v[0] == tvid and v[1] == prodid)])
