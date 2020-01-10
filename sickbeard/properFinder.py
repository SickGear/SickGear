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
import re
import threading
import traceback

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex, MultipleShowObjectsException, AuthException

import sickbeard
from . import db, failed_history, helpers, history, logger, search, show_name_helpers
from .classes import Proper
from .common import ARCHIVED, FAILED, DOWNLOADED, SNATCHED_ANY, SNATCHED_PROPER, \
    NeededQualities, Quality
from .history import dateFormat
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from .sgdatetime import SGDatetime

from _23 import filter_iter, list_values, map_consume, map_list
from six import string_types

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import AnyStr, List, Tuple


def search_propers(provider_proper_obj=None):
    """

    :param provider_proper_obj: Optional dict with provider keys containing Proper objects
    :type provider_proper_obj: dict
    :return:
    """
    if not sickbeard.DOWNLOAD_PROPERS:
        return

    logger.log(('Checking Propers from recent search', 'Beginning search for new Propers')[None is provider_proper_obj])

    age_shows, age_anime = sickbeard.BACKLOG_DAYS + 2, 14
    aired_since_shows = datetime.datetime.today() - datetime.timedelta(days=age_shows)
    aired_since_anime = datetime.datetime.today() - datetime.timedelta(days=age_anime)
    recent_shows, recent_anime = _recent_history(aired_since_shows, aired_since_anime)
    if recent_shows or recent_anime:
        propers = _get_proper_list(aired_since_shows, recent_shows, recent_anime, proper_dict=provider_proper_obj)

        if propers:
            _download_propers(propers)
    else:
        logger.log('No downloads or snatches found for the last %s%s days to use for a Propers search' %
                   (age_shows, ('', ' (%s for anime)' % age_anime)[helpers.has_anime()]))

    run_at = ''
    if None is provider_proper_obj:
        _set_last_proper_search(datetime.datetime.now())

        proper_sch = sickbeard.properFinderScheduler
        if None is proper_sch.start_time:
            run_in = proper_sch.lastRun + proper_sch.cycleTime - datetime.datetime.now()
            run_at = ', next check '
            if datetime.timedelta() > run_in:
                run_at += 'imminent'
            else:
                hours, remainder = divmod(run_in.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                run_at += 'in approx. ' + ('%dm, %ds' % (minutes, seconds), '%dh, %dm' % (hours, minutes))[0 < hours]

        logger.log('Completed search for new Propers%s' % run_at)
    else:
        logger.log('Completed checking Propers from recent search')


def get_old_proper_level(show_obj, tvid, prodid, season, episode_numbers, old_status, new_quality,
                         extra_no_name, version, is_anime=False):
    """

    :param show_obj: show object
    :type show_obj: sickbeard.tv.TVShow
    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    :param season: season number
    :type season: int
    :param episode_numbers: episode numbers
    :type episode_numbers: List[int]
    :param old_status: old status
    :type old_status: int
    :param new_quality: new quality
    :type new_quality: int
    :param extra_no_name: extra info from release name
    :type extra_no_name: AnyStr
    :param version: version
    :type version: int
    :param is_anime: is anime
    :type is_anime: bool
    :return: tuple of: proper level, extra info from release name, release name
    :rtype: Tuple[int, AnyStr, AnyStr]
    """
    level = 0
    rel_name = None
    if old_status not in SNATCHED_ANY:
        level = Quality.get_proper_level(extra_no_name, version, is_anime)
    elif show_obj:
        my_db = db.DBConnection()
        np = NameParser(False, show_obj=show_obj)
        for episode in episode_numbers:
            # noinspection SqlResolve
            result = my_db.select(
                'SELECT resource FROM history'
                ' WHERE indexer = ? AND showid = ?'
                ' AND season = ? AND episode = ? AND '
                '(%s) ORDER BY date DESC LIMIT 1' % (' OR '.join(['action LIKE "%%%02d"' % x for x in SNATCHED_ANY])),
                [tvid, prodid, season, episode])
            if not result or not isinstance(result[0]['resource'], string_types) or not result[0]['resource']:
                continue
            nq = Quality.sceneQuality(result[0]['resource'], show_obj.is_anime)
            if nq != new_quality:
                continue
            try:
                p = np.parse(result[0]['resource'])
            except (BaseException, Exception):
                continue
            level = Quality.get_proper_level(p.extra_info_no_name(), p.version, show_obj.is_anime)
            extra_no_name = p.extra_info_no_name()
            rel_name = result[0]['resource']
            break
    return level, extra_no_name, rel_name


def get_webdl_type(extra_info_no_name, rel_name):
    """

    :param extra_info_no_name: extra info from release name
    :type extra_info_no_name: AnyStr
    :param rel_name: release name
    :type rel_name: AnyStr
    :return: web dl type
    :rtype: AnyStr
    """
    if not sickbeard.WEBDL_TYPES:
        load_webdl_types()

    for t in sickbeard.WEBDL_TYPES:
        try:
            if re.search(r'\b%s\b' % t[1], extra_info_no_name, flags=re.I):
                return t[0]
        except (BaseException, Exception):
            continue

    return ('webdl', 'webrip')[None is re.search(r'\bweb.?dl\b', rel_name, flags=re.I)]


def load_webdl_types():
    """
    Fetch all web dl/rip types
    """
    new_types = []
    default_types = [('Amazon', r'AMZN|AMAZON'), ('Netflix', r'NETFLIX|NF'), ('Hulu', r'HULU')]
    url = 'https://raw.githubusercontent.com/SickGear/sickgear.extdata/master/SickGear/webdl_types.txt'
    url_data = helpers.get_url(url)

    my_db = db.DBConnection()
    sql_result = my_db.select('SELECT * FROM webdl_types')
    old_types = [(r['dname'], r['regex']) for r in sql_result]

    if isinstance(url_data, string_types) and url_data.strip():
        try:
            for line in url_data.splitlines():
                try:
                    (key, val) = line.strip().split(u'::', 1)
                except (BaseException, Exception):
                    continue
                if None is key or None is val:
                    continue
                new_types.append((key, val))
        except (IOError, OSError):
            pass

        cl = []
        for nt in new_types:
            if nt not in old_types:
                cl.append(['REPLACE INTO webdl_types (dname, regex) VALUES (?,?)', [nt[0], nt[1]]])

        for ot in old_types:
            if ot not in new_types:
                cl.append(['DELETE FROM webdl_types WHERE dname = ? AND regex = ?', [ot[0], ot[1]]])

        if cl:
            my_db.mass_action(cl)
    else:
        new_types = old_types

    sickbeard.WEBDL_TYPES = new_types + default_types


def _get_proper_list(aired_since_shows, recent_shows, recent_anime, proper_dict=None):
    """

    :param aired_since_shows: date since aired
    :type aired_since_shows: datetime.datetime
    :param recent_shows: list of recent shows
    :type recent_shows: List[Tuple[int, int]]
    :param recent_anime: list of recent anime shows
    :type recent_anime: List[Tuple[int, int]]
    :param proper_dict: dict with provider keys containing Proper objects
    :type proper_dict: dict
    :return: list of propers
    :rtype: List[sickbeard.classes.Proper]
    """
    propers = {}

    my_db = db.DBConnection()
    # for each provider get a list of arbitrary Propers
    orig_thread_name = threading.currentThread().name
    for cur_provider in filter_iter(lambda p: p.is_active(), sickbeard.providers.sortedProviderList()):
        if not recent_anime and cur_provider.anime_only:
            continue

        if None is not proper_dict:
            found_propers = proper_dict.get(cur_provider.get_id(), [])
            if not found_propers:
                continue
        else:
            threading.currentThread().name = '%s :: [%s]' % (orig_thread_name, cur_provider.name)

            logger.log('Searching for new PROPER releases')

            try:
                found_propers = cur_provider.find_propers(search_date=aired_since_shows, shows=recent_shows,
                                                          anime=recent_anime)
            except AuthException as e:
                logger.log('Authentication error: %s' % ex(e), logger.ERROR)
                continue
            except (BaseException, Exception) as e:
                logger.log('Error while searching %s, skipping: %s' % (cur_provider.name, ex(e)), logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)
                continue
            finally:
                threading.currentThread().name = orig_thread_name

        # if they haven't been added by a different provider than add the Proper to the list
        for cur_proper in found_propers:
            name = _generic_name(cur_proper.name)
            if name in propers:
                continue

            try:
                np = NameParser(False, try_scene_exceptions=True, show_obj=cur_proper.parsed_show_obj,
                                indexer_lookup=False)
                parse_result = np.parse(cur_proper.name)
            except (InvalidNameException, InvalidShowException, Exception):
                continue

            # get the show object
            cur_proper.parsed_show_obj = (cur_proper.parsed_show_obj
                                          or helpers.find_show_by_id(parse_result.show_obj.tvid_prodid))
            if None is cur_proper.parsed_show_obj:
                logger.log('Skip download; cannot find show with ID [%s] from %s' %
                           (cur_proper.prodid, sickbeard.TVInfoAPI(cur_proper.tvid).name), logger.ERROR)
                continue

            cur_proper.tvid = cur_proper.parsed_show_obj.tvid
            cur_proper.prodid = cur_proper.parsed_show_obj.prodid

            if not (-1 != cur_proper.prodid and parse_result.series_name and parse_result.episode_numbers
                    and (cur_proper.tvid, cur_proper.prodid) in recent_shows + recent_anime):
                continue

            # only get anime Proper if it has release group and version
            if parse_result.is_anime and not parse_result.release_group and -1 == parse_result.version:
                logger.log('Ignored Proper with no release group and version in name [%s]' % cur_proper.name,
                           logger.DEBUG)
                continue

            if not show_name_helpers.pass_wordlist_checks(cur_proper.name, parse=False, indexer_lookup=False):
                logger.log('Ignored unwanted Proper [%s]' % cur_proper.name, logger.DEBUG)
                continue

            re_x = dict(re_prefix='.*', re_suffix='.*')
            result = show_name_helpers.contains_any(cur_proper.name, cur_proper.parsed_show_obj.rls_ignore_words,
                                                    **re_x)
            if None is not result and result:
                logger.log('Ignored Proper containing ignore word [%s]' % cur_proper.name, logger.DEBUG)
                continue

            result = show_name_helpers.contains_any(cur_proper.name, cur_proper.parsed_show_obj.rls_require_words,
                                                    **re_x)
            if None is not result and not result:
                logger.log('Ignored Proper for not containing any required word [%s]' % cur_proper.name, logger.DEBUG)
                continue

            cur_size = getattr(cur_proper, 'size', None)
            if failed_history.has_failed(cur_proper.name, cur_size, cur_provider.name):
                continue

            cur_proper.season = parse_result.season_number if None is not parse_result.season_number else 1
            cur_proper.episode = parse_result.episode_numbers[0]
            # check if we actually want this Proper (if it's the right quality)
            sql_result = my_db.select(
                'SELECT release_group, status, version, release_name'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' AND season = ? AND episode = ?'
                ' LIMIT 1',
                [cur_proper.tvid, cur_proper.prodid,
                 cur_proper.season, cur_proper.episode])
            if not sql_result:
                continue

            # only keep the Proper if we already retrieved the same quality ep (don't get better/worse ones)
            # check if we want this release: same quality as current, current has correct status
            # restrict other release group releases to Proper's
            old_status, old_quality = Quality.splitCompositeStatus(int(sql_result[0]['status']))
            cur_proper.quality = Quality.nameQuality(cur_proper.name, parse_result.is_anime)
            cur_proper.is_repack, cur_proper.properlevel = Quality.get_proper_level(
                parse_result.extra_info_no_name(), parse_result.version, parse_result.is_anime, check_is_repack=True)
            cur_proper.proper_level = cur_proper.properlevel    # local non global value
            old_release_group = sql_result[0]['release_group']
            try:
                same_release_group = parse_result.release_group.lower() == old_release_group.lower()
            except (BaseException, Exception):
                same_release_group = parse_result.release_group == old_release_group
            if old_status not in SNATCHED_ANY + [DOWNLOADED, ARCHIVED] \
                    or cur_proper.quality != old_quality \
                    or (cur_proper.is_repack and not same_release_group):
                continue

            np = NameParser(False, try_scene_exceptions=True, show_obj=cur_proper.parsed_show_obj, indexer_lookup=False)
            try:
                extra_info = np.parse(sql_result[0]['release_name']).extra_info_no_name()
            except (BaseException, Exception):
                extra_info = None
            # don't take Proper of the same level we already downloaded
            old_proper_level, old_extra_no_name, old_name = \
                get_old_proper_level(cur_proper.parsed_show_obj, cur_proper.tvid, cur_proper.prodid,
                                     cur_proper.season, parse_result.episode_numbers,
                                     old_status, cur_proper.quality, extra_info,
                                     parse_result.version, parse_result.is_anime)
            if cur_proper.proper_level <= old_proper_level:
                continue

            is_web = (old_quality in (Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB) or
                      (old_quality == Quality.SDTV and
                       isinstance(sql_result[0]['release_name'], string_types) and
                       re.search(r'\Wweb.?(dl|rip|.([hx]\W?26[45]|hevc))\W', sql_result[0]['release_name'], re.I)))

            if is_web:
                old_name = (old_name, sql_result[0]['release_name'])[old_name in ('', None)]
                old_webdl_type = get_webdl_type(old_extra_no_name, old_name)
                new_webdl_type = get_webdl_type(parse_result.extra_info_no_name(), cur_proper.name)
                if old_webdl_type != new_webdl_type:
                    logger.log('Ignored Proper webdl source [%s], does not match existing webdl source [%s] for [%s]'
                               % (old_webdl_type, new_webdl_type, cur_proper.name), logger.DEBUG)
                    continue

            # for webdls, prevent Propers from different groups
            log_same_grp = 'Ignored Proper from release group [%s] does not match existing group [%s] for [%s]' \
                           % (parse_result.release_group, old_release_group, cur_proper.name)
            if sickbeard.PROPERS_WEBDL_ONEGRP and is_web and not same_release_group:
                logger.log(log_same_grp, logger.DEBUG)
                continue

            # check if we actually want this Proper (if it's the right release group and a higher version)
            if parse_result.is_anime:
                old_version = int(sql_result[0]['version'])
                if not (-1 < old_version < parse_result.version):
                    continue
                if not same_release_group:
                    logger.log(log_same_grp, logger.DEBUG)
                    continue
                found_msg = 'Found anime Proper v%s to replace v%s' % (parse_result.version, old_version)
            else:
                found_msg = 'Found Proper [%s]' % cur_proper.name

            # make sure the episode has been downloaded before
            history_limit = datetime.datetime.today() - datetime.timedelta(days=30)
            # noinspection SqlResolve
            history_results = my_db.select(
                'SELECT resource FROM history'
                ' WHERE indexer = ? AND showid = ?'
                ' AND season = ? AND episode = ? AND quality = ? AND date >= ?'
                ' AND (%s)' % ' OR '.join(['action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, ARCHIVED]]),
                [cur_proper.tvid, cur_proper.prodid,
                 cur_proper.season, cur_proper.episode, cur_proper.quality,
                 history_limit.strftime(history.dateFormat)])

            # skip if the episode has never downloaded, because a previous quality is required to match the Proper
            if not len(history_results):
                logger.log('Ignored Proper cannot find a recent history item for [%s]' % cur_proper.name, logger.DEBUG)
                continue

            # make sure that none of the existing history downloads are the same Proper as the download candidate
            clean_proper_name = _generic_name(helpers.remove_non_release_groups(
                cur_proper.name, cur_proper.parsed_show_obj.is_anime))
            is_same = False
            for hitem in history_results:
                # if the result exists in history already we need to skip it
                if clean_proper_name == _generic_name(helpers.remove_non_release_groups(
                        ek.ek(os.path.basename, hitem['resource']))):
                    is_same = True
                    break
            if is_same:
                logger.log('Ignored Proper already in history [%s]' % cur_proper.name)
                continue

            logger.log(found_msg, logger.DEBUG)

            # finish populating the Proper instance
            # cur_proper.show_obj = cur_proper.parsed_show_obj.prodid
            cur_proper.provider = cur_provider
            cur_proper.extra_info = parse_result.extra_info
            cur_proper.extra_info_no_name = parse_result.extra_info_no_name
            cur_proper.release_group = parse_result.release_group

            cur_proper.is_anime = parse_result.is_anime
            cur_proper.version = parse_result.version

            propers[name] = cur_proper

        cur_provider.log_result('Propers', len(propers), '%s' % cur_provider.name)

    return list_values(propers)


def _download_propers(proper_list):
    """
    download propers from given list

    :param proper_list: proper list
    :type proper_list: List[sickbeard.classes.Proper]
    """
    verified_propers = True
    consumed_proper = []
    downloaded_epid = set()

    _epid = operator.attrgetter('tvid', 'prodid', 'season', 'episode')
    while verified_propers:
        verified_propers = set()

        # get verified list; sort the list of unique Propers for highest proper_level, newest first
        for cur_proper in sorted(
                filter_iter(lambda p: p not in consumed_proper,
                            # allows Proper to fail or be rejected and another to be tried (with a different name)
                            filter_iter(lambda p: _epid(p) not in downloaded_epid, proper_list)),
                key=operator.attrgetter('properlevel', 'date'), reverse=True):  # type: Proper

            epid = _epid(cur_proper)

            # if the show is in our list and there hasn't been a Proper already added for that particular episode
            # then add it to our list of Propers
            if epid not in map_list(_epid, verified_propers):
                logger.log('Proper may be useful [%s]' % cur_proper.name)
                verified_propers.add(cur_proper)
            else:
                # use Proper with the highest level
                remove_propers = set()
                map_consume(lambda vp: remove_propers.add(vp),
                            filter_iter(lambda p: (epid == _epid(p) and cur_proper.proper_level > p.proper_level),
                                        verified_propers))

                if remove_propers:
                    verified_propers -= remove_propers
                    logger.log('A more useful Proper [%s]' % cur_proper.name)
                    verified_propers.add(cur_proper)

        for cur_proper in list(verified_propers):
            consumed_proper += [cur_proper]

            # scene release checking
            scene_only = getattr(cur_proper.provider, 'scene_only', False)
            scene_rej_nuked = getattr(cur_proper.provider, 'scene_rej_nuked', False)
            if any([scene_only, scene_rej_nuked]) and not cur_proper.parsed_show_obj.is_anime:
                scene_or_contain = getattr(cur_proper.provider, 'scene_or_contain', '')
                scene_contains = False
                if scene_only and scene_or_contain:
                    re_extras = dict(re_prefix='.*', re_suffix='.*')
                    r = show_name_helpers.contains_any(cur_proper.name, scene_or_contain, **re_extras)
                    if None is not r and r:
                        scene_contains = True

                if scene_contains and not scene_rej_nuked:
                    reject = False
                else:
                    reject, url = search.can_reject(cur_proper.name)
                    if reject:
                        if isinstance(reject, string_types):
                            if scene_rej_nuked:
                                logger.log('Rejecting nuked release. Nuke reason [%s] source [%s]' % (reject, url),
                                           logger.DEBUG)
                            else:
                                logger.log('Considering nuked release. Nuke reason [%s] source [%s]' % (reject, url),
                                           logger.DEBUG)
                                reject = False
                        elif scene_contains:
                            reject = False
                        else:
                            logger.log('Rejecting as not scene release listed at any [%s]' % url, logger.DEBUG)

                if reject:
                    continue

            # make the result object
            ep_obj = cur_proper.parsed_show_obj.get_episode(cur_proper.season, cur_proper.episode)
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
            if search.snatch_episode(result, SNATCHED_PROPER):
                downloaded_epid.add(_epid(cur_proper))


def get_needed_qualites(needed=None):
    """

    :param needed: optional needed object
    :type needed: sickbeard.common.NeededQualities
    :return: needed object
    :rtype: sickbeard.common.NeededQualities
    """
    if not isinstance(needed, NeededQualities):
        needed = NeededQualities()
    if not sickbeard.DOWNLOAD_PROPERS or needed.all_needed:
        return needed

    age_shows, age_anime = sickbeard.BACKLOG_DAYS + 2, 14
    aired_since_shows = datetime.datetime.today() - datetime.timedelta(days=age_shows)
    aired_since_anime = datetime.datetime.today() - datetime.timedelta(days=age_anime)

    my_db = db.DBConnection()
    sql_result = my_db.select(
        'SELECT DISTINCT s.indexer AS tv_id, s.indexer_id AS prod_id, e.season, e.episode'
        ' FROM history AS h'
        ' INNER JOIN tv_episodes AS e'
        ' ON (h.indexer = e.indexer AND h.showid = e.showid'
        ' AND h.season = e.season AND h.episode = e.episode)'
        ' INNER JOIN tv_shows AS s'
        ' ON (e.indexer = s.indexer AND e.showid = s.indexer_id)'
        ' WHERE h.date >= %s' % min(aired_since_shows, aired_since_anime).strftime(dateFormat) +
        ' AND (%s)' % ' OR '.join(['h.action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, FAILED]])
    )

    for cur_result in sql_result:
        if needed.all_needed:
            break
        try:
            show_obj = helpers.find_show_by_id({int(cur_result['tv_id']): int(cur_result['prod_id'])})
        except MultipleShowObjectsException:
            continue
        if show_obj:
            needed.check_needed_types(show_obj)
            if needed.all_show_qualities_needed(show_obj) or needed.all_qualities_needed:
                continue
            ep_obj = show_obj.get_episode(season=cur_result['season'], episode=cur_result['episode'])
            if ep_obj:
                ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                if ep_status in SNATCHED_ANY + [DOWNLOADED, ARCHIVED]:
                    needed.check_needed_qualities([ep_quality])

    return needed


def _recent_history(aired_since_shows, aired_since_anime):
    # type: (datetime.datetime, datetime.datetime) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]
    """

    :param aired_since_shows: aired since date
    :param aired_since_anime: aired anime since date
    """
    recent_shows, recent_anime = [], []

    my_db = db.DBConnection()

    sql_result = my_db.select(
        'SELECT DISTINCT s.indexer AS tv_id, s.indexer_id AS prod_id'
        ' FROM history AS h'
        ' INNER JOIN tv_episodes AS e'
        ' ON (h.indexer = e.indexer AND h.showid = e.showid'
        ' AND h.season = e.season AND h.episode = e.episode)'
        ' INNER JOIN tv_shows AS s'
        ' ON (e.indexer = s.indexer AND e.showid = s.indexer_id)'
        ' WHERE h.date >= %s' % min(aired_since_shows, aired_since_anime).strftime(dateFormat) +
        ' AND (%s)' % ' OR '.join(['h.action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, FAILED]])
    )

    for cur_result in sql_result:

        try:
            show_obj = helpers.find_show_by_id({int(cur_result['tv_id']): int(cur_result['prod_id'])})
        except MultipleShowObjectsException:
            continue
        if show_obj:
            if not show_obj.is_anime:
                (cur_result['tv_id'], cur_result['prod_id']) not in recent_shows and \
                    recent_shows.append((cur_result['tv_id'], cur_result['prod_id']))
            else:
                (cur_result['tv_id'], cur_result['prod_id']) not in recent_anime and show_obj.is_anime and \
                    recent_anime.append((cur_result['tv_id'], cur_result['prod_id']))

    return recent_shows, recent_anime


def _generic_name(name):
    return name.replace('.', ' ').replace('-', ' ').replace('_', ' ').lower()


def _set_last_proper_search(when):

    logger.log(u'Setting the last Proper search in the DB to %s' % when, logger.DEBUG)

    my_db = db.DBConnection()
    sql_result = my_db.select('SELECT * FROM info')

    if 0 == len(sql_result):
        my_db.action('INSERT INTO info (last_backlog, last_indexer, last_proper_search) VALUES (?,?,?)',
                     [0, 0, SGDatetime.totimestamp(when)])
    else:
        # noinspection SqlConstantCondition
        my_db.action('UPDATE info SET last_proper_search=%s WHERE 1=1' % SGDatetime.totimestamp(when))


def next_proper_timeleft():
    return sickbeard.properFinderScheduler.timeLeft()


def get_last_proper_search():

    my_db = db.DBConnection()
    sql_result = my_db.select('SELECT * FROM info')

    try:
        last_proper_search = int(sql_result[0]['last_proper_search'])
    except (BaseException, Exception):
        return 1

    return last_proper_search
