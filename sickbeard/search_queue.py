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

import time
import traceback
import threading
import datetime

import sickbeard
from sickbeard import db, logger, common, exceptions, helpers, network_timezones, generic_queue, search, \
    failed_history, history, ui
from sickbeard.search import wantedEpisodes


search_queue_lock = threading.Lock()

BACKLOG_SEARCH = 10
RECENT_SEARCH = 20
FAILED_SEARCH = 30
MANUAL_SEARCH = 40

MANUAL_SEARCH_HISTORY = []
MANUAL_SEARCH_HISTORY_SIZE = 100

class SearchQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self)
        self.queue_name = "SEARCHQUEUE"

    def is_in_queue(self, show, segment):
        for cur_item in self.queue:
            if isinstance(cur_item, BacklogQueueItem) and cur_item.show == show and cur_item.segment == segment:
                return True
        return False

    def is_ep_in_queue(self, segment):
        for cur_item in self.queue:
            if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and cur_item.segment == segment:
                return True
        return False
    
    def is_show_in_queue(self, show):
        for cur_item in self.queue:
            if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and cur_item.show.indexerid == show:
                return True
        return False
    
    def get_all_ep_from_queue(self, show):
        ep_obj_list = []
        for cur_item in self.queue:
            if isinstance(cur_item, (ManualSearchQueueItem, FailedQueueItem)) and str(cur_item.show.indexerid) == show:
                ep_obj_list.append(cur_item)
        
        if ep_obj_list:
            return ep_obj_list
        return False
    
    def pause_backlog(self):
        self.min_priority = generic_queue.QueuePriorities.HIGH

    def unpause_backlog(self):
        self.min_priority = 0

    def is_backlog_paused(self):
        # backlog priorities are NORMAL, this should be done properly somewhere
        return self.min_priority >= generic_queue.QueuePriorities.NORMAL

    def is_manualsearch_in_progress(self):
        # Only referenced in webserve.py, only current running manualsearch or failedsearch is needed!!
        if isinstance(self.currentItem, (ManualSearchQueueItem, FailedQueueItem)):
            return True
        return False
    
    def is_backlog_in_progress(self):
        for cur_item in self.queue + [self.currentItem]:
            if isinstance(cur_item, BacklogQueueItem):
                return True
        return False

    def is_recentsearch_in_progress(self):
        for cur_item in self.queue + [self.currentItem]:
            if isinstance(cur_item, RecentSearchQueueItem):
                return True
        return False

    def queue_length(self):
        length = {'backlog': 0, 'recent': 0, 'manual': 0, 'failed': 0}
        for cur_item in self.queue:
            if isinstance(cur_item, RecentSearchQueueItem):
                length['recent'] += 1
            elif isinstance(cur_item, BacklogQueueItem):
                length['backlog'] += 1
            elif isinstance(cur_item, ManualSearchQueueItem):
                length['manual'] += 1
            elif isinstance(cur_item, FailedQueueItem):
                length['failed'] += 1
        return length


    def add_item(self, item):
        if isinstance(item, RecentSearchQueueItem):
            # recent searches
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, BacklogQueueItem) and not self.is_in_queue(item.show, item.segment):
            # backlog searches
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, (ManualSearchQueueItem, FailedQueueItem)) and not self.is_ep_in_queue(item.segment):
            # manual and failed searches
            generic_queue.GenericQueue.add_item(self, item)
        else:
            logger.log(u"Not adding item, it's already in the queue", logger.DEBUG)


class RecentSearchQueueItem(generic_queue.QueueItem):
    def __init__(self):
        self.success = None
        self.episodes = []
        generic_queue.QueueItem.__init__(self, 'Recent Search', RECENT_SEARCH)

    def run(self):
        generic_queue.QueueItem.run(self)

        self._change_missing_episodes()

        self.update_providers()

        show_list = sickbeard.showList
        fromDate = datetime.date.fromordinal(1)
        for curShow in show_list:
            if curShow.paused:
                continue

            self.episodes.extend(wantedEpisodes(curShow, fromDate))

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
                found_results = search.searchForNeededEpisodes(self.episodes)

                if not len(found_results):
                    logger.log(u'No needed episodes found')
                else:
                    for result in found_results:
                        # just use the first result for now
                        logger.log(u'Downloading %s from %s' % (result.name, result.provider.name))
                        self.success = search.snatchEpisode(result)

                        # give the CPU a break
                        time.sleep(common.cpu_presets[sickbeard.CPU_PRESET])

            except Exception:
                logger.log(traceback.format_exc(), logger.DEBUG)

            if self.success is None:
                self.success = False

        self.finish()

    @staticmethod
    def _change_missing_episodes():
        if not network_timezones.network_dict:
            network_timezones.update_network_dict()

        if network_timezones.network_dict:
            curDate = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
        else:
            curDate = (datetime.date.today() - datetime.timedelta(days=2)).toordinal()

        curTime = datetime.datetime.now(network_timezones.sb_timezone)

        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM tv_episodes WHERE status = ? AND season > 0 AND airdate <= ?',
                                 [common.UNAIRED, curDate])

        sql_l = []
        wanted = show = None

        for sqlEp in sqlResults:
            try:
                if not show or int(sqlEp['showid']) != show.indexerid:
                    show = helpers.findCertainShow(sickbeard.showList, int(sqlEp['showid']))

                # for when there is orphaned series in the database but not loaded into our showlist
                if not show:
                    continue

            except exceptions.MultipleShowObjectsException:
                logger.log(u'ERROR: expected to find a single show matching ' + str(sqlEp['showid']))
                continue

            try:
                end_time = network_timezones.parse_date_time(sqlEp['airdate'], show.airs, show.network) + datetime.timedelta(minutes=helpers.tryInt(show.runtime, 60))
                # filter out any episodes that haven't aired yet
                if end_time > curTime:
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
                    sql_l.append(ep.get_sql())
                    wanted |= (False, True)[common.WANTED == ep.status]
        else:
            logger.log(u'No unaired episodes marked wanted')

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)
            if wanted:
                logger.log(u'Found new episodes marked wanted')

    @staticmethod
    def update_providers():
        origThreadName = threading.currentThread().name
        threads = []

        logger.log('Updating provider caches with recent upload data')

        providers = [x for x in sickbeard.providers.sortedProviderList() if x.isActive() and x.enable_recentsearch]
        for curProvider in providers:
            # spawn separate threads for each provider so we don't need to wait for providers with slow network operation
            threads.append(threading.Thread(target=curProvider.cache.updateCache, name=origThreadName +
                                                                                       ' :: [' + curProvider.name + ']'))
            # start the thread we just created
            threads[-1].start()

        # wait for all threads to finish
        for t in threads:
            t.join()

        logger.log('Finished updating provider caches')


class ManualSearchQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment):
        generic_queue.QueueItem.__init__(self, 'Manual Search', MANUAL_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'MANUAL-' + str(show.indexerid)
        self.success = None
        self.show = show
        self.segment = segment
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log("Beginning manual search for: [" + self.segment.prettyName() + "]")
            self.started = True
            
            searchResult = search.searchProviders(self.show, [self.segment], True)

            if searchResult:
                # just use the first result for now
                logger.log(u"Downloading " + searchResult[0].name + " from " + searchResult[0].provider.name)
                self.success = search.snatchEpisode(searchResult[0])

                # give the CPU a break
                time.sleep(common.cpu_presets[sickbeard.CPU_PRESET])

            else:
                ui.notifications.message('No downloads were found',
                                         "Couldn't find a download for <i>%s</i>" % self.segment.prettyName())

                logger.log(u"Unable to find a download for: [" + self.segment.prettyName() + "]")

        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)
        
        ### Keep a list with the 100 last executed searches
        fifo(MANUAL_SEARCH_HISTORY, self, MANUAL_SEARCH_HISTORY_SIZE)
        
        if self.success is None:
            self.success = False

        self.finish()


class BacklogQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment):
        generic_queue.QueueItem.__init__(self, 'Backlog', BACKLOG_SEARCH)
        self.priority = generic_queue.QueuePriorities.LOW
        self.name = 'BACKLOG-' + str(show.indexerid)
        self.success = None
        self.show = show
        self.segment = segment

    def run(self):
        generic_queue.QueueItem.run(self)

        try:
            logger.log("Beginning backlog search for: [" + self.show.name + "]")
            searchResult = search.searchProviders(self.show, self.segment, False)

            if searchResult:
                for result in searchResult:
                    # just use the first result for now
                    logger.log(u"Downloading " + result.name + " from " + result.provider.name)
                    search.snatchEpisode(result)

                    # give the CPU a break
                    time.sleep(common.cpu_presets[sickbeard.CPU_PRESET])
            else:
                logger.log(u"No needed episodes found during backlog search for: [" + self.show.name + "]")
        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)

        self.finish()


class FailedQueueItem(generic_queue.QueueItem):
    def __init__(self, show, segment):
        generic_queue.QueueItem.__init__(self, 'Retry', FAILED_SEARCH)
        self.priority = generic_queue.QueuePriorities.HIGH
        self.name = 'RETRY-' + str(show.indexerid)
        self.show = show
        self.segment = segment
        self.success = None
        self.started = None

    def run(self):
        generic_queue.QueueItem.run(self)
        self.started = True
        
        try:
            for epObj in self.segment:
            
                logger.log(u"Marking episode as bad: [" + epObj.prettyName() + "]")
                
                failed_history.markFailed(epObj)
    
                (release, provider) = failed_history.findRelease(epObj)
                if release:
                    failed_history.logFailed(release)
                    history.logFailed(epObj, release, provider)
    
                failed_history.revertEpisode(epObj)
                logger.log("Beginning failed download search for: [" + epObj.prettyName() + "]")

            searchResult = search.searchProviders(self.show, self.segment, True)

            if searchResult:
                for result in searchResult:
                    # just use the first result for now
                    logger.log(u"Downloading " + result.name + " from " + result.provider.name)
                    search.snatchEpisode(result)

                    # give the CPU a break
                    time.sleep(common.cpu_presets[sickbeard.CPU_PRESET])
            else:
                pass
                #logger.log(u"No valid episode found to retry for: [" + self.segment.prettyName() + "]")
        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)
            
        ### Keep a list with the 100 last executed searches
        fifo(MANUAL_SEARCH_HISTORY, self, MANUAL_SEARCH_HISTORY_SIZE)

        if self.success is None:
            self.success = False

        self.finish()
        
def fifo(myList, item, maxSize = 100):
    if len(myList) >= maxSize:
        myList.pop(0)
    myList.append(item)
