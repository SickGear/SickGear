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

import re
import time
import threading
import datetime
import sickbeard
import traceback

from collections import defaultdict
from lib import adba
from sickbeard import helpers
from sickbeard import name_cache
from sickbeard import logger
from sickbeard import db
from sickbeard.classes import OrderedDefaultdict

exception_dict = {}
anidb_exception_dict = {}
xem_exception_dict = {}
xem_ids_list = defaultdict(list)

exceptionsCache = {}
exceptionsSeasonCache = {}

exceptionLock = threading.Lock()


def shouldRefresh(list):
    max_refresh_age_secs = 86400  # 1 day

    my_db = db.DBConnection()
    rows = my_db.select('SELECT last_refreshed FROM scene_exceptions_refresh WHERE list = ?', [list])
    if rows:
        last_refresh = int(rows[0]['last_refreshed'])
        return int(time.mktime(datetime.datetime.today().timetuple())) > last_refresh + max_refresh_age_secs
    else:
        return True


def setLastRefresh(list):
    my_db = db.DBConnection()
    my_db.upsert('scene_exceptions_refresh',
                 {'last_refreshed': int(time.mktime(datetime.datetime.today().timetuple()))},
                 {'list': list})


def get_scene_exceptions(indexer_id, season=-1):
    """
    Given a indexer_id, return a list of all the scene exceptions.
    """
    global exceptionsCache
    exceptions_list = []

    if indexer_id not in exceptionsCache or season not in exceptionsCache[indexer_id]:
        my_db = db.DBConnection()
        exceptions = my_db.select('SELECT show_name FROM scene_exceptions WHERE indexer_id = ? and season = ?',
                                  [indexer_id, season])
        if exceptions:
            exceptions_list = list(set([cur_exception['show_name'] for cur_exception in exceptions]))

            if indexer_id not in exceptionsCache:
                exceptionsCache[indexer_id] = {}
            exceptionsCache[indexer_id][season] = exceptions_list
    else:
        exceptions_list = exceptionsCache[indexer_id][season]

    if 1 == season:  # if we where looking for season 1 we can add generic names
        exceptions_list += get_scene_exceptions(indexer_id, season=-1)

    return exceptions_list


def get_all_scene_exceptions(indexer_id):
    exceptions_dict = OrderedDefaultdict(list)

    my_db = db.DBConnection()
    exceptions = my_db.select('SELECT show_name,season FROM scene_exceptions WHERE indexer_id = ? ORDER BY season', [indexer_id])

    if exceptions:
        for cur_exception in exceptions:
            exceptions_dict[cur_exception['season']].append(cur_exception['show_name'])

    return exceptions_dict


def get_scene_seasons(indexer_id):
    """
    return a list of season numbers that have scene exceptions
    """
    global exceptionsSeasonCache
    exception_sseason_list = []

    if indexer_id not in exceptionsSeasonCache:
        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT DISTINCT(season) as season FROM scene_exceptions WHERE indexer_id = ?',
                                   [indexer_id])
        if sql_results:
            exception_sseason_list = list(set([int(x['season']) for x in sql_results]))

            if indexer_id not in exceptionsSeasonCache:
                exceptionsSeasonCache[indexer_id] = {}

            exceptionsSeasonCache[indexer_id] = exception_sseason_list
    else:
        exception_sseason_list = exceptionsSeasonCache[indexer_id]

    return exception_sseason_list


def get_scene_exception_by_name(show_name):
    return get_scene_exception_by_name_multiple(show_name)[0]


def get_scene_exception_by_name_multiple(show_name):
    """
    Given a show name, return the indexerid of the exception, None if no exception
    is present.
    """
    try:
        exception_result = name_cache.nameCache[helpers.full_sanitizeSceneName(show_name)]
        return [exception_result]
    except:
        return [[None, None]]


