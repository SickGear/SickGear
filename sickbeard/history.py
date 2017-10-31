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

import db
import datetime

import sickbeard
from sickbeard import helpers, logger
from sickbeard.common import SNATCHED, SNATCHED_PROPER, SUBTITLED, FAILED, Quality
from sickbeard.name_parser.parser import NameParser


dateFormat = '%Y%m%d%H%M%S'


def _log_history_item(action, showid, season, episode, quality, resource, provider, version=-1):
    log_date = datetime.datetime.today().strftime(dateFormat)

    if not isinstance(resource, unicode):
        resource = unicode(resource, 'utf-8', 'replace')

    my_db = db.DBConnection()
    my_db.action(
        'INSERT INTO history (action, date, showid, season, episode, quality, resource, provider, version)'
        ' VALUES (?,?,?,?,?,?,?,?,?)',
        [action, log_date, showid, season, episode, quality, resource, provider, version])


def log_snatch(search_result):
    for curEpObj in search_result.episodes:

        showid = int(curEpObj.show.indexerid)
        season = int(curEpObj.season)
        episode = int(curEpObj.episode)
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

        _log_history_item(action, showid, season, episode, quality, resource, provider, version)


def log_download(episode, filename, new_ep_quality, release_group=None, version=-1):
    showid = int(episode.show.indexerid)
    season = int(episode.season)
    ep_num = int(episode.episode)

    quality = new_ep_quality

    # store the release group as the provider if possible
    if release_group:
        provider = release_group
    else:
        provider = -1

    action = episode.status

    _log_history_item(action, showid, season, ep_num, quality, filename, provider, version)


def log_subtitle(showid, season, episode, status, subtitle_result):
    resource = subtitle_result.path
    provider = subtitle_result.service
    status, quality = Quality.splitCompositeStatus(status)
    action = Quality.compositeStatus(SUBTITLED, quality)

    _log_history_item(action, showid, season, episode, quality, resource, provider)


def log_failed(ep_obj, release, provider=None):
    showid = int(ep_obj.show.indexerid)
    season = int(ep_obj.season)
    ep_num = int(ep_obj.episode)
    status, quality = Quality.splitCompositeStatus(ep_obj.status)
    action = Quality.compositeStatus(FAILED, quality)

    _log_history_item(action, showid, season, ep_num, quality, release, provider)


def reset_status(indexerid, season, episode):
    """ Revert episode history to status from download history,
        if history exists """
    my_db = db.DBConnection()

    history_sql = 'SELECT h.action, h.showid, h.season, h.episode, t.status' \
        ' FROM history AS h' \
                  ' INNER JOIN tv_episodes AS t' \
                  ' ON h.showid = t.showid AND h.season = t.season AND h.episode = t.episode' \
                  ' WHERE t.showid = ? AND t.season = ? AND t.episode = ?' \
                  ' GROUP BY h.action' \
                  ' ORDER BY h.date DESC' \
                  ' LIMIT 1'

    sql_history = my_db.select(history_sql, [str(indexerid), str(season), str(episode)])
    if 1 == len(sql_history):
        history = sql_history[0]

        # update status only if status differs
        # FIXME: this causes issues if the user changed status manually
        #        replicating refactored behavior anyway.
        if history['status'] != history['action']:
            undo_status = 'UPDATE tv_episodes SET status = ?' \
                          ' WHERE showid = ? AND season = ? AND episode = ?'

            my_db.action(undo_status, [history['action'],
                                       history['showid'],
                                       history['season'],
                                       history['episode']])


def history_snatched_proper_fix():
    my_db = db.DBConnection()
    if not my_db.has_flag('history_snatch_proper'):
        logger.log('Updating history items with status Snatched Proper in a background process...')
        sql_result = my_db.select('SELECT rowid, resource, quality, showid'
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
                    show_obj = helpers.findCertainShow(sickbeard.showList, int(r['showid']))
                except (StandardError, Exception):
                    pass
                np = NameParser(False, showObj=show_obj, testing=True)
                try:
                    pr = np.parse(r['resource'])
                except (StandardError, Exception):
                    continue
                if 0 < Quality.get_proper_level(pr.extra_info_no_name(), pr.version, pr.is_anime):
                    cl.append(['UPDATE history SET action = ? WHERE rowid = ?',
                               [Quality.compositeStatus(SNATCHED_PROPER, int(r['quality'])),
                                r['rowid']]])
            if cl:
                my_db.mass_action(cl)
            logger.log('Completed the history table update with status Snatched Proper.')
        my_db.add_flag('history_snatch_proper')
