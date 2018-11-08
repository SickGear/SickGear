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


import time
import datetime
import traceback
import sickbeard

from sickbeard import logger
from sickbeard import db
from sickbeard.exceptions import ex
from sickbeard.helpers import tryInt
from sickbeard.scene_exceptions import xem_ids_list


def get_scene_numbering(indexer_id, indexer, season, episode, fallback_to_xem=True):
    """
    Returns a tuple, (season, episode), with the scene numbering (if there is one),
    otherwise returns the xem numbering (if fallback_to_xem is set), otherwise
    returns the TVDB numbering.
    (so the return values will always be set)

    @param indexer_id: int
    @param indexer: int
    @param season: int
    @param episode: int
    @param fallback_to_xem: bool If set (the default), check xem for matches if there is no local scene numbering
    @return: (int, int) a tuple with (season, episode)
    """
    if None is indexer_id or None is season or None is episode:
        return season, episode

    show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(indexer_id))
    if show_obj and not show_obj.is_scene:
        return season, episode

    result = find_scene_numbering(int(indexer_id), int(indexer), season, episode)
    if result:
        return result
    else:
        if fallback_to_xem:
            xem_result = find_xem_numbering(int(indexer_id), int(indexer), season, episode)
            if xem_result:
                return xem_result
        return season, episode


def find_scene_numbering(indexer_id, indexer, season, episode):
    """
    Same as get_scene_numbering(), but returns None if scene numbering is not set
    """
    if None is indexer_id or None is season or None is episode:
        return

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT scene_season, scene_episode'
        ' FROM scene_numbering'
        ' WHERE indexer = ? AND indexer_id = ? AND season = ? AND episode = ? AND (scene_season OR scene_episode) != 0',
        [indexer, indexer_id, season, episode])

    if rows:
        return int(rows[0]['scene_season']), int(rows[0]['scene_episode'])


def get_scene_absolute_numbering(indexer_id, indexer, absolute_number, season, episode, fallback_to_xem=True):
    """
    Returns a tuple, (season, episode), with the scene numbering (if there is one),
    otherwise returns the xem numbering (if fallback_to_xem is set), otherwise
    returns the TVDB numbering.
    (so the return values will always be set)

    @param indexer_id: int
    @param indexer: int
    @param absolute_number: int
    @param season: int
    @param episode: int
    @param fallback_to_xem: bool If set (the default), check xem for matches if there is no local scene numbering
    @return: (int, int) a tuple with (season, episode)
    """
    has_sxe = None is not season and None is not episode
    if None is indexer_id or (None is absolute_number and not has_sxe):
        return absolute_number

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, indexer_id)
    if show_obj and not show_obj.is_scene and not has_sxe:
        return absolute_number

    result = find_scene_absolute_numbering(indexer_id, indexer, absolute_number, season, episode)
    if result:
        return result
    else:
        if fallback_to_xem:
            xem_result = find_xem_absolute_numbering(indexer_id, indexer, absolute_number, season, episode)
            if xem_result:
                return xem_result
        return absolute_number


def find_scene_absolute_numbering(indexer_id, indexer, absolute_number, season=None, episode=None):
    """
    Same as get_scene_numbering(), but returns None if scene numbering is not set
    """
    has_sxe = None is not season and None is not episode
    if None is indexer_id or (None is absolute_number and not has_sxe):
        return

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    sql_vars, cond = (([absolute_number], 'and absolute_number = ?'),
                      ([season, episode], 'and season = ? AND episode = ?'))[has_sxe]
    rows = my_db.select(
        'SELECT scene_absolute_number'
        ' FROM scene_numbering'
        ' WHERE indexer = ? AND indexer_id = ? %s AND scene_absolute_number != 0' % cond,
        [indexer, indexer_id] + sql_vars)

    if rows:
        return int(rows[0]['scene_absolute_number'])


def get_indexer_numbering(indexer_id, indexer, scene_season, scene_episode, fallback_to_xem=True):
    """
    Returns a tuple, (season, episode) with the TVDB numbering for (sceneSeason, sceneEpisode)
    (this works like the reverse of get_scene_numbering)
    """
    if None is indexer_id or None is scene_season or None is scene_episode:
        return scene_season, scene_episode

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT season, episode'
        ' FROM scene_numbering'
        ' WHERE indexer = ? AND indexer_id = ? AND scene_season = ? AND scene_episode = ?',
        [indexer, indexer_id, scene_season, scene_episode])

    if rows:
        return int(rows[0]['season']), int(rows[0]['episode'])
    else:
        if fallback_to_xem:
            return get_indexer_numbering_for_xem(indexer_id, indexer, scene_season, scene_episode)
        return scene_season, scene_episode


