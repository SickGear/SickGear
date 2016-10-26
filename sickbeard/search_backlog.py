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

from __future__ import with_statement, division

import datetime
import threading
from math import ceil

import sickbeard

from sickbeard import db, scheduler, helpers
from sickbeard import search_queue
from sickbeard import logger
from sickbeard import ui
from sickbeard.providers.generic import GenericProvider
from sickbeard.search import wanted_episodes
from sickbeard.helpers import find_show_by_id
from sickbeard.sbdatetime import sbdatetime

NORMAL_BACKLOG = 0
LIMITED_BACKLOG = 10
FULL_BACKLOG = 20
FORCED_BACKLOG = 30


class BacklogSearchScheduler(scheduler.Scheduler):
    def force_search(self, force_type=NORMAL_BACKLOG):
        self.action.forcetype = force_type
        self.action.force = True
        self.force = True

    def next_run(self):
        if 1 >= self.action._lastBacklog:
            return datetime.date.today()
        elif (self.action._lastBacklog + self.action.cycleTime) < datetime.date.today().toordinal():
            return datetime.date.today()
        else:
            return datetime.date.fromordinal(self.action._lastBacklog + self.action.cycleTime)

    def next_backlog_timeleft(self):
        now = datetime.datetime.now()
        torrent_enabled = 0 < len([x for x in sickbeard.providers.sortedProviderList() if x.is_active() and
                                   x.enable_backlog and x.providerType == GenericProvider.TORRENT])
        if now > self.action.nextBacklog or self.action.nextCyleTime != self.cycleTime:
            nextruntime = now + self.timeLeft()
            if not torrent_enabled:
                nextpossibleruntime = (datetime.datetime.fromtimestamp(self.action.last_runtime) +
                                       datetime.timedelta(hours=23))
                for _ in xrange(5):
                    if nextruntime > nextpossibleruntime:
                        self.action.nextBacklog = nextruntime
                        self.action.nextCyleTime = self.cycleTime
                        break
                    nextruntime += self.cycleTime
            else:
                self.action.nextCyleTime = self.cycleTime
                self.action.nextBacklog = nextruntime
        return self.action.nextBacklog - now if self.action.nextBacklog > now else datetime.timedelta(seconds=0)


