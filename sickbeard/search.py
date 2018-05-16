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

from __future__ import with_statement

import os
import re
import threading
import datetime
import traceback

import sickbeard

from common import SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, DOWNLOADED, Quality, SEASON_RESULT, MULTI_EP_RESULT

from sickbeard import logger, db, show_name_helpers, exceptions, helpers
from sickbeard import sab
from sickbeard import nzbget
from sickbeard import clients
from sickbeard import history
from sickbeard import notifiers
from sickbeard import nzbSplitter
from sickbeard import ui
from sickbeard import encodingKludge as ek
from sickbeard import failed_history
from sickbeard.exceptions import ex
from sickbeard.providers.generic import GenericProvider
from sickbeard import common
from sickbeard.tv import TVEpisode


def _download_result(result):
    """
    Downloads a result to the appropriate black hole folder.

    Returns a bool representing success.

    result: SearchResult instance to download.
    """

    res_provider = result.provider
    if None is res_provider:
        logger.log(u'Invalid provider name - this is a coding error, report it please', logger.ERROR)
        return False

    # nzbs with an URL can just be downloaded from the provider
    if 'nzb' == result.resultType:
        new_result = res_provider.download_result(result)
    # if it's an nzb data result
    elif 'nzbdata' == result.resultType:

        # get the final file path to the nzb
        file_name = ek.ek(os.path.join, sickbeard.NZB_DIR, u'%s.nzb' % result.name)

        logger.log(u'Saving NZB to %s' % file_name)

        new_result = True

        # save the data to disk
        try:
            data = result.get_data()
            if not data:
                new_result = False
            else:
                with ek.ek(open, file_name, 'w') as file_out:
                    file_out.write(data)

                helpers.chmodAsParent(file_name)

        except EnvironmentError as e:
            logger.log(u'Error trying to save NZB to black hole: %s' % ex(e), logger.ERROR)
            new_result = False
    elif 'torrent' == res_provider.providerType:
        new_result = res_provider.download_result(result)
    else:
        logger.log(u'Invalid provider type - this is a coding error, report it please', logger.ERROR)
        new_result = False

    return new_result


def snatch_episode(result, end_status=SNATCHED):
    """
    Contains the internal logic necessary to actually "snatch" a result that
    has been found.

    Returns a bool representing success.

    result: SearchResult instance to be snatched.
    endStatus: the episode status that should be used for the episode object once it's snatched.
    """

    if None is result:
        return False

    result.priority = 0  # -1 = low, 0 = normal, 1 = high
    if sickbeard.ALLOW_HIGH_PRIORITY:
        # if it aired recently make it high priority
        for cur_ep in result.episodes:
            if datetime.date.today() - cur_ep.airdate <= datetime.timedelta(days=7):
                result.priority = 1
    if 0 < result.properlevel:
        end_status = SNATCHED_PROPER

    # NZBs can be sent straight to SAB or saved to disk
    if result.resultType in ('nzb', 'nzbdata'):
        if 'blackhole' == sickbeard.NZB_METHOD:
            dl_result = _download_result(result)
        elif 'sabnzbd' == sickbeard.NZB_METHOD:
            dl_result = sab.send_nzb(result)
        elif 'nzbget' == sickbeard.NZB_METHOD:
            dl_result = nzbget.send_nzb(result)
        else:
            logger.log(u'Unknown NZB action specified in config: %s' % sickbeard.NZB_METHOD, logger.ERROR)
            dl_result = False

    # TORRENTs can be sent to clients or saved to disk
    elif 'torrent' == result.resultType:
        if not result.url.startswith('magnet') and None is not result.get_data_func:
            result.url = result.get_data_func(result.url)
            result.get_data_func = None  # consume only once
            if not result.url:
                return False
        # torrents are saved to disk when blackhole mode
        if 'blackhole' == sickbeard.TORRENT_METHOD:
            dl_result = _download_result(result)
        else:
            # make sure we have the torrent file content
            if not result.content and not result.url.startswith('magnet'):
                result.content = result.provider.get_url(result.url)
                if result.provider.should_skip() or not result.content:
                    logger.log(u'Torrent content failed to download from %s' % result.url, logger.ERROR)
                    return False
            # Snatches torrent with client
            client = clients.get_client_instance(sickbeard.TORRENT_METHOD)()
            dl_result = client.send_torrent(result)

            if getattr(result, 'cache_file', None):
                helpers.remove_file_failed(result.cache_file)
    else:
        logger.log(u'Unknown result type, unable to download it', logger.ERROR)
        dl_result = False

    if not dl_result:
        return False

    if sickbeard.USE_FAILED_DOWNLOADS:
        failed_history.add_snatched(result)

    ui.notifications.message(u'Episode snatched', result.name)

    history.log_snatch(result)

    # don't notify when we re-download an episode
    sql_l = []
    update_imdb_data = True
    for cur_ep_obj in result.episodes:
        with cur_ep_obj.lock:
            if is_first_best_match(cur_ep_obj.status, result):
                cur_ep_obj.status = Quality.compositeStatus(SNATCHED_BEST, result.quality)
            else:
                cur_ep_obj.status = Quality.compositeStatus(end_status, result.quality)

            item = cur_ep_obj.get_sql()
            if None is not item:
                sql_l.append(item)

        if cur_ep_obj.status not in Quality.DOWNLOADED:
            notifiers.notify_snatch(cur_ep_obj._format_pattern('%SN - %Sx%0E - %EN - %QN'))

            update_imdb_data = update_imdb_data and cur_ep_obj.show.load_imdb_info()

    if 0 < len(sql_l):
        my_db = db.DBConnection()
        my_db.mass_action(sql_l)

    return True