def get_indexer_absolute_numbering(indexer_id, indexer, scene_absolute_number, fallback_to_xem=True, scene_season=None):
    """
    Returns a tuple, (season, episode, absolute_number) with the TVDB numbering for (sceneAbsoluteNumber)
    (this works like the reverse of get_absolute_numbering)
    """
    if None is indexer_id or None is scene_absolute_number:
        return scene_absolute_number

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    if None is scene_season:
        rows = my_db.select(
            'SELECT absolute_number'
            ' FROM scene_numbering'
            ' WHERE indexer = ? AND indexer_id = ? AND scene_absolute_number = ?',
            [indexer, indexer_id, scene_absolute_number])
    else:
        rows = my_db.select(
            'SELECT absolute_number'
            ' FROM scene_numbering'
            ' WHERE indexer = ? AND indexer_id = ? AND scene_absolute_number = ? AND scene_season = ?',
            [indexer, indexer_id, scene_absolute_number, scene_season])

    if rows:
        return int(rows[0]['absolute_number'])
    else:
        if fallback_to_xem:
            return get_indexer_absolute_numbering_for_xem(indexer_id, indexer, scene_absolute_number, scene_season)
        return scene_absolute_number


def set_scene_numbering(indexer_id, indexer, season=None, episode=None, absolute_number=None, scene_season=None,
                        scene_episode=None, scene_absolute=None, anime=False):
    """
    Set scene numbering for a season/episode.
    To clear the scene numbering, leave both sceneSeason and sceneEpisode as None.

    """
    if None is indexer_id:
        return

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    if None is not season and None is not episode:
        my_db.action(
            'INSERT OR IGNORE INTO scene_numbering (indexer, indexer_id, season, episode) VALUES (?,?,?,?)',
            [indexer, indexer_id, season, episode])

        # sxe replaced abs_num as key, migrate data with only abs
        _, _, ep_absolute_number = _get_sea(indexer, indexer_id, season, episode)
        rows = my_db.select(
            'SELECT scene_season, scene_episode, scene_absolute_number'
            ' FROM scene_numbering'
            ' WHERE indexer = ? AND indexer_id = ? AND season IS NULL AND episode IS NULL AND absolute_number = ?',
            [indexer, indexer_id, ep_absolute_number])

        if not len(rows):
            update, values = (('scene_absolute_number = ?', [scene_absolute]),
                              ('scene_season = ?, scene_episode = ?', [scene_season, scene_episode]))[not anime]
        else:
            for row in rows:
                scene_season = scene_season or row['scene_season']
                scene_episode = scene_episode or row['scene_episode']
                scene_absolute = scene_absolute or row['scene_absolute_number']

            update, values = ('scene_season = ?, scene_episode = ?, scene_absolute_number = ?',
                              [scene_season, scene_episode, scene_absolute])
        my_db.action(
            'UPDATE scene_numbering'
            ' SET %s' % update +
            ' WHERE indexer = ? AND indexer_id = ? AND season = ? AND episode = ?',
            values + [indexer, indexer_id, season, episode])

        my_db.action(
            'DELETE'
            ' FROM scene_numbering'
            ' WHERE indexer = ? AND indexer_id = ? AND'
            ' ((absolute_number = ? OR (season = ? AND episode = ?))'
            ' AND scene_season IS NULL AND scene_episode IS NULL AND scene_absolute_number IS NULL)',
            [indexer, indexer_id, ep_absolute_number, season, episode])

    elif absolute_number:
        my_db.action(
            'INSERT OR IGNORE INTO scene_numbering (indexer, indexer_id, absolute_number) VALUES (?,?,?)',
            [indexer, indexer_id, absolute_number])

        my_db.action(
            'UPDATE scene_numbering'
            ' SET scene_absolute_number = ?'
            ' WHERE indexer = ? AND indexer_id = ? AND absolute_number = ?',
            [scene_absolute, indexer, indexer_id, absolute_number])