class BacklogSearcher:
    def __init__(self):

        self._lastBacklog = self._get_last_backlog()
        self.cycleTime = sickbeard.BACKLOG_FREQUENCY
        self.lock = threading.Lock()
        self.amActive = False
        self.amPaused = False
        self.amWaiting = False
        self.forcetype = NORMAL_BACKLOG
        self.force = False
        self.nextBacklog = datetime.datetime.fromtimestamp(1)
        self.nextCyleTime = None
        self.currentSearchInfo = None

        self._reset_progress_indicator()

    @property
    def last_runtime(self):
        return self._get_last_runtime()

    def _reset_progress_indicator(self):
        self.percentDone = 0
        self.currentSearchInfo = {'title': 'Initializing'}

    def get_progress_indicator(self):
        if self.amActive:
            return ui.ProgressIndicator(self.percentDone, self.currentSearchInfo)
        else:
            return None

    def am_running(self):
        logger.log(u'amWaiting: ' + str(self.amWaiting) + ', amActive: ' + str(self.amActive), logger.DEBUG)
        return (not self.amWaiting) and self.amActive

    def add_backlog_item(self, items, standard_backlog, limited_backlog, forced, torrent_only):
        for segments in items:
            if len(segments):
                for season, segment in segments.items():
                    self.currentSearchInfo = {'title': segment[0].show.name + ' Season ' + str(season)}

                    backlog_queue_item = search_queue.BacklogQueueItem(
                        segment[0].show, segment, standard_backlog=standard_backlog, limited_backlog=limited_backlog,
                        forced=forced, torrent_only=torrent_only)
                    sickbeard.searchQueueScheduler.action.add_item(backlog_queue_item)

    @staticmethod
    def change_backlog_parts(old_count, new_count):
        try:
            my_db = db.DBConnection('cache.db')
            sql_result = my_db.select('SELECT * FROM backlogparts')
            if sql_result:
                current_parts = len(set(s['part'] for s in sql_result))
                parts_count = len(sql_result)
                new_part_count = int(ceil(new_count / old_count * current_parts))
                parts = int(ceil(parts_count / new_part_count))
                cl = ([], [['DELETE FROM backlogparts']])[parts_count > 1]
                p = new_count - new_part_count
                for i, s in enumerate(sql_result):
                    if i % parts == 0:
                        p += 1
                    cl.append(['INSERT INTO backlogparts (part, indexerid, indexer) VALUES (?,?,?)',
                               [p, s['indexerid'], s['indexer']]])

                if 0 < len(cl):
                    my_db.mass_action(cl)
        except (StandardError, Exception):
            pass

    def search_backlog(self, which_shows=None, force_type=NORMAL_BACKLOG, force=False):

        if self.amActive:
            logger.log(u'Backlog is still running, not starting it again', logger.DEBUG)
            return

        if which_shows:
            show_list = which_shows
            standard_backlog = False
        else:
            show_list = sickbeard.showList
            standard_backlog = True

        now = datetime.datetime.now()
        any_torrent_enabled = continued_backlog = False
        if not force and standard_backlog and (datetime.datetime.now() - datetime.datetime.fromtimestamp(
                self._get_last_runtime())) < datetime.timedelta(hours=23):
            any_torrent_enabled = any([x for x in sickbeard.providers.sortedProviderList() if x.is_active()
                                       and x.enable_backlog and x.providerType == GenericProvider.TORRENT])
            if not any_torrent_enabled:
                logger.log('Last scheduled Backlog run was within the last day, skipping this run.', logger.DEBUG)
                return

        self._get_last_backlog()
        self.amActive = True
        self.amPaused = False

        cur_date = datetime.date.today().toordinal()
        from_date = datetime.date.fromordinal(1)
        limited_from_date = datetime.date.today() - datetime.timedelta(days=sickbeard.BACKLOG_DAYS)

        limited_backlog = False
        if standard_backlog and (any_torrent_enabled or sickbeard.BACKLOG_NOFULL):
            logger.log(u'Running limited backlog for episodes missed during the last %s day(s)' %
                       str(sickbeard.BACKLOG_DAYS))
            from_date = limited_from_date
            limited_backlog = True

        runparts = []
        if standard_backlog and not any_torrent_enabled and sickbeard.BACKLOG_NOFULL:
            logger.log(u'Skipping automated full backlog search because it is disabled in search settings')

        if standard_backlog and not any_torrent_enabled and not sickbeard.BACKLOG_NOFULL:
            my_db = db.DBConnection('cache.db')
            sql_result = my_db.select('SELECT * FROM backlogparts WHERE part in (SELECT MIN(part) FROM backlogparts)')
            if sql_result:
                sl = []
                part_nr = int(sql_result[0]['part'])
                for s in sql_result:
                    show_obj = find_show_by_id(sickbeard.showList, {int(s['indexer']): int(s['indexerid'])})
                    if show_obj:
                        sl.append(show_obj)
                        runparts.append([int(s['indexerid']), int(s['indexer'])])
                show_list = sl
                continued_backlog = True
                my_db.action('DELETE FROM backlogparts WHERE part = ?', [part_nr])

        forced = standard_backlog and force_type != NORMAL_BACKLOG

        wanted_list = []
        for curShow in show_list:
            if not curShow.paused:
                w = wanted_episodes(curShow, from_date, make_dict=True,
                                    unaired=(sickbeard.SEARCH_UNAIRED and not sickbeard.UNAIRED_RECENT_SEARCH_ONLY))
                if w:
                    wanted_list.append(w)

        parts = []
        if standard_backlog and not any_torrent_enabled and not continued_backlog and not sickbeard.BACKLOG_NOFULL:
            fullbacklogparts = sum([len(w) for w in wanted_list if w]) // sickbeard.BACKLOG_FREQUENCY
            h_part = []
            counter = 0
            for w in wanted_list:
                f = False
                for season, segment in w.iteritems():
                    counter += 1
                    if not f:
                        h_part.append([segment[0].show.indexerid, segment[0].show.indexer])
                        f = True
                if counter > fullbacklogparts:
                    counter = 0
                    parts.append(h_part)
                    h_part = []

            if h_part:
                parts.append(h_part)

        def in_showlist(show, showlist):
            return 0 < len([item for item in showlist if item[1] == show.indexer and item[0] == show.indexerid])

        if not runparts and parts:
            runparts = parts[0]
            wanted_list = [w for w in wanted_list if w and in_showlist(w.itervalues().next()[0].show, runparts)]

        limited_wanted_list = []
        if standard_backlog and not any_torrent_enabled and runparts:
            for curShow in sickbeard.showList:
                if not curShow.paused and not in_showlist(curShow, runparts):
                    w = wanted_episodes(curShow, limited_from_date, make_dict=True,
                                        unaired=(sickbeard.SEARCH_UNAIRED and not sickbeard.UNAIRED_RECENT_SEARCH_ONLY))
                    if w:
                        limited_wanted_list.append(w)

        self.add_backlog_item(wanted_list, standard_backlog, limited_backlog, forced, any_torrent_enabled)
        if standard_backlog and not any_torrent_enabled and limited_wanted_list:
            self.add_backlog_item(limited_wanted_list, standard_backlog, True, forced, any_torrent_enabled)

        if standard_backlog and not sickbeard.BACKLOG_NOFULL and not any_torrent_enabled and not continued_backlog:
            cl = ([], [['DELETE FROM backlogparts']])[len(parts) > 1]
            for i, l in enumerate(parts):
                if 0 == i:
                    continue
                for m in l:
                    cl.append(['INSERT INTO backlogparts (part, indexerid, indexer) VALUES (?,?,?)',
                               [i + 1, m[0], m[1]]])

            if 0 < len(cl):
                my_db.mass_action(cl)

        # don't consider this an actual backlog search if we only did recent eps
        # or if we only did certain shows
        if from_date == datetime.date.fromordinal(1) and standard_backlog:
            self._set_last_backlog(cur_date)
            self._get_last_backlog()

        if standard_backlog and not any_torrent_enabled:
            self._set_last_runtime(now)

        self.amActive = False
        self._reset_progress_indicator()

    @staticmethod
    def _get_last_runtime():
        logger.log('Retrieving the last runtime of Backlog from the DB', logger.DEBUG)

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM info')

        if 0 == len(sql_results):
            last_run_time = 1
        elif None is sql_results[0]['last_run_backlog'] or '' == sql_results[0]['last_run_backlog']:
            last_run_time = 1
        else:
            last_run_time = int(sql_results[0]['last_run_backlog'])
            if last_run_time > sbdatetime.now().totimestamp(default=0):
                last_run_time = 1

        return last_run_time

    def _set_last_runtime(self, when):
        logger.log('Setting the last backlog runtime in the DB to %s' % when, logger.DEBUG)

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM info')

        if len(sql_results) == 0:
            my_db.action('INSERT INTO info (last_backlog, last_indexer, last_run_backlog) VALUES (?,?,?)',
                        [1, 0, sbdatetime.totimestamp(when, default=0)])
        else:
            my_db.action('UPDATE info SET last_run_backlog=%s' % sbdatetime.totimestamp(when, default=0))

        self.nextBacklog = datetime.datetime.fromtimestamp(1)

    def _get_last_backlog(self):

        logger.log('Retrieving the last check time from the DB', logger.DEBUG)

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM info')

        if 0 == len(sql_results):
            last_backlog = 1
        elif None is sql_results[0]['last_backlog'] or '' == sql_results[0]['last_backlog']:
            last_backlog = 1
        else:
            last_backlog = int(sql_results[0]['last_backlog'])
            if last_backlog > datetime.date.today().toordinal():
                last_backlog = 1

        self._lastBacklog = last_backlog
        return self._lastBacklog

    @staticmethod
    def _set_last_backlog(when):

        logger.log('Setting the last backlog in the DB to %s' % when, logger.DEBUG)

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM info')

        if len(sql_results) == 0:
            my_db.action('INSERT INTO info (last_backlog, last_indexer, last_run_backlog) VALUES (?,?,?)',
                         [str(when), 0, 1])
        else:
            my_db.action('UPDATE info SET last_backlog=%s' % when)

    def run(self):
        try:
            force_type = self.forcetype
            force = self.force
            self.forcetype = NORMAL_BACKLOG
            self.force = False
            self.search_backlog(force_type=force_type, force=force)
        except:
            self.amActive = False
            raise