def pass_show_wordlist_checks(name, show):
    re_extras = dict(re_prefix='.*', re_suffix='.*')
    result = show_name_helpers.contains_any(name, show.rls_ignore_words, **re_extras)
    if None is not result and result:
        logger.log(u'Ignored: %s for containing ignore word' % name)
        return False

    result = show_name_helpers.contains_any(name, show.rls_require_words, **re_extras)
    if None is not result and not result:
        logger.log(u'Ignored: %s for not containing any required word match' % name)
        return False
    return True


def pick_best_result(results, show, quality_list=None, filter_rls=False):
    logger.log(u'Picking the best result out of %s' % [x.name for x in results], logger.DEBUG)

    # find the best result for the current episode
    best_result = None
    best_fallback_result = None
    scene_only = scene_or_contain = scene_loose = scene_loose_active = scene_rej_nuked = scene_nuked_active = False
    if filter_rls:
        try:
            provider = getattr(results[0], 'provider', None)
            scene_only = getattr(provider, 'scene_only', False)
            scene_or_contain = getattr(provider, 'scene_or_contain', '')
            recent_task = 'RECENT' in filter_rls
            scene_loose = getattr(provider, 'scene_loose', False) and recent_task
            scene_loose_active = getattr(provider, 'scene_loose_active', False) and not recent_task
            scene_rej_nuked = getattr(provider, 'scene_rej_nuked', False)
            scene_nuked_active = getattr(provider, 'scene_nuked_active', False) and not recent_task
        except (StandardError, Exception):
            filter_rls = False

    addendum = ''
    for cur_result in results:

        if show.is_anime and not show.release_groups.is_valid(cur_result):
            continue

        if quality_list and cur_result.quality not in quality_list:
            logger.log(u'Rejecting unwanted quality %s for [%s]' % (
                Quality.qualityStrings[cur_result.quality], cur_result.name), logger.DEBUG)
            continue

        if not pass_show_wordlist_checks(cur_result.name, show):
            continue

        cur_size = getattr(cur_result, 'size', None)
        if sickbeard.USE_FAILED_DOWNLOADS and None is not cur_size and failed_history.has_failed(
                cur_result.name, cur_size, cur_result.provider.name):
            logger.log(u'Rejecting previously failed [%s]' % cur_result.name)
            continue

        if filter_rls and any([scene_only, scene_loose, scene_loose_active, scene_rej_nuked, scene_nuked_active]):
            if show.is_anime:
                addendum = u'anime (skipping scene/nuke filter) '
            else:
                scene_contains = False
                if scene_only and scene_or_contain:
                    re_extras = dict(re_prefix='.*', re_suffix='.*')
                    r = show_name_helpers.contains_any(cur_result.name, scene_or_contain, **re_extras)
                    if None is not r and r:
                        scene_contains = True

                if scene_contains and not scene_rej_nuked:
                    logger.log(u'Considering title match to \'or contain\' [%s]' % cur_result.name, logger.DEBUG)
                    reject = False
                else:
                    reject, url = can_reject(cur_result.name)
                    if reject:
                        if isinstance(reject, basestring):
                            if scene_rej_nuked and not scene_nuked_active:
                                logger.log(u'Rejecting nuked release. Nuke reason [%s] source [%s]' % (reject, url),
                                           logger.DEBUG)
                            elif scene_nuked_active:
                                best_fallback_result = best_candidate(best_fallback_result, cur_result)
                            else:
                                logger.log(u'Considering nuked release. Nuke reason [%s] source [%s]' % (reject, url),
                                           logger.DEBUG)
                                reject = False
                        elif scene_contains or any([scene_loose, scene_loose_active]):
                            best_fallback_result = best_candidate(best_fallback_result, cur_result)
                        else:
                            logger.log(u'Rejecting as not scene release listed at any [%s]' % url, logger.DEBUG)

                if reject:
                    continue

        best_result = best_candidate(best_result, cur_result)

    if best_result and scene_only and not show.is_anime:
        addendum = u'scene release filtered '
    elif not best_result and best_fallback_result:
        addendum = u'non scene release filtered '
        best_result = best_fallback_result

    if best_result:
        logger.log(u'Picked as the best %s[%s]' % (addendum, best_result.name), logger.DEBUG)
    else:
        logger.log(u'No result picked.', logger.DEBUG)

    return best_result


