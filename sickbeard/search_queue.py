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

import sickbeard
from sickbeard import db, logger, common, exceptions, helpers, network_timezones, generic_queue, search, \
    failed_history, history, ui, properFinder
from sickbeard.search import wanted_episodes
from sickbeard.common import Quality


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

    def get_all_ep_from_queue(self, show):
        with self.lock:
            ep_obj_list = []
            for cur_item in self.queue:
                if (isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and
                        show == str(cur_item.show.indexerid)):
                    ep_obj_list.append(cur_item)

            if ep_obj_list:
                return ep_obj_list
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

    def is_manualsearch_in_progress(self):
        # Only referenced in webserve.py, only current running manualsearch or failedsearch is needed!!
        return self._is_in_progress((ManualSearchQueueItem, FailedQueueItem))

    def is_backlog_in_progress(self):
        return self._is_in_progress(BacklogQueueItem)

    def is_recentsearch_in_progress(self):
        return self._is_in_progress(RecentSearchQueueItem)

    def is_propersearch_in_progress(self):
        return self._is_in_progress(ProperSearchQueueItem)

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
        length = {'backlog': [], 'recent': 0, 'manual': [], 'failed': [], 'proper': 0}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:
                if isinstance(cur_item, RecentSearchQueueItem):
                    length['recent'] += 1
                elif isinstance(cur_item, BacklogQueueItem):
                    length['backlog'].append({'indexerid': cur_item.show.indexerid, 'indexer': cur_item.show.indexer,
                                              'name': cur_item.show.name, 'segment': cur_item.segment,
                                              'standard_backlog': cur_item.standard_backlog,
                                              'limited_backlog': cur_item.limited_backlog, 'forced': cur_item.forced,
                                              'torrent_only': cur_item.torrent_only})
                elif isinstance(cur_item, ProperSearchQueueItem):
                    length['proper'] += 1
                elif isinstance(cur_item, ManualSearchQueueItem):
                    length['manual'].append({'indexerid': cur_item.show.indexerid, 'indexer': cur_item.show.indexer,
                                             'name': cur_item.show.name, 'segment': cur_item.segment})
                elif isinstance(cur_item, FailedQueueItem):
                    length['failed'].append({'indexerid': cur_item.show.indexerid, 'indexer': cur_item.show.indexer,
                                             'name': cur_item.show.name, 'segment': cur_item.segment})
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

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            self._change_missing_episodes()

            show_list = sickbeard.showList
            from_date = datetime.date.fromordinal(1)
            need_anime = need_sports = need_sd = need_hd = need_uhd = False
            max_sd = Quality.SDDVD
            hd_qualities = [Quality.HDTV, Quality.FULLHDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL,
                            Quality.HDBLURAY, Quality.FULLHDBLURAY]
            max_hd = Quality.FULLHDBLURAY
            for curShow in show_list:
                if curShow.paused:
                    continue

                wanted_eps = wanted_episodes(curShow, from_date, unaired=sickbeard.SEARCH_UNAIRED)
                if wanted_eps:
                    if not need_anime and curShow.is_anime:
                        need_anime = True
                    if not need_sports and curShow.is_sports:
                        need_sports = True
                    if not need_sd or not need_hd:
                        for w in wanted_eps:
                            if not w.show.is_anime and not w.show.is_sports:
                                if not need_sd and max_sd >= min(w.wantedQuality):
                                    need_sd = True
                                if not need_hd and any(i in hd_qualities for i in w.wantedQuality):
                                    need_hd = True
                                if not need_uhd and max_hd < max(w.wantedQuality):
                                    need_uhd = True
                self.episodes.extend(wanted_eps)

            self.update_providers(need_anime=need_anime, need_sports=need_sports,
                                  need_sd=need_sd, need_hd=need_hd, need_uhd=need_uhd)

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

                            helpers.cpu_sleep()

                except Exception:
                    logger.log(traceback.format_exc(), logger.DEBUG)

                if None is self.success:
                    self.success = False

        finally:
            self.finish()

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
        sql_results = my_db.select('SELECT * FROM tv_episodes WHERE status = ? AND season > 0 AND airdate <= ? AND airdate > 1',
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
            except:
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
    def update_providers(need_anime=True, need_sports=True, need_sd=True, need_hd=True, need_uhd=True):
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
                                            kwargs={'need_anime': need_anime, 'need_sports': need_sports,
                                                    'need_sd': need_sd, 'need_hd': need_hd, 'need_uhd': need_uhd},
                                            name='%s :: [%s]' % (orig_thread_name, cur_provider.name)))
            # start the thread we just created
            threads[-1].start()

        if not len(providers):
            logger.log('No NZB/Torrent sources enabled in Search Provider options for cache update', logger.WARNING)

        if threads:
            # wait for all threads to finish
            for t in threads:
                t.join()

            logger.log('Finished updating provider caches')


