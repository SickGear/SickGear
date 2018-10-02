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

import traceback
import threading
import datetime
import re
import copy

import sickbeard
from sickbeard import db, logger, common, exceptions, helpers, network_timezones, generic_queue, search, \
    failed_history, history, ui, properFinder
from sickbeard.search import wanted_episodes, get_aired_in_season, set_wanted_aired
from sickbeard.classes import Proper, SimpleNamespace
from sickbeard.indexers.indexer_config import INDEXER_TVDB


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
        self.queue_name = 'SEARCHQUEUE'

    def is_in_queue(self, show, segment):
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, BacklogQueueItem) and cur_item.show == show and cur_item.segment == segment:
                    return True
            return False

    def is_ep_in_queue(self, segment):
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and cur_item.segment == segment:
                    return True
            return False

    def is_show_in_queue(self, show):
        with self.lock:
            for cur_item in self.queue:
                if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and cur_item.show.indexerid == show:
                    return True
            return False

    def pause_backlog(self):
        with self.lock:
            self.min_priority = generic_queue.QueuePriorities.HIGH

    def unpause_backlog(self):
        with self.lock:
            self.min_priority = 0

    def is_backlog_paused(self):
        # backlog priorities are NORMAL, this should be done properly somewhere
        with self.lock:
            return self.min_priority >= generic_queue.QueuePriorities.NORMAL

    def _is_in_progress(self, item_type):
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, item_type):
                    return True
            return False

    def get_queued_manual(self, show):
        """
        Returns None or List of base info items of all show related items in manual or failed queue
        :param show: show indexerid or None for all q items
        :type show: String or None
        :return: List with 0 or more items
        """
        ep_obj_list = []
        with self.lock:
            for cur_item in self.queue:
                if (isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and
                        (not show or show == str(cur_item.show.indexerid))):
                    ep_obj_list.append(cur_item.base_info())

        return ep_obj_list

    def get_current_manual_item(self, show):
        """
        Returns a base info item of the currently active manual search item
        :param show: show indexerid or None for all q items
        :type show: String or None
        :return: base info item of ManualSearchQueueItem or FailedQueueItem or None
        """
        with self.lock:
            if self.currentItem and isinstance(self.currentItem, (ManualSearchQueueItem, FailedQueueItem)) \
                    and (not show or show == str(self.currentItem.show.indexerid)):
                return self.currentItem.base_info()

    def is_backlog_in_progress(self):
        return self._is_in_progress(BacklogQueueItem)

    def is_recentsearch_in_progress(self):
        return self._is_in_progress(RecentSearchQueueItem)

    def is_propersearch_in_progress(self):
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, ProperSearchQueueItem) and None is cur_item.propers:
                    return True
            return False

    def is_standard_backlog_in_progress(self):
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, BacklogQueueItem) and cur_item.standard_backlog:
                    return True
            return False

    def type_of_backlog_in_progress(self):
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
        length = {'backlog': [], 'recent': 0, 'manual': [], 'failed': [], 'proper': []}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:
                if isinstance(cur_item, RecentSearchQueueItem):
                    length['recent'] += 1
                elif isinstance(cur_item, BacklogQueueItem):
                    length['backlog'] += [dict(indexerid=cur_item.show.indexerid, indexer=cur_item.show.indexer,
                                               name=cur_item.show.name, segment=cur_item.segment,
                                               standard_backlog=cur_item.standard_backlog,
                                               limited_backlog=cur_item.limited_backlog, forced=cur_item.forced,
                                               torrent_only=cur_item.torrent_only)]
                elif isinstance(cur_item, ProperSearchQueueItem):
                    length['proper'] += [dict(recent=None is not cur_item.propers)]
                elif isinstance(cur_item, ManualSearchQueueItem):
                    length['manual'] += [dict(indexerid=cur_item.show.indexerid, indexer=cur_item.show.indexer,
                                              name=cur_item.show.name, segment=cur_item.segment)]
                elif isinstance(cur_item, FailedQueueItem):
                    length['failed'] += [dict(indexerid=cur_item.show.indexerid, indexer=cur_item.show.indexer,
                                              name=cur_item.show.name, segment=cur_item.segment)]
            return length

    def add_item(self, item):
        if isinstance(item, (RecentSearchQueueItem, ProperSearchQueueItem)):
            # recent and proper searches
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, BacklogQueueItem) and not self.is_in_queue(item.show, item.segment):
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
        self.episodes = []
        generic_queue.QueueItem.__init__(self, 'Recent Search', RECENT_SEARCH)
        self.snatched_eps = set([])

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            self._change_missing_episodes()

            show_list = sickbeard.showList
            from_date = datetime.date.fromordinal(1)
            needed = common.neededQualities()
            for curShow in show_list:
                if curShow.paused:
                    continue

                wanted_eps = wanted_episodes(curShow, from_date, unaired=sickbeard.SEARCH_UNAIRED)

                if wanted_eps:
                    if not needed.all_needed:
                        if not needed.all_types_needed:
                            needed.check_needed_types(curShow)
                        if not needed.all_qualities_needed:
                            for w in wanted_eps:
                                if needed.all_qualities_needed:
                                    break
                                if not w.show.is_anime and not w.show.is_sports:
                                    needed.check_needed_qualities(w.wantedQuality)

                    self.episodes.extend(wanted_eps)

            if sickbeard.DOWNLOAD_PROPERS:
                properFinder.get_needed_qualites(needed)

            self.update_providers(needed=needed)
            self._check_for_propers(needed)

            if not self.episodes:
                logger.log(u'No search of cache for episodes required')
                self.success = True
            else:
                num_shows = len(set([ep.show.name for ep in self.episodes]))
                logger.log(u'Found %d needed episode%s spanning %d show%s'
                           % (len(self.episodes), helpers.maybe_plural(len(self.episodes)),
                              num_shows, helpers.maybe_plural(num_shows)))

                try:
                    logger.log(u'Beginning recent search for episodes')
                    found_results = search.search_for_needed_episodes(self.episodes)

                    if not len(found_results):
                        logger.log(u'No needed episodes found')
                    else:
                        for result in found_results:
                            # just use the first result for now
                            logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                            self.success = search.snatch_episode(result)
                            if self.success:
                                for ep in result.episodes:
                                    self.snatched_eps.add((ep.show.indexer, ep.show.indexerid, ep.season, ep.episode))

                            helpers.cpu_sleep()

                except (StandardError, Exception):
                    logger.log(traceback.format_exc(), logger.ERROR)

                if None is self.success:
                    self.success = False

        finally:
            self.finish()

    @staticmethod
    def _check_for_propers(needed):
        if not sickbeard.DOWNLOAD_PROPERS:
            return

        propers = {}
        my_db = db.DBConnection('cache.db')
        sql_results = my_db.select('SELECT * FROM provider_cache')
        re_p = r'\brepack|proper|real%s\b' % ('', '|v[2-9]')[needed.need_anime]

        proper_regex = re.compile(re_p, flags=re.I)

        for s in sql_results:
            if proper_regex.search(s['name']):
                try:
                    show = helpers.find_show_by_id(sickbeard.showList, {INDEXER_TVDB: int(s['indexerid'])})
                except (StandardError, Exception):
                    continue
                if show:
                    propers.setdefault(s['provider'], []).append(
                        Proper(s['name'], s['url'], datetime.datetime.fromtimestamp(s['time']), show, parsed_show=show))

        if propers:
            logger.log('Found Proper/Repack/Real in recent search, sending data to properfinder')
            propersearch_queue_item = sickbeard.search_queue.ProperSearchQueueItem(propers=propers)
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
        sql_results = my_db.select(
            'SELECT * FROM tv_episodes WHERE status = ? AND season > 0 AND airdate <= ? AND airdate > 1',
            [common.UNAIRED, cur_date])

        sql_l = []
        show = None
        wanted = False

        for sqlEp in sql_results:
            try:
                if not show or show.indexerid != int(sqlEp['showid']):
                    show = helpers.findCertainShow(sickbeard.showList, int(sqlEp['showid']))

                # for when there is orphaned series in the database but not loaded into our showlist
                if not show:
                    continue

            except exceptions.MultipleShowObjectsException:
                logger.log(u'ERROR: expected to find a single show matching %s' % sqlEp['showid'])
                continue

            try:
                end_time = (network_timezones.parse_date_time(sqlEp['airdate'], show.airs, show.network) +
                            datetime.timedelta(minutes=helpers.tryInt(show.runtime, 60)))
                # filter out any episodes that haven't aired yet
                if end_time > cur_time:
                    continue
            except (StandardError, Exception):
                # if an error occurred assume the episode hasn't aired yet
                continue

            ep = show.getEpisode(int(sqlEp['season']), int(sqlEp['episode']))
            with ep.lock:
                # Now that it is time, change state of UNAIRED show into expected or skipped
                ep.status = (common.WANTED, common.SKIPPED)[ep.show.paused]
                result = ep.get_sql()
                if None is not result:
                    sql_l.append(result)
                    wanted |= (False, True)[common.WANTED == ep.status]
        else:
            logger.log(u'No unaired episodes marked wanted')

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)
            if wanted:
                logger.log(u'Found new episodes marked wanted')

    @staticmethod
    def update_providers(needed=common.neededQualities(need_all=True)):
        orig_thread_name = threading.currentThread().name
        threads = []

        providers = [x for x in sickbeard.providers.sortedProviderList() if x.is_active() and x.enable_recentsearch]
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
    def __init__(self, propers=None):
        generic_queue.QueueItem.__init__(self, 'Proper Search', PROPER_SEARCH)
        self.priority = (generic_queue.QueuePriorities.VERYHIGH, generic_queue.QueuePriorities.HIGH)[None is propers]
        self.propers = propers
        self.success = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            properFinder.search_propers(self.propers)
        finally:
            self.finish()


class BaseSearchQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment, name, action_id=0):
        super(BaseSearchQueueItem, self).__init__(name, action_id)
        self.segment = segment
        self.show = show
        self.added_dt = None
        self.success = None
        self.snatched_eps = set([])

    def base_info(self):
        return SimpleNamespace(
            success=self.success,
            added_dt=self.added_dt,
            snatched_eps=copy.deepcopy(self.snatched_eps),
            show=SimpleNamespace(
                indexer=self.show.indexer, indexerid=self.show.indexerid,
                quality=self.show.quality, upgrade_once=self.show.upgrade_once),
            segment=[SimpleNamespace(
                season=s.season, episode=s.episode, status=s.status,
                show=SimpleNamespace(
                    indexer=s.show.indexer, indexerid=s.show.indexerid,
                    quality=s.show.quality, upgrade_once=s.show.upgrade_once
                )) for s in ([self.segment], self.segment)[isinstance(self.segment, list)]])

    # def copy(self, deepcopy_obj=None):
    #     if not isinstance(deepcopy_obj, list):
    #         deepcopy_obj = []
    #     deepcopy_obj += ['segment']
    #     same_show = True
    #     if (isinstance(self.segment, list) and getattr(self.segment[0], 'show') is not self.show) \
    #             or getattr(self.segment, 'show') is not self.show:
    #         same_show = False
    #         deepcopy_obj += ['show']
    #     n_o = super(BaseSearchQueueItem, self).copy(deepcopy_obj)
    #     if same_show:
    #         n_o.show = (getattr(n_o.segment, 'show'), getattr(n_o.segment[0], 'show'))[isinstance(n_o.segment, list)]
    #     return n_o


