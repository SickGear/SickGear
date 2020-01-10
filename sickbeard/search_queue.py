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

import copy
import datetime
import re
import threading
import traceback

import exceptions_helper

import sickbeard
from . import common, db, failed_history, generic_queue, helpers, \
    history, logger, network_timezones, properFinder, search, ui
from .classes import Proper, SimpleNamespace
from .search import wanted_episodes, get_aired_in_season, set_wanted_aired
from .tv import TVEpisode

from _23 import filter_list

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Union


search_queue_lock = threading.Lock()

BACKLOG_SEARCH = 10
RECENT_SEARCH = 20
FAILED_SEARCH = 30
MANUAL_SEARCH = 40
PROPER_SEARCH = 50

MANUAL_SEARCH_HISTORY = []
MANUAL_SEARCH_HISTORY_SIZE = 100


class SearchQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self)
        self.queue_name = 'SEARCHQUEUE'  # type: AnyStr

    def is_in_queue(self, show_obj, segment):
        # type: (sickbeard.tv.TVShow, List[sickbeard.tv.TVEpisode]) -> bool
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, BacklogQueueItem) \
                        and show_obj == cur_item.show_obj \
                        and segment == cur_item.segment:
                    return True
            return False

    def is_ep_in_queue(self, segment):
        # type: (List[sickbeard.tv.TVEpisode]) -> bool
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and cur_item.segment == segment:
                    return True
            return False

    def is_show_in_queue(self, tvid_prodid):
        # type: (AnyStr) -> bool
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and \
                        tvid_prodid == cur_item.show_obj.tvid_prodid:
                    return True
            return False

    def pause_backlog(self):
        # type: (...) -> None
        with self.lock:
            self.min_priority = generic_queue.QueuePriorities.HIGH

    def unpause_backlog(self):
        # type: (...) -> None
        with self.lock:
            self.min_priority = 0

    def is_backlog_paused(self):
        # type: (...) -> bool

        # backlog priorities are NORMAL, this should be done properly somewhere
        with self.lock:
            return self.min_priority >= generic_queue.QueuePriorities.NORMAL

    def _is_in_progress(self, item_type):
        # type: (Any) -> bool
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, item_type):
                    return True
            return False

    def get_queued_manual(self, tvid_prodid):
        # type: (Optional[AnyStr]) -> List[BaseSearchQueueItem]
        """
        Returns None or List of base info items of all show related items in manual or failed queue
        :param tvid_prodid: show tvid_prodid or None for all q items
        :return: List with 0 or more items
        """
        ep_ns_list = []
        with self.lock:
            for cur_item in self.queue:
                if (isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and
                        (not tvid_prodid or tvid_prodid == str(cur_item.show_obj.tvid_prodid))):
                    ep_ns_list.append(cur_item.base_info())

        return ep_ns_list

    def get_current_manual_item(self, tvid_prodid):
        # type: (Optional[AnyStr]) -> Union[ManualSearchQueueItem, FailedQueueItem]
        """
        Returns a base info item of the currently active manual search item
        :param tvid_prodid: show tvid_prodid or None for all q items
        :type tvid_prodid: String or None
        :return: base info item of ManualSearchQueueItem or FailedQueueItem or None
        """
        with self.lock:
            if self.currentItem and isinstance(self.currentItem, (ManualSearchQueueItem, FailedQueueItem)) \
                    and (not tvid_prodid or tvid_prodid == str(self.currentItem.show_obj.tvid_prodid)):
                return self.currentItem.base_info()

    def is_backlog_in_progress(self):
        # type: (...) -> bool
        return self._is_in_progress(BacklogQueueItem)

    def is_recentsearch_in_progress(self):
        # type: (...) -> bool
        return self._is_in_progress(RecentSearchQueueItem)

    def is_propersearch_in_progress(self):
        # type: (...) -> bool
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, ProperSearchQueueItem) and None is cur_item.propers:
                    return True
            return False

    def is_standard_backlog_in_progress(self):
        # type: (...) -> bool
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, BacklogQueueItem) and cur_item.standard_backlog:
                    return True
            return False

    def type_of_backlog_in_progress(self):
        # type: (...) -> AnyStr
        limited = full = other = False
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, BacklogQueueItem):
                    if cur_item.standard_backlog:
                        if cur_item.limited_backlog:
                            limited = True
                        else:
                            full = True
                    else:
                        other = True

            types = []
            for msg, variant in ['Limited', limited], ['Full', full], ['On Demand', other]:
                if variant:
                    types.append(msg)
            message = 'None'
            if types:
                message = ', '.join(types)
            return message

    def queue_length(self):
        # type: (...) -> Dict[List]
        length = dict(backlog=[], recent=0, manual=[], failed=[], proper=[])
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:
                if not cur_item:
                    continue
                if isinstance(cur_item, RecentSearchQueueItem):
                    length['recent'] += 1
                elif isinstance(cur_item, ProperSearchQueueItem):
                    length['proper'] += [dict(recent=None is not cur_item.propers)]
                else:
                    result_item = dict(
                        name=cur_item.show_obj.name, segment=cur_item.segment,
                        tvid=cur_item.show_obj.tvid, prodid=cur_item.show_obj.prodid,
                        tvid_prodid=cur_item.show_obj.tvid_prodid,
                        # legacy keys for api responses
                        indexer=cur_item.show_obj.tvid, indexerid=cur_item.show_obj.prodid
                    )
                    if isinstance(cur_item, BacklogQueueItem):
                        result_item.update(dict(
                            standard_backlog=cur_item.standard_backlog, limited_backlog=cur_item.limited_backlog,
                            forced=cur_item.forced, torrent_only=cur_item.torrent_only))
                        length['backlog'] += [result_item]
                    elif isinstance(cur_item, FailedQueueItem):
                        length['failed'] += [result_item]
                    elif isinstance(cur_item, ManualSearchQueueItem):
                        length['manual'] += [result_item]
            return length

    def add_item(
            self,
            item  # type: Union[RecentSearchQueueItem, ProperSearchQueueItem, BacklogQueueItem, ManualSearchQueueItem, FailedQueueItem]
    ):
        # type: (...) -> None
        """

        :param item:
        :type item: RecentSearchQueueItem or ProperSearchQueueItem or BacklogQueueItem or ManualSearchQueueItem or
        FailedQueueItem
        """
        if isinstance(item, (RecentSearchQueueItem, ProperSearchQueueItem)):
            # recent and proper searches
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, BacklogQueueItem) and not self.is_in_queue(item.show_obj, item.segment):
            # backlog searches
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, (ManualSearchQueueItem, FailedQueueItem)) and not self.is_ep_in_queue(item.segment):
            # manual and failed searches
            generic_queue.GenericQueue.add_item(self, item)
        else:
            logger.log(u'Not adding item, it\'s already in the queue', logger.DEBUG)


