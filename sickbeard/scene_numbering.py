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
#
# Created on Sep 20, 2012
# @author: Dermot Buckley <dermot@buckley.ie>
# @copyright: Dermot Buckley
#

import datetime
import traceback
from sqlite3 import Row

from exceptions_helper import ex


import sickbeard
from . import db, logger
from .helpers import try_int
from .scene_exceptions import xem_ids_list
from .sgdatetime import timestamp_near

from _23 import filter_iter, map_list

# noinspection PyUnreachableCode
if False:
    from typing import Dict, Tuple


def get_scene_numbering(tvid, prodid, season, episode, fallback_to_xem=True, show_obj=None, **kwargs):
    """
    Returns a tuple, (season, episode), with the scene numbering (if there is one),
    otherwise returns the xem numbering (if fallback_to_xem is set), otherwise
    returns the TVDB numbering.
    (so the return values will always be set)

    kwargs['scene_result']: type: Optional[List[Row]] passed thru
    kwargs['show_result']: type: Optional[List[Row]] passed thru

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param season:
    :type season: int
    :param episode:
    :type episode: int
    :param fallback_to_xem: If set (the default), check xem for matches if there is no local scene numbering
    :type fallback_to_xem: bool
    :param show_obj:
    :type show_obj:
    :return: (int, int) a tuple with (season, episode)
    :rtype: Tuple[int, int]
    """
    if None is prodid or None is season or None is episode:
        return season, episode

    tvid, prodid = int(tvid), int(prodid)
    if None is show_obj:
        show_obj = sickbeard.helpers.find_show_by_id({tvid: prodid})
    if show_obj and not show_obj.is_scene:
        return season, episode

    result = find_scene_numbering(tvid, prodid, season, episode, scene_result=kwargs.get('scene_result'))
    if result:
        return result
    else:
        if fallback_to_xem:
            xem_result = find_xem_numbering(tvid, prodid, season, episode, show_result=kwargs.get('show_result'))
            if xem_result:
                return xem_result
        return season, episode


