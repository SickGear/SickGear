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
from sickbeard.common import DOWNLOADED, SNATCHED_ANY, SNATCHED_PROPER, Quality, ARCHIVED, FAILED, neededQualities
from sickbeard.exceptions import ex, MultipleShowObjectsException
from sickbeard import failed_history
from sickbeard.history import dateFormat
from sickbeard.sbdatetime import sbdatetime

from name_parser.parser import NameParser, InvalidNameException, InvalidShowException


def search_propers(proper_list=None):

    if not sickbeard.DOWNLOAD_PROPERS:
        return

    logger.log(('Checking Propers from recent search', 'Beginning search for new Propers')[None is proper_list])

    age_shows, age_anime = sickbeard.BACKLOG_DAYS + 2, 14
    aired_since_shows = datetime.datetime.today() - datetime.timedelta(days=age_shows)
    aired_since_anime = datetime.datetime.today() - datetime.timedelta(days=age_anime)
    recent_shows, recent_anime = _recent_history(aired_since_shows, aired_since_anime)
    if recent_shows or recent_anime:
        propers = _get_proper_list(aired_since_shows, recent_shows, recent_anime, proper_list=proper_list)

        if propers:
            _download_propers(propers)
    else:
        logger.log('No downloads or snatches found for the last %s%s days to use for a Propers search' %
                   (age_shows, ('', ' (%s for anime)' % age_anime)[helpers.has_anime()]))

    run_at = ''
    if None is proper_list:
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


def get_old_proper_level(show_obj, indexer, indexerid, season, episodes, old_status, new_quality,
                         extra_no_name, version, is_anime=False):
    level = 0
    is_internal = False
    codec = ''
    rel_name = None
    if old_status not in SNATCHED_ANY:
        level = Quality.get_proper_level(extra_no_name, version, is_anime)
    elif show_obj:
        my_db = db.DBConnection()
        np = NameParser(False, showObj=show_obj)
        for episode in episodes:
            result = my_db.select(
                'SELECT resource FROM history'
                ' WHERE showid = ?'
                ' AND season = ? AND episode = ? AND '
                '(%s) ORDER BY date DESC LIMIT 1' % (' OR '.join('action LIKE "%%%02d"' % x for x in SNATCHED_ANY)),
                [indexerid, season, episode])
            if not result or not isinstance(result[0]['resource'], basestring) or not result[0]['resource']:
                continue
            nq = Quality.sceneQuality(result[0]['resource'], show_obj.is_anime)
            if nq != new_quality:
                continue
            try:
                p = np.parse(result[0]['resource'])
            except (StandardError, Exception):
                continue
            level = Quality.get_proper_level(p.extra_info_no_name(), p.version, show_obj.is_anime)
            extra_no_name = p.extra_info_no_name()
            rel_name = result[0]['resource']
            is_internal = p.extra_info_no_name() and re.search(r'\binternal\b', p.extra_info_no_name(), flags=re.I)
            codec = _get_codec(p.extra_info_no_name())
            break
    return level, is_internal, codec, extra_no_name, rel_name


def _get_codec(extra_info_no_name):
    if not extra_info_no_name:
        return ''
    if re.search(r'\b[xh]264\b', extra_info_no_name, flags=re.I):
        return '264'
    elif re.search(r'\bxvid\b', extra_info_no_name, flags=re.I):
        return 'xvid'
    elif re.search(r'\b[xh]\W?265|hevc\b', extra_info_no_name, flags=re.I):
        return 'hevc'
    return ''


def get_webdl_type(extra_info_no_name, rel_name):
    if not sickbeard.WEBDL_TYPES:
        load_webdl_types()

    for t in sickbeard.WEBDL_TYPES:
        try:
            if re.search(r'\b%s\b' % t[1], extra_info_no_name, flags=re.I):
                return t[0]
        except (StandardError, Exception):
            continue

    return ('webdl', 'webrip')[None is re.search(r'\bweb.?dl\b', rel_name, flags=re.I)]