def find_xem_numbering(indexer_id, indexer, season, episode):
    """
    Returns the scene numbering, as retrieved from xem.
    Refreshes/Loads as needed.

    @param indexer_id: int
    @param indexer: int
    @param season: int
    @param episode: int
    @return: (int, int) a tuple of scene_season, scene_episode, or None if there is no special mapping.
    """
    if None is indexer_id or None is season or None is episode:
        return season, episode

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    xem_refresh(indexer_id, indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT scene_season, scene_episode'
        ' FROM tv_episodes'
        ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ? AND (scene_season OR scene_episode) != 0',
        [indexer, indexer_id, season, episode])

    if rows:
        return int(rows[0]['scene_season']), int(rows[0]['scene_episode'])


def find_xem_absolute_numbering(indexer_id, indexer, absolute_number, season, episode):
    """
    Returns the scene numbering, as retrieved from xem.
    Refreshes/Loads as needed.

    @param indexer_id: int
    @param indexer: int
    @param absolute_number: int
    @param season: int
    @param episode: int
    @return: int
    """
    if None is indexer_id or None is absolute_number:
        return absolute_number

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    xem_refresh(indexer_id, indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT scene_absolute_number'
        ' FROM tv_episodes'
        ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ? AND scene_absolute_number != 0',
        [indexer, indexer_id, season, episode])

    if rows:
        return int(rows[0]['scene_absolute_number'])


def get_indexer_numbering_for_xem(indexer_id, indexer, scene_season, scene_episode):
    """
    Reverse of find_xem_numbering: lookup a tvdb season and episode using scene numbering

    @param indexer_id: int
    @param indexer: int
    @param scene_season: int
    @param scene_episode: int
    @return: (int, int) a tuple of (season, episode)
    """
    if None is indexer_id or None is scene_season or None is scene_episode:
        return scene_season, scene_episode

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    xem_refresh(indexer_id, indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT season, episode'
        ' FROM tv_episodes'
        ' WHERE indexer = ? AND showid = ? AND scene_season = ? AND scene_episode = ?',
        [indexer, indexer_id, scene_season, scene_episode])

    if rows:
        return int(rows[0]['season']), int(rows[0]['episode'])

    return scene_season, scene_episode


def get_indexer_absolute_numbering_for_xem(indexer_id, indexer, scene_absolute_number, scene_season=None):
    """
    Reverse of find_xem_numbering: lookup a tvdb season and episode using scene numbering

    @param indexer_id: int
    @param indexer: int
    @param scene_absolute_number: int
    @param scene_season: int/None
    @return: int
    """
    if None is indexer_id or None is scene_absolute_number:
        return scene_absolute_number

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    xem_refresh(indexer_id, indexer)

    my_db = db.DBConnection()
    if None is scene_season:
        rows = my_db.select(
            'SELECT absolute_number'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND scene_absolute_number = ?',
            [indexer, indexer_id, scene_absolute_number])
    else:
        rows = my_db.select(
            'SELECT absolute_number'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND scene_absolute_number = ? AND scene_season = ?',
            [indexer, indexer_id, scene_absolute_number, scene_season])

    if rows:
        return int(rows[0]['absolute_number'])

    return scene_absolute_number


def get_scene_numbering_for_show(indexer_id, indexer):
    """
    Returns a dict of (season, episode) : (scene_season, scene_episode) mappings
    for an entire show.  Both the keys and values of the dict are tuples.
    Will be empty if no scene numbers are set
    """
    return _get_numbering_for_show('scene_numbering', indexer, indexer_id)


def has_xem_scene_mapping(indexer_id, indexer):
    """
    Test if a scene mapping exists for a show at XEM

    :param indexer_id:
    :type indexer_id: int
    :param indexer:
    :type indexer: int
    :return: True if scene mapping exists, False if not
    :rtype: Bool
    """
    return bool(get_xem_numbering_for_show(indexer_id, indexer))


def get_xem_numbering_for_show(indexer_id, indexer):
    """
    Returns a dict of (season, episode) : (scene_season, scene_episode) mappings
    for an entire show.  Both the keys and values of the dict are tuples.
    Will be empty if no scene numbers are set in xem
    """
    return _get_numbering_for_show('tv_episodes', indexer, indexer_id)