class RecentSearchQueueItem(generic_queue.QueueItem):
    def __init__(self):
        self.success = None
        self.ep_obj_list = []  # type: List
        generic_queue.QueueItem.__init__(self, 'Recent Search', RECENT_SEARCH)
        self.snatched_eps = set([])  # type: set

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            self._change_missing_episodes()

            show_list = sickbeard.showList
            from_date = datetime.date.fromordinal(1)
            needed = common.NeededQualities()
            for cur_show_obj in show_list:
                if cur_show_obj.paused:
                    continue

                wanted_eps = wanted_episodes(cur_show_obj, from_date, unaired=sickbeard.SEARCH_UNAIRED)

                if wanted_eps:
                    if not needed.all_needed:
                        if not needed.all_types_needed:
                            needed.check_needed_types(cur_show_obj)
                        if not needed.all_qualities_needed:
                            for w in wanted_eps:
                                if needed.all_qualities_needed:
                                    break
                                if not w.show_obj.is_anime and not w.show_obj.is_sports:
                                    needed.check_needed_qualities(w.wanted_quality)

                    self.ep_obj_list.extend(wanted_eps)

            if sickbeard.DOWNLOAD_PROPERS:
                properFinder.get_needed_qualites(needed)

            self.update_providers(needed=needed)
            self._check_for_propers(needed)

            if not self.ep_obj_list:
                logger.log(u'No search of cache for episodes required')
                self.success = True
            else:
                num_shows = len(set([ep_obj.show_obj.name for ep_obj in self.ep_obj_list]))
                logger.log(u'Found %d needed episode%s spanning %d show%s'
                           % (len(self.ep_obj_list), helpers.maybe_plural(self.ep_obj_list),
                              num_shows, helpers.maybe_plural(num_shows)))

                try:
                    logger.log(u'Beginning recent search for episodes')
                    # noinspection PyTypeChecker
                    search_results = search.search_for_needed_episodes(self.ep_obj_list)

                    if not len(search_results):
                        logger.log(u'No needed episodes found')
                    else:
                        for result in search_results:
                            logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                            self.success = search.snatch_episode(result)
                            if self.success:
                                for ep_obj in result.ep_obj_list:
                                    self.snatched_eps.add((ep_obj.show_obj.tvid_prodid, ep_obj.season, ep_obj.episode))

                            helpers.cpu_sleep()

                except (BaseException, Exception):
                    logger.log(traceback.format_exc(), logger.ERROR)

                if None is self.success:
                    self.success = False

        finally:
            self.finish()

    @staticmethod
    def _check_for_propers(needed):
        # type: (sickbeard.common.NeededQualities) -> None
        if not sickbeard.DOWNLOAD_PROPERS:
            return

        propers = {}
        my_db = db.DBConnection('cache.db')
        sql_result = my_db.select('SELECT * FROM provider_cache')
        re_p = r'\brepack|proper|real%s\b' % ('', '|v[2-9]')[needed.need_anime]

        proper_regex = re.compile(re_p, flags=re.I)

        for cur_result in sql_result:
            if proper_regex.search(cur_result['name']):
                try:
                    show_obj = helpers.find_show_by_id({int(cur_result['indexer']): int(cur_result['indexerid'])})
                except (BaseException, Exception):
                    continue
                if show_obj:
                    propers.setdefault(cur_result['provider'], []).append(
                        Proper(cur_result['name'], cur_result['url'],
                               datetime.datetime.fromtimestamp(cur_result['time']), show_obj, parsed_show_obj=show_obj))

        if propers:
            logger.log('Found Proper/Repack/Real in recent search, sending data to properfinder')
            propersearch_queue_item = sickbeard.search_queue.ProperSearchQueueItem(provider_proper_obj=propers)
            sickbeard.searchQueueScheduler.action.add_item(propersearch_queue_item)

    @staticmethod
    def _change_missing_episodes():
        if not network_timezones.network_dict:
            network_timezones.update_network_dict()

        if network_timezones.network_dict:
            cur_date = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
        else:
            cur_date = (datetime.date.today() - datetime.timedelta(days=2)).toordinal()

        cur_time = datetime.datetime.now(network_timezones.sb_timezone)

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT indexer AS tvid, showid AS prodid, airdate, season, episode'
            ' FROM tv_episodes'
            ' WHERE status = ? AND season > 0 AND airdate <= ? AND airdate > 1'
            ' ORDER BY indexer, showid', [common.UNAIRED, cur_date])

        sql_l = []
        show_obj = None
        wanted = False

        for cur_result in sql_result:
            tvid, prodid = int(cur_result['tvid']), int(cur_result['prodid'])
            try:
                if not show_obj or not (show_obj.tvid == tvid and show_obj.prodid == prodid):
                    show_obj = helpers.find_show_by_id({tvid: prodid})

                # for when there is orphaned series in the database but not loaded into our showlist
                if not show_obj:
                    continue

            except exceptions_helper.MultipleShowObjectsException:
                logger.log(u'ERROR: expected to find a single show matching %s' % cur_result['showid'])
                continue

            try:
                end_time = (network_timezones.parse_date_time(cur_result['airdate'], show_obj.airs, show_obj.network) +
                            datetime.timedelta(minutes=helpers.try_int(show_obj.runtime, 60)))
                # filter out any episodes that haven't aired yet
                if end_time > cur_time:
                    continue
            except (BaseException, Exception):
                # if an error occurred assume the episode hasn't aired yet
                continue

            ep_obj = show_obj.get_episode(int(cur_result['season']), int(cur_result['episode']))
            with ep_obj.lock:
                # Now that it is time, change state of UNAIRED show into expected or skipped
                ep_obj.status = (common.WANTED, common.SKIPPED)[ep_obj.show_obj.paused]
                result = ep_obj.get_sql()
                if None is not result:
                    sql_l.append(result)
                    wanted |= (False, True)[common.WANTED == ep_obj.status]

        if not wanted:
            logger.log(u'No unaired episodes marked wanted')

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)
            if wanted:
                logger.log(u'Found new episodes marked wanted')

    @staticmethod
    def update_providers(needed=common.NeededQualities(need_all=True)):
        # type: (sickbeard.common.NeededQualities) -> None
        """

        :param needed: needed class
        :type needed: common.NeededQualities
        """
        orig_thread_name = threading.currentThread().name
        threads = []

        providers = filter_list(lambda x: x.is_active() and x.enable_recentsearch,
                                sickbeard.providers.sortedProviderList())
        for cur_provider in providers:
            if not cur_provider.cache.should_update():
                continue

            if not threads:
                logger.log('Updating provider caches with recent upload data')

            # spawn a thread for each provider to save time waiting for slow response providers
            threads.append(threading.Thread(target=cur_provider.cache.updateCache,
                                            kwargs={'needed': needed},
                                            name='%s :: [%s]' % (orig_thread_name, cur_provider.name)))
            # start the thread we just created
            threads[-1].start()

        if not len(providers):
            logger.log('No NZB/Torrent providers in Media Providers/Options are enabled to match recent episodes',
                       logger.WARNING)

        if threads:
            # wait for all threads to finish
            for t in threads:
                t.join()

            logger.log('Finished updating provider caches')


