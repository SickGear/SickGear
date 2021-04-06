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

# noinspection PyPep8Naming
from exceptions_helper import ex

from . import db, generic_queue, logger, helpers, ui

# noinspection PyUnreachableCode
if False:
    from six import integer_types
    from typing import AnyStr, Dict, List, Optional
    from .tv import TVShow
    from lib.tvinfo_base import CastList


class PeopleQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self, cache_db_tables=['people_queue'])
        self.queue_name = 'PEOPLEQUEUE'  # type: AnyStr

    def load_queue(self):
        try:
            my_db = db.DBConnection('cache.db')
            queue_sql = my_db.select('SELECT * FROM people_queue')
            for q in queue_sql:
                if PeopleQueueActions.SHOWCAST == q['action_id']:
                    try:
                        show_obj = helpers.find_show_by_id({q['indexer']: q['indexer_id']})
                    except (BaseException, Exception):
                        continue
                    if not show_obj:
                        continue
                    self.add_cast_update(show_obj=show_obj, show_info_cast=None, uid=q['uid'], force=bool(q['forced']),
                                         scheduled_update=bool(q['scheduled']), add_to_db=False)
        except (BaseException, Exception) as e:
            logger.error('Exception loading queue %s: %s' % (self.__class__.__name__, ex(e)))
        try:
            my_db = db.DBConnection()
            if not my_db.has_flag('cast_loaded'):
                import sickbeard
                [self.add_cast_update(s, show_info_cast=None, scheduled_update=True)
                 for s in sickbeard.showList if not s.cast_list]
                my_db.set_flag('cast_loaded')
        except (BaseException, Exception):
            pass

    def _clear_sql(self):
        return [
            ['DELETE FROM people_queue']
        ]

    def _get_item_sql(self, item):
        # type: (PeopleQueueItem) -> List[List]
        return [
            ['INSERT OR IGNORE INTO people_queue (indexer, indexer_id, action_id, forced, scheduled, uid)'
             ' VALUES (?,?,?,?,?,?)',
             [item.show_obj._tvid, item.show_obj._prodid, item.action_id, int(item.force), int(item.scheduled_update),
              item.uid]]
        ]

    def _delete_item_from_db_sql(self, item):
        # type: (PeopleQueueItem) -> List[List]
        return [
            ['DELETE FROM people_queue WHERE uid = ?', [item.uid]]
        ]

    def queue_data(self):
        # type: (...) -> Dict[AnyStr, List[AnyStr, Dict]]
        data = {'main_cast': []}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:  # type: PeopleQueueItem
                if not cur_item:
                    continue
                result_item = {'name': cur_item.show_obj.name, 'tvid_prodid': cur_item.show_obj.tvid_prodid,
                               'uid': cur_item.uid, 'forced': cur_item.force}
                if isinstance(cur_item, CastQueueItem):
                    data['main_cast'].append(result_item)
            return data

    def show_in_queue(self, show_obj, check_inprogress=False):
        # type: (TVShow, Optional[bool]) -> bool
        with self.lock:
            return any(1 for q in ((self.currentItem and [self.currentItem]) or []) + self.queue
                       if show_obj == q.show_obj and (True, q.inProgress)[check_inprogress])

    def abort_cast_update(self, show_obj):
        # type: (TVShow) -> None
        if show_obj:
            with self.lock:
                to_remove = []
                for c in ((self.currentItem and [self.currentItem]) or []) + self.queue:
                    if show_obj == c.show_obj:
                        try:
                            to_remove.append(c.uid)
                        except (BaseException, Exception):
                            pass
                        try:
                            c.stop.set()
                        except (BaseException, Exception):
                            pass

                if to_remove:
                    try:
                        self.remove_from_queue(to_remove)
                    except (BaseException, Exception):
                        pass

    def add_cast_update(self, show_obj, show_info_cast, uid=None, add_to_db=True, force=False, scheduled_update=False,
                        switch=False):
        # type: (TVShow, Optional[CastList], AnyStr, bool, bool, bool, bool) -> CastQueueItem
        """

        :param show_obj: TV Show object
        :param show_info_cast: TV Info object
        :param uid: unique id
        :param add_to_db: add to queue db table
        :param force:
        :param scheduled_update: suppresses ui notifications
        :param switch: part of id switch
        """
        with self.lock:
            if not self.show_in_queue(show_obj):
                cast_item = CastQueueItem(show_obj=show_obj, show_info_cast=show_info_cast, uid=uid, force=force,
                                          scheduled_update=scheduled_update, switch=switch)
                self.add_item(cast_item, add_to_db=add_to_db)
                return cast_item


class PeopleQueueActions(object):
    SHOWCAST = 1

    names = {
        SHOWCAST: 'Show Cast',
            }


class PeopleQueueItem(generic_queue.QueueItem):
    def __init__(self, action_id, show_obj, uid=None, force=False, **kwargs):
        # type: (integer_types, TVShow, AnyStr, bool, Dict) -> PeopleQueueItem
        """

        :param action_id:
        :param show_obj: show object
        """
        generic_queue.QueueItem.__init__(self, PeopleQueueActions.names[action_id], action_id, uid=uid)
        self.show_obj = show_obj  # type: TVShow
        self.force = force  # type: bool


class CastQueueItem(PeopleQueueItem):
    def __init__(self, show_obj, show_info_cast=None, uid=None, force=False, scheduled_update=False, switch=False,
                 **kwargs):
        # type: (TVShow, CastList, AnyStr, bool, bool, bool, Dict) -> CastQueueItem
        """

        :param show_obj: show obj
        :param show_info_cast: show info cast list
        :param scheduled_update: suppresses ui notifications
        :param switch: part of id switch
        """
        PeopleQueueItem.__init__(self, PeopleQueueActions.SHOWCAST, show_obj, uid=uid, force=force, **kwargs)
        self.show_info_cast = show_info_cast  # type: Optional[CastList]
        self.scheduled_update = scheduled_update  # type: bool
        self.switch = switch  # type: bool

    def run(self):

        PeopleQueueItem.run(self)

        if self.show_obj:
            logger.log('Starting cast update for show %s' % self.show_obj.name)
            old_cast = self.show_obj.cast_list_id()
            if not self.scheduled_update and not self.switch:
                ui.notifications.message('Starting cast update for show %s' % self.show_obj.name)
            try:
                self.show_obj.load_cast_from_tvinfo(self.show_info_cast, force=self.force, stop_event=self.stop)
                update_success = True
            except (BaseException, Exception) as e:
                update_success = False
                logger.error('Exception in cast update queue: %s' % ex(e))
                logger.debug('Traceback: %s' % traceback.format_exc())

            if update_success and (old_cast != self.show_obj.cast_list_id()):
                logger.debug('Update show nfo with new cast data')
                self.show_obj.write_show_nfo(force=True)

            logger.log('Finished cast update for show %s' % self.show_obj.name)
            if not self.scheduled_update and not self.switch:
                ui.notifications.message('Finished cast update for show %s' % self.show_obj.name)

        self.finish()

    def __str__(self):
        return '<Cast Queue Item (%s)%s>' % (self.show_obj.name, ('', ' - forced')[self.force])

    def __repr__(self):
        return self.__str__()