def retrieve_exceptions():
    """
    Looks up the exceptions on github, parses them into a dict, and inserts them into the
    scene_exceptions table in cache.db. Also clears the scene name cache.
    """
    global exception_dict, anidb_exception_dict, xem_exception_dict

    # exceptions are stored on github pages
    for indexer in sickbeard.indexerApi().indexers:
        if shouldRefresh(sickbeard.indexerApi(indexer).name):
            logger.log(u'Checking for scene exception updates for %s' % sickbeard.indexerApi(indexer).name)

            url = sickbeard.indexerApi(indexer).config['scene_url']

            url_data = helpers.getURL(url)
            if None is url_data:
                # When None is urlData, trouble connecting to github
                logger.log(u'Check scene exceptions update failed. Unable to get URL: %s' % url, logger.ERROR)
                continue

            else:
                setLastRefresh(sickbeard.indexerApi(indexer).name)

                # each exception is on one line with the format indexer_id: 'show name 1', 'show name 2', etc
                for cur_line in url_data.splitlines():
                    cur_line = cur_line.decode('utf-8')
                    indexer_id, sep, aliases = cur_line.partition(':')  # @UnusedVariable

                    if not aliases:
                        continue

                    indexer_id = int(indexer_id)

                    # regex out the list of shows, taking \' into account
                    # alias_list = [re.sub(r'\\(.)', r'\1', x) for x in re.findall(r"'(.*?)(?<!\\)',?", aliases)]
                    alias_list = [{re.sub(r'\\(.)', r'\1', x): -1} for x in re.findall(r"'(.*?)(?<!\\)',?", aliases)]
                    exception_dict[indexer_id] = alias_list
                    del alias_list
                del url_data

    # XEM scene exceptions
    _xem_exceptions_fetcher()
    for xem_ex in xem_exception_dict:
        if xem_ex in exception_dict:
            exception_dict[xem_ex] = exception_dict[xem_ex] + xem_exception_dict[xem_ex]
        else:
            exception_dict[xem_ex] = xem_exception_dict[xem_ex]

    # AniDB scene exceptions
    _anidb_exceptions_fetcher()
    for anidb_ex in anidb_exception_dict:
        if anidb_ex in exception_dict:
            exception_dict[anidb_ex] = exception_dict[anidb_ex] + anidb_exception_dict[anidb_ex]
        else:
            exception_dict[anidb_ex] = anidb_exception_dict[anidb_ex]

    changed_exceptions = False

    # write all the exceptions we got off the net into the database
    my_db = db.DBConnection()
    cl = []
    for cur_indexer_id in exception_dict:

        # get a list of the existing exceptions for this ID
        existing_exceptions = [x['show_name'] for x in
                               my_db.select('SELECT * FROM scene_exceptions WHERE indexer_id = ?', [cur_indexer_id])]

        if cur_indexer_id not in exception_dict:
            continue

        for cur_exception_dict in exception_dict[cur_indexer_id]:
            try:
                cur_exception, cur_season = cur_exception_dict.items()[0]
            except Exception:
                logger.log('scene exception error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)
                continue

            # if this exception isn't already in the DB then add it
            if cur_exception not in existing_exceptions:

                if not isinstance(cur_exception, unicode):
                    cur_exception = unicode(cur_exception, 'utf-8', 'replace')

                cl.append(['INSERT INTO scene_exceptions (indexer_id, show_name, season) VALUES (?,?,?)',
                           [cur_indexer_id, cur_exception, cur_season]])
                changed_exceptions = True

    my_db.mass_action(cl)

    # since this could invalidate the results of the cache we clear it out after updating
    if changed_exceptions:
        logger.log(u'Updated scene exceptions')
    else:
        logger.log(u'No scene exceptions update needed')

    # cleanup
    exception_dict.clear()
    anidb_exception_dict.clear()
    xem_exception_dict.clear()


def update_scene_exceptions(indexer_id, scene_exceptions):
    """
    Given a indexer_id, and a list of all show scene exceptions, update the db.
    """
    global exceptionsCache
    my_db = db.DBConnection()
    my_db.action('DELETE FROM scene_exceptions WHERE indexer_id=?', [indexer_id])

    # A change has been made to the scene exception list. Let's clear the cache, to make this visible
    exceptionsCache[indexer_id] = defaultdict(list)

    logger.log(u'Updating scene exceptions', logger.MESSAGE)
    for exception in scene_exceptions:
        cur_season, cur_exception = exception.split('|', 1)

        exceptionsCache[indexer_id][cur_season].append(cur_exception)

        if not isinstance(cur_exception, unicode):
            cur_exception = unicode(cur_exception, 'utf-8', 'replace')

        my_db.action('INSERT INTO scene_exceptions (indexer_id, show_name, season) VALUES (?,?,?)',
                     [indexer_id, cur_exception, cur_season])


def _anidb_exceptions_fetcher():
    global anidb_exception_dict

    if shouldRefresh('anidb'):
        logger.log(u'Checking for scene exception updates for AniDB')
        for show in sickbeard.showList:
            if show.is_anime and 1 == show.indexer:
                try:
                    anime = adba.Anime(None, name=show.name, tvdbid=show.indexerid, autoCorrectName=True)
                except:
                    continue
                else:
                    if anime.name and anime.name != show.name:
                        anidb_exception_dict[show.indexerid] = [{anime.name: -1}]

        setLastRefresh('anidb')
    return anidb_exception_dict


def _xem_exceptions_fetcher():
    global xem_exception_dict

    xem_list = 'xem_us'
    for show in sickbeard.showList:
        if show.is_anime and not show.paused:
            xem_list = 'xem'
            break

    if shouldRefresh(xem_list):
        for indexer in [i for i in sickbeard.indexerApi().indexers if 'xem_origin' in sickbeard.indexerApi(i).config]:
            logger.log(u'Checking for XEM scene exception updates for %s' % sickbeard.indexerApi(indexer).name)

            url = 'http://thexem.de/map/allNames?origin=%s%s&seasonNumbers=1'\
                  % (sickbeard.indexerApi(indexer).config['xem_origin'], ('&language=us', '')['xem' == xem_list])

            parsed_json = helpers.getURL(url, json=True, timeout=90)
            if not parsed_json:
                logger.log(u'Check scene exceptions update failed for %s, Unable to get URL: %s'
                           % (sickbeard.indexerApi(indexer).name, url), logger.ERROR)
                continue

            if 'failure' == parsed_json['result']:
                continue

            for indexerid, names in parsed_json['data'].items():
                try:
                    xem_exception_dict[int(indexerid)] = names
                except:
                    continue

        setLastRefresh(xem_list)

    return xem_exception_dict


def _xem_get_ids(indexer_name, xem_origin):
    xem_ids = []

    url = 'http://thexem.de/map/havemap?origin=%s' % xem_origin

    task = 'Fetching show ids with%s xem scene mapping%s for origin'
    logger.log(u'%s %s' % (task % ('', 's'), indexer_name))
    parsed_json = helpers.getURL(url, json=True, timeout=90)
    if not parsed_json:
        logger.log(u'Failed %s %s, Unable to get URL: %s'
                   % (task.lower() % ('', 's'), indexer_name, url), logger.ERROR)
    else:
        if 'result' in parsed_json and 'success' == parsed_json['result'] and 'data' in parsed_json:
            try:
                for indexerid in parsed_json['data']:
                    xem_id = helpers.tryInt(indexerid)
                    if xem_id and xem_id not in xem_ids:
                        xem_ids.append(xem_id)
            except:
                pass
            if 0 == len(xem_ids):
                logger.log(u'Failed %s %s, no data items parsed from URL: %s'
                           % (task.lower() % ('', 's'), indexer_name, url), logger.WARNING)

    logger.log(u'Finished %s %s' % (task.lower() % (' %s' % len(xem_ids), helpers.maybe_plural(len(xem_ids))),
                                    indexer_name))
    return xem_ids


def get_xem_ids():
    global xem_ids_list

    for iid, name in sickbeard.indexerApi().xem_supported_indexers.iteritems():
        xem_ids = _xem_get_ids(name, sickbeard.indexerApi(iid).config['xem_origin'])
        if len(xem_ids):
            xem_ids_list[iid] = xem_ids


def has_abs_episodes(ep_obj=None, name=None):
    return any((name or ep_obj.show.name or '').lower().startswith(x.lower()) for x in [
        'The Eighties', 'The Making of the Mob', 'The Night Of', 'Roots 2016', 'Trepalium'
    ])
