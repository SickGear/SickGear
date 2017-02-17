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

import datetime
import re
import urllib

from sickbeard import db, logger
from sickbeard.common import FAILED, WANTED, Quality, statusStrings
from sickbeard.exceptions import EpisodeNotFoundException, ex
from sickbeard.history import dateFormat


def db_cmd(sql, params, select=True):

    my_db = db.DBConnection('failed.db')
    sql_result = select and my_db.select(sql, params) or my_db.action(sql, params)
    return sql_result


def db_select(sql, params):

    return db_cmd(sql, params)


def db_action(sql, params=None):

    return db_cmd(sql, params, False)


def prepare_failed_name(release):
    """Standardizes release name for failed DB"""

    fixed = urllib.unquote(release)
    if fixed.endswith('.nzb'):
        fixed = fixed.rpartition('.')[0]

    fixed = re.sub('[.\-+ ]', '_', fixed)

    if not isinstance(fixed, unicode):
        fixed = unicode(fixed, 'utf-8', 'replace')

    return fixed


def add_failed(release):

    size = -1
    provider = ''

    release = prepare_failed_name(release)

    sql_results = db_select('SELECT * FROM history t WHERE t.release=?', [release])

    if not any(sql_results):
        logger.log('Release not found in failed.db snatch history', logger.WARNING)

    elif 1 < len(sql_results):
        logger.log('Multiple logged snatches found for release in failed.db', logger.WARNING)
        sizes = len(set(x['size'] for x in sql_results))
        providers = len(set(x['provider'] for x in sql_results))

        if 1 == sizes:
            logger.log('However, they\'re all the same size. Continuing with found size', logger.WARNING)
            size = sql_results[0]['size']

        else:
            logger.log(
                'They also vary in size. Deleting logged snatches and recording this release with no size/provider',
                logger.WARNING)
            for result in sql_results:
                remove_snatched(result['release'], result['size'], result['provider'])

        if 1 == providers:
            logger.log('They\'re also from the same provider. Using it as well')
            provider = sql_results[0]['provider']
    else:
        size = sql_results[0]['size']
        provider = sql_results[0]['provider']

    if not has_failed(release, size, provider):
        db_action('INSERT INTO failed (`release`, `size`, `provider`) VALUES (?, ?, ?)', [release, size, provider])

    remove_snatched(release, size, provider)


def add_snatched(search_result):
    """
    :param search_result: SearchResult object
    """

    log_date = datetime.datetime.today().strftime(dateFormat)

    provider = 'unknown'
    if None is not search_result.provider:
        provider = search_result.provider.name

    for episode in search_result.episodes:
        db_action(
            'INSERT INTO history (`date`, `size`, `release`, `provider`, `showid`, `season`, `episode`, `old_status`)'
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [log_date, search_result.size, prepare_failed_name(search_result.name), provider,
             search_result.episodes[0].show.indexerid, episode.season, episode.episode, episode.status])


def set_episode_failed(ep_obj):

    try:
        with ep_obj.lock:
            quality = Quality.splitCompositeStatus(ep_obj.status)[1]
            ep_obj.status = Quality.compositeStatus(FAILED, quality)
            ep_obj.saveToDB()

    except EpisodeNotFoundException as e:
        logger.log('Unable to get episode, please set its status manually: %s' % ex(e), logger.WARNING)


def remove_failed(release):

    db_action('DELETE FROM history WHERE %s=?' % '`release`', [prepare_failed_name(release)])


def remove_snatched(release, size, provider):

    db_action('DELETE FROM history WHERE %s=? AND %s=? AND %s=?' % ('`release`', '`size`', '`provider`'),
              [prepare_failed_name(release), size, provider])


def remove_old_history():

    db_action('DELETE FROM history WHERE date < %s' %
              str((datetime.datetime.today() - datetime.timedelta(days=30)).strftime(dateFormat)))


def has_failed(release, size, provider='%'):
    """
    Returns True if a release has previously failed.

    If provider is given, return True only if the release is found
    with that specific provider. Otherwise, return True if the release
    is found with any provider.
    """
    return any(db_select('SELECT * FROM failed t WHERE t.release=? AND t.size=? AND t.provider LIKE ?',
                         [prepare_failed_name(release), size, provider]))


def revert_episode(ep_obj):
    """Restore the episodes of a failed download to their original state"""
    sql_results = db_select(
        'SELECT * FROM history t WHERE t.showid=? AND t.season=?', [ep_obj.show.indexerid, ep_obj.season])

    history_eps = {r['episode']: r for r in sql_results}

    try:
        logger.log('Reverting episode %sx%s: [%s]' % (ep_obj.season, ep_obj.episode, ep_obj.name))
        with ep_obj.lock:
            if ep_obj.episode in history_eps:
                status_revert = history_eps[ep_obj.episode]['old_status']

                status, quality = Quality.splitCompositeStatus(status_revert)
                logger.log('Found in failed.db history with status: %s quality: %s' % (
                    statusStrings[status], Quality.qualityStrings[quality]))
            else:
                status_revert = WANTED

                logger.log('Episode not found in failed.db history. Setting it to WANTED', logger.WARNING)

            ep_obj.status = status_revert
            ep_obj.saveToDB()

    except EpisodeNotFoundException as e:
        logger.log('Unable to create episode, please set its status manually: %s' % ex(e), logger.WARNING)


def find_old_status(ep_obj):
    """
    :param ep_obj:
    :return: Old status if failed history item found
    """
    # Search for release in snatch history
    results = db_select(
        'SELECT t.old_status FROM history t WHERE t.showid=? AND t.season=? AND t.episode=? '
        + 'ORDER BY t.date DESC LIMIT 1', [ep_obj.show.indexerid, ep_obj.season, ep_obj.episode])
    if any(results):
        return results[0]['old_status']


def find_release(ep_obj):
    """
    Find releases in history by show ID and season.
    Return None for release if multiple found or no release found.
    """
    # Clear old snatches for this release if any exist
    from_where = ' FROM history WHERE showid=%s AND season=%s AND episode=%s' % \
                 (ep_obj.show.indexerid, ep_obj.season, ep_obj.episode)
    db_action('DELETE %s AND date < (SELECT max(date) %s)' % (from_where, from_where))

    # Search for release in snatch history
    results = db_select(
        'SELECT t.release, t.provider, t.date FROM history t WHERE t.showid=? AND t.season=? AND t.episode=?',
        [ep_obj.show.indexerid, ep_obj.season, ep_obj.episode])

    if any(results):
        r = results[0]
        release = r['release']
        provider = r['provider']

        # Clear any incomplete snatch records for this release if any exist
        db_action('DELETE FROM history WHERE %s=? AND %s!=?' % ('`release`', '`date`'), [release, r['date']])

        # Found a previously failed release
        logger.log('Found failed.db history release %sx%s: [%s]' % (
            ep_obj.season, ep_obj.episode, release), logger.DEBUG)
    else:
        release = None
        provider = None

        # Release not found
        logger.log('No found failed.db history release for %sx%s: [%s]' % (
            ep_obj.season, ep_obj.episode, ep_obj.show.name), logger.DEBUG)

    return release, provider