class ProperSearchQueueItem(generic_queue.QueueItem):
    def __init__(self, provider_proper_obj=None):
        # type: (Optional[Dict]) -> None
        generic_queue.QueueItem.__init__(self, 'Proper Search', PROPER_SEARCH)
        self.priority = (generic_queue.QueuePriorities.VERYHIGH,
                         generic_queue.QueuePriorities.HIGH)[None is provider_proper_obj]
        self.propers = provider_proper_obj  # type: Optional[Dict]
        self.success = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            properFinder.search_propers(self.propers)
        finally:
            self.finish()


class BaseSearchQueueItem(generic_queue.QueueItem):
    def __init__(self, show_obj, segment, name, action_id=0):
        # type: (sickbeard.tv.TVShow, Union[TVEpisode, List[TVEpisode]], AnyStr, int) -> None
        """

        :param show_obj: show object
        :param segment: segment
        :param name: name
        :param action_id:
        """
        super(BaseSearchQueueItem, self).__init__(name, action_id)
        self.segment = segment  # type: Union[TVEpisode, List[TVEpisode]]
        self.show_obj = show_obj
        self.added_dt = None
        self.success = None
        self.snatched_eps = set([])

    def base_info(self):
        return SimpleNamespace(
            success=self.success,
            added_dt=self.added_dt,
            snatched_eps=copy.deepcopy(self.snatched_eps),
            show_ns=SimpleNamespace(
                tvid=self.show_obj.tvid, prodid=self.show_obj.prodid, tvid_prodid=self.show_obj.tvid_prodid,
                quality=self.show_obj.quality, upgrade_once=self.show_obj.upgrade_once),
            segment_ns=[SimpleNamespace(
                season=s.season, episode=s.episode, status=s.status,
                show_ns=SimpleNamespace(
                    tvid=s.show_obj.tvid, prodid=s.show_obj.prodid, tvid_prodid=self.show_obj.tvid_prodid,
                    quality=s.show_obj.quality, upgrade_once=s.show_obj.upgrade_once
                )) for s in ([self.segment], self.segment)[isinstance(self.segment, list)]])