def best_candidate(best_result, cur_result):
    logger.log(u'Quality is %s for [%s]' % (Quality.qualityStrings[cur_result.quality], cur_result.name))

    if not best_result or best_result.quality < cur_result.quality != Quality.UNKNOWN:
        best_result = cur_result

    elif best_result.quality == cur_result.quality:
        if cur_result.properlevel > best_result.properlevel and \
                (not cur_result.is_repack or cur_result.release_group == best_result.release_group):
            best_result = cur_result
        elif cur_result.properlevel == best_result.properlevel:
            if 'xvid' in best_result.name.lower() and 'x264' in cur_result.name.lower():
                logger.log(u'Preferring (x264 over xvid) [%s]' % cur_result.name)
                best_result = cur_result
            elif 'internal' in best_result.name.lower() and 'internal' not in cur_result.name.lower():
                best_result = cur_result

    return best_result


def is_final_result(result):
    """
    Checks if the given result is good enough quality that we can stop searching for other ones.

    If the result is the highest quality in both the any/best quality lists then this function
    returns True, if not then it's False

    """

    logger.log(u'Checking if searching should continue after finding %s' % result.name, logger.DEBUG)

    show_obj = result.episodes[0].show

    any_qualities, best_qualities = Quality.splitQuality(show_obj.quality)

    # if there is a redownload that's higher than this then we definitely need to keep looking
    if best_qualities and max(best_qualities) > result.quality:
        return False

    # if it does not match the shows black and white list its no good
    elif show_obj.is_anime and show_obj.release_groups.is_valid(result):
        return False

    # if there's no redownload that's higher (above) and this is the highest initial download then we're good
    elif any_qualities and result.quality in any_qualities:
        return True

    elif best_qualities and max(best_qualities) == result.quality:

        # if this is the best redownload but we have a higher initial download then keep looking
        if any_qualities and max(any_qualities) > result.quality:
            return False

        # if this is the best redownload and we don't have a higher initial download then we're done
        else:
            return True

    # if we got here than it's either not on the lists, they're empty, or it's lower than the highest required
    else:
        return False


def is_first_best_match(ep_status, result):
    """
    Checks if the given result is a best quality match and if we want to archive the episode on first match.
    """

    logger.log(u'Checking if the first best quality match should be archived for episode %s' %
               result.name, logger.DEBUG)

    show_obj = result.episodes[0].show
    cur_status, cur_quality = Quality.splitCompositeStatus(ep_status)

    any_qualities, best_qualities = Quality.splitQuality(show_obj.quality)

    # if there is a redownload that's a match to one of our best qualities and
    # we want to archive the episode then we are done
    if best_qualities and show_obj.upgrade_once and \
            (result.quality in best_qualities and
             (cur_status in (SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, DOWNLOADED) or
              result.quality not in any_qualities)):
        return True

    return False


def set_wanted_aired(ep_obj, unaired, ep_count, ep_count_scene, manual=False):
    ep_status, ep_quality = common.Quality.splitCompositeStatus(ep_obj.status)
    ep_obj.wantedQuality = get_wanted_qualities(ep_obj, ep_status, ep_quality, unaired=unaired, manual=manual)
    ep_obj.eps_aired_in_season = ep_count.get(ep_obj.season, 0)
    ep_obj.eps_aired_in_scene_season = ep_count_scene.get(
        ep_obj.scene_season, 0) if ep_obj.scene_season else ep_obj.eps_aired_in_season