class ProperSearchQueueItem(generic_queue.QueueItem):
    def __init__(self):
        generic_queue.QueueItem.__init__(self, 'Proper Search', PROPER_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.success = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            properFinder.search_propers()
        finally:
            self.finish()


class ManualSearchQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment):
        generic_queue.QueueItem.__init__(self, 'Manual Search', MANUAL_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'MANUAL-%s' % show.indexerid
        self.success = None
        self.show = show
        self.segment = segment
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log(u'Beginning manual search for: [%s]' % self.segment.prettyName())
            self.started = True

            search_result = search.search_providers(self.show, [self.segment], True, try_other_searches=True)

            if search_result:
                # just use the first result for now
                logger.log(u'Downloading %s from %s' % (search_result[0].name, search_result[0].provider.name))
                self.success = search.snatch_episode(search_result[0])

                helpers.cpu_sleep()

            else:
                ui.notifications.message('No downloads found',
                                         u'Could not find a download for <i>%s</i>' % self.segment.prettyName())

                logger.log(u'Unable to find a download for: [%s]' % self.segment.prettyName())

        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)

        finally:
            # Keep a list with the 100 last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self, MANUAL_SEARCH_HISTORY_SIZE)

            if self.success is None:
                self.success = False

            self.finish()


class BacklogQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment, standard_backlog=False, limited_backlog=False, forced=False, torrent_only=False):
        generic_queue.QueueItem.__init__(self, 'Backlog', BACKLOG_SEARCH)
        self.priority = generic_queue.QueuePriorities.LOW
        self.name = 'BACKLOG-%s' % show.indexerid
        self.success = None
        self.show = show
        self.segment = segment
        self.standard_backlog = standard_backlog
        self.limited_backlog = limited_backlog
        self.forced = forced
        self.torrent_only = torrent_only

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log(u'Beginning backlog search for: [%s]' % self.show.name)
            search_result = search.search_providers(
                self.show, self.segment, False,
                try_other_searches=(not self.standard_backlog or not self.limited_backlog))

            if search_result:
                for result in search_result:
                    # just use the first result for now
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    search.snatch_episode(result)

                    helpers.cpu_sleep()
            else:
                logger.log(u'No needed episodes found during backlog search for: [%s]' % self.show.name)
        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)

        finally:
            self.finish()


class FailedQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment):
        generic_queue.QueueItem.__init__(self, 'Retry', FAILED_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'RETRY-%s' % show.indexerid
        self.show = show
        self.segment = segment
        self.success = None
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)
        self.started = True

        try:
            for epObj in self.segment:

                logger.log(u'Marking episode as bad: [%s]' % epObj.prettyName())

                failed_history.markFailed(epObj)

                (release, provider) = failed_history.findRelease(epObj)
                if release:
                    failed_history.logFailed(release)
                    history.logFailed(epObj, release, provider)

                failed_history.revertEpisode(epObj)
                logger.log(u'Beginning failed download search for: [%s]' % epObj.prettyName())

            search_result = search.search_providers(self.show, self.segment, True, try_other_searches=True)

            if search_result:
                for result in search_result:
                    # just use the first result for now
                    logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                    search.snatch_episode(result)

                    helpers.cpu_sleep()
            else:
                pass
                # logger.log(u'No valid episode found to retry for: [%s]' % self.segment.prettyName())
        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)

        finally:
            # Keep a list with the 100 last executed searches
            fifo(MANUAL_SEARCH_HISTORY, self, MANUAL_SEARCH_HISTORY_SIZE)

            if self.success is None:
                self.success = False

            self.finish()


def fifo(my_list, item, max_size=100):
    if len(my_list) >= max_size:
        my_list.pop(0)
    my_list.append(item)
