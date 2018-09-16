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
import threading
import copy

from sickbeard import logger


class QueuePriorities:
    LOW = 10
    NORMAL = 20
    HIGH = 30
    VERYHIGH = 40


class GenericQueue(object):
    def __init__(self):

        self.currentItem = None

        self.queue = []

        self.queue_name = 'QUEUE'

        self.min_priority = 0

        self.lock = threading.Lock()

    def pause(self):
        logger.log(u'Pausing queue')
        if self.lock:
            self.min_priority = 999999999999

    def unpause(self):
        logger.log(u'Unpausing queue')
        with self.lock:
            self.min_priority = 0

    def add_item(self, item):
        with self.lock:
            item.added = datetime.datetime.now()
            self.queue.append(item)

            return item

    def run(self, force=False):

        # only start a new task if one isn't already going
        with self.lock:
            if self.currentItem is None or not self.currentItem.isAlive():

                # if the thread is dead then the current item should be finished
                if self.currentItem:
                    self.currentItem.finish()
                    self.currentItem = None

                # if there's something in the queue then run it in a thread and take it out of the queue
                if len(self.queue) > 0:

                    # sort by priority
                    def sorter(x, y):
                        """
                        Sorts by priority descending then time ascending
                        """
                        if x.priority == y.priority:
                            if y.added == x.added:
                                return 0
                            elif y.added < x.added:
                                return 1
                            elif y.added > x.added:
                                return -1
                        else:
                            return y.priority - x.priority

                    self.queue.sort(cmp=sorter)
                    if self.queue[0].priority < self.min_priority:
                        return

                    # launch the queue item in a thread
                    self.currentItem = self.queue.pop(0)
                    if not self.queue_name == 'SEARCHQUEUE':
                        self.currentItem.name = self.queue_name + '-' + self.currentItem.name
                    self.currentItem.start()


class QueueItem(threading.Thread):
    def __init__(self, name, action_id=0):
        super(QueueItem, self).__init__()

        self.name = name.replace(' ', '-').upper()
        self.inProgress = False
        self.priority = QueuePriorities.NORMAL
        self.action_id = action_id
        self.stop = threading.Event()
        self.added = None

    def copy(self, deepcopy_obj=None):
        """
        Returns a shallow copy of QueueItem with optional deepcopy of in deepcopy_obj listed objects
        :param deepcopy_obj: List of properties to be deep copied
        :type deepcopy_obj: list
        :return: return QueueItem
        :rtype: QueueItem
        """
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        if deepcopy_obj:
            for o in deepcopy_obj:
                if self.__dict__.get(o):
                    new_seg = copy.deepcopy(self.__dict__.get(o))
                    result.__dict__[o] = new_seg
        return result

    def run(self):
        """Implementing classes should call this"""

        self.inProgress = True

    def finish(self):
        """Implementing Classes should call this"""

        self.inProgress = False

        threading.currentThread().name = self.name