def get_wanted_qualities(ep_obj, cur_status, cur_quality, unaired=False, manual=False):
    if isinstance(ep_obj, TVEpisode):
        return sickbeard.WANTEDLIST_CACHE.get_wantedlist(ep_obj.show.quality, ep_obj.show.upgrade_once,
                                                         cur_quality, cur_status, unaired, manual)

    return []


def get_aired_in_season(show, return_sql=False):
    ep_count = {}
    ep_count_scene = {}
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
    my_db = db.DBConnection()

    if show.air_by_date:
        sql_string = 'SELECT ep.status, ep.season, ep.scene_season, ep.episode, ep.airdate ' + \
                     'FROM [tv_episodes] AS ep, [tv_shows] AS show ' + \
                     'WHERE season != 0 AND ep.showid = show.indexer_id AND show.paused = 0 ' + \
                     'AND ep.showid = ? AND ep.indexer = ? AND show.air_by_date = 1'
    else:
        sql_string = 'SELECT status, season, scene_season, episode, airdate ' + \
                     'FROM [tv_episodes] ' + \
                     'WHERE showid = ? AND indexer = ? AND season > 0'

    sql_results = my_db.select(sql_string, [show.indexerid, show.indexer])
    for result in sql_results:
        if 1 < helpers.tryInt(result['airdate']) <= tomorrow:
            cur_season = helpers.tryInt(result['season'])
            ep_count[cur_season] = ep_count.setdefault(cur_season, 0) + 1
            cur_scene_season = helpers.tryInt(result['scene_season'], -1)
            if -1 != cur_scene_season:
                ep_count_scene[cur_scene_season] = ep_count.setdefault(cur_scene_season, 0) + 1

    if return_sql:
        return ep_count, ep_count_scene, sql_results

    return ep_count, ep_count_scene


def wanted_episodes(show, from_date, make_dict=False, unaired=False):

    ep_count, ep_count_scene, sql_results_org = get_aired_in_season(show, return_sql=True)

    from_date_ord = from_date.toordinal()
    if unaired:
        sql_results = [s for s in sql_results_org if s['airdate'] > from_date_ord or s['airdate'] == 1]
    else:
        sql_results = [s for s in sql_results_org if s['airdate'] > from_date_ord]

    if make_dict:
        wanted = {}
    else:
        wanted = []

    total_wanted = total_replacing = total_unaired = 0

    if 0 < len(sql_results) and 2 < len(sql_results) - len(show.episodes):
        myDB = db.DBConnection()
        show_ep_sql = myDB.select('SELECT * FROM tv_episodes WHERE showid = ? AND indexer = ?',
                                  [show.indexerid, show.indexer])
    else:
        show_ep_sql = None

    for result in sql_results:
        ep_obj = show.getEpisode(int(result['season']), int(result['episode']), ep_sql=show_ep_sql)
        cur_status, cur_quality = common.Quality.splitCompositeStatus(ep_obj.status)
        ep_obj.wantedQuality = get_wanted_qualities(ep_obj, cur_status, cur_quality, unaired=unaired)
        if not ep_obj.wantedQuality:
            continue

        ep_obj.eps_aired_in_season = ep_count.get(helpers.tryInt(result['season']), 0)
        ep_obj.eps_aired_in_scene_season = ep_count_scene.get(
            helpers.tryInt(result['scene_season']), 0) if result['scene_season'] else ep_obj.eps_aired_in_season
        if make_dict:
            wanted.setdefault(ep_obj.scene_season if ep_obj.show.is_scene else ep_obj.season, []).append(ep_obj)
        else:
            wanted.append(ep_obj)

        if cur_status in (common.WANTED, common.FAILED):
            total_wanted += 1
        elif cur_status in (common.UNAIRED, common.SKIPPED, common.IGNORED, common.UNKNOWN):
            total_unaired += 1
        else:
            total_replacing += 1

    if 0 < total_wanted + total_replacing + total_unaired:
        actions = []
        for msg, total in ['%d episode%s', total_wanted], \
                          ['to upgrade %d episode%s', total_replacing], \
                          ['%d unaired episode%s', total_unaired]:
            if 0 < total:
                actions.append(msg % (total, helpers.maybe_plural(total)))
        logger.log(u'We want %s for %s' % (' and '.join(actions), show.name))

    return wanted