def _get_numbering_for_show(tbl, indexer, indexer_id):

    result = {}

    if None is not indexer_id:
        if 'tv_episodes' == tbl:
            xem_refresh(indexer_id, indexer)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        rows = my_db.select(
            'SELECT season, episode, scene_season, scene_episode'
            ' FROM %s' % tbl +
            ' WHERE indexer = ? AND %s = ?' % ('indexer_id', 'showid')['tv_episodes' == tbl] +
            ' AND (scene_season OR scene_episode) != 0'
            ' ORDER BY season, episode',
            [int(indexer), int(indexer_id)])

        for row in rows:
            season, episode = tryInt(row['season'], None), tryInt(row['episode'], None)
            if None is not season and None is not episode:
                scene_season, scene_episode = tryInt(row['scene_season'], None), tryInt(row['scene_episode'], None)
                if None is not scene_season and None is not scene_episode:
                    result[(season, episode)] = (scene_season, scene_episode)

    return result


def get_scene_absolute_numbering_for_show(indexer_id, indexer):
    """
    Returns a dict of (season, episode) : scene_absolute_number mappings for an entire show.
    Will be empty if no scene numbers are set
    """
    return _get_absolute_numbering_for_show('scene_numbering', indexer, indexer_id)


def get_xem_absolute_numbering_for_show(indexer_id, indexer):
    """
    Returns a dict of (season, episode) : scene_absolute_number mappings for an entire show.
    Will be empty if no scene numbers are set in xem
    """
    return _get_absolute_numbering_for_show('tv_episodes', indexer, indexer_id)


def _get_absolute_numbering_for_show(tbl, indexer, indexer_id):

    result = {}

    if None is not indexer_id:
        if 'tv_episodes' == tbl:
            xem_refresh(indexer_id, indexer)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        rows = my_db.select(
            'SELECT season, episode, absolute_number, scene_absolute_number'
            ' FROM %s' % tbl +
            ' WHERE indexer = ? AND %s = ?' % ('indexer_id', 'showid')['tv_episodes' == tbl] +
            ' AND scene_absolute_number != 0'
            ' ORDER BY season, episode',
            [int(indexer), int(indexer_id)])

        for row in rows:
            season, episode, abs_num = map(lambda x: tryInt(row[x], None), ('season', 'episode', 'absolute_number'))
            if None is season and None is episode and None is not abs_num:
                season, episode, _ = _get_sea(indexer, indexer_id, absolute_number=abs_num)

            if None is not season and None is not episode:
                scene_absolute_number = tryInt(row['scene_absolute_number'], None)
                if None is not scene_absolute_number:
                    result[(season, episode)] = scene_absolute_number

    return result


def _get_sea(indexer, indexer_id, season=None, episode=None, absolute_number=None):
    show_obj = sickbeard.helpers.find_show_by_id(sickbeard.showList, {indexer: indexer_id},
                                                 no_mapped_ids=True)
    if show_obj:
        ep_obj = None
        if None is not absolute_number:
            ep_obj = show_obj.getEpisode(absolute_number=absolute_number)
        elif None is not season and None is not episode:
            ep_obj = show_obj.getEpisode(season, episode)
        if None is not ep_obj:
            season, episode, absolute_number = ep_obj.season, ep_obj.episode, ep_obj.absolute_number
    return season, episode, absolute_number


