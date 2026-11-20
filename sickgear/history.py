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

import datetime

import sickgear
from . import db
from . import helpers, logger
from .common import DOWNLOAD_CLIENTS, FAILED, SNATCHED, SNATCHED_BEST, SNATCHED_PROPER, SUBTITLED, Quality
from .name_parser.parser import NameParser

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Optional, Tuple, Union
    from .tv import TVShow, TVEpisode
    from sqlite3 import Row


dateFormat = '%Y%m%d%H%M%S'


def _log_history_item(action, tvid, prodid, season, episode, quality, resource, provider, version=-1, puid=None,
                      client=None, client_uid=None):
    # type: (int, int, int, int, int, int, AnyStr, AnyStr, int, Optional[str], Optional[ind], Optional[int]) -> None
    """

    :param action: action
    :param tvid: tvid
    :param prodid: prodid
    :param season: season number
    :param episode: episode number
    :param quality: quality
    :param provider: provider name
    :param version: version
    :param puid: puid of result
    :param client_uid: client uid
    """
    log_date = datetime.datetime.now().strftime(dateFormat)

    with db.DBConnection() as sg_db:
        sg_db.action(
            'INSERT INTO history'
            ' (action, date, showid, season, episode, quality, resource, provider, version, indexer, hide, puid,'
            ' client, client_uid)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [action, log_date, int(prodid), int(season), int(episode), quality, resource, provider, version,
             int(tvid), 0, puid, client, client_uid])


def log_snatch(search_result, client=None, client_result=None):
    # type: (sickgear.classes.SearchResult, Optional[int], Union[str, int, bool]) -> None
    """
    log search result to db

    :param search_result: search result
    :param client: client from common DOWNLOAD_CLIENTS
    :param client_result: client result
    """
    for cur_ep_obj in search_result.ep_obj_list:

        quality = search_result.quality
        version = search_result.version
        is_proper = 0 < search_result.properlevel

        provider_class = search_result.provider
        if None is not provider_class:
            provider = provider_class.name
        else:
            provider = 'unknown'

        action = Quality.composite_status((SNATCHED, SNATCHED_PROPER)[is_proper], search_result.quality)

        resource = search_result.name

        client_uid = (None, client_result)[isinstance(client_result, (str, int))]

        _log_history_item(action, cur_ep_obj.show_obj.tvid, cur_ep_obj.show_obj.prodid,
                          cur_ep_obj.season, cur_ep_obj.episode, quality, resource, provider, version,
                          search_result.puid_str, client, client_uid)


def log_download(ep_obj, filename, new_ep_quality, release_group=None, version=-1, puid=None,
                      client=None, client_uid=None):
    # type: (sickgear.tv.TVEpisode, AnyStr, int, AnyStr, int, Optional[str], Optional[int], Optional[int]) -> None
    """
    log download of episode

    :param ep_obj: episode objects
    :param filename: filename
    :param new_ep_quality: new episode quality
    :param release_group: release group
    :param version: version
    :param puid: puid
    :param client: client from common DOWNLOAD_CLIENTS
    :param client_uid: client uid
    """
    quality = new_ep_quality

    # store the release group as the provider if possible
    if release_group:
        provider = release_group
    else:
        provider = -1

    action = ep_obj.status

    _log_history_item(action, ep_obj.show_obj.tvid, ep_obj.show_obj.prodid,
                      ep_obj.season, ep_obj.episode, quality, filename, provider, version,
                      puid, client, client_uid)


def log_subtitle(tvid, prodid, season, episode, status, subtitle_result):
    # type: (int, int, int, int, int, Any ) -> None
    """
    log subtitle download

    :param tvid: tvid
    :param prodid: prodid
    :param season: season number
    :param episode: episode number
    :param status: episode status
    :param subtitle_result: subtitle result
    :type subtitle_result:
    """
    resource = subtitle_result.path
    provider = subtitle_result.service
    status, quality = Quality.split_composite_status(status)
    action = Quality.composite_status(SUBTITLED, quality)

    _log_history_item(action, tvid, prodid, season, episode, quality, resource, provider)


def log_failed(ep_obj, release, provider=None, client=None, client_uid=None, puid=None):
    # type: (TVEpisode, str, str, int, Union[int, str], str) -> None
    """
    log failed downloaded episode

    :param ep_obj: episode object
    :param release: release
    :param provider: provider name
    :param client: client id from common
    :param client_uid: client uid
    :param puid: puid
    """
    status, quality = Quality.split_composite_status(ep_obj.status)
    action = Quality.composite_status(FAILED, quality)

    _log_history_item(action, ep_obj.show_obj.tvid, ep_obj.show_obj.prodid,
                      ep_obj.season, ep_obj.episode, quality, release, provider,
                      client=client, client_uid=client_uid, puid=puid)