def search_for_needed_episodes(episodes):
    found_results = {}

    search_done = False

    orig_thread_name = threading.currentThread().name

    providers = [x for x in sickbeard.providers.sortedProviderList() if x.is_active() and x.enable_recentsearch]

    for cur_provider in providers:
        threading.currentThread().name = '%s :: [%s]' % (orig_thread_name, cur_provider.name)

        cur_found_results = cur_provider.search_rss(episodes)

        search_done = True

        # pick a single result for each episode, respecting existing results
        for cur_ep in cur_found_results:

            if cur_ep.show.paused:
                logger.log(u'Show %s is paused, ignoring all RSS items for %s' %
                           (cur_ep.show.name, cur_ep.prettyName()), logger.DEBUG)
                continue

            # find the best result for the current episode
            best_result = pick_best_result(cur_found_results[cur_ep], cur_ep.show, filter_rls=orig_thread_name)

            # if all results were rejected move on to the next episode
            if not best_result:
                logger.log(u'All found results for %s were rejected.' % cur_ep.prettyName(), logger.DEBUG)
                continue

            # if it's already in the list (from another provider) and the newly found quality is no better then skip it
            if cur_ep in found_results and best_result.quality <= found_results[cur_ep].quality:
                continue

            # filter out possible bad torrents from providers
            if 'torrent' == best_result.resultType and 'blackhole' != sickbeard.TORRENT_METHOD:
                best_result.content = None
                if not best_result.url.startswith('magnet'):
                    best_result.content = best_result.provider.get_url(best_result.url)
                    if best_result.provider.should_skip():
                        break
                    if not best_result.content:
                        continue

            found_results[cur_ep] = best_result

            try:
                cur_provider.save_list()
            except (StandardError, Exception):
                pass

    threading.currentThread().name = orig_thread_name

    if not len(providers):
        logger.log('No NZB/Torrent providers in Media Providers/Options are enabled to match recent episodes', logger.WARNING)
    elif not search_done:
        logger.log('Failed recent search of %s enabled provider%s. More info in debug log.' % (
            len(providers), helpers.maybe_plural(len(providers))), logger.ERROR)

    return found_results.values()


def can_reject(release_name):
    """
    Check if a release name should be rejected at external services.
    If any site reports result as a valid scene release, then return None, None.
    If predb reports result as nuked, then return nuke reason and url attempted.
    If fail to find result at all services, return reject and url details for each site.

    :param release_name: Release title
    :type release_name: String
    :return: None, None if release has no issue otherwise True/Nuke reason, URLs that rejected
    :rtype: Tuple (None, None or True/String, String)
    """
    rej_urls = []
    srrdb_url = 'https://www.srrdb.com/api/search/r:%s/order:date-desc' % re.sub('\]\[', '', release_name)
    resp = helpers.getURL(srrdb_url, json=True)
    if not resp:
        srrdb_rej = True
        rej_urls += ['Failed contact \'%s\'' % srrdb_url]
    else:
        srrdb_rej = (not len(resp.get('results', []))
                     or release_name.lower() != resp.get('results', [{}])[0].get('release', '').lower())
        rej_urls += ([], ['\'%s\'' % srrdb_url])[srrdb_rej]

    sane_name = helpers.full_sanitizeSceneName(release_name)
    predb_url = 'https://predb.ovh/api/v1/?q=@name "%s"' % sane_name
    resp = helpers.getURL(predb_url, json=True)
    predb_rej = True
    if not resp:
        rej_urls += ['Failed contact \'%s\'' % predb_url]
    elif 'success' == resp.get('status', '').lower():
        rows = resp and (resp.get('data') or {}).get('rows') or []
        for data in rows:
            if sane_name == helpers.full_sanitizeSceneName((data.get('name', '') or '').strip()):
                nuke_type = (data.get('nuke') or {}).get('type')
                if not nuke_type:
                    predb_rej = not helpers.tryInt(data.get('preAt'))
                else:
                    predb_rej = 'un' not in nuke_type and data.get('nuke', {}).get('reason', 'Reason not set')
                break
        rej_urls += ([], ['\'%s\'' % predb_url])[bool(predb_rej)]

    pred = any([not srrdb_rej, not predb_rej])

    return pred and (None, None) or (predb_rej or True,  ', '.join(rej_urls))


