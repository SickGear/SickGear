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

import sickgear
from . import db, logger, scheduler, search_queue, ui
from .helpers import find_show_by_id
from .providers.generic import GenericProvider
from .search import wanted_episodes
from .sgdatetime import SGDatetime
from .tv import TVidProdid, TVEpisode, TVShow

from six import iteritems, itervalues, moves

# noinspection PyUnreachableCode
if False:
    from typing import Dict, List, Optional

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
        if 1 >= self.action.last_backlog:
            return datetime.date.today()
        elif (self.action.last_backlog + self.action.cycle_time) < datetime.date.today().toordinal():
            return datetime.date.today()
        return datetime.date.fromordinal(self.action.last_backlog + self.action.cycle_time)

    def next_backlog_timeleft(self):
        now = datetime.datetime.now()
        torrent_enabled = 0 < len([x for x in sickgear.providers.sorted_sources() if x.is_active() and
                                   getattr(x, 'enable_backlog', None) and GenericProvider.TORRENT == x.providerType])
        if now > self.action.nextBacklog or self.action.nextCyleTime != self.cycle_time:
            nextruntime = now + self.time_left()
            if not torrent_enabled:
                nextpossibleruntime = (datetime.datetime.fromtimestamp(self.action.last_runtime) +
                                       datetime.timedelta(hours=23))
                for _ in moves.xrange(5):
                    if nextruntime > nextpossibleruntime:
                        self.action.nextBacklog = nextruntime
                        self.action.nextCyleTime = self.cycle_time
                        break
                    nextruntime += self.cycle_time
            else:
                self.action.nextCyleTime = self.cycle_time
                self.action.nextBacklog = nextruntime
        return self.action.nextBacklog - now if self.action.nextBacklog > now else datetime.timedelta(seconds=0)


