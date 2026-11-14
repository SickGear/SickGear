# Author: Tyler Fenby <tylerfenby@gmail.com>
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

from sqlite3 import Cursor
import datetime
import re

from . import db, logger
from .common import DOWNLOAD_CLIENTS, FAILED, WANTED, Quality, statusStrings
from .history import dateFormat
from exceptions_helper import EpisodeNotFoundException, ex

from _23 import unquote

# noinspection PyUnresolvedReferences
# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Optional, Tuple, Union
    from .tv import TVEpisode
    from .classes import NZBSearchResult, NZBDataSearchResult, TorrentSearchResult, Proper


def db_cmd(sql, params, select=True):
    # type: (AnyStr, List, bool) -> Union[List, Optional[Cursor]]
    """

    :param sql: sql string
    :param params: list of parameters
    :param select: use selcet
    :return: sql result
    """
    with db.DBConnection('failed.db') as sg_db:
        if select:
            sql_result = sg_db.select(sql, params)
        else:
            sql_result = sg_db.action(sql, params)
        return sql_result


def db_select(sql, params):
    # type: (AnyStr, List) -> List
    """

    :param sql: sql string
    :param params: list of parameters
    :return: sql result
    """
    return db_cmd(sql, params)


def db_action(sql, params=None):
    # type: (AnyStr, Optional[List]) -> Optional[Cursor]
    """

    :param sql: sql string
    :param params: list of parameters
    :return: sql result
    """
    return db_cmd(sql, params, False)


def prepare_failed_name(release):
    # type: (str) -> str
    """Standardizes release name for failed DB
    :param release: release name
    :return: standardized release name
    """

    fixed = unquote(release)
    if fixed.endswith('.nzb'):
        fixed = fixed.rpartition('.')[0]

    fixed = re.sub(r'[.\-+ ]', '_', fixed)

    return fixed


def add_failed(release, puid=None, client=None, client_uid=None):
    # type: (str, str, int, str) -> None
    """

    :param release: release name
    :param puid: puid
    :param client: client id
    :param client_uid: client uid
    """
    size = -1
    provider = ''

    release = prepare_failed_name(release)

    if puid:
        sql_result = db_select('SELECT * FROM history t WHERE t.puid=?', [puid])
    else:
        sql_result = db_select('SELECT * FROM history t WHERE t.release=?', [release])

    if not any(sql_result):
        logger.warning('Release not found in failed.db snatch history')

    elif 1 < len(sql_result):
        logger.warning('Multiple logged snatches found for release in failed.db')
        sizes = len(set([x['size'] for x in sql_result]))
        providers = len(set([x['provider'] for x in sql_result]))

        if 1 == sizes:
            logger.warning('However, they\'re all the same size. Continuing with found size')
            size = sql_result[0]['size']

        else:
            logger.warning(
                'They also vary in size. Deleting logged snatches and recording this release with no size/provider')
            for cur_result in sql_result:
                remove_snatched(cur_result['release'], cur_result['size'], cur_result['provider'])

        if 1 == providers:
            logger.log('They\'re also from the same provider. Using it as well')
            provider = sql_result[0]['provider']
    else:
        size = sql_result[0]['size']
        provider = sql_result[0]['provider']

    if not has_failed(release, size, provider, puid=puid):
        db_action('INSERT INTO failed (`release`, `size`, `provider`, `puid`, `client`, `client_uid`)'
                  ' VALUES (?, ?, ?, ?, ?, ?)', [release, size, provider, puid, client, client_uid])

    remove_snatched(release, size, provider, puid=puid)


def add_snatched(search_result, client=None, client_uid=None):
    # type: (Union[NZBSearchResult, NZBDataSearchResult, TorrentSearchResult, Proper], int, Union[int, str]) -> None
    """
    :param search_result: SearchResult object
    :param client: client id from common
    :param client_uid: client uid
    """
    log_date = datetime.datetime.now().strftime(dateFormat)

    provider = 'unknown'
    if None is not search_result.provider:
        provider = search_result.provider.name

    client_uid = (None, client_uid)[isinstance(client_uid, (str, int))]

    for ep_obj in search_result.ep_obj_list:
        db_action(
            'INSERT INTO history (`date`, `size`, `release`, `provider`, `showid`, `season`, `episode`, `old_status`, '
            '`indexer`, `client`, `client_uid`, `puid`) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            [log_date, search_result.size, prepare_failed_name(search_result.name), provider,
             search_result.ep_obj_list[0].show_obj.prodid, ep_obj.season, ep_obj.episode, ep_obj.status,
             search_result.ep_obj_list[0].show_obj.tvid, client, client_uid, search_result.puid_str])


def set_episode_failed(ep_obj):
    # type: (TVEpisode) -> None
    """
    set episode object to failed

    :param ep_obj: episode object
    """
    try:
        with ep_obj.lock:
            quality = Quality.split_composite_status(ep_obj.status)[1]
            ep_obj.status = Quality.composite_status(FAILED, quality)
            ep_obj.save_to_db()

    except EpisodeNotFoundException as e:
        logger.warning(f'Unable to get episode, please set its status manually: {ex(e)}')