def xem_refresh(indexer_id, indexer, force=False):
    """
    Refresh data from xem for a tv show

    @param indexer_id: int
    @param indexer: int
    @param force: bool
    """
    if None is indexer_id:
        return

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    if 'xem_origin' not in sickbeard.indexerApi(indexer).config or indexer_id not in xem_ids_list.get(indexer, []):
        return

    # XEM API URL
    url = 'http://thexem.de/map/all?id=%s&origin=%s&destination=scene' % (
        indexer_id, sickbeard.indexerApi(indexer).config['xem_origin'])

    max_refresh_age_secs = 86400  # 1 day

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT last_refreshed'
        ' FROM xem_refresh'
        ' WHERE indexer = ? AND indexer_id = ?',
        [indexer, indexer_id])
    if rows:
        last_refresh = int(rows[0]['last_refreshed'])
        refresh = int(time.mktime(datetime.datetime.today().timetuple())) > last_refresh + max_refresh_age_secs
    else:
        refresh = True

    if refresh or force:
        logger.log(
            u'Looking up XEM scene mapping for show %s on %s' % (indexer_id, sickbeard.indexerApi(indexer).name),
            logger.DEBUG)

        # mark refreshed
        my_db.upsert('xem_refresh',
                     {'indexer': indexer, 'last_refreshed': int(time.mktime(datetime.datetime.today().timetuple()))},
                     {'indexer_id': indexer_id})

        try:
            parsed_json = sickbeard.helpers.getURL(url, json=True, timeout=90)
            if not parsed_json or '' == parsed_json:
                logger.log(u'No XEM data for show %s on %s' % (
                    indexer_id, sickbeard.indexerApi(indexer).name), logger.MESSAGE)
                return

            if 'success' in parsed_json['result']:
                cl = []
                for entry in filter(lambda x: 'scene' in x, parsed_json['data']):
                    # use scene2 for doubles
                    scene = 'scene%s' % ('', '_2')['scene_2' in entry]
                    cl.append([
                        'UPDATE tv_episodes'
                        ' SET scene_season = ?, scene_episode = ?, scene_absolute_number = ?'
                        ' WHERE showid = ? AND season = ? AND episode = ?',
                        [entry[scene]['season'], entry[scene]['episode'], entry[scene]['absolute'],
                         indexer_id,
                         entry[sickbeard.indexerApi(indexer).config['xem_origin']]['season'],
                         entry[sickbeard.indexerApi(indexer).config['xem_origin']]['episode']
                         ]])

                if 0 < len(cl):
                    my_db = db.DBConnection()
                    my_db.mass_action(cl)
            else:
                logger.log(u'Empty lookup result - no XEM data for show %s on %s' % (
                    indexer_id, sickbeard.indexerApi(indexer).name), logger.DEBUG)
        except Exception as e:
            logger.log(
                u'Exception while refreshing XEM data for show ' + str(indexer_id) + ' on ' + sickbeard.indexerApi(
                    indexer).name + ': ' + ex(e), logger.WARNING)
            logger.log(traceback.format_exc(), logger.ERROR)


def fix_xem_numbering(indexer_id, indexer):

    if None is indexer_id:
        return {}

    indexer_id = int(indexer_id)
    indexer = int(indexer)

    my_db = db.DBConnection()
    rows = my_db.select(
        'SELECT season, episode, absolute_number, scene_season, scene_episode, scene_absolute_number'
        ' FROM tv_episodes'
        ' WHERE indexer = ? AND showid = ?',
        [indexer, indexer_id])

    last_absolute_number = None
    last_scene_season = None
    last_scene_episode = None
    last_scene_absolute_number = None

    update_absolute_number = False
    update_scene_season = False
    update_scene_episode = False
    update_scene_absolute_number = False

    logger.log(
        u'Fixing any XEM scene mapping issues for show %s on %s' % (indexer_id, sickbeard.indexerApi(indexer).name),
        logger.DEBUG)

    cl = []
    for row in rows:
        season = int(row['season'])
        episode = int(row['episode'])

        if not int(row['scene_season']) and last_scene_season:
            scene_season = last_scene_season + 1
            update_scene_season = True
        else:
            scene_season = int(row['scene_season'])
            if last_scene_season and scene_season < last_scene_season:
                scene_season = last_scene_season + 1
                update_scene_season = True

        if not int(row['scene_episode']) and last_scene_episode:
            scene_episode = last_scene_episode + 1
            update_scene_episode = True
        else:
            scene_episode = int(row['scene_episode'])
            if last_scene_episode and scene_episode < last_scene_episode:
                scene_episode = last_scene_episode + 1
                update_scene_episode = True

        # check for unset values and correct them
        if not int(row['absolute_number']) and last_absolute_number:
            absolute_number = last_absolute_number + 1
            update_absolute_number = True
        else:
            absolute_number = int(row['absolute_number'])
            if last_absolute_number and absolute_number < last_absolute_number:
                absolute_number = last_absolute_number + 1
                update_absolute_number = True

        if not int(row['scene_absolute_number']) and last_scene_absolute_number:
            scene_absolute_number = last_scene_absolute_number + 1
            update_scene_absolute_number = True
        else:
            scene_absolute_number = int(row['scene_absolute_number'])
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
                'UPDATE tv_episodes'
                ' SET absolute_number = ?'
                ' WHERE showid = ? AND season = ? AND episode = ?',
                [absolute_number,
                 indexer_id,
                 season,
                 episode
                 ]])
            update_absolute_number = False

        if update_scene_season:
            cl.append([
                'UPDATE tv_episodes'
                ' SET scene_season = ?'
                ' WHERE showid = ? AND season = ? AND episode = ?',
                [scene_season,
                 indexer_id,
                 season,
                 episode
                 ]])
            update_scene_season = False

        if update_scene_episode:
            cl.append([
                'UPDATE tv_episodes'
                ' SET scene_episode = ?'
                ' WHERE showid = ? AND season = ? AND episode = ?',
                [scene_episode,
                 indexer_id,
                 season,
                 episode
                 ]])
            update_scene_episode = False

        if update_scene_absolute_number:
            cl.append([
                'UPDATE tv_episodes'
                ' SET scene_absolute_number = ?'
                ' WHERE showid = ? AND season = ? AND episode = ?',
                [scene_absolute_number,
                 indexer_id,
                 season,
                 episode
                 ]])
            update_scene_absolute_number = False

    if 0 < len(cl):
        my_db = db.DBConnection()
        my_db.mass_action(cl)


