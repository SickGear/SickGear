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

import copy
import datetime
import threading

from . import logger

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Union
    from .search_queue import BaseSearchQueueItem
    from .show_queue import ShowQueueItem


class QueuePriorities(object):
    LOW = 10
    NORMAL = 20
    HIGH = 30
    VERYHIGH = 40


class GenericQueue(object):
    def __init__(self):

        self.currentItem = None  # type: QueueItem or None

        self.queue = []  # type: List[Union[QueueItem, BaseSearchQueueItem, ShowQueueItem]]

        self.queue_name = 'QUEUE'  # type: AnyStr

        self.min_priority = 0  # type: int

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
        """

        :param item: Queue Item
        :type item: QueueItem
        :return: Queue Item
        :rtype: QueueItem
        """
        with self.lock:
            item.added = datetime.datetime.now()
            self.queue.append(item)

            return item

    def run(self):

        # only start a new task if one isn't already going
        with self.lock:
            if None is self.currentItem or not self.currentItem.is_alive():

                # if the thread is dead then the current item should be finished
                if self.currentItem:
                    self.currentItem.finish()
                    self.currentItem = None

                # if there's something in the queue then run it in a thread and take it out of the queue
                if 0 < len(self.queue):

                    self.queue.sort(key=lambda y: (-y.priority, y.added))
                    if self.queue[0].priority < self.min_priority:
                        return

                    # launch the queue item in a thread
                    self.currentItem = self.queue.pop(0)
                    if 'SEARCHQUEUE' != self.queue_name:
                        self.currentItem.name = self.queue_name + '-' + self.currentItem.name
                    self.currentItem.start()


class QueueItem(threading.Thread):
    def __init__(self, name, action_id=0):
        # type: (AnyStr, int) -> None
        """

        :param name: name
        :param action_id:
        """
        super(QueueItem, self).__init__()

        self.name = name.replace(' ', '-').upper()  # type: AnyStr
        self.inProgress = False  # type: bool
        self.priority = QueuePriorities.NORMAL  # type: int
        self.action_id = action_id  # type: int
        self.stop = threading.Event()
        self.added = None

    def copy(self, deepcopy_obj=None):
        """

        :param deepcopy_obj: List of properties to be deep copied
        :type deepcopy_obj: List
        :return: a shallow copy of QueueItem with optional deepcopy of in deepcopy_obj listed objects
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