class ManualSearchQueueItem(BaseSearchQueueItem):
    def __init__(self, show_obj, segment):
        # type: (sickbeard.tv.TVShow, sickbeard.tv.TVEpisode) -> None
        """

        :param show_obj: show object
        :param segment: segment
        """
        super(ManualSearchQueueItem, self).__init__(show_obj, segment, 'Manual Search', MANUAL_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH  # type: int
        self.name = 'MANUAL-%s' % show_obj.tvid_prodid  # type: AnyStr
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log(u'Beginning manual search for: [%s]' % self.segment.pretty_name())
            self.started = True

            ep_count, ep_count_scene = get_aired_in_season(self.show_obj)
            set_wanted_aired(self.segment, True, ep_count, ep_count_scene, manual=True)
            if not getattr(self.segment, 'wanted_quality', None):
                ep_status, ep_quality = common.Quality.splitCompositeStatus(self.segment.status)
                self.segment.wanted_quality = search.get_wanted_qualities(self.segment, ep_status, ep_quality,
                                                                          unaired=True, manual=True)
                if not self.segment.wanted_quality:
                    logger.log('No qualities wanted for episode, exiting manual search')
                    self.success = False
                    self.finish()
                    return

            search_result = search.search_providers(self.show_obj, [self.segment], True, try_other_searches=True)

            if search_result:
                for result in search_result:  # type: sickbeard.classes.NZBSearchResult
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    self.success = search.snatch_episode(result)
                    for ep_obj in result.ep_obj_list:  # type: sickbeard.tv.TVEpisode
                        self.snatched_eps.add((ep_obj.show_obj.tvid_prodid, ep_obj.season, ep_obj.episode))

                    helpers.cpu_sleep()

                    # just use the first result for now
                    break
            else:
                ui.notifications.message('No downloads found',
                                         u'Could not find a download for <i>%s</i>' % self.segment.pretty_name())

                logger.log(u'Unable to find a download for: [%s]' % self.segment.pretty_name())

        except (BaseException, Exception):
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            # Keep a list with the last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self.base_info())

            if None is self.success:
                self.success = False

            self.finish()


class BacklogQueueItem(BaseSearchQueueItem):
    def __init__(
            self,
            show_obj,  # type: sickbeard.tv.TVShow
            segment,  # type: List[sickbeard.tv.TVEpisode]
            standard_backlog=False,  # type: bool
            limited_backlog=False,  # type: bool
            forced=False,  # type: bool
            torrent_only=False  # type: bool
    ):
        """

        :param show_obj: show object
        :param segment: segment
        :param standard_backlog: is standard backlog
        :param limited_backlog: is limited backlog
        :param forced: forced
        :param torrent_only: torrent only
        """
        super(BacklogQueueItem, self).__init__(show_obj, segment, 'Backlog', BACKLOG_SEARCH)
        self.priority = generic_queue.QueuePriorities.LOW  # type: int
        self.name = 'BACKLOG-%s' % show_obj.tvid_prodid  # type: AnyStr
        self.standard_backlog = standard_backlog  # type: bool
        self.limited_backlog = limited_backlog  # type: bool
        self.forced = forced  # type: bool
        self.torrent_only = torrent_only  # type: bool

    def run(self):
        generic_queue.QueueItem.run(self)

        is_error = False
        try:
            if not self.standard_backlog:
                ep_count, ep_count_scene = get_aired_in_season(self.show_obj)
                for ep_obj in self.segment:  # type: sickbeard.tv.TVEpisode
                    set_wanted_aired(ep_obj, True, ep_count, ep_count_scene)

            logger.log(u'Beginning backlog search for: [%s]' % self.show_obj.name)
            search_result = search.search_providers(
                self.show_obj, self.segment, False,
                try_other_searches=(not self.standard_backlog or not self.limited_backlog),
                scheduled=self.standard_backlog)

            if search_result:
                for result in search_result:  # type: sickbeard.classes.NZBSearchResult
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    if search.snatch_episode(result):
                        for ep_obj in result.ep_obj_list:  # type: sickbeard.tv.TVEpisode
                            self.snatched_eps.add((ep_obj.show_obj.tvid_prodid, ep_obj.season, ep_obj.episode))

                    helpers.cpu_sleep()
            else:
                logger.log(u'No needed episodes found during backlog search for: [%s]' % self.show_obj.name)
        except (BaseException, Exception):
            is_error = True
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            logger.log('Completed backlog search %sfor: [%s]'
                       % (('', 'with a debug error ')[is_error], self.show_obj.name))
            self.finish()


class FailedQueueItem(BaseSearchQueueItem):
    def __init__(self, show_obj, segment):
        # type: (sickbeard.tv.TVShow, List[sickbeard.tv.TVEpisode]) -> None
        """

        :param show_obj: show object
        :param segment: segment
        """
        super(FailedQueueItem, self).__init__(show_obj, segment, 'Retry', FAILED_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH  # type: int
        self.name = 'RETRY-%s' % show_obj.tvid_prodid  # type: AnyStr
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)
        self.started = True

        try:
            ep_count, ep_count_scene = get_aired_in_season(self.show_obj)
            for ep_obj in self.segment:  # type: sickbeard.tv.TVEpisode

                logger.log(u'Marking episode as bad: [%s]' % ep_obj.pretty_name())

                failed_history.set_episode_failed(ep_obj)
                (release, provider) = failed_history.find_release(ep_obj)
                failed_history.revert_episode(ep_obj)
                if release:
                    failed_history.add_failed(release)
                    history.log_failed(ep_obj, release, provider)

                logger.log(u'Beginning failed download search for: [%s]' % ep_obj.pretty_name())

                set_wanted_aired(ep_obj, True, ep_count, ep_count_scene, manual=True)

            search_result = search.search_providers(self.show_obj, self.segment, True, try_other_searches=True) or []

            for result in search_result:  # type: sickbeard.classes.NZBSearchResult
                logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                if search.snatch_episode(result):
                    for ep_obj in result.ep_obj_list:  # type: sickbeard.tv.TVEpisode
                        self.snatched_eps.add((ep_obj.show_obj.tvid_prodid, ep_obj.season, ep_obj.episode))

                helpers.cpu_sleep()
            else:
                pass
                # logger.log(u'No valid episode found to retry for: [%s]' % self.segment.pretty_name())
        except (BaseException, Exception):
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            # Keep a list with the last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self.base_info())

            if None is self.success:
                self.success = False

            self.finish()


def fifo(my_list, item):
    # type: (List, Any) -> None

    remove_old_fifo(my_list)
    item.added_dt = datetime.datetime.now()
    if len(my_list) >= MANUAL_SEARCH_HISTORY_SIZE:
        my_list.pop(0)
    my_list.append(item)


def remove_old_fifo(my_list, age=datetime.timedelta(minutes=30)):
    # type: (List, datetime.timedelta) -> None

    try:
        now = datetime.datetime.now()
        my_list[:] = [i for i in my_list if not isinstance(getattr(i, 'added_dt', None), datetime.datetime)
                      or now - i.added_dt < age]
    except (BaseException, Exception):
        pass