def find_scene_numbering(tvid, prodid, season, episode, scene_result=None):
    """
    Same as get_scene_numbering(), but returns None if scene numbering is not set
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param season: season number
    :type season: int
    :param episode: episode number
    :type episode: int
    :param scene_result:
    :type scene_result:
    :return:
    :rtype: Tuple[int, int] or None
    """
    if None is prodid or None is season or None is episode:
        return

    tvid, prodid = int(tvid), int(prodid)

    sql_result = None
    if None is not scene_result:
        for cur_row in scene_result:
            if cur_row['season'] == season and cur_row['episode'] == episode:
                if cur_row['scene_season'] or cur_row['scene_episode']:
                    sql_result = [cur_row]
                break
    else:
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT scene_season, scene_episode
            FROM scene_numbering
            WHERE indexer = ? AND indexer_id = ? AND season = ? AND episode = ? AND (scene_season OR scene_episode) != 0
            """, [tvid, prodid, season, episode])

    if sql_result:
        s_s, s_e = try_int(sql_result[0]['scene_season'], None), try_int(sql_result[0]['scene_episode'], None)
        if None is not s_s and None is not s_e:
            return s_s, s_e


def get_scene_absolute_numbering(tvid, prodid, absolute_number, season, episode, fallback_to_xem=True,
                                 show_obj=None, **kwargs):
    """
    Returns a tuple, (season, episode), with the scene numbering (if there is one),
    otherwise returns the xem numbering (if fallback_to_xem is set), otherwise
    returns the TVDB numbering.
    (so the return values will always be set)

    kwargs['scene_result']: type: Optional[List[Row]] passed thru
    kwargs['show_result']: type: Optional[List[Row]] passed thru

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param absolute_number: absolute number
    :type absolute_number: int
    :param season: season number
    :type season: int
    :param episode: episode number
    :type episode: int
    :param fallback_to_xem: fallback_to_xem: bool If set (the default), check xem for matches if there is no
    local scene numbering
    :type fallback_to_xem: bool
    :param show_obj:
    :type show_obj:
    :return: (int, int) a tuple with (season, episode)
    :rtype: Tuple[int, int] or None
    """
    has_sxe = None is not season and None is not episode
    if None is prodid or (None is absolute_number and not has_sxe):
        return absolute_number

    tvid, prodid = int(tvid), int(prodid)

    if None is show_obj:
        show_obj = sickbeard.helpers.find_show_by_id({tvid: prodid})
    if show_obj and not show_obj.is_scene and not has_sxe:
        return absolute_number

    result = find_scene_absolute_numbering(tvid, prodid, absolute_number, season, episode,
                                           scene_result=kwargs.get('scene_result'))
    if result:
        return result

    if fallback_to_xem:
        xem_result = find_xem_absolute_numbering(tvid, prodid, absolute_number, season, episode,
                                                 show_result=kwargs.get('show_result'))
        if xem_result:
            return xem_result
    return absolute_number


def find_scene_absolute_numbering(tvid, prodid, absolute_number, season=None, episode=None, scene_result=None):
    """
    Same as get_scene_numbering(), but returns None if scene numbering is not set

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int or long
    :param absolute_number:
    :type absolute_number: int
    :param season:
    :type season: int
    :param episode:
    :type episode: int
    :param scene_result:
    :type scene_result:
    :return:
    :rtype: None or int
    """
    has_sxe = None is not season and None is not episode
    if None is prodid or (None is absolute_number and not has_sxe):
        return

    tvid, prodid = int(tvid), int(prodid)

    sql_result = None
    if None is not scene_result:
        for cur_row in scene_result:
            if cur_row['season'] == season and cur_row['episode'] == episode:
                if cur_row['scene_absolute_number']:
                    sql_result = [cur_row]
                break
    else:
        my_db = db.DBConnection()
        sql_vars, cond = (([absolute_number], 'absolute_number = ?'),
                          ([season, episode], 'season = ? AND episode = ?'))[has_sxe]
        sql_result = my_db.select(
            """
            SELECT scene_absolute_number
            FROM scene_numbering
            WHERE indexer = ? AND indexer_id = ? AND %s AND scene_absolute_number != 0
            """ % cond, [tvid, prodid] + sql_vars)

    if sql_result:
        return try_int(sql_result[0]['scene_absolute_number'], None)


def get_indexer_numbering(tvid, prodid, scene_season, scene_episode, fallback_to_xem=True):
    """

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param scene_season: scene season
    :type scene_season: int
    :param scene_episode: scene episode
    :type scene_episode: int
    :param fallback_to_xem:
    :type fallback_to_xem: bool
    :return: a tuple, (season, episode) with the TVDB numbering for (sceneSeason, sceneEpisode)
    (this works like the reverse of get_scene_numbering)
    :rtype: Tuple[int, int]
    """
    if None is prodid or None is scene_season or None is scene_episode:
        return scene_season, scene_episode

    tvid, prodid = int(tvid), int(prodid)

    my_db = db.DBConnection()
    sql_result = my_db.select(
        """
        SELECT season, episode
        FROM scene_numbering
        WHERE indexer = ? AND indexer_id = ? AND scene_season = ? AND scene_episode = ?
        """, [tvid, prodid, scene_season, scene_episode])

    if sql_result:
        ss, se = try_int(sql_result[0]['season'], None), try_int(sql_result[0]['episode'], None)
        if None is not ss and None is not se:
            return ss, se
    if fallback_to_xem:
        return get_indexer_numbering_for_xem(tvid, prodid, scene_season, scene_episode)
    return scene_season, scene_episode


def get_indexer_absolute_numbering(tvid, prodid, scene_absolute_number, fallback_to_xem=True, scene_season=None):
    """
    Returns a tuple, (season, episode, absolute_number) with the TVDB numbering for (sceneAbsoluteNumber)
    (this works like the reverse of get_absolute_numbering)
    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int or long
    :param scene_absolute_number:
    :type scene_absolute_number: int
    :param fallback_to_xem:
    :type fallback_to_xem: bool
    :param scene_season:
    :type scene_season: int
    :return:
    :rtype: int
    """
    if None is prodid or None is scene_absolute_number:
        return scene_absolute_number

    tvid, prodid = int(tvid), int(prodid)

    my_db = db.DBConnection()

    sql = """
    SELECT absolute_number
    FROM scene_numbering
    WHERE indexer = ? AND indexer_id = ? AND scene_absolute_number = ?
    """
    params = [tvid, prodid, scene_absolute_number]
    if None is not scene_season:
        sql += ' AND scene_season = ?'
        params += [scene_season]

    for cur_row in (my_db.select(sql, params) or []):
        an = try_int(cur_row['absolute_number'], None)
        if None is not an:
            return an
    if fallback_to_xem:
        return get_indexer_absolute_numbering_for_xem(tvid, prodid, scene_absolute_number, scene_season)
    return scene_absolute_number


def set_scene_numbering(tvid=None, prodid=None, season=None, episode=None, absolute_number=None,
                        scene_season=None, scene_episode=None, scene_absolute=None, anime=False):
    """
    Set scene numbering for a season/episode.
    To clear the scene numbering, leave both sceneSeason and sceneEpisode as None.

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param season:
    :type season: int
    :param episode:
    :type episode: int
    :param absolute_number:
    :type absolute_number: int
    :param scene_season:
    :type scene_season: int
    :param scene_episode:
    :type scene_episode: int
    :param scene_absolute:
    :type scene_absolute: int
    :param anime:
    :type anime: bool
    """
    if None is tvid or None is prodid:
        return

    my_db = db.DBConnection()
    if None is not season and None is not episode:
        my_db.action(
            """
            INSERT OR IGNORE INTO scene_numbering
            (indexer, indexer_id, season, episode) VALUES (?,?,?,?)
            """, [tvid, prodid, season, episode])

        # sxe replaced abs_num as key, migrate data with only abs
        _, _, ep_absolute_number = _get_sea(tvid, prodid, season, episode)
        sql_result = my_db.select(
            """
            SELECT scene_season, scene_episode, scene_absolute_number
            FROM scene_numbering
            WHERE indexer = ? AND indexer_id = ? AND season IS NULL AND episode IS NULL AND absolute_number = ?
            """, [tvid, prodid, ep_absolute_number])

        if not len(sql_result):
            update, values = (('scene_absolute_number = ?', [scene_absolute]),
                              ('scene_season = ?, scene_episode = ?', [scene_season, scene_episode]))[not anime]
        else:
            for cur_row in sql_result:
                scene_season = scene_season or cur_row['scene_season']
                scene_episode = scene_episode or cur_row['scene_episode']
                scene_absolute = scene_absolute or cur_row['scene_absolute_number']

            update, values = ('scene_season = ?, scene_episode = ?, scene_absolute_number = ?',
                              [scene_season, scene_episode, scene_absolute])
        my_db.action(
            """
            UPDATE scene_numbering
            SET %s
            WHERE indexer = ? AND indexer_id = ?
            AND season = ? AND episode = ?
            """ % update, values + [tvid, prodid, season, episode])

        my_db.action(
            """
            DELETE
            FROM scene_numbering
            WHERE indexer = ? AND indexer_id = ? 
            AND ((absolute_number = ? OR (season = ? AND episode = ?))
                AND scene_season IS NULL AND scene_episode IS NULL AND scene_absolute_number IS NULL)
            """, [tvid, prodid, ep_absolute_number, season, episode])

    elif absolute_number:
        my_db.action(
            """
            INSERT OR IGNORE INTO scene_numbering
            (indexer, indexer_id, absolute_number) VALUES (?,?,?)
            """, [tvid, prodid, absolute_number])

        my_db.action(
            """
            UPDATE scene_numbering
            SET scene_absolute_number = ?
            WHERE indexer = ? AND indexer_id = ? AND absolute_number = ?
            """, [scene_absolute, tvid, prodid, absolute_number])


def find_xem_numbering(tvid, prodid, season, episode, show_result=None):
    """
    Returns the scene numbering, as retrieved from xem.
    Refreshes/Loads as needed.

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param season:
    :type season: int
    :param episode:
    :type episode: int
    :param show_result:
    :type show_result:
    :return:
    :rtype: (int, int) a tuple of scene_season, scene_episode, or None if there is no special mapping.
    """
    if None is prodid or None is season or None is episode:
        return season, episode

    tvid, prodid = int(tvid), int(prodid)

    xem_refresh(tvid, prodid)

    sql_result = None
    if None is not show_result:
        if isinstance(show_result, Row) and (season, episode) == (show_result['season'], show_result['episode']) \
                and (show_result['scene_season'] or show_result['scene_episode']):
            sql_result = [show_result]
    else:
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT scene_season, scene_episode
            FROM tv_episodes
            WHERE indexer = ? AND showid = ? AND season = ? AND episode = ? AND (scene_season OR scene_episode) != 0
            """, [tvid, prodid, season, episode])

    if sql_result:
        s_s, s_e = try_int(sql_result[0]['scene_season'], None), try_int(sql_result[0]['scene_episode'], None)
        if None is not s_s and None is not s_e:
            return s_s, s_e