def search_providers(show, episodes, manual_search=False, torrent_only=False, try_other_searches=False, old_status=None, scheduled=False):
    found_results = {}
    final_results = []

    search_done = False

    orig_thread_name = threading.currentThread().name

    use_quality_list = None
    if any([episodes]):
        old_status = old_status or failed_history.find_old_status(episodes[0]) or episodes[0].status
        if old_status:
            status, quality = Quality.splitCompositeStatus(old_status)
            use_quality_list = (status not in (
                common.WANTED, common.FAILED, common.UNAIRED, common.SKIPPED, common.IGNORED, common.UNKNOWN))

    provider_list = [x for x in sickbeard.providers.sortedProviderList() if x.is_active() and x.enable_backlog and
                     (not torrent_only or x.providerType == GenericProvider.TORRENT) and
                     (not scheduled or x.enable_scheduled_backlog)]
    for cur_provider in provider_list:
        if cur_provider.anime_only and not show.is_anime:
            logger.log(u'%s is not an anime, skipping' % show.name, logger.DEBUG)
            continue

        threading.currentThread().name = '%s :: [%s]' % (orig_thread_name, cur_provider.name)
        provider_id = cur_provider.get_id()

        found_results[provider_id] = {}

        search_count = 0
        search_mode = cur_provider.search_mode

        while True:
            search_count += 1

            if 'eponly' == search_mode:
                logger.log(u'Performing episode search for %s' % show.name)
            else:
                logger.log(u'Performing season pack search for %s' % show.name)

            try:
                cur_provider.cache._clearCache()
                search_results = cur_provider.find_search_results(show, episodes, search_mode, manual_search,
                                                                  try_other_searches=try_other_searches)
                if any(search_results):
                    logger.log(', '.join(['%s %s candidate%s' % (
                        len(v), (('multiep', 'season')[SEASON_RESULT == k], 'episode')['ep' in search_mode],
                        helpers.maybe_plural(len(v))) for (k, v) in search_results.iteritems()]))
            except exceptions.AuthException as e:
                logger.log(u'Authentication error: %s' % ex(e), logger.ERROR)
                break
            except Exception as e:
                logger.log(u'Error while searching %s, skipping: %s' % (cur_provider.name, ex(e)), logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)
                break
            finally:
                threading.currentThread().name = orig_thread_name

            search_done = True

            if len(search_results):
                # make a list of all the results for this provider
                for cur_ep in search_results:
                    # skip non-tv crap
                    search_results[cur_ep] = filter(
                        lambda ep_item: show_name_helpers.pass_wordlist_checks(
                            ep_item.name, parse=False, indexer_lookup=False) and
                                        ep_item.show == show, search_results[cur_ep])

                    if cur_ep in found_results:
                        found_results[provider_id][cur_ep] += search_results[cur_ep]
                    else:
                        found_results[provider_id][cur_ep] = search_results[cur_ep]

                break
            elif not cur_provider.search_fallback or search_count == 2:
                break

            search_mode = '%sonly' % ('ep', 'sp')['ep' in search_mode]
            logger.log(u'Falling back to %s search ...' % ('season pack', 'episode')['ep' in search_mode])

        # skip to next provider if we have no results to process
        if not len(found_results[provider_id]):
            continue

        any_qualities, best_qualities = Quality.splitQuality(show.quality)

        # pick the best season NZB
        best_season_result = None
        if SEASON_RESULT in found_results[provider_id]:
            best_season_result = pick_best_result(found_results[provider_id][SEASON_RESULT], show,
                                                  any_qualities + best_qualities)

        highest_quality_overall = 0
        for cur_episode in found_results[provider_id]:
            for cur_result in found_results[provider_id][cur_episode]:
                if Quality.UNKNOWN != cur_result.quality and highest_quality_overall < cur_result.quality:
                    highest_quality_overall = cur_result.quality
        logger.log(u'%s is the highest quality of any match' % Quality.qualityStrings[highest_quality_overall],
                   logger.DEBUG)

        # see if every episode is wanted
        if best_season_result:
            # get the quality of the season nzb
            season_qual = best_season_result.quality
            logger.log(u'%s is the quality of the season %s' % (Quality.qualityStrings[season_qual],
                                                                best_season_result.provider.providerType), logger.DEBUG)

            my_db = db.DBConnection()
            sql = 'SELECT episode FROM tv_episodes WHERE showid = %s AND (season IN (%s))' %\
                  (show.indexerid, ','.join([str(x.season) for x in episodes]))
            ep_nums = [int(x['episode']) for x in my_db.select(sql)]

            logger.log(u'Executed query: [%s]' % sql)
            logger.log(u'Episode list: %s' % ep_nums, logger.DEBUG)

            all_wanted = True
            any_wanted = False
            for ep_num in ep_nums:
                for season in set([x.season for x in episodes]):
                    if not show.wantEpisode(season, ep_num, season_qual):
                        all_wanted = False
                    else:
                        any_wanted = True

            # if we need every ep in the season and there's nothing better then just download this and
            # be done with it (unless single episodes are preferred)
            if all_wanted and highest_quality_overall == best_season_result.quality:
                logger.log(u'Every episode in this season is needed, downloading the whole %s %s' %
                           (best_season_result.provider.providerType, best_season_result.name))
                ep_objs = []
                for ep_num in ep_nums:
                    for season in set([x.season for x in episodes]):
                        ep_objs.append(show.getEpisode(season, ep_num))
                best_season_result.episodes = ep_objs

                return [best_season_result]

            elif not any_wanted:
                logger.log(u'No episodes from this season are wanted at this quality, ignoring the result of ' +
                           best_season_result.name, logger.DEBUG)
            else:
                if GenericProvider.NZB == best_season_result.provider.providerType:
                    logger.log(u'Breaking apart the NZB and adding the individual ones to our results', logger.DEBUG)

                    # if not, break it apart and add them as the lowest priority results
                    individual_results = nzbSplitter.splitResult(best_season_result)

                    individual_results = filter(
                        lambda r: show_name_helpers.pass_wordlist_checks(
                            r.name, parse=False, indexer_lookup=False) and r.show == show, individual_results)

                    for cur_result in individual_results:
                        if 1 == len(cur_result.episodes):
                            ep_num = cur_result.episodes[0].episode
                        elif 1 < len(cur_result.episodes):
                            ep_num = MULTI_EP_RESULT

                        if ep_num in found_results[provider_id]:
                            found_results[provider_id][ep_num].append(cur_result)
                        else:
                            found_results[provider_id][ep_num] = [cur_result]

                # If this is a torrent all we can do is leech the entire torrent,
                # user will have to select which eps not do download in his torrent client
                else:

                    # Season result from Torrent Provider must be a full-season torrent, creating multi-ep result for it
                    logger.log(u'Adding multi episode result for full season torrent. In your torrent client, set ' +
                               u'the episodes that you do not want to "don\'t download"')
                    ep_objs = []
                    for ep_num in ep_nums:
                        for season in set([x.season for x in episodes]):
                            ep_objs.append(show.getEpisode(season, ep_num))
                    best_season_result.episodes = ep_objs

                    ep_num = MULTI_EP_RESULT
                    if ep_num in found_results[provider_id]:
                        found_results[provider_id][ep_num].append(best_season_result)
                    else:
                        found_results[provider_id][ep_num] = [best_season_result]

        # go through multi-ep results and see if we really want them or not, get rid of the rest
        multi_results = {}
        if MULTI_EP_RESULT in found_results[provider_id]:
            for multi_result in found_results[provider_id][MULTI_EP_RESULT]:

                logger.log(u'Checking usefulness of multi episode result [%s]' % multi_result.name, logger.DEBUG)

                if sickbeard.USE_FAILED_DOWNLOADS and failed_history.has_failed(multi_result.name, multi_result.size,
                                                                                multi_result.provider.name):
                    logger.log(u'Rejecting previously failed multi episode result [%s]' % multi_result.name)
                    continue

                # see how many of the eps that this result covers aren't covered by single results
                needed_eps = []
                not_needed_eps = []
                for ep_obj in multi_result.episodes:
                    ep_num = ep_obj.episode
                    # if we have results for the episode
                    if ep_num in found_results[provider_id] and 0 < len(found_results[provider_id][ep_num]):
                        needed_eps.append(ep_num)
                    else:
                        not_needed_eps.append(ep_num)

                logger.log(u'Single episode check result is... needed episodes: %s, not needed episodes: %s' %
                           (needed_eps, not_needed_eps), logger.DEBUG)

                if not not_needed_eps:
                    logger.log(u'All of these episodes were covered by single episode results, ' +
                               'ignoring this multi episode result', logger.DEBUG)
                    continue

                # check if these eps are already covered by another multi-result
                multi_needed_eps = []
                multi_not_needed_eps = []
                for ep_obj in multi_result.episodes:
                    ep_num = ep_obj.episode
                    if ep_num in multi_results:
                        multi_not_needed_eps.append(ep_num)
                    else:
                        multi_needed_eps.append(ep_num)

                logger.log(u'Multi episode check result is... multi needed episodes: ' +
                           '%s, multi not needed episodes: %s' % (multi_needed_eps, multi_not_needed_eps), logger.DEBUG)

                if not multi_needed_eps:
                    logger.log(u'All of these episodes were covered by another multi episode nzb, ' +
                               'ignoring this multi episode result',
                               logger.DEBUG)
                    continue

                # if we're keeping this multi-result then remember it
                for ep_obj in multi_result.episodes:
                    multi_results[ep_obj.episode] = multi_result

                # don't bother with the single result if we're going to get it with a multi result
                for ep_obj in multi_result.episodes:
                    ep_num = ep_obj.episode
                    if ep_num in found_results[provider_id]:
                        logger.log(u'A needed multi episode result overlaps with a single episode result for episode ' +
                                   '#%s, removing the single episode results from the list' % ep_num, logger.DEBUG)
                        del found_results[provider_id][ep_num]

        # of all the single ep results narrow it down to the best one for each episode
        final_results += set(multi_results.values())
        quality_list = use_quality_list and (None, best_qualities)[any(best_qualities)] or None
        for cur_ep in found_results[provider_id]:
            if cur_ep in (MULTI_EP_RESULT, SEASON_RESULT):
                continue

            if 0 == len(found_results[provider_id][cur_ep]):
                continue

            best_result = pick_best_result(found_results[provider_id][cur_ep], show, quality_list,
                                           filter_rls=orig_thread_name)

            # if all results were rejected move on to the next episode
            if not best_result:
                continue

            # filter out possible bad torrents from providers
            if 'torrent' == best_result.resultType:
                if not best_result.url.startswith('magnet') and None is not best_result.get_data_func:
                    best_result.url = best_result.get_data_func(best_result.url)
                    best_result.get_data_func = None  # consume only once
                    if not best_result.url:
                        continue
                if best_result.url.startswith('magnet'):
                    if 'blackhole' != sickbeard.TORRENT_METHOD:
                        best_result.content = None
                else:
                    cache_file = ek.ek(os.path.join, sickbeard.CACHE_DIR or helpers._getTempDir(),
                                       '%s.torrent' % (helpers.sanitizeFileName(best_result.name)))
                    if not helpers.download_file(best_result.url, cache_file, session=best_result.provider.session):
                        continue

                    try:
                        with open(cache_file, 'rb') as fh:
                            td = fh.read()
                        setattr(best_result, 'cache_file', cache_file)
                    except (StandardError, Exception):
                        continue

                    if getattr(best_result.provider, 'chk_td', None):
                        name = None
                        try:
                            hdr = re.findall('(\w+(\d+):)', td[0:6])[0]
                            x, v = len(hdr[0]), int(hdr[1])
                            while x < len(td):
                                y = x + v
                                name = 'name' == td[x: y]
                                w = re.findall('((?:i-?\d+e|e+|d|l+)*(\d+):)', td[y: y + 32])[0]
                                x, v = y + len(w[0]), int(w[1])
                                if name:
                                    name = td[x: x + v]
                                    break
                        except (StandardError, Exception):
                            continue
                        if name:
                            if not pass_show_wordlist_checks(name, show):
                                continue
                            if not show_name_helpers.pass_wordlist_checks(name, indexer_lookup=False):
                                logger.log('Ignored: %s (debug log has detail)' % name)
                                continue
                            best_result.name = name

                    if 'blackhole' != sickbeard.TORRENT_METHOD:
                        best_result.content = td

            # add result if its not a duplicate and
            found = False
            for i, result in enumerate(final_results):
                for best_result_ep in best_result.episodes:
                    if best_result_ep in result.episodes:
                        if best_result.quality > result.quality:
                            final_results.pop(i)
                        else:
                            found = True
            if not found:
                final_results += [best_result]

        # check that we got all the episodes we wanted first before doing a match and snatch
        wanted_ep_count = 0
        for wanted_ep in episodes:
            for result in final_results:
                if wanted_ep in result.episodes and is_final_result(result):
                    wanted_ep_count += 1

        # make sure we search every provider for results unless we found everything we wanted
        if len(episodes) == wanted_ep_count:
            break

    if not len(provider_list):
        logger.log('No NZB/Torrent providers in Media Providers/Options are allowed for active searching', logger.WARNING)
    elif not search_done:
        logger.log('Failed active search of %s enabled provider%s. More info in debug log.' % (
            len(provider_list), helpers.maybe_plural(len(provider_list))), logger.ERROR)
    elif not any(final_results):
        logger.log('No suitable candidates')

    return final_results
