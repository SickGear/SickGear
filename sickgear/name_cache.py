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

from collections import defaultdict
import threading

import sickgear
from . import db
from .helpers import full_sanitize_scene_name, try_int

from six import iteritems
from _23 import map_consume

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union
    from .tv import TVShow, TVShowBase

nameCache = {}
sceneNameCache = {}
nameCacheLock = threading.Lock()


def add_name_to_cache(name, tvid=0, prodid=0, season=-1):
    """Adds the show & tvdb id to the namecache

    :param name: the show name to cache
    :type name: AnyStr
    :param tvid: the tvinfo source id that this show should be cached with (can be None/0 for unknown)
    :type tvid: int
    :param prodid: the production id that this show should be cached with (can be None/0 for unknown)
    :type prodid: int or long
    :param season: the season the name exception belongs to. -1 for generic exception
    :type season: int
    """
    global nameCache

    with nameCacheLock:
        # standardize the name we're using to account for small differences in providers
        name = full_sanitize_scene_name(name)
        if name not in nameCache:
            nameCache[name] = [int(tvid), int(prodid), season]


def retrieve_name_from_cache(name):
    # type: (AnyStr) -> Union[Tuple[int, int], Tuple[None, None]]
    """Looks up the given name in the name cache

    :param name: The show name to look up.
    :return: the tuple of (tvid, prodid) id resulting from a cache lookup or None if the show wasn't found
    """
    global nameCache

    name = full_sanitize_scene_name(name)
    try:
        if name in nameCache:
            return int(nameCache[name][0]), int(nameCache[name][1])
    except (BaseException, Exception):
        pass
    return None, None


def build_name_cache(show_obj=None, update_only_scene=False):
    # type: (Optional[Union[TVShow, TVShowBase]], bool) -> None
    """Adds all new name exceptions to the namecache memory and flushes any removed name exceptions

    :param show_obj : Only update name cache for this show object, otherwise update all
    :param update_only_scene: (optional) only update scene name cache
    """
    global nameCache, sceneNameCache
    with nameCacheLock:

        if not update_only_scene:
            if show_obj:
                # search for only the requested show id and flush old show entries from namecache
                show_ids = {show_obj.tvid: [show_obj.prodid]}

                nameCache = dict([(k, v) for k, v in iteritems(nameCache)
                                  if not (v[0] == show_obj.tvid and v[1] == show_obj.prodid)])
                sceneNameCache = dict([(k, v) for k, v in iteritems(sceneNameCache)
                                       if not (v[0] == show_obj.tvid and v[1] == show_obj.prodid)])

                # add standard indexer name to namecache
                nameCache[full_sanitize_scene_name(show_obj.unique_name or show_obj.name)] = \
                    [show_obj.tvid, show_obj.prodid, -1]
            else:
                # generate list of production ids to look up in cache.db
                show_ids = defaultdict(list)
                map_consume(lambda _so: show_ids[_so.tvid].append(_so.prodid), sickgear.showList)

                # add all standard show indexer names to namecache
                nameCache = dict(
                    [(full_sanitize_scene_name(cur_so.unique_name or cur_so.name), [cur_so.tvid, cur_so.prodid, -1])
                     for cur_so in sickgear.showList if cur_so])
                sceneNameCache = {}

            tmp_scene_name_cache = sceneNameCache.copy()

        else:
            # generate list of production ids to look up in cache.db
            show_ids = defaultdict(list)
            map_consume(lambda _so: show_ids[_so.tvid].append(_so.prodid), sickgear.showList)

            tmp_scene_name_cache = {}

        cache_results = []
        cache_db = db.DBConnection()
        for cur_tvid, cur_prodid_list in iteritems(show_ids):
            cache_results += cache_db.select(
                f'SELECT show_name, indexer AS tv_id, indexer_id AS prod_id, season'
                f' FROM scene_exceptions'
                f' WHERE indexer = {cur_tvid} AND indexer_id IN ({",".join(map(str, cur_prodid_list))})')

        if cache_results:
            for cur_result in cache_results:
                tvid = int(cur_result['tv_id'])
                prodid = int(cur_result['prod_id'])
                season = try_int(cur_result['season'], -1)
                name = full_sanitize_scene_name(cur_result['show_name'])
                tmp_scene_name_cache[name] = [tvid, prodid, season]

            sceneNameCache = tmp_scene_name_cache.copy()


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