def remove_failed(release):
    # type: (str) -> None
    """

    :param release: release name
    """
    db_action(f'DELETE FROM history WHERE `release`=?', [prepare_failed_name(release)])


def remove_snatched(release, size, provider, puid=None):
    # type: (str, int, str, str) -> None
    """

    :param release: release name
    :param size: release size
    :param provider: provider name
    :param puid: puid
    """
    if puid:
        db_action('DELETE FROM history WHERE puid=?', [puid])
    else:
        db_action(f'DELETE FROM history WHERE `release`=? AND `size`=? AND `provider`=?',
                  [prepare_failed_name(release), size, provider])


def has_failed(release=None, size=None, provider='%', puid=None, client=None, client_uid=None):
    # type: (str, int, str, str, int, str) -> bool
    """
    Returns True if a release has previously failed.

    If provider is given, return True only if the release is found
    with that specific provider. Otherwise, return True if the release
    is found with any provider.

    Note: only uses 1 condition in priority of non empty/None parameters:
    1. puid
    2. client/client_uid
    3. release/size

    Note 2:
    only clients that provide real unique ids are checked:
    * sabnzbd

    :param release: release name
    :param size: size of release
    :param provider: provider name
    :param puid: puid
    :param client: client id
    :param client_uid: client uid
    :return: has failed
    """
    if puid:
        return any(db_select('SELECT * FROM failed t WHERE t.puid=? LIMIT 1', [puid]))

    elif client and client in DOWNLOAD_CLIENTS.TRUSTED_CLIENT_IDS and client_uid:
        return any(db_select('SELECT * FROM failed t WHERE t.client=? AND t.client_uid=? LIMIT 1',
                             [client, client_uid]))

    elif release and size:
        return any(db_select('SELECT * FROM failed t WHERE t.release=? AND t.size=? AND t.provider LIKE ? LIMIT 1',
                             [prepare_failed_name(release), size, provider]))

    return False


def revert_episode(ep_obj):
    # type: (TVEpisode) -> None
    """
    Restore the episodes of a failed download to their original state

    :param ep_obj: episode object
    """
    sql_result = db_select(
        'SELECT * FROM history t WHERE t.indexer=? AND t.showid=? AND t.season=?',
        [ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season])

    history_eps = {r['episode']: r for r in sql_result}

    try:
        logger.log(f'Reverting episode {ep_obj.season}x{ep_obj.episode}: [{ep_obj.name}]')
        with ep_obj.lock:
            if ep_obj.episode in history_eps:
                status_revert = history_eps[ep_obj.episode]['old_status']

                status, quality = Quality.split_composite_status(status_revert)
                logger.log(f'Found in failed.db history with'
                           f' status: {statusStrings[status]}'
                           f' quality: {Quality.qualityStrings[quality]}')
            else:
                status_revert = WANTED

                logger.warning('Episode not found in failed.db history. Setting it to WANTED')

            ep_obj.status = status_revert
            ep_obj.save_to_db()

    except EpisodeNotFoundException as e:
        logger.warning(f'Unable to create episode, please set its status manually: {ex(e)}')


def find_old_status(ep_obj):
    # type: (TVEpisode) -> Optional[int]
    """
    :param ep_obj: episode object
    :return: Old status if failed history item found
    """
    # Search for release in snatch history
    results = db_select(
        'SELECT t.old_status FROM history t WHERE t.indexer=? AND t.showid=? AND t.season=? AND t.episode=? '
        + 'ORDER BY t.date DESC LIMIT 1', [ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season, ep_obj.episode])
    if any(results):
        return results[0]['old_status']


def find_release(ep_obj):
    # type: (TVEpisode) -> Tuple[str, str]
    """
    Find releases in history by show ID and season.
    Return None for release if multiple found or no release found.
    :param ep_obj: episode object
    """
    # Clear old snatches for this release if any exist
    from_where = ' FROM history WHERE indexer=%s AND showid=%s AND season=%s AND episode=%s' % \
                 (ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season, ep_obj.episode)
    db_action(f'DELETE {from_where} AND date < (SELECT max(date) {from_where})')

    # Search for release in snatch history
    results = db_select(
        'SELECT t.release, t.provider, t.date FROM history t WHERE t.indexer=? AND t.showid=? AND t.season=? '
        'AND t.episode=?', [ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season, ep_obj.episode])

    if any(results):
        r = results[0]
        release = r['release']
        provider = r['provider']

        # Clear any incomplete snatch records for this release if any exist
        db_action(f'DELETE FROM history WHERE `release`=? AND `date`!=?', [release, r['date']])

        # Found a previously failed release
        logger.debug(f'Found failed.db history release {ep_obj.season}x{ep_obj.episode}: [{release}]')
    else:
        release = None
        provider = None

        # Release not found
        logger.debug(f'No found failed.db history release for'
                     f' {ep_obj.season}x{ep_obj.episode}: [{ep_obj.show_obj.unique_name}]')

    return release, provider
