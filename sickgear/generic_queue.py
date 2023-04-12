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

from . import db, logger
from exceptions_helper import ex
from six import integer_types

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Callable, Dict, List, Optional, Tuple, Union
    from .search_queue import BaseSearchQueueItem
    from .show_queue import ShowQueueItem
    from .people_queue import CastQueueItem


class QueuePriorities(object):
    LOW = 10
    NORMAL = 20
    HIGH = 30
    VERYHIGH = 40


class GenericQueue(object):
    def __init__(self, cache_db_tables=None, main_db_tables=None):
        # type: (List[AnyStr], List[AnyStr]) -> None

        self.currentItem = None  # type: QueueItem or None

        self.queue = []  # type: List[Union[QueueItem, BaseSearchQueueItem, ShowQueueItem]]

        self.queue_name = 'QUEUE'  # type: AnyStr

        self.min_priority = 0  # type: int

        self.events = {}  # type: Dict[int, List[Callable]]

        self.lock = threading.RLock()

        self.cache_db_tables = cache_db_tables or []  # type: List[AnyStr]
        self.main_db_tables = main_db_tables or []  # type: List[AnyStr]

        self._id_counter = self._load_init_id()  # type: integer_types

    def _load_init_id(self):
        # type: (...) -> integer_types
        """
        fetch highest uid for queue type to initialize the class

        """
        my_db = db.DBConnection('cache.db')
        cr = my_db.mass_action([['SELECT max(uid) as max_id FROM %s' % t] for t in self.cache_db_tables])
        my_db = db.DBConnection()
        mr = my_db.mass_action([['SELECT max(uid) as max_id FROM %s' % t] for t in self.main_db_tables])
        return max([c[0]['max_id'] or 0 for c in cr] + [s[0]['max_id'] or 0 for s in mr] + [0])

    def _get_new_id(self):
        # type: (...) -> integer_types
        self._id_counter += 1
        return self._id_counter

    def load_queue(self):
        pass

    def save_queue(self):
        cl = self._clear_sql()
        try:
            with self.lock:
                for item in ((self.currentItem and [self.currentItem]) or []) + self.queue:
                    cl.extend(self._get_item_sql(item))

            if cl:
                my_db = db.DBConnection('cache.db')
                my_db.mass_action(cl)
        except (BaseException, Exception) as e:
            logger.error('Exception saving queue %s to db: %s' % (self.__class__.__name__, ex(e)))

    def _clear_sql(self):
        # type: (...) -> List[List]
        return []

    def save_item(self, item):
        try:
            if item:
                item_sql = self._get_item_sql(item)
                if item_sql:
                    my_db = db.DBConnection('cache.db')
                    my_db.mass_action(item_sql)
        except (BaseException, Exception) as e:
            logger.error('Exception saving item %s to db: %s' % (item, ex(e)))

    def delete_item(self, item, finished_run=False):
        # type: (Union[QueueItem, CastQueueItem], bool) -> None
        """

        :param item:
        :param finished_run: set to True when queue item has run
        """
        if item:
            try:
                item_sql = self._delete_item_from_db_sql(item)
                if item_sql:
                    my_db = db.DBConnection('cache.db')
                    my_db.mass_action(item_sql)
            except (BaseException, Exception) as e:
                logger.error('Exception deleting item %s from db: %s' % (item, ex(e)))

    def _get_item_sql(self, item):
        # type: (Union[QueueItem, CastQueueItem]) -> List[List]
        return []

    def _delete_item_from_db_sql(self, item):
        # type: (Union[QueueItem, CastQueueItem]) -> List[List]
        pass

    def remove_from_queue(self, to_remove=None, force=False):
        # type: (List[AnyStr], bool) -> None
        """
        remove given uid items from queue

        :param to_remove: list of uids to remove from queue
        :param force: force removal from db
        """
        self._remove_from_queue(to_remove=to_remove, excluded_types=[], force=force)

    def _remove_from_queue(self, to_remove=None, excluded_types=None, force=False):
        # type: (List[AnyStr], List, bool) -> None
        """
        remove given uid items from queue

        :param to_remove: list of uids to remove from queue
        :param force: force removal from db
        """
        if to_remove:
            excluded_types = excluded_types or []
            with self.lock:
                if not force:
                    to_remove = [r for r in to_remove for q in self.queue
                                 if r == q.uid and (q.action_id not in excluded_types)]
                del_sql = [
                    ['DELETE FROM %s WHERE uid IN (%s)' % (t, ','.join(['?'] * len(to_remove))), to_remove]
                    for t in self.cache_db_tables
                ]
                del_main_sql = [
                    ['DELETE FROM %s WHERE uid IN (%s)' % (t, ','.join(['?'] * len(to_remove))), to_remove]
                    for t in self.main_db_tables
                ]

                self.queue = [q for q in self.queue if q.uid not in to_remove]
                if del_sql:
                    my_db = db.DBConnection('cache.db')
                    my_db.mass_action(del_sql)
                if del_main_sql:
                    my_db = db.DBConnection()
                    my_db.mass_action(del_main_sql)

    def clear_queue(self, action_types=None):
        # type: (integer_types) -> None
        """
        clear queue excluding internal defined types

        :param action_types: only clear supplied action types
        """
        if not isinstance(action_types, list):
            action_types = [action_types]
        return self._clear_queue(action_types=action_types)

    def _clear_queue(self, action_types=None, excluded_types=None):
        # type: (List[integer_types], List) -> None
        excluded_types = excluded_types or []
        with self.lock:
            if action_types:
                self.queue = [q for q in self.queue if q.action_id in excluded_types or q.action_id not in action_types]
                del_sql = [
                    ['DELETE FROM %s WHERE action_id IN (%s)' % (t, ','.join(['?'] * len(action_types))), action_types]
                    for t in self.cache_db_tables
                ]
                del_main_sql = [
                    ['DELETE FROM %s WHERE action_id IN (%s)' % (t, ','.join(['?'] * len(action_types))), action_types]
                    for t in self.main_db_tables
                ]
            else:
                self.queue = [q for q in self.queue if q.action_id in excluded_types]
                del_sql = [
                    ['DELETE FROM %s' % t] for t in self.cache_db_tables
                ]
                del_main_sql = [
                    ['DELETE FROM %s' % t] for t in self.main_db_tables
                ]
            if del_sql:
                my_db = db.DBConnection('cache.db')
                my_db.mass_action(del_sql)
            if del_main_sql:
                my_db = db.DBConnection()
                my_db.mass_action(del_main_sql)

    def pause(self):
        logger.log('Pausing queue')
        if self.lock:
            self.min_priority = 999999999999

    def unpause(self):
        logger.log('Unpausing queue')
        with self.lock:
            self.min_priority = 0

    def add_item(self, item, add_to_db=True):
        """

        :param item: Queue Item
        :type item: QueueItem
        :param add_to_db: add to db
        :return: Queue Item
        :rtype: QueueItem
        """
        with self.lock:
            item.added = datetime.datetime.now()
            item.uid = item.uid or self._get_new_id()
            self.queue.append(item)
            if add_to_db:
                self.save_item(item)

            return item

    def check_events(self):
        pass

    def add_event(self, event_type, method):
        # type: (int, Callable) -> None
        if isinstance(event_type, integer_types) and callable(method):
            if event_type not in self.events:
                self.events[event_type] = []
            if method not in self.events[event_type]:
                self.events[event_type].append(method)

    def remove_event(self, event_type, method):
        # type: (int, Callable) -> None
        if isinstance(event_type, integer_types) and callable(method):
            if event_type in self.events and method in self.events[event_type]:
                try:
                    self.events[event_type].remove(method)
                    if 0 == len(self.events[event_type]):
                        del self.events[event_type]
                except (BaseException, Exception) as e:
                    logger.error('Error removing event method from queue: %s' % ex(e))

    def execute_events(self, event_type, *args, **kwargs):
        # type: (int, Tuple, Dict) -> None
        if event_type in self.events:
            for event in self.events.get(event_type):
                try:
                    event(*args, **kwargs)
                except (BaseException, Exception) as e:
                    logger.error('Error executing Event: %s' % ex(e))

    def run(self):

        # only start a new task if one isn't already going
        with self.lock:
            if None is self.currentItem or not self.currentItem.is_alive():

                # if the thread is dead then the current item should be finished
                if self.currentItem:
                    self.currentItem.finish()
                    try:
                        self.delete_item(self.currentItem, finished_run=True)
                    except (BaseException, Exception):
                        pass
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

                self.check_events()


class QueueItem(threading.Thread):
    def __init__(self, name, action_id=0, uid=None):
        # type: (AnyStr, int, integer_types) -> None
        """

        :param name: name
        :param action_id:
        :param uid:
        """
        super(QueueItem, self).__init__()

        self.name = name.replace(' ', '-').upper()  # type: AnyStr
        self.inProgress = False  # type: bool
        self.priority = QueuePriorities.NORMAL  # type: int
        self.action_id = action_id  # type: int
        self.stop = threading.Event()
        self.added = None  # type: Optional[datetime.datetime]
        self.uid = uid  # type: integer_types

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

        threading.current_thread().name = self.name