def find_xem_absolute_numbering(tvid, prodid, absolute_number, season, episode, show_result=None):
    """
    Returns the scene numbering, as retrieved from xem.
    Refreshes/Loads as needed.

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param absolute_number:
    :type absolute_number: int
    :param season:
    :type season: int
    :param episode:
    :type episode: int
    :param show_result:
    :type show_result:
    :return:
    :rtype: int
    """
    if None is prodid or None is absolute_number:
        return absolute_number

    tvid, prodid = int(tvid), int(prodid)

    xem_refresh(tvid, prodid)

    sql_result = None
    if None is not show_result:
        if isinstance(show_result, Row) and (season, episode) == (show_result['season'], show_result['episode']) \
                and show_result['scene_absolute_number']:
            sql_result = [show_result]
    else:
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT scene_absolute_number
            FROM tv_episodes
            WHERE indexer = ? AND showid = ? AND season = ? AND episode = ? AND scene_absolute_number != 0
            """, [tvid, prodid, season, episode])

    if sql_result:
        return try_int(sql_result[0]['scene_absolute_number'], None)


def get_indexer_numbering_for_xem(tvid, prodid, scene_season, scene_episode):
    """
    Reverse of find_xem_numbering: lookup a tvdb season and episode using scene numbering

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param scene_season:
    :type scene_season: int
    :param scene_episode:
    :type scene_episode: int
    :return:
    :rtype: (int, int) a tuple of (season, episode)
    """
    if None is prodid or None is scene_season or None is scene_episode:
        return scene_season, scene_episode

    tvid, prodid = int(tvid), int(prodid)

    xem_refresh(tvid, prodid)

    my_db = db.DBConnection()
    sql_result = my_db.select(
        """
        SELECT season, episode
        FROM tv_episodes
        WHERE indexer = ? AND showid = ? AND scene_season = ? AND scene_episode = ?
        """, [tvid, prodid, scene_season, scene_episode])

    for cur_row in (sql_result or []):
        ss, se = try_int(cur_row['season'], None), try_int(cur_row['episode'], None)
        if None is not ss and None is not se:
            return ss, se
        break

    return scene_season, scene_episode


def get_indexer_absolute_numbering_for_xem(tvid, prodid, scene_absolute_number, scene_season=None):
    """
    Reverse of find_xem_numbering: lookup a tvdb season and episode using scene numbering

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param scene_absolute_number:
    :type scene_absolute_number: int
    :param scene_season:
    :type scene_season: int
    :return:
    :rtype: int
    """
    if None is prodid or None is scene_absolute_number:
        return scene_absolute_number

    tvid, prodid = int(tvid), int(prodid)

    xem_refresh(tvid, prodid)

    my_db = db.DBConnection()
    sql = """
    SELECT absolute_number
    FROM tv_episodes
    WHERE indexer = ? AND showid = ? AND scene_absolute_number = ?
    """
    params = [tvid, prodid, scene_absolute_number]
    if None is not scene_season:
        sql += ' AND scene_season = ?'
        params += [scene_season]

    for cur_row in (my_db.select(sql, params) or []):
        an = try_int(cur_row['absolute_number'], None)
        if None is not an:
            return an
        break

    return scene_absolute_number


def get_scene_numbering_for_show(tvid, prodid):
    """
    Returns a dict of (season, episode) : (scene_season, scene_episode) mappings
    for an entire show.  Both the keys and values of the dict are tuples.
    Will be empty if no scene numbers are set
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: ing or long
    :return:
    :rtype: Dict
    """
    return _get_numbering_for_show('scene_numbering', tvid, prodid)


def has_xem_scene_mapping(tvid, prodid):
    """
    Test if a scene mapping exists for a show at XEM

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :return: True if scene mapping exists, False if not
    :rtype: Bool
    """
    return bool(get_xem_numbering_for_show(tvid, prodid))


def get_xem_numbering_for_show(tvid, prodid):
    """
    Returns a dict of (season, episode) : (scene_season, scene_episode) mappings
    for an entire show.  Both the keys and values of the dict are tuples.
    Will be empty if no scene numbers are set in xem
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :return:
    :rtype: Dict
    """
    return _get_numbering_for_show('tv_episodes', tvid, prodid)


def _get_numbering_for_show(tbl, tvid, prodid):
    """

    :param tbl: table
    :type tbl: AnyStr
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :return:
    :rtype: Dict
    """
    result = {}

    if None is not prodid:
        if 'tv_episodes' == tbl:
            xem_refresh(tvid, prodid)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            """
            SELECT season, episode, scene_season, scene_episode
            FROM %s
            WHERE indexer = ? AND %s = ? AND (scene_season OR scene_episode) != 0
            ORDER BY season, episode
            """ % (tbl, ('indexer_id', 'showid')['tv_episodes' == tbl]), [int(tvid), int(prodid)])

        for cur_row in sql_result:
            season, episode = try_int(cur_row['season'], None), try_int(cur_row['episode'], None)
            if None is not season and None is not episode:
                scene_season, scene_episode = try_int(cur_row['scene_season'], None), \
                                              try_int(cur_row['scene_episode'], None)
                if None is not scene_season and None is not scene_episode:
                    result[(season, episode)] = (scene_season, scene_episode)

    return result


def get_scene_absolute_numbering_for_show(tvid, prodid):
    """
    Returns a dict of (season, episode) : scene_absolute_number mappings for an entire show.
    Will be empty if no scene numbers are set
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :return:
    :rtype: Dict
    """
    return _get_absolute_numbering_for_show('scene_numbering', tvid, prodid)


def get_xem_absolute_numbering_for_show(tvid, prodid):
    """
    Returns a dict of (season, episode) : scene_absolute_number mappings for an entire show.
    Will be empty if no scene numbers are set in xem
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :return:
    :rtype: Dict
    """
    return _get_absolute_numbering_for_show('tv_episodes', tvid, prodid)


def _get_absolute_numbering_for_show(tbl, tvid, prodid):
    """

    :param tbl: table name
    :type tbl: AnyStr
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :return:
    :rtype: Dict
    """
    result = {}

    if None is not prodid:
        if 'tv_episodes' == tbl:
            xem_refresh(tvid, prodid)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            """
            SELECT season, episode, absolute_number, scene_absolute_number
            FROM %s
            WHERE indexer = ? AND %s = ? AND scene_absolute_number != 0
            ORDER BY season, episode
            """ % (tbl, ('indexer_id', 'showid')['tv_episodes' == tbl]), [int(tvid), int(prodid)])

        for cur_row in sql_result:
            season, episode, abs_num = map_list(lambda x: try_int(cur_row[x], None),
                                                ('season', 'episode', 'absolute_number'))
            if None is season and None is episode and None is not abs_num:
                season, episode, _ = _get_sea(tvid, prodid, absolute_number=abs_num)

            if None is not season and None is not episode:
                scene_absolute_number = try_int(cur_row['scene_absolute_number'], None)
                if None is not scene_absolute_number:
                    result[(season, episode)] = scene_absolute_number

    return result


def _get_sea(tvid, prodid, season=None, episode=None, absolute_number=None):
    """

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param season: season number
    :type season: int or None
    :param episode: episode number
    :type episode: int or None
    :param absolute_number: absolute number
    :type absolute_number: int or None
    :return:
    :rtype: Tuple[int, int, int]
    """
    show_obj = sickbeard.helpers.find_show_by_id({tvid: prodid}, no_mapped_ids=True)
    if show_obj:
        ep_obj = None
        if None is not absolute_number:
            ep_obj = show_obj.get_episode(absolute_number=absolute_number)
        elif None is not season and None is not episode:
            ep_obj = show_obj.get_episode(season, episode)
        if None is not ep_obj:
            season, episode, absolute_number = ep_obj.season, ep_obj.episode, ep_obj.absolute_number
    return season, episode, absolute_number


def xem_refresh(tvid, prodid, force=False):
    """
    Refresh data from xem for a tv show

    :param tvid:
    :type tvid: int
    :param prodid:
    :type prodid: int
    :param force:
    :type force: bool
    """
    if None is prodid:
        return

    tvid, prodid = int(tvid), int(prodid)
    tvinfo = sickbeard.TVInfoAPI(tvid)

    if 'xem_origin' not in tvinfo.config or prodid not in xem_ids_list.get(tvid, []):
        return

    xem_origin = tvinfo.config['xem_origin']

    # XEM API URL
    # noinspection HttpUrlsUsage
    url = 'http://thexem.info/map/all?id=%s&origin=%s&destination=scene' % (prodid, xem_origin)

    max_refresh_age_secs = 86400  # 1 day

    my_db = db.DBConnection()
    sql_result = my_db.select(
        """
        SELECT last_refreshed
        FROM xem_refresh
        WHERE indexer = ? AND indexer_id = ?
        """, [tvid, prodid])
    if sql_result:
        last_refresh = int(sql_result[0]['last_refreshed'])
        refresh = int(timestamp_near(datetime.datetime.now())) > last_refresh + max_refresh_age_secs
    else:
        refresh = True

    if refresh or force:
        logger.log(u'Looking up XEM scene mapping for show %s on %s' % (prodid, tvinfo.name), logger.DEBUG)

        # mark refreshed
        my_db.upsert('xem_refresh',
                     dict(last_refreshed=int(timestamp_near(datetime.datetime.now()))),
                     dict(indexer=tvid, indexer_id=prodid))

        try:
            parsed_json = sickbeard.helpers.get_url(url, parse_json=True, timeout=90)
            if not parsed_json or '' == parsed_json:
                logger.log(u'No XEM data for show %s on %s' % (prodid, tvinfo.name), logger.MESSAGE)
                return

            if 'success' in parsed_json['result']:
                cl = map_list(lambda entry: [
                        """
                        UPDATE tv_episodes
                        SET scene_season = ?, scene_episode = ?, scene_absolute_number = ?
                        WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                        """, [entry.get('scene%s' % ('', '_2')['scene_2' in entry]).get(v)
                              for v in ('season', 'episode', 'absolute')]
                        + [tvid, prodid]
                        + [entry.get(xem_origin).get(v) for v in ('season', 'episode')]
                ], filter_iter(lambda x: 'scene' in x, parsed_json['data']))

                if 0 < len(cl):
                    my_db = db.DBConnection()
                    my_db.mass_action(cl)
            else:
                logger.log(u'Empty lookup result - no XEM data for show %s on %s' % (prodid, tvinfo.name), logger.DEBUG)
        except (BaseException, Exception) as e:
            logger.log(u'Exception refreshing XEM data for show ' + str(prodid) + ' on ' + tvinfo.name + ': ' + ex(e),
                       logger.WARNING)
            logger.log(traceback.format_exc(), logger.ERROR)


def fix_xem_numbering(tvid, prodid):
    """

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    """
    if None is prodid:
        return {}

    tvid, prodid = int(tvid), int(prodid)

    my_db = db.DBConnection()
    sql_result = my_db.select(
        """
        SELECT season, episode, absolute_number, scene_season, scene_episode, scene_absolute_number
        FROM tv_episodes
        WHERE indexer = ? AND showid = ?
        """, [tvid, prodid])

    last_absolute_number = None
    last_scene_season = None
    last_scene_episode = None
    last_scene_absolute_number = None

    update_absolute_number = False
    update_scene_season = False
    update_scene_episode = False
    update_scene_absolute_number = False

    logger.log(
        u'Fixing any XEM scene mapping issues for show %s on %s' % (prodid, sickbeard.TVInfoAPI(tvid).name),
        logger.DEBUG)

    cl = []
    for cur_row in sql_result:
        season = int(cur_row['season'])
        episode = int(cur_row['episode'])

        if not int(cur_row['scene_season']) and last_scene_season:
            scene_season = last_scene_season + 1
            update_scene_season = True
        else:
            scene_season = int(cur_row['scene_season'])
            if last_scene_season and scene_season < last_scene_season:
                scene_season = last_scene_season + 1
                update_scene_season = True

        if not int(cur_row['scene_episode']) and last_scene_episode:
            scene_episode = last_scene_episode + 1
            update_scene_episode = True
        else:
            scene_episode = int(cur_row['scene_episode'])
            if last_scene_episode and scene_episode < last_scene_episode:
                scene_episode = last_scene_episode + 1
                update_scene_episode = True

        # check for unset values and correct them
        if not int(cur_row['absolute_number']) and last_absolute_number:
            absolute_number = last_absolute_number + 1
            update_absolute_number = True
        else:
            absolute_number = int(cur_row['absolute_number'])
            if last_absolute_number and absolute_number < last_absolute_number:
                absolute_number = last_absolute_number + 1
                update_absolute_number = True

        if not int(cur_row['scene_absolute_number']) and last_scene_absolute_number:
            scene_absolute_number = last_scene_absolute_number + 1
            update_scene_absolute_number = True
        else:
            scene_absolute_number = int(cur_row['scene_absolute_number'])
            if last_scene_absolute_number and scene_absolute_number < last_scene_absolute_number:
                scene_absolute_number = last_scene_absolute_number + 1
                update_scene_absolute_number = True

        # store values for lookup on next iteration
        last_absolute_number = absolute_number
        last_scene_season = scene_season
        last_scene_episode = scene_episode
        last_scene_absolute_number = scene_absolute_number

        if update_absolute_number:
            cl.append([
                """
                UPDATE tv_episodes
                SET absolute_number = ?
                WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                """, [absolute_number, tvid, prodid, season, episode]
            ])
            update_absolute_number = False

        if update_scene_season:
            cl.append([
                """
                UPDATE tv_episodes
                SET scene_season = ?
                WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                """, [scene_season, tvid, prodid, season, episode]
            ])
            update_scene_season = False

        if update_scene_episode:
            cl.append([
                """
                UPDATE tv_episodes
                SET scene_episode = ?
                WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                """, [scene_episode, tvid, prodid, season, episode]
            ])
            update_scene_episode = False

        if update_scene_absolute_number:
            cl.append([
                """
                UPDATE tv_episodes
                SET scene_absolute_number = ?
                WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                """, [scene_absolute_number, tvid, prodid, season, episode]
            ])
            update_scene_absolute_number = False

    if 0 < len(cl):
        my_db = db.DBConnection()
        my_db.mass_action(cl)


def set_scene_numbering_helper(tvid, prodid, for_season=None, for_episode=None, for_absolute=None,
                               scene_season=None, scene_episode=None, scene_absolute=None):
    """

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param for_season:
    :type for_season: int or None
    :param for_episode:
    :type for_episode: int or None
    :param for_absolute:
    :type for_absolute: int or None
    :param scene_season:
    :type scene_season: int or None
    :param scene_episode:
    :type scene_episode: int or None
    :param scene_absolute:
    :type scene_absolute: int or None
    :return:
    :rtype: Dict[AnyStr, int]
    """
    # sanitize:
    tvid = None if tvid in [None, 'null', ''] else int(tvid)
    prodid = None if prodid in [None, 'null', ''] else int(prodid)

    show_obj = sickbeard.helpers.find_show_by_id({tvid: prodid}, no_mapped_ids=True)
    if not show_obj:
        return {'success': False}

    for_season = None if for_season in [None, 'null', ''] else int(for_season)
    for_episode = None if for_episode in [None, 'null', ''] else int(for_episode)
    ep_args = {'show': prodid, 'season': for_season, 'episode': for_episode}
    scene_args = {'tvid': tvid, 'prodid': prodid, 'season': for_season, 'episode': for_episode}
    if not show_obj.is_anime:
        scene_season = None if scene_season in [None, 'null', ''] else int(scene_season)
        scene_episode = None if scene_episode in [None, 'null', ''] else int(scene_episode)
        action_log = u'Set episode scene numbering to %sx%s for episode %sx%s of "%s"' \
                     % (scene_season, scene_episode, for_season, for_episode, show_obj.unique_name)
        scene_args.update({'scene_season': scene_season, 'scene_episode': scene_episode})
        result = {'forSeason': for_season, 'forEpisode': for_episode, 'sceneSeason': None, 'sceneEpisode': None}
    else:
        for_absolute = None if for_absolute in [None, 'null', ''] else int(for_absolute)
        scene_absolute = None if scene_absolute in [None, 'null', ''] else int(scene_absolute)
        action_log = u'Set absolute scene numbering to %s for episode %sx%s of "%s"' \
                     % (scene_absolute, for_season, for_episode, show_obj.unique_name)
        ep_args.update({'absolute': for_absolute})
        scene_args.update({'absolute_number': for_absolute, 'scene_absolute': scene_absolute, 'anime': True})
        result = {'forAbsolute': for_absolute, 'sceneAbsolute': None}

    if ep_args.get('absolute'):
        ep_obj = show_obj.get_episode(absolute_number=int(ep_args['absolute']))
    elif None is not ep_args['season'] and None is not ep_args['episode']:
        ep_obj = show_obj.get_episode(int(ep_args['season']), int(ep_args['episode']))
    else:
        ep_obj = 'Invalid parameters'

    result['success'] = None is not ep_obj and not isinstance(ep_obj, str)
    if result['success']:
        logger.log(action_log, logger.DEBUG)
        set_scene_numbering(**scene_args)
        show_obj.flush_episodes()
        if not show_obj.is_anime:
            if (None is scene_season and None is scene_episode) or (0 == scene_season and 0 == scene_episode):
                # when clearing the field, do not return existing values of sxe, otherwise this may be confusing
                # with the case where manually setting sxe to the actual sxe is done to prevent a data overwrite.
                # So now the only instance an actual sxe is in the field is if user enters it, else 0x0 is presented.
                return result
        elif None is scene_absolute or 0 == scene_absolute:
            return result
    else:
        result['errorMessage'] = "Episode couldn't be retrieved, invalid parameters"

    if not show_obj.is_anime:
        scene_numbering = get_scene_numbering(tvid, prodid, for_season, for_episode, show_obj=show_obj)
        if scene_numbering:
            (result['sceneSeason'], result['sceneEpisode']) = scene_numbering
    else:
        scene_numbering = get_scene_absolute_numbering(tvid, prodid, for_absolute, for_season, for_episode,
                                                       show_obj=show_obj)
        if scene_numbering:
            result['sceneAbsolute'] = scene_numbering

    return result
