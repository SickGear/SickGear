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

from __future__ import division

import datetime
import time
import threading
import traceback

from . import logger
from exceptions_helper import ex


class Scheduler(threading.Thread):
    def __init__(self, action, cycleTime=datetime.timedelta(minutes=10), run_delay=datetime.timedelta(minutes=0),
                 start_time=None, threadName="ScheduledThread", silent=True, prevent_cycle_run=None, paused=False):
        super(Scheduler, self).__init__()

        self.lastRun = datetime.datetime.now() + run_delay - cycleTime
        self.action = action
        self.cycleTime = cycleTime
        self.start_time = start_time
        self.prevent_cycle_run = prevent_cycle_run

        self.name = threadName
        self.silent = silent
        self._stopper = threading.Event()
        self._unpause = threading.Event()
        if not paused:
            self._unpause.set()
        self.lock = threading.Lock()
        self.force = False

    def pause(self):
        self._unpause.clear()

    def unpause(self):
        self._unpause.set()

    def stopit(self):
        """ Stop the thread's activity.
        """
        self._stopper.set()
        self.unpause()

    def set_paused_state(self):
        if hasattr(self.action, 'is_enabled'):
            self.silent = not self.action.is_enabled()
            if self.silent:
                self.pause()
            else:
                self.unpause()

    def timeLeft(self):
        return self.cycleTime - (datetime.datetime.now() - self.lastRun)

    def forceRun(self):
        if not self.action.amActive:
            self.force = True
            return True
        return False

    def run(self):
        self.set_paused_state()

        # if self._unpause Event() is NOT set the loop pauses
        while self._unpause.wait() and not self._stopper.is_set():

            if getattr(self.action, 'is_enabled', True):
                try:
                    current_time = datetime.datetime.now()
                    should_run = False

                    # check if interval has passed
                    if current_time - self.lastRun >= self.cycleTime:
                        # check if wanting to start around certain time taking interval into account
                        if self.start_time:
                            hour_diff = current_time.time().hour - self.start_time.hour
                            if not hour_diff < 0 and hour_diff < self.cycleTime.seconds // 3600:
                                should_run = True
                            else:
                                # set lastRun to only check start_time after another cycleTime
                                self.lastRun = current_time
                        else:
                            should_run = True

                    if self.force:
                        should_run = True

                    if should_run and ((self.prevent_cycle_run is not None and self.prevent_cycle_run()) or
                                       getattr(self.action, 'prevent_run', False)):
                        logger.log(u'%s skipping this cycleTime' % self.name, logger.WARNING)
                        # set lastRun to only check start_time after another cycleTime
                        self.lastRun = current_time
                        should_run = False

                    if should_run:
                        self.lastRun = current_time

                        try:
                            if not self.silent:
                                logger.log(u"Starting new thread: " + self.name, logger.DEBUG)

                            self.action.run()
                        except (BaseException, Exception) as e:
                            logger.log(u"Exception generated in thread " + self.name + ": " + ex(e), logger.ERROR)
                            logger.log(repr(traceback.format_exc()), logger.ERROR)

                finally:
                    if self.force:
                        self.force = False
            else:
                # disabled schedulers will only be rechecked every 30 seconds until enabled
                time.sleep(30)

            time.sleep(1)

        # exiting thread
        self._stopper.clear()
        self._unpause.clear()