def set_scene_numbering_helper(indexerid, indexer, for_season=None, for_episode=None, for_absolute=None,
                               scene_season=None, scene_episode=None, scene_absolute=None):
    # sanitize:
    indexerid = None if indexerid in [None, 'null', ''] else int(indexerid)
    indexer = None if indexer in [None, 'null', ''] else int(indexer)

    show_obj = sickbeard.helpers.find_show_by_id(sickbeard.showList, {indexer: indexerid}, no_mapped_ids=True)
    if not show_obj:
        return {'success': False}

    for_season = None if for_season in [None, 'null', ''] else int(for_season)
    for_episode = None if for_episode in [None, 'null', ''] else int(for_episode)
    ep_args = {'show': indexerid, 'season': for_season, 'episode': for_episode}
    scene_args = {'indexer': indexer, 'indexer_id': indexerid, 'season': for_season, 'episode': for_episode}
    if not show_obj.is_anime:
        scene_season = None if scene_season in [None, 'null', ''] else int(scene_season)
        scene_episode = None if scene_episode in [None, 'null', ''] else int(scene_episode)
        action_log = u'Set episode scene numbering to %sx%s for episode %sx%s of "%s"' \
                     % (scene_season, scene_episode, for_season, for_episode, show_obj.name)
        scene_args.update({'scene_season': scene_season, 'scene_episode': scene_episode})
        result = {'forSeason': for_season, 'forEpisode': for_episode, 'sceneSeason': None, 'sceneEpisode': None}
    else:
        for_absolute = None if for_absolute in [None, 'null', ''] else int(for_absolute)
        scene_absolute = None if scene_absolute in [None, 'null', ''] else int(scene_absolute)
        action_log = u'Set absolute scene numbering to %s for episode %sx%s of "%s"' \
                     % (scene_absolute, for_season, for_episode, show_obj.name)
        ep_args.update({'absolute': for_absolute})
        scene_args.update({'absolute_number': for_absolute, 'scene_absolute': scene_absolute, 'anime': True})
        result = {'forAbsolute': for_absolute, 'sceneAbsolute': None}

    if ep_args.get('absolute'):
        ep_obj = show_obj.getEpisode(absolute_number=int(ep_args['absolute']))
    elif None is not ep_args['season'] and None is not ep_args['episode']:
        ep_obj = show_obj.getEpisode(int(ep_args['season']), int(ep_args['episode']))
    else:
        ep_obj = 'Invalid parameters'

    result['success'] = None is not ep_obj and not isinstance(ep_obj, str)
    if result['success']:
        logger.log(action_log, logger.DEBUG)
        set_scene_numbering(**scene_args)
        show_obj.flushEpisodes()
    else:
        result['errorMessage'] = "Episode couldn't be retrieved, invalid parameters"

    if not show_obj.is_anime:
        scene_numbering = get_scene_numbering(indexerid, indexer, for_season, for_episode)
        if scene_numbering:
            (result['sceneSeason'], result['sceneEpisode']) = scene_numbering
    else:
        scene_numbering = get_scene_absolute_numbering(indexerid, indexer, for_absolute, for_season, for_episode)
        if scene_numbering:
            result['sceneAbsolute'] = scene_numbering

    return result