def reset_status(tvid, prodid, season, episode):
    # type: (int, int, int, int) -> None
    """
    Revert episode history to status from download history, if history exists

    :param tvid: tvid
    :param prodid: prodid
    :param season: season number
    :param episode: episode number
    """
    history_sql = 'SELECT h.action,  h.indexer AS tv_id, h.showid AS prod_id, h.season, h.episode, t.status' \
                  ' FROM history AS h' \
                  ' INNER JOIN tv_episodes AS t' \
                  ' ON h.indexer = t.indexer AND h.showid = t.showid' \
                  ' AND h.season = t.season AND h.episode = t.episode' \
                  ' WHERE t.indexer = ? AND t.showid = ?' \
                  ' AND t.season = ? AND t.episode = ?' \
                  ' GROUP BY h.action' \
                  ' ORDER BY h.date DESC' \
                  ' LIMIT 1'

    with db.DBConnection() as sg_db:
        sql_history = sg_db.select(history_sql, [str(tvid), str(prodid), str(season), str(episode)])
        if 1 == len(sql_history):
            history = sql_history[0]

            # update status only if status differs
            # FIXME: this causes issues if the user changed status manually
            #        replicating refactored behavior anyway.
            if history['status'] != history['action']:
                undo_status = 'UPDATE tv_episodes' \
                              ' SET status = ?' \
                              ' WHERE indexer = ? AND showid = ?' \
                              ' AND season = ? AND episode = ?'

                sg_db.action(undo_status, [history['action'],
                                           history['tv_id'], history['prod_id'],
                                           history['season'], history['episode']])


def find_show_by_puidstr(puid_str):
    # type: (str) -> TVShow
    with db.DBConnection() as my_db:
        if (sql_result := my_db.select(
                f'SELECT * FROM history WHERE puid = ? AND'
                f' (action LIKE "%{SNATCHED:02d}" OR action LIKE "%{SNATCHED_PROPER:02d}"'
                f' OR action LIKE "%{SNATCHED_BEST:02d}") LIMIT 1', [puid_str])):
            show_obj = None
            try:
                show_obj = helpers.find_show_by_id({int(sql_result[0]['indexer']): int(sql_result[0]['showid'])},
                                                   check_multishow=True)
            except (BaseException, Exception):
                pass
            return show_obj


def find_data_by_puidstr(puid_str):
    # type: (str) -> Optional[Row]
    """
    Returns the sql row or None of the matching history table

    :param puid_str: puid of download
    :return: Sql Row
    """
    with db.DBConnection() as my_db:
        if (sql_result := my_db.select(
                f'SELECT * FROM history WHERE puid = ? AND'
                f' (action LIKE "%{SNATCHED:02d}" OR action LIKE "%{SNATCHED_PROPER:02d}"'
                f' OR action LIKE "%{SNATCHED_BEST:02d}") LIMIT 1', [puid_str])):
            return sql_result[0]
    return None


def find_show_puid_by_client_uid(client, client_uid):
    # type: (int, Union[int, str]) -> Tuple[TVShow, str]
    """
    get show object and puid by client and client_uid from history db
    only looks for snatched entries

    :param client: client from common.DOWNLOAD_CLIENTS
    :param client_uid: uid send from client
    """
    show_obj = None
    puid = None
    if client in DOWNLOAD_CLIENTS.TRUSTED_CLIENT_IDS:
        with db.DBConnection() as my_db:
            if (sql_result := my_db.select(
                    f'SELECT * FROM history WHERE client = ? AND client_uid = ? AND'
                    f' (action LIKE "%{SNATCHED:02d}" OR action LIKE "%{SNATCHED_PROPER:02d}"'
                    f' OR action LIKE "%{SNATCHED_BEST:02d}") LIMIT 1', [client, client_uid])):
                try:
                    show_obj = helpers.find_show_by_id({int(sql_result[0]['indexer']): int(sql_result[0]['showid'])},
                                                       check_multishow=True)
                    puid = sql_result[0]['puid']
                except (BaseException, Exception):
                    pass
    return show_obj, puid


def find_show_by_client_uid(client, client_uid):
    # type: (int, Union[int, str]) -> TVShow
    """
    get show object by client and client_uid from history db
    only looks for snatched entries

    :param client: client from common.DOWNLOAD_CLIENTS
    :param client_uid: uid send from client
    """
    return find_show_puid_by_client_uid(client, client_uid)[0]


def history_snatched_proper_fix():
    with db.DBConnection() as sg_db:
        if not sg_db.has_flag('history_snatch_proper'):
            logger.log('Updating history items with status Snatched Proper in a background process...')
            # noinspection SqlResolve
            sql_result = sg_db.select('SELECT rowid, `resource`, quality,'
                                      ' indexer AS tv_id, showid AS prod_id'
                                      ' FROM history'
                                      " WHERE action LIKE '%%%02d'" % SNATCHED +
                                      " AND (UPPER(resource) LIKE '%PROPER%'"
                                      " OR UPPER(resource) LIKE '%REPACK%'"
                                      " OR UPPER(resource) LIKE '%REAL%')")
            if sql_result:
                sql_l = []
                for r in sql_result:
                    show_obj = None
                    try:
                        show_obj = helpers.find_show_by_id({int(r['tv_id']): int(r['prod_id'])}, check_multishow=True)
                    except (BaseException, Exception):
                        pass
                    np = NameParser(False, show_obj=show_obj, testing=True)
                    try:
                        pr = np.parse(r['resource'])
                    except (BaseException, Exception):
                        continue
                    if 0 < Quality.get_proper_level(pr.extra_info_no_name(), pr.version, pr.is_anime):
                        sql_l.append(['UPDATE history SET action = ? WHERE rowid = ?',
                                      [Quality.composite_status(SNATCHED_PROPER, int(r['quality'])),
                                       r['rowid']]])
                if sql_l:
                    sg_db.mass_action(sql_l)
                logger.log('Completed the history table update with status Snatched Proper.')
            sg_db.add_flag('history_snatch_proper')
