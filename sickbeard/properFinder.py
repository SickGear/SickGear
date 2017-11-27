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

import datetime
import operator
import os
import threading
import traceback
import re

import sickbeard

from sickbeard import db, exceptions, helpers, history, logger, search, show_name_helpers
from sickbeard import encodingKludge as ek
from sickbeard.common import DOWNLOADED, SNATCHED_ANY, SNATCHED_PROPER, Quality, ARCHIVED, FAILED
from sickbeard.exceptions import ex, MultipleShowObjectsException
from sickbeard import failed_history
from sickbeard.history import dateFormat

from name_parser.parser import NameParser, InvalidNameException, InvalidShowException


def search_propers():

    if not sickbeard.DOWNLOAD_PROPERS:
        return

    logger.log(u'Beginning search for new propers')

    age_shows, age_anime = sickbeard.BACKLOG_DAYS + 2, 14
    aired_since_shows = datetime.datetime.today() - datetime.timedelta(days=age_shows)
    aired_since_anime = datetime.datetime.today() - datetime.timedelta(days=age_anime)
    recent_shows, recent_anime = _recent_history(aired_since_shows, aired_since_anime)
    if recent_shows or recent_anime:
        propers = _get_proper_list(aired_since_shows, recent_shows, recent_anime)

        if propers:
            _download_propers(propers)
    else:
        logger.log(u'No downloads or snatches found for the last %s%s days to use for a propers search' %
                   (age_shows, ('', ' (%s for anime)' % age_anime)[helpers.has_anime()]))

    _set_last_proper_search(datetime.datetime.today().toordinal())

    run_at = ''
    proper_sch = sickbeard.properFinderScheduler
    if None is proper_sch.start_time:
        run_in = proper_sch.lastRun + proper_sch.cycleTime - datetime.datetime.now()
        run_at = u', next check '
        if datetime.timedelta() > run_in:
            run_at += u'imminent'
        else:
            hours, remainder = divmod(run_in.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            run_at += u'in approx. ' + ('%dh, %dm' % (hours, minutes) if 0 < hours else '%dm, %ds' % (minutes, seconds))

    logger.log(u'Completed the search for new propers%s' % run_at)


def get_old_proper_level(showObj, indexer, indexerid, season, episodes, old_status, new_quality,
                         extra_no_name, version, is_anime=False):
    level = 0
    is_internal = False
    codec = ''
    if old_status not in SNATCHED_ANY:
        level = Quality.get_proper_level(extra_no_name, version, is_anime)
    elif showObj:
        myDB = db.DBConnection()
        np = NameParser(False, showObj=showObj)
        for episode in episodes:
            result = myDB.select('SELECT resource FROM history WHERE showid = ? AND season = ? AND episode = ? AND '
                                 '(' + ' OR '.join("action LIKE '%%%02d'" % x for x in SNATCHED_ANY) + ') '
                                 'ORDER BY date DESC LIMIT 1',
                                 [indexerid, season, episode])
            if not result or not isinstance(result[0]['resource'], basestring) or not result[0]['resource']:
                continue
            nq = Quality.sceneQuality(result[0]['resource'], showObj.is_anime)
            if nq != new_quality:
                continue
            try:
                p = np.parse(result[0]['resource'])
            except (StandardError, Exception):
                continue
            level = Quality.get_proper_level(p.extra_info_no_name(), p.version, showObj.is_anime)
            is_internal = p.extra_info_no_name() and re.search(r'\binternal\b', p.extra_info_no_name(), flags=re.I)
            codec = _get_codec(p.extra_info_no_name())
            break
    return level, is_internal, codec


def _get_codec(extra_info_no_name):
    if not extra_info_no_name:
        return ''
    if re.search(r'\b[xh]264\b', extra_info_no_name, flags=re.I):
        return '264'
    elif re.search(r'\bxvid\b', extra_info_no_name, flags=re.I):
        return 'xvid'
    elif re.search(r'\b[xh]265|hevc\b', extra_info_no_name, flags=re.I):
        return 'hevc'
    return ''


def _get_proper_list(aired_since_shows, recent_shows, recent_anime):
    propers = {}

    # for each provider get a list of the
    orig_thread_name = threading.currentThread().name
    providers = [x for x in sickbeard.providers.sortedProviderList() if x.is_active()]
    for cur_provider in providers:
        if not recent_anime and cur_provider.anime_only:
            continue
        threading.currentThread().name = orig_thread_name + ' :: [' + cur_provider.name + ']'

        logger.log(u'Searching for new PROPER releases')

        try:
            found_propers = cur_provider.find_propers(search_date=aired_since_shows, shows=recent_shows,
                                                      anime=recent_anime)
        except exceptions.AuthException as e:
            logger.log(u'Authentication error: ' + ex(e), logger.ERROR)
            continue
        except Exception as e:
            logger.log(u'Error while searching ' + cur_provider.name + ', skipping: ' + ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            continue
        finally:
            threading.currentThread().name = orig_thread_name

        # if they haven't been added by a different provider than add the proper to the list
        count = 0
        for x in found_propers:
            name = _generic_name(x.name)
            if name not in propers:
                try:
                    np = NameParser(False, try_scene_exceptions=True, showObj=x.parsed_show, indexer_lookup=False)
                    parse_result = np.parse(x.name)
                    if parse_result.series_name and parse_result.episode_numbers and \
                            (parse_result.show.indexer, parse_result.show.indexerid) in recent_shows + recent_anime:
                        cur_size = getattr(x, 'size', None)
                        if failed_history.has_failed(x.name, cur_size, cur_provider.name):
                            continue
                        logger.log(u'Found new proper: ' + x.name, logger.DEBUG)
                        x.show = parse_result.show.indexerid
                        x.provider = cur_provider
                        x.is_repack, x.properlevel = Quality.get_proper_level(parse_result.extra_info_no_name(),
                                                                              parse_result.version,
                                                                              parse_result.is_anime,
                                                                              check_is_repack=True)
                        x.is_internal = parse_result.extra_info_no_name() and \
                                        re.search(r'\binternal\b', parse_result.extra_info_no_name(), flags=re.I)
                        x.codec = _get_codec(parse_result.extra_info_no_name())
                        propers[name] = x
                        count += 1
                except (InvalidNameException, InvalidShowException):
                    continue
                except (StandardError, Exception):
                    continue

        cur_provider.log_result('Propers', count, '%s' % cur_provider.name)

    # take the list of unique propers and get it sorted by
    sorted_propers = sorted(propers.values(), key=operator.attrgetter('properlevel', 'date'), reverse=True)
    verified_propers = set()

    for cur_proper in sorted_propers:

        np = NameParser(False, try_scene_exceptions=True, showObj=cur_proper.parsed_show, indexer_lookup=False)
        try:
            parse_result = np.parse(cur_proper.name)
        except (StandardError, Exception):
            continue

        # set the indexerid in the db to the show's indexerid
        cur_proper.indexerid = parse_result.show.indexerid

        # set the indexer in the db to the show's indexer
        cur_proper.indexer = parse_result.show.indexer

        # populate our Proper instance
        cur_proper.season = parse_result.season_number if None is not parse_result.season_number else 1
        cur_proper.episode = parse_result.episode_numbers[0]
        cur_proper.release_group = parse_result.release_group
        cur_proper.version = parse_result.version
        cur_proper.extra_info = parse_result.extra_info
        cur_proper.extra_info_no_name = parse_result.extra_info_no_name
        cur_proper.quality = Quality.nameQuality(cur_proper.name, parse_result.is_anime)
        cur_proper.is_anime = parse_result.is_anime

        # only get anime proper if it has release group and version
        if parse_result.is_anime:
            if not cur_proper.release_group and -1 == cur_proper.version:
                logger.log(u'Proper %s doesn\'t have a release group and version, ignoring it' % cur_proper.name,
                           logger.DEBUG)
                continue

        if not show_name_helpers.pass_wordlist_checks(cur_proper.name, parse=False, indexer_lookup=False):
            logger.log(u'Proper %s isn\'t a valid scene release that we want, ignoring it' % cur_proper.name,
                       logger.DEBUG)
            continue

        re_extras = dict(re_prefix='.*', re_suffix='.*')
        result = show_name_helpers.contains_any(cur_proper.name, parse_result.show.rls_ignore_words, **re_extras)
        if None is not result and result:
            logger.log(u'Ignored: %s for containing ignore word' % cur_proper.name)
            continue

        result = show_name_helpers.contains_any(cur_proper.name, parse_result.show.rls_require_words, **re_extras)
        if None is not result and not result:
            logger.log(u'Ignored: %s for not containing any required word match' % cur_proper.name)
            continue

        # check if we actually want this proper (if it's the right quality)
        my_db = db.DBConnection()
        sql_results = my_db.select(
            'SELECT release_group, status, version, release_name FROM tv_episodes WHERE showid = ? AND indexer = ? ' +
            'AND season = ? AND episode = ?',
            [cur_proper.indexerid, cur_proper.indexer, cur_proper.season, cur_proper.episode])
        if not sql_results:
            continue

        # only keep the proper if we have already retrieved the same quality ep (don't get better/worse ones)
        # don't take proper of the same level we already downloaded
        old_status, old_quality = Quality.splitCompositeStatus(int(sql_results[0]['status']))
        cur_proper.is_repack, cur_proper.proper_level = Quality.get_proper_level(cur_proper.extra_info_no_name(),
                                                                                 cur_proper.version,
                                                                                 cur_proper.is_anime,
                                                                                 check_is_repack=True)

        old_release_group = sql_results[0]['release_group']
        # check if we want this release: same quality as current, current has correct status
        # restrict other release group releases to proper's
        if old_status not in SNATCHED_ANY + [DOWNLOADED, ARCHIVED] \
                or cur_proper.quality != old_quality \
                or (cur_proper.is_repack and cur_proper.release_group != old_release_group):
            continue

        np = NameParser(False, try_scene_exceptions=True, showObj=parse_result.show, indexer_lookup=False)
        try:
            extra_info = np.parse(sql_results[0]['release_name']).extra_info_no_name()
        except (StandardError, Exception):
            extra_info = None

        old_proper_level, old_is_internal, old_codec = get_old_proper_level(parse_result.show, cur_proper.indexer,
                                                                            cur_proper.indexerid, cur_proper.season,
                                                                            parse_result.episode_numbers, old_status,
                                                                            cur_proper.quality, extra_info,
                                                                            cur_proper.version, cur_proper.is_anime)
        if cur_proper.proper_level < old_proper_level:
            continue
        elif cur_proper.proper_level == old_proper_level:
            if '264' == cur_proper.codec and 'xvid' == old_codec:
                pass
            elif old_is_internal and not cur_proper.is_internal:
                pass
            else:
                continue

        log_same_grp = 'Skipping proper from release group: [%s], does not match existing release group: [%s] for [%s]'\
                       % (cur_proper.release_group, old_release_group, cur_proper.name)

        # for webldls, prevent propers from different groups
        if sickbeard.PROPERS_WEBDL_ONEGRP and \
                (old_quality in (Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB) or
                    (old_quality == Quality.SDTV and re.search(r'\Wweb.?(dl|rip|.[hx]26[45])\W', str(sql_results[0]['release_name']), re.I))) and \
                cur_proper.release_group != old_release_group:
            logger.log(log_same_grp, logger.DEBUG)
            continue

        # check if we actually want this proper (if it's the right release group and a higher version)
        if parse_result.is_anime:

            old_version = int(sql_results[0]['version'])
            if -1 < old_version < cur_proper.version:
                logger.log(u'Found new anime v%s to replace existing v%s' % (cur_proper.version, old_version))
            else:
                continue

            if cur_proper.release_group != old_release_group:
                logger.log(log_same_grp, logger.DEBUG)
                continue

        # if the show is in our list and there hasn't been a proper already added for that particular episode
        # then add it to our list of propers
        if cur_proper.indexerid != -1:
            if (cur_proper.indexerid, cur_proper.indexer, cur_proper.season, cur_proper.episode) not in map(
                    operator.attrgetter('indexerid', 'indexer', 'season', 'episode'), verified_propers):
                logger.log(u'Found a proper that may be useful: %s' % cur_proper.name)
                verified_propers.add(cur_proper)
            else:
                rp = set()
                for vp in verified_propers:
                    if vp.indexer == cur_proper.indexer and vp.indexerid == cur_proper.indexerid and \
                                    vp.season == cur_proper.season and vp.episode == cur_proper.episode and \
                                    vp.proper_level < cur_proper.proper_level:
                        rp.add(vp)
                if rp:
                    verified_propers = verified_propers - rp
                    logger.log(u'Found a proper that may be useful: %s' % cur_proper.name)
                    verified_propers.add(cur_proper)

    return list(verified_propers)


def _download_propers(proper_list):

    for cur_proper in proper_list:

        history_limit = datetime.datetime.today() - datetime.timedelta(days=30)

        # make sure the episode has been downloaded before
        my_db = db.DBConnection()
        history_results = my_db.select(
            'SELECT resource FROM history ' +
            'WHERE showid = ? AND season = ? AND episode = ? AND quality = ? AND date >= ? ' +
            'AND (' + ' OR '.join("action LIKE '%%%02d'" % x for x in SNATCHED_ANY + [DOWNLOADED, ARCHIVED]) + ')',
            [cur_proper.indexerid, cur_proper.season, cur_proper.episode, cur_proper.quality,
             history_limit.strftime(history.dateFormat)])

        # if we didn't download this episode in the first place we don't know what quality to use for the proper = skip
        if 0 == len(history_results):
            logger.log(u'Skipping download because cannot find an original history entry for proper ' + cur_proper.name)
            continue

        else:

            # get the show object
            show_obj = helpers.findCertainShow(sickbeard.showList, cur_proper.indexerid)
            if None is show_obj:
                logger.log(u'Unable to find the show with indexerid ' + str(
                    cur_proper.indexerid) + ' so unable to download the proper', logger.ERROR)
                continue

            # make sure that none of the existing history downloads are the same proper we're trying to download
            clean_proper_name = _generic_name(helpers.remove_non_release_groups(cur_proper.name, show_obj.is_anime))
            is_same = False
            for result in history_results:
                # if the result exists in history already we need to skip it
                if clean_proper_name == _generic_name(helpers.remove_non_release_groups(
                        ek.ek(os.path.basename, result['resource']))):
                    is_same = True
                    break
            if is_same:
                logger.log(u'This proper is already in history, skipping it', logger.DEBUG)
                continue

            ep_obj = show_obj.getEpisode(cur_proper.season, cur_proper.episode)

            # make the result object
            result = cur_proper.provider.get_result([ep_obj], cur_proper.url)
            if None is result:
                continue
            result.name = cur_proper.name
            result.quality = cur_proper.quality
            result.version = cur_proper.version
            result.properlevel = cur_proper.proper_level
            result.is_repack = cur_proper.is_repack
            result.puid = cur_proper.puid

            # snatch it
            search.snatch_episode(result, SNATCHED_PROPER)


def _recent_history(aired_since_shows, aired_since_anime):

    recent_shows, recent_anime = [], []

    my_db = db.DBConnection()

    sql_results = my_db.select(
        'SELECT DISTINCT s.indexer, s.indexer_id FROM history as h' +
        ' INNER JOIN tv_episodes AS e ON (h.showid == e.showid AND h.season == e.season AND h.episode == e.episode)' +
        ' INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id)' +
        ' WHERE h.date >= %s' % min(aired_since_shows, aired_since_anime).strftime(dateFormat) +
        ' AND (%s)' % ' OR '.join(['h.action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, FAILED]])
    )

    for sqlshow in sql_results:
        try:
            show = helpers.find_show_by_id(sickbeard.showList, {int(sqlshow['indexer']): int(sqlshow['indexer_id'])})
        except MultipleShowObjectsException:
            continue
        if show:
            if not show.is_anime:
                (sqlshow['indexer'], sqlshow['indexer_id']) not in recent_shows and \
                    recent_shows.append((sqlshow['indexer'], sqlshow['indexer_id']))
            else:
                (sqlshow['indexer'], sqlshow['indexer_id']) not in recent_anime and show.is_anime and \
                    recent_anime.append((sqlshow['indexer'], sqlshow['indexer_id']))

    return recent_shows, recent_anime


def _generic_name(name):
    return name.replace('.', ' ').replace('-', ' ').replace('_', ' ').lower()


def _set_last_proper_search(when):

    logger.log(u'Setting the last Proper search in the DB to %s' % when, logger.DEBUG)

    my_db = db.DBConnection()
    sql_results = my_db.select('SELECT * FROM info')

    if 0 == len(sql_results):
        my_db.action('INSERT INTO info (last_backlog, last_indexer, last_proper_search) VALUES (?,?,?)',
                     [0, 0, str(when)])
    else:
        my_db.action('UPDATE info SET last_proper_search=%s' % when)


def _get_last_proper_search():

    my_db = db.DBConnection()
    sql_results = my_db.select('SELECT * FROM info')

    try:
        last_proper_search = datetime.date.fromordinal(int(sql_results[0]['last_proper_search']))
    except (StandardError, Exception):
        return datetime.date.fromordinal(1)

    return last_proper_search
