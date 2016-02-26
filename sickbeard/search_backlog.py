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

import datetime

import sickbeard

from sickbeard import db, scheduler
from sickbeard import search_queue
from sickbeard import logger
from sickbeard import ui
from sickbeard.search import wanted_episodes
from sickbeard.scheduler import Job

NORMAL_BACKLOG = 0
LIMITED_BACKLOG = 10
FULL_BACKLOG = 20

class BacklogSearchScheduler(scheduler.Scheduler):
    def forceSearch(self, force_type=NORMAL_BACKLOG):
        self.force = True
        self.action.forcetype = force_type

    def nextRun(self):
        if self.action._lastBacklog <= 1:
            return datetime.date.today()
        elif (self.action._lastBacklog + self.action.cycleTime) < datetime.date.today().toordinal():
            return datetime.date.today()
        else:
            return datetime.date.fromordinal(self.action._lastBacklog + self.action.cycleTime)


class BacklogSearcher(Job):
    def __init__(self):
        super(BacklogSearcher, self).__init__(self.queue_task, kwargs={}, thread_lock=True)

        self._lastBacklog = self._get_lastBacklog()
        self.cycleTime = sickbeard.BACKLOG_FREQUENCY
        self.amPaused = False
        self.amWaiting = False
        self.forcetype = NORMAL_BACKLOG

        self._resetPI()

    def _resetPI(self):
        self.percentDone = 0
        self.currentSearchInfo = {'title': 'Initializing'}

    def getProgressIndicator(self):
        if self.amActive:
            return ui.ProgressIndicator(self.percentDone, self.currentSearchInfo)
        else:
            return None

    def am_running(self):
        logger.log(u'amWaiting: ' + str(self.amWaiting) + ', amActive: ' + str(self.amActive), logger.DEBUG)
        return (not self.amWaiting) and self.amActive

    def search_backlog(self, which_shows=None, force_type=NORMAL_BACKLOG):

        if which_shows:
            show_list = which_shows
            standard_backlog = False
        else:
            show_list = sickbeard.showList
            standard_backlog = True

        self._get_lastBacklog()

        curDate = datetime.date.today().toordinal()
        fromDate = datetime.date.fromordinal(1)

        limited_backlog = False
        if (not which_shows and force_type == LIMITED_BACKLOG) or (not which_shows and force_type != FULL_BACKLOG and not curDate - self._lastBacklog >= self.cycleTime):
            logger.log(u'Running limited backlog for episodes missed during the last %s day(s)' % str(sickbeard.BACKLOG_DAYS))
            fromDate = datetime.date.today() - datetime.timedelta(days=sickbeard.BACKLOG_DAYS)
            limited_backlog = True

        forced = False
        if not which_shows and force_type != NORMAL_BACKLOG:
            forced = True

        self.amPaused = False

        # go through non air-by-date shows and see if they need any episodes
        for curShow in show_list:

            if curShow.paused:
                continue

            segments = wanted_episodes(curShow, fromDate, make_dict=True)

            for season, segment in segments.items():
                self.currentSearchInfo = {'title': curShow.name + ' Season ' + str(season)}

                backlog_queue_item = search_queue.BacklogQueueItem(curShow, segment, standard_backlog=standard_backlog, limited_backlog=limited_backlog, forced=forced)
                sickbeard.searchQueueScheduler.action.add_item(backlog_queue_item)  # @UndefinedVariable
            else:
                logger.log(u'Nothing needs to be downloaded for %s, skipping' % str(curShow.name), logger.DEBUG)

        # don't consider this an actual backlog search if we only did recent eps
        # or if we only did certain shows
        if fromDate == datetime.date.fromordinal(1) and not which_shows:
            self._set_lastBacklog(curDate)
            self._get_lastBacklog()

        self._resetPI()

    def _get_lastBacklog(self):

        logger.log(u'Retrieving the last check time from the DB', logger.DEBUG)

        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM info')

        if len(sqlResults) == 0:
            lastBacklog = 1
        elif sqlResults[0]['last_backlog'] == None or sqlResults[0]['last_backlog'] == '':
            lastBacklog = 1
        else:
            lastBacklog = int(sqlResults[0]['last_backlog'])
            if lastBacklog > datetime.date.today().toordinal():
                lastBacklog = 1

        self._lastBacklog = lastBacklog
        return self._lastBacklog

    def _set_lastBacklog(self, when):

        logger.log(u'Setting the last backlog in the DB to ' + str(when), logger.DEBUG)

        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM info')

        if len(sqlResults) == 0:
            myDB.action('INSERT INTO info (last_backlog, last_indexer) VALUES (?,?)', [str(when), 0])
        else:
            myDB.action('UPDATE info SET last_backlog=' + str(when))

    def queue_task(self):

        try:
            force_type = self.forcetype
            self.forcetype = NORMAL_BACKLOG
            self.search_backlog(force_type=force_type)
        except:
            raise