def load_webdl_types():
    new_types = []
    default_types = [('Amazon', r'AMZN|AMAZON'), ('Netflix', r'NETFLIX|NF'), ('Hulu', r'HULU')]
    url = 'https://raw.githubusercontent.com/SickGear/sickgear.extdata/master/SickGear/webdl_types.txt'
    url_data = helpers.getURL(url)

    my_db = db.DBConnection()
    sql_results = my_db.select('SELECT * FROM webdl_types')
    old_types = [(r['dname'], r['regex']) for r in sql_results]

    if isinstance(url_data, basestring) and url_data.strip():
        try:
            for line in url_data.splitlines():
                try:
                    (key, val) = line.decode('utf-8').strip().split(u'::', 1)
                except (StandardError, Exception):
                    continue
                if key is None or val is None:
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


def _get_proper_list(aired_since_shows, recent_shows, recent_anime, proper_list=None):
    propers = {}

    my_db = db.DBConnection()
    # for each provider get a list of arbitrary Propers
    orig_thread_name = threading.currentThread().name
    providers = filter(lambda p: p.is_active(), sickbeard.providers.sortedProviderList())
    for cur_provider in providers:
        if not recent_anime and cur_provider.anime_only:
            continue

        if None is not proper_list:
            found_propers = proper_list.get(cur_provider.get_id(), [])
            if not found_propers:
                continue
        else:
            threading.currentThread().name = '%s :: [%s]' % (orig_thread_name, cur_provider.name)

            logger.log('Searching for new PROPER releases')

            try:
                found_propers = cur_provider.find_propers(search_date=aired_since_shows, shows=recent_shows,
                                                          anime=recent_anime)
            except exceptions.AuthException as e:
                logger.log('Authentication error: %s' % ex(e), logger.ERROR)
                continue
            except Exception as e:
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
                np = NameParser(False, try_scene_exceptions=True, showObj=cur_proper.parsed_show, indexer_lookup=False)
                parse_result = np.parse(cur_proper.name)
            except (InvalidNameException, InvalidShowException, Exception):
                continue

            # get the show object
            cur_proper.parsed_show = (cur_proper.parsed_show
                                      or helpers.findCertainShow(sickbeard.showList, parse_result.show.indexerid))
            if None is cur_proper.parsed_show:
                logger.log('Skip download; cannot find show with indexerid [%s]' % cur_proper.indexerid, logger.ERROR)
                continue

            cur_proper.indexer = cur_proper.parsed_show.indexer
            cur_proper.indexerid = cur_proper.parsed_show.indexerid

            if not (-1 != cur_proper.indexerid and parse_result.series_name and parse_result.episode_numbers
                    and (cur_proper.indexer, cur_proper.indexerid) in recent_shows + recent_anime):
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
            result = show_name_helpers.contains_any(cur_proper.name, cur_proper.parsed_show.rls_ignore_words, **re_x)
            if None is not result and result:
                logger.log('Ignored Proper containing ignore word [%s]' % cur_proper.name, logger.DEBUG)
                continue

            result = show_name_helpers.contains_any(cur_proper.name, cur_proper.parsed_show.rls_require_words, **re_x)
            if None is not result and not result:
                logger.log('Ignored Proper for not containing any required word [%s]' % cur_proper.name, logger.DEBUG)
                continue

            cur_size = getattr(cur_proper, 'size', None)
            if failed_history.has_failed(cur_proper.name, cur_size, cur_provider.name):
                continue

            cur_proper.season = parse_result.season_number if None is not parse_result.season_number else 1
            cur_proper.episode = parse_result.episode_numbers[0]
            # check if we actually want this Proper (if it's the right quality)
            sql_results = my_db.select(
                'SELECT release_group, status, version, release_name'
                ' FROM tv_episodes'
                ' WHERE showid = ? AND indexer = ? AND season = ? AND episode = ?'
                ' LIMIT 1',
                [cur_proper.indexerid, cur_proper.indexer, cur_proper.season, cur_proper.episode])
            if not sql_results:
                continue

            # only keep the Proper if we already retrieved the same quality ep (don't get better/worse ones)
            # check if we want this release: same quality as current, current has correct status
            # restrict other release group releases to Proper's
            old_status, old_quality = Quality.splitCompositeStatus(int(sql_results[0]['status']))
            cur_proper.quality = Quality.nameQuality(cur_proper.name, parse_result.is_anime)
            cur_proper.is_repack, cur_proper.properlevel = Quality.get_proper_level(
                parse_result.extra_info_no_name(), parse_result.version, parse_result.is_anime, check_is_repack=True)
            cur_proper.proper_level = cur_proper.properlevel    # local non global value
            old_release_group = sql_results[0]['release_group']
            try:
                same_release_group = parse_result.release_group.lower() == old_release_group.lower()
            except (StandardError, Exception):
                same_release_group = parse_result.release_group == old_release_group
            if old_status not in SNATCHED_ANY + [DOWNLOADED, ARCHIVED] \
                    or cur_proper.quality != old_quality \
                    or (cur_proper.is_repack and not same_release_group):
                continue

            np = NameParser(False, try_scene_exceptions=True, showObj=cur_proper.parsed_show, indexer_lookup=False)
            try:
                extra_info = np.parse(sql_results[0]['release_name']).extra_info_no_name()
            except (StandardError, Exception):
                extra_info = None
            # don't take Proper of the same level we already downloaded
            old_proper_level, old_is_internal, old_codec, old_extra_no_name, old_name = \
                get_old_proper_level(cur_proper.parsed_show, cur_proper.indexer, cur_proper.indexerid,
                                     cur_proper.season, parse_result.episode_numbers,
                                     old_status, cur_proper.quality, extra_info,
                                     parse_result.version, parse_result.is_anime)
            cur_proper.codec = _get_codec(parse_result.extra_info_no_name())
            if cur_proper.proper_level < old_proper_level:
                continue

            cur_proper.is_internal = (parse_result.extra_info_no_name() and
                                      re.search(r'\binternal\b', parse_result.extra_info_no_name(), flags=re.I))
            if cur_proper.proper_level == old_proper_level:
                if (('264' == cur_proper.codec and 'xvid' == old_codec)
                        or (old_is_internal and not cur_proper.is_internal)):
                    pass
                continue

            is_web = (old_quality in (Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB) or
                      (old_quality == Quality.SDTV and re.search(r'\Wweb.?(dl|rip|.[hx]26[45])\W',
                                                                 str(sql_results[0]['release_name']), re.I)))

            if is_web:
                old_name = (old_name, sql_results[0]['release_name'])[old_name in ('', None)]
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
                old_version = int(sql_results[0]['version'])
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
            history_results = my_db.select(
                'SELECT resource FROM history'
                ' WHERE showid = ?'
                ' AND season = ? AND episode = ? AND quality = ? AND date >= ?'
                ' AND (%s)' % ' OR '.join('action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, ARCHIVED]),
                [cur_proper.indexerid,
                 cur_proper.season, cur_proper.episode, cur_proper.quality,
                 history_limit.strftime(history.dateFormat)])

            # skip if the episode has never downloaded, because a previous quality is required to match the Proper
            if not len(history_results):
                logger.log('Ignored Proper cannot find a recent history item for [%s]' % cur_proper.name, logger.DEBUG)
                continue

            # make sure that none of the existing history downloads are the same Proper as the download candidate
            clean_proper_name = _generic_name(helpers.remove_non_release_groups(
                cur_proper.name, cur_proper.parsed_show.is_anime))
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
            # cur_proper.show = cur_proper.parsed_show.indexerid
            cur_proper.provider = cur_provider
            cur_proper.extra_info = parse_result.extra_info
            cur_proper.extra_info_no_name = parse_result.extra_info_no_name
            cur_proper.release_group = parse_result.release_group

            cur_proper.is_anime = parse_result.is_anime
            cur_proper.version = parse_result.version

            propers[name] = cur_proper

        cur_provider.log_result('Propers', len(propers), '%s' % cur_provider.name)

    return propers.values()


def _download_propers(proper_list):
    verified_propers = True
    consumed_proper = []
    downloaded_epid = set()

    _epid = operator.attrgetter('indexerid', 'indexer', 'season', 'episode')
    while verified_propers:
        verified_propers = set()

        # get verified list; sort the list of unique Propers for highest proper_level, newest first
        for cur_proper in sorted(
                filter(lambda p: p not in consumed_proper,
                       # allows Proper to fail or be rejected and another to be tried (with a different name)
                       filter(lambda p: _epid(p) not in downloaded_epid, proper_list)),
                key=operator.attrgetter('properlevel', 'date'), reverse=True):

            epid = _epid(cur_proper)

            # if the show is in our list and there hasn't been a Proper already added for that particular episode
            # then add it to our list of Propers
            if epid not in map(_epid, verified_propers):
                logger.log('Proper may be useful [%s]' % cur_proper.name)
                verified_propers.add(cur_proper)
            else:
                # use Proper with the highest level
                remove_propers = set()
                map(lambda vp: remove_propers.add(vp),
                    filter(lambda p: (epid == _epid(p) and cur_proper.proper_level > p.proper_level), verified_propers))

                if remove_propers:
                    verified_propers -= remove_propers
                    logger.log('A more useful Proper [%s]' % cur_proper.name)
                    verified_propers.add(cur_proper)

        for cur_proper in list(verified_propers):
            consumed_proper += [cur_proper]

            # scene release checking
            scene_only = getattr(cur_proper.provider, 'scene_only', False)
            scene_rej_nuked = getattr(cur_proper.provider, 'scene_rej_nuked', False)
            if any([scene_only, scene_rej_nuked]) and not cur_proper.parsed_show.is_anime:
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
                        if isinstance(reject, basestring):
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
            ep_obj = cur_proper.parsed_show.getEpisode(cur_proper.season, cur_proper.episode)
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
    if not isinstance(needed, neededQualities):
        needed = neededQualities()
    if not sickbeard.DOWNLOAD_PROPERS or needed.all_needed:
        return needed

    age_shows, age_anime = sickbeard.BACKLOG_DAYS + 2, 14
    aired_since_shows = datetime.datetime.today() - datetime.timedelta(days=age_shows)
    aired_since_anime = datetime.datetime.today() - datetime.timedelta(days=age_anime)

    my_db = db.DBConnection()
    sql_results = my_db.select(
        'SELECT DISTINCT s.indexer, s.indexer_id, e.season, e.episode FROM history as h' +
        ' INNER JOIN tv_episodes AS e ON (h.showid == e.showid AND h.season == e.season AND h.episode == e.episode)' +
        ' INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id)' +
        ' WHERE h.date >= %s' % min(aired_since_shows, aired_since_anime).strftime(dateFormat) +
        ' AND (%s)' % ' OR '.join(['h.action LIKE "%%%02d"' % x for x in SNATCHED_ANY + [DOWNLOADED, FAILED]])
    )

    for sql_episode in sql_results:
        if needed.all_needed:
            break
        try:
            show = helpers.find_show_by_id(
                sickbeard.showList, {int(sql_episode['indexer']): int(sql_episode['indexer_id'])})
        except MultipleShowObjectsException:
            continue
        if show:
            needed.check_needed_types(show)
            if needed.all_show_qualities_needed(show) or needed.all_qualities_needed:
                continue
            ep_obj = show.getEpisode(season=sql_episode['season'], episode=sql_episode['episode'])
            if ep_obj:
                ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
                if ep_status in SNATCHED_ANY + [DOWNLOADED, ARCHIVED]:
                    needed.check_needed_qualities([ep_quality])

    return needed


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
                     [0, 0, sbdatetime.totimestamp(when)])
    else:
        my_db.action('UPDATE info SET last_proper_search=%s' % sbdatetime.totimestamp(when))


def next_proper_timeleft():
    return sickbeard.properFinderScheduler.timeLeft()


def get_last_proper_search():

    my_db = db.DBConnection()
    sql_results = my_db.select('SELECT * FROM info')

    try:
        last_proper_search = int(sql_results[0]['last_proper_search'])
    except (StandardError, Exception):
        return 1

    return last_proper_search