class BacklogSearcher(object):
    def __init__(self):

        self.last_backlog = self._get_last_backlog()
        self.cycle_time = sickgear.BACKLOG_PERIOD
        self.lock = threading.Lock()
        self.amActive = False  # type: bool
        self.amPaused = False  # type: bool
        self.amWaiting = False  # type: bool
        self.forcetype = NORMAL_BACKLOG  # type: int
        self.force = False  # type: bool
        self.nextBacklog = datetime.datetime.fromtimestamp(1)  # type: datetime.datetime
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

    def am_running(self):
        # type: (...) -> bool
        logger.debug(f'amWaiting: {self.amWaiting}, amActive: {self.amActive}')
        return (not self.amWaiting) and self.amActive

    def add_backlog_item(self,
                         items,  # type: List[Dict[int, List[TVEpisode]]]
                         standard_backlog,  # type: bool
                         limited_backlog,  # type: bool
                         forced,  # type: bool
                         torrent_only,  # type: bool
                         prevent_same=False  # type: bool
                         ):
        """
        add given list of show items to search backlog queue

        :param items: list of episodes to add to search
        :param standard_backlog: standard (scheduled) backlog
        :param limited_backlog: limited search
        :param forced: forced search
        :param torrent_only: only torrents
        :param prevent_same: prevent same search
        """
        for segments in items:
            if len(segments):
                for season, segment in iteritems(segments):  # type: int, List[TVEpisode]
                    if prevent_same and \
                            sickgear.search_queue_scheduler.action.is_in_queue(segment[0].show_obj, segment):
                        continue

                    self.currentSearchInfo = {'title': segment[0].show_obj.name + ' Season ' + str(season)}

                    backlog_queue_item = search_queue.BacklogQueueItem(
                        segment[0].show_obj, segment,
                        standard_backlog=standard_backlog, limited_backlog=limited_backlog,
                        forced=forced, torrent_only=torrent_only)
                    sickgear.search_queue_scheduler.action.add_item(backlog_queue_item)

    @staticmethod
    def change_backlog_parts(old_count, new_count):
        try:
            my_db = db.DBConnection('cache.db')
            sql_result = my_db.select('SELECT * FROM backlogparts')
            if sql_result:
                current_parts = len(set([s['part'] for s in sql_result]))
                parts_count = len(sql_result)
                new_part_count = int(ceil(new_count / old_count * current_parts))
                parts = int(ceil(parts_count / new_part_count))
                # noinspection SqlConstantCondition
                cl = ([], [['DELETE FROM backlogparts WHERE 1=1']])[1 < parts_count]
                p = new_count - new_part_count
                for i, s in enumerate(sql_result):
                    if 0 == i % parts:
                        p += 1
                    cl.append(['INSERT INTO backlogparts (part, indexerid, indexer) VALUES (?,?,?)',
                               [p, s['indexerid'], s['indexer']]])

                if 0 < len(cl):
                    my_db.mass_action(cl)
        except (BaseException, Exception):
            pass

    @staticmethod
    def providers_active(torrent_only=False, scheduled=False):
        # type: (bool, bool) -> bool
        """
        Checks if there are any providers active for backlog search

        :param torrent_only: only check torrent providers
        :param scheduled: scheduled backlog search (can be from webif or scheduler)
        :return: any provider is active for given backlog
        """
        return 0 < len([x for x in sickgear.providers.sorted_sources() if x.is_active() and
                        getattr(x, 'enable_backlog', None) and
                        (not torrent_only or GenericProvider.TORRENT == x.providerType) and
                        (not scheduled or getattr(x, 'enable_scheduled_backlog', None))])

    def search_backlog(self,
                       which_shows=None,  # type: Optional[List[TVShow]]
                       force_type=NORMAL_BACKLOG,  # type: int
                       force=False,  # type: bool
                       prevent_same=False  # type: bool
                       ):
        """
        start backlog for given list of shows or start next scheduled backlog

        :param which_shows: optional list of shows to backlog search
        :param force_type: type of backlog
        :param force: force backlog
        :param prevent_same: don't start same search again
        :return: nothing
        :rtype: None
        """
        if self.amActive and not which_shows:
            logger.debug('Backlog is still running, not starting it again')
            return

        if which_shows:
            show_list = which_shows
            standard_backlog = False
        else:
            show_list = sickgear.showList
            standard_backlog = True

        now = datetime.datetime.now()
        any_torrent_enabled = continued_backlog = False
        if not force and standard_backlog and (datetime.datetime.now() - datetime.datetime.fromtimestamp(
                self._get_last_runtime())) < datetime.timedelta(hours=23):
            any_torrent_enabled = any(map(
                lambda x: x.is_active() and getattr(x, 'enable_backlog', None)
                and GenericProvider.TORRENT == x.providerType,
                sickgear.providers.sorted_sources()))
            if not any_torrent_enabled:
                logger.debug('Last scheduled backlog run was within the last day, skipping this run.')
                return

        if not self.providers_active(any_torrent_enabled, standard_backlog):
            logger.warning('No NZB/Torrent provider has active searching enabled in config/Media Providers,'
                           ' cannot start backlog.')
            return

        self._get_last_backlog()
        self.amActive = True
        self.amPaused = False

        cur_date = datetime.date.today().toordinal()
        from_date = datetime.date.fromordinal(1)
        limited_from_date = datetime.date.today() - datetime.timedelta(days=sickgear.BACKLOG_LIMITED_PERIOD)

        limited_backlog = False
        if standard_backlog and (any_torrent_enabled or sickgear.BACKLOG_NOFULL):
            logger.log(f'Running limited backlog for episodes missed during the last'
                       f' {sickgear.BACKLOG_LIMITED_PERIOD} day(s)')
            from_date = limited_from_date
            limited_backlog = True

        runparts = []
        if standard_backlog and not any_torrent_enabled and sickgear.BACKLOG_NOFULL:
            logger.log('Skipping automated full backlog search because it is disabled in search settings')

        my_db = db.DBConnection('cache.db')
        if standard_backlog and not any_torrent_enabled and not sickgear.BACKLOG_NOFULL:
            sql_result = my_db.select('SELECT * FROM backlogparts WHERE part in (SELECT MIN(part) FROM backlogparts)')
            if sql_result:
                sl = []
                part_nr = int(sql_result[0]['part'])
                for s in sql_result:
                    show_obj = find_show_by_id({int(s['indexer']): int(s['indexerid'])})
                    if show_obj:
                        sl.append(show_obj)
                        runparts.append(show_obj.tvid_prodid)
                show_list = sl
                continued_backlog = True
                my_db.action('DELETE FROM backlogparts WHERE part = ?', [part_nr])

        forced = standard_backlog and force_type != NORMAL_BACKLOG

        wanted_list = []
        for cur_show_obj in show_list:
            if not cur_show_obj.paused:
                w = wanted_episodes(cur_show_obj, from_date, make_dict=True,
                                    unaired=(sickgear.SEARCH_UNAIRED and not sickgear.UNAIRED_RECENT_SEARCH_ONLY))
                if w:
                    wanted_list.append(w)

        parts = []
        if standard_backlog and not any_torrent_enabled and not continued_backlog and not sickgear.BACKLOG_NOFULL:
            fullbacklogparts = sum([len(w) for w in wanted_list if w]) // sickgear.BACKLOG_PERIOD
            h_part = []
            counter = 0
            for w in wanted_list:  # type: Dict
                f = False
                for season, segment in iteritems(w):  # type: int, List[TVEpisode]
                    counter += 1
                    if not f:
                        h_part.append(segment[0].show_obj.tvid_prodid)
                        f = True
                if counter > fullbacklogparts:
                    counter = 0
                    parts.append(h_part)
                    h_part = []

            if h_part:
                parts.append(h_part)

        if not runparts and parts:
            runparts = parts[0]
            wanted_list = list(filter(
                lambda wi: wi and next(itervalues(wi))[0].show_obj.tvid_prodid in runparts, wanted_list))

        limited_wanted_list = []
        if standard_backlog and not any_torrent_enabled and runparts:
            for cur_show_obj in sickgear.showList:
                if not cur_show_obj.paused and cur_show_obj.tvid_prodid not in runparts:
                    w = wanted_episodes(cur_show_obj, limited_from_date, make_dict=True,
                                        unaired=(sickgear.SEARCH_UNAIRED and not sickgear.UNAIRED_RECENT_SEARCH_ONLY))
                    if w:
                        limited_wanted_list.append(w)

        self.add_backlog_item(wanted_list, standard_backlog, limited_backlog, forced, any_torrent_enabled,
                              prevent_same=prevent_same)
        if standard_backlog and not any_torrent_enabled and limited_wanted_list:
            self.add_backlog_item(limited_wanted_list, standard_backlog, True, forced, any_torrent_enabled)

        if standard_backlog and not sickgear.BACKLOG_NOFULL and not any_torrent_enabled and not continued_backlog:
            # noinspection SqlConstantCondition
            cl = ([], [['DELETE FROM backlogparts WHERE 1=1']])[any(parts)]
            for i, l in enumerate(parts):
                if 0 == i:
                    continue
                cl += list(map(lambda m: ['INSERT INTO backlogparts (part, indexer, indexerid) VALUES (?,?,?)',
                                          [i + 1] + TVidProdid(m).list], l))

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
        logger.debug('Retrieving the last runtime of Backlog from the DB')

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM info')

        if 0 == len(sql_result):
            last_run_time = 1
        elif None is sql_result[0]['last_run_backlog'] or '' == sql_result[0]['last_run_backlog']:
            last_run_time = 1
        else:
            last_run_time = int(sql_result[0]['last_run_backlog'])
            if last_run_time > SGDatetime.timestamp_near():
                last_run_time = 1

        return last_run_time

    def _set_last_runtime(self, when):
        logger.debug('Setting the last backlog runtime in the DB to %s' % when)

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM info')

        if isinstance(when, datetime.datetime):
            when = SGDatetime.timestamp_near(when)
        else:
            when = SGDatetime.timestamp_far(when, default=0)
        if 0 == len(sql_result):
            my_db.action('INSERT INTO info (last_backlog, last_indexer, last_run_backlog) VALUES (?,?,?)', [1, 0, when])
        else:
            # noinspection SqlConstantCondition
            my_db.action('UPDATE info SET last_run_backlog=%s WHERE 1=1' % when)

        self.nextBacklog = datetime.datetime.fromtimestamp(1)

    def _get_last_backlog(self):

        logger.debug('Retrieving the last check time from the DB')

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM info')

        if 0 == len(sql_result):
            last_backlog = 1
        elif None is sql_result[0]['last_backlog'] or '' == sql_result[0]['last_backlog']:
            last_backlog = 1
        else:
            last_backlog = int(sql_result[0]['last_backlog'])
            if last_backlog > datetime.date.today().toordinal():
                last_backlog = 1

        self.last_backlog = last_backlog
        return self.last_backlog

    @staticmethod
    def _set_last_backlog(when):

        logger.debug('Setting the last backlog in the DB to %s' % when)

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM info')

        if 0 == len(sql_result):
            my_db.action('INSERT INTO info (last_backlog, last_indexer, last_run_backlog) VALUES (?,?,?)',
                         [str(when), 0, 1])
        else:
            # noinspection SqlConstantCondition
            my_db.action('UPDATE info SET last_backlog=%s WHERE 1=1' % when)

    def run(self):
        try:
            force_type = self.forcetype
            force = self.force
            self.forcetype = NORMAL_BACKLOG
            self.force = False
            self.search_backlog(force_type=force_type, force=force)
        except (BaseException, Exception):
            self.amActive = False
            raise