class ManualSearchQueueItem(BaseSearchQueueItem):
    def __init__(self, show, segment):
        super(ManualSearchQueueItem, self).__init__(show, segment, 'Manual Search', MANUAL_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'MANUAL-%s' % show.indexerid
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log(u'Beginning manual search for: [%s]' % self.segment.prettyName())
            self.started = True

            ep_count, ep_count_scene = get_aired_in_season(self.show)
            set_wanted_aired(self.segment, True, ep_count, ep_count_scene, manual=True)

            search_result = search.search_providers(self.show, [self.segment], True, try_other_searches=True)

            if search_result:
                # just use the first result for now
                logger.log(u'Downloading %s from %s' % (search_result[0].name, search_result[0].provider.name))
                self.success = search.snatch_episode(search_result[0])
                for ep in search_result[0].episodes:
                    self.snatched_eps.add((ep.show.indexer, ep.show.indexerid, ep.season, ep.episode))

                helpers.cpu_sleep()

            else:
                ui.notifications.message('No downloads found',
                                         u'Could not find a download for <i>%s</i>' % self.segment.prettyName())

                logger.log(u'Unable to find a download for: [%s]' % self.segment.prettyName())

        except (StandardError, Exception):
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            # Keep a list with the last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self.base_info())

            if self.success is None:
                self.success = False

            self.finish()


class BacklogQueueItem(BaseSearchQueueItem):
    def __init__(self, show, segment, standard_backlog=False, limited_backlog=False, forced=False, torrent_only=False):
        super(BacklogQueueItem, self).__init__(show, segment, 'Backlog', BACKLOG_SEARCH)
        self.priority = generic_queue.QueuePriorities.LOW
        self.name = 'BACKLOG-%s' % show.indexerid
        self.standard_backlog = standard_backlog
        self.limited_backlog = limited_backlog
        self.forced = forced
        self.torrent_only = torrent_only

    def run(self):
        generic_queue.QueueItem.run(self)

        is_error = False
        try:
            if not self.standard_backlog:
                ep_count, ep_count_scene = get_aired_in_season(self.show)
                for ep_obj in self.segment:
                    set_wanted_aired(ep_obj, True, ep_count, ep_count_scene)

            logger.log(u'Beginning backlog search for: [%s]' % self.show.name)
            search_result = search.search_providers(
                self.show, self.segment, False,
                try_other_searches=(not self.standard_backlog or not self.limited_backlog),
                scheduled=self.standard_backlog)

            if search_result:
                for result in search_result:
                    # just use the first result for now
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    if search.snatch_episode(result):
                        for ep in result.episodes:
                            self.snatched_eps.add((ep.show.indexer, ep.show.indexerid, ep.season, ep.episode))

                    helpers.cpu_sleep()
            else:
                logger.log(u'No needed episodes found during backlog search for: [%s]' % self.show.name)
        except (StandardError, Exception):
            is_error = True
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            logger.log('Completed backlog search %sfor: [%s]' % (('', 'with a debug error ')[is_error], self.show.name))
            self.finish()


class FailedQueueItem(BaseSearchQueueItem):
    def __init__(self, show, segment):
        super(FailedQueueItem, self).__init__(show, segment, 'Retry', FAILED_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'RETRY-%s' % show.indexerid
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)
        self.started = True

        try:
            ep_count, ep_count_scene = get_aired_in_season(self.show)
            for ep_obj in self.segment:

                logger.log(u'Marking episode as bad: [%s]' % ep_obj.prettyName())

                failed_history.set_episode_failed(ep_obj)
                (release, provider) = failed_history.find_release(ep_obj)
                failed_history.revert_episode(ep_obj)
                if release:
                    failed_history.add_failed(release)
                    history.log_failed(ep_obj, release, provider)

                logger.log(u'Beginning failed download search for: [%s]' % ep_obj.prettyName())

                set_wanted_aired(ep_obj, True, ep_count, ep_count_scene, manual=True)

            search_result = search.search_providers(self.show, self.segment, True, try_other_searches=True)

            if search_result:
                for result in search_result:
                    # just use the first result for now
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    if search.snatch_episode(result):
                        for ep in result.episodes:
                            self.snatched_eps.add((ep.show.indexer, ep.show.indexerid, ep.season, ep.episode))

                    helpers.cpu_sleep()
            else:
                pass
                # logger.log(u'No valid episode found to retry for: [%s]' % self.segment.prettyName())
        except (StandardError, Exception):
            logger.log(traceback.format_exc(), logger.ERROR)

        finally:
            # Keep a list with the last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self.base_info())

            if self.success is None:
                self.success = False

            self.finish()


def fifo(my_list, item):
    remove_old_fifo(my_list)
    item.added_dt = datetime.datetime.now()
    if len(my_list) >= MANUAL_SEARCH_HISTORY_SIZE:
        my_list.pop(0)
    my_list.append(item)


def remove_old_fifo(my_list, age=datetime.timedelta(minutes=30)):
    try:
        now = datetime.datetime.now()
        my_list[:] = [i for i in my_list if not isinstance(getattr(i, 'added_dt', None), datetime.datetime)
                      or now - i.added_dt < age]
    except (StandardError, Exception):
        pass
