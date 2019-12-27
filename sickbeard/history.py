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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from . import db
import datetime

from . import helpers, logger
from .common import FAILED, SNATCHED, SNATCHED_PROPER, SUBTITLED, Quality
from .name_parser.parser import NameParser
import sickbeard

from six import PY2, text_type

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr


dateFormat = '%Y%m%d%H%M%S'


def _log_history_item(action, tvid, prodid, season, episode, quality, resource, provider, version=-1):
    # type: (int, int, int, int, int, int, AnyStr, AnyStr, int) -> None
    """

    :param action: action
    :param tvid: tvid
    :param prodid: prodid
    :param season: season number
    :param episode: episode number
    :param quality: quality
    :param provider: provider name
    :param version: version
    """
    log_date = datetime.datetime.today().strftime(dateFormat)

    if PY2 and not isinstance(resource, text_type):
        resource = text_type(resource, 'utf-8', 'replace')

    my_db = db.DBConnection()
    my_db.action(
        'INSERT INTO history (action, date, showid, season, episode, quality, resource, provider, version, indexer)'
        ' VALUES (?,?,?,?,?,?,?,?,?,?)',
        [action, log_date, int(prodid), int(season), int(episode), quality, resource, provider, version, int(tvid)])


def log_snatch(search_result):
    # type: (sickbeard.classes.SearchResult) -> None
    """
    log search result to db

    :param search_result: search result
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

        action = Quality.compositeStatus((SNATCHED, SNATCHED_PROPER)[is_proper], search_result.quality)

        resource = search_result.name

        _log_history_item(action, cur_ep_obj.show_obj.tvid, cur_ep_obj.show_obj.prodid,
                          cur_ep_obj.season, cur_ep_obj.episode, quality, resource, provider, version)


def log_download(ep_obj, filename, new_ep_quality, release_group=None, version=-1):
    # type: (sickbeard.tv.TVEpisode, AnyStr, int, AnyStr, int) -> None
    """
    log download of episode

    :param ep_obj: episode objects
    :param filename: filename
    :param new_ep_quality: new episode quality
    :param release_group: release group
    :param version: version
    """
    quality = new_ep_quality

    # store the release group as the provider if possible
    if release_group:
        provider = release_group
    else:
        provider = -1

    action = ep_obj.status

    _log_history_item(action, ep_obj.show_obj.tvid, ep_obj.show_obj.prodid,
                      ep_obj.season, ep_obj.episode, quality, filename, provider, version)


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
    status, quality = Quality.splitCompositeStatus(status)
    action = Quality.compositeStatus(SUBTITLED, quality)

    _log_history_item(action, tvid, prodid, season, episode, quality, resource, provider)


def log_failed(ep_obj, release, provider=None):
    # type: (sickbeard.tv.TVEpisode, AnyStr, AnyStr) -> None
    """
    log failed downloaded episode

    :param ep_obj: episode object
    :param release: release
    :param provider: provider name
    """
    status, quality = Quality.splitCompositeStatus(ep_obj.status)
    action = Quality.compositeStatus(FAILED, quality)

    _log_history_item(action, ep_obj.show_obj.tvid, ep_obj.show_obj.prodid,
                      ep_obj.season, ep_obj.episode, quality, release, provider)


def reset_status(tvid, prodid, season, episode):
    # type: (int, int, int, int) -> None
    """
    Revert episode history to status from download history, if history exists

    :param tvid: tvid
    :param prodid: prodid
    :param season: season number
    :param episode: episode number
    """
    my_db = db.DBConnection()

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

    sql_history = my_db.select(history_sql, [str(tvid), str(prodid), str(season), str(episode)])
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

            my_db.action(undo_status, [history['action'],
                                       history['tv_id'], history['prod_id'],
                                       history['season'], history['episode']])


def history_snatched_proper_fix():
    my_db = db.DBConnection()
    if not my_db.has_flag('history_snatch_proper'):
        logger.log('Updating history items with status Snatched Proper in a background process...')
        # noinspection SqlResolve
        sql_result = my_db.select('SELECT rowid, `resource`, quality,'
                                  ' indexer AS tv_id, showid AS prod_id'
                                  ' FROM history'
                                  ' WHERE action LIKE "%%%02d"' % SNATCHED +
                                  ' AND (UPPER(resource) LIKE "%PROPER%"'
                                  ' OR UPPER(resource) LIKE "%REPACK%"'
                                  ' OR UPPER(resource) LIKE "%REAL%")')
        if sql_result:
            cl = []
            for r in sql_result:
                show_obj = None
                try:
                    show_obj = helpers.find_show_by_id({int(r['tv_id']): int(r['prod_id'])})
                except (BaseException, Exception):
                    pass
                np = NameParser(False, show_obj=show_obj, testing=True)
                try:
                    pr = np.parse(r['resource'])
                except (BaseException, Exception):
                    continue
                if 0 < Quality.get_proper_level(pr.extra_info_no_name(), pr.version, pr.is_anime):
                    cl.append(['UPDATE history SET action = ? WHERE rowid = ?',
                               [Quality.compositeStatus(SNATCHED_PROPER, int(r['quality'])),
                                r['rowid']]])
            if cl:
                my_db.mass_action(cl)
            logger.log('Completed the history table update with status Snatched Proper.')
        my_db.add_flag('history_snatch_proper')
