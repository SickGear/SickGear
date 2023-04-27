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
import os
import traceback

from lib.dateutil.parser import parser
from lib.tvinfo_base.exceptions import *

import exceptions_helper
from exceptions_helper import ex

import sickgear
from . import logger, ui, db, generic_queue, name_cache
from .anime import AniGroupList
from .common import SKIPPED, WANTED, UNAIRED, Quality, statusStrings
from .helpers import should_delete_episode, find_show_by_id
from .indexermapper import clean_show_name, map_indexers_to_show
from .indexers.indexer_config import TVINFO_TVDB, TVINFO_TVRAGE
from .name_parser.parser import NameParser
from .tv import TVidProdid, TVShow, TVSWITCH_DUPLICATE_SHOW, TVSWITCH_EP_DELETED, TVSWITCH_ID_CONFLICT, \
    TVSWITCH_NO_NEW_ID, TVSWITCH_NORMAL, TVSWITCH_NOT_FOUND_ERROR, TVSWITCH_SAME_ID, TVSWITCH_SOURCE_NOT_FOUND_ERROR, \
    TVSWITCH_VERIFY_ERROR

from six import integer_types, iteritems, itervalues
from sg_helpers import try_int

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union
    from lib.tvinfo_base import TVInfoShow
    from .tv import TVEpisode

# Define special priority of tv source switch tasks, higher than anything else except newly added shows
SWITCH_PRIO = generic_queue.QueuePriorities.HIGH + 5

DAILY_SHOW_UPDATE_FINISHED_EVENT = 1


def bool_none(val):
    # type: (Optional[int]) -> Optional[bool]
    if None is val:
        return None
    return bool(val)


class ShowQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self, cache_db_tables=['show_queue'], main_db_tables=['tv_src_switch'])
        self.queue_name = 'SHOWQUEUE'
        self.daily_update_running = False
        if not db.DBConnection().has_flag('kodi_nfo_uid'):
            self.add_event(DAILY_SHOW_UPDATE_FINISHED_EVENT, sickgear.metadata.kodi.set_nfo_uid_updated)

    def check_events(self):
        if self.daily_update_running and \
                not (self.is_show_update_running() or sickgear.update_show_scheduler.is_running_job):
            self.execute_events(DAILY_SHOW_UPDATE_FINISHED_EVENT)
            self.daily_update_running = False

    def load_queue(self):
        try:
            my_db = db.DBConnection('cache.db')
            sql_result = my_db.select('SELECT * FROM show_queue')
            for cur_row in sql_result:
                show_obj = None
                if ShowQueueActions.ADD != cur_row['action_id']:
                    try:
                        show_obj = find_show_by_id({cur_row['tvid']: cur_row['prodid']})
                    except (BaseException, Exception):
                        continue
                    if not show_obj:
                        continue

                if cur_row['action_id'] in (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE,
                                            ShowQueueActions.WEBFORCEUPDATE):
                    self.update_show(add_to_db=False, force=bool(cur_row['force']),
                                     pausestatus_after=bool_none(cur_row['pausestatus_after']),
                                     scheduled_update=bool(cur_row['scheduled_update']),
                                     show_obj=show_obj, skip_refresh=bool(cur_row['skip_refresh']),
                                     uid=cur_row['uid'],
                                     web=ShowQueueActions.WEBFORCEUPDATE == cur_row['action_id'])

                elif ShowQueueActions.REFRESH == cur_row['action_id']:
                    self.refresh_show(add_to_db=False, force=bool(cur_row['force']),
                                      force_image_cache=bool(cur_row['force_image_cache']),
                                      priority=cur_row['priority'],
                                      scheduled_update=bool(cur_row['scheduled_update']),
                                      show_obj=show_obj,
                                      uid=cur_row['uid'])

                elif ShowQueueActions.RENAME == cur_row['action_id']:
                    self.rename_show_episodes(add_to_db=False, show_obj=show_obj, uid=cur_row['uid'])

                elif ShowQueueActions.SUBTITLE == cur_row['action_id']:
                    self.download_subtitles(add_to_db=False, show_obj=show_obj, uid=cur_row['uid'])

                elif ShowQueueActions.ADD == cur_row['action_id']:
                    self.add_show(
                        tvid=cur_row['tvid'], prodid=cur_row['prodid'], show_dir=cur_row['show_dir'],
                        quality=cur_row['quality'], upgrade_once=bool(cur_row['upgrade_once']),
                        wanted_begin=cur_row['wanted_begin'], wanted_latest=cur_row['wanted_latest'],
                        tag=cur_row['tag'],
                        paused=bool_none(cur_row['paused']), prune=cur_row['prune'],
                        default_status=cur_row['default_status'], scene=bool_none(cur_row['scene']),
                        subtitles=cur_row['subtitles'],
                        flatten_folders=bool_none(cur_row['flatten_folders']), anime=bool_none(cur_row['anime']),
                        blocklist=cur_row['blocklist'], allowlist=cur_row['allowlist'],
                        show_name=cur_row['show_name'], new_show=bool(cur_row['new_show']),
                        lang=cur_row['lang'], uid=cur_row['uid'], add_to_db=False)

        except (BaseException, Exception) as e:
            logger.error('Exception loading queue %s: %s' % (self.__class__.__name__, ex(e)))

    def save_item(self, item):
        # type: (ShowQueueItem) -> None
        if ShowQueueActions.SWITCH == item.action_id:
            my_db = db.DBConnection()
            my_db.action(
                """
                REPLACE INTO tv_src_switch (old_indexer, old_indexer_id, new_indexer, new_indexer_id,
                 action_id, status, uid, mark_wanted, set_pause, force_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, [item.show_obj.tvid, item.show_obj.prodid, item.new_tvid, item.new_prodid,
                      ShowQueueActions.SWITCH, TVSWITCH_NORMAL, item.uid, int(item.mark_wanted), int(item.set_pause),
                      int(item.force_id)])
        else:
            generic_queue.GenericQueue.save_item(self, item)

    def _clear_sql(self):
        # noinspection SqlWithoutWhere
        return [['DELETE FROM show_queue']]

    def _get_item_sql(self, item):
        # type: (ShowQueueItem) -> List[List]
        if isinstance(item, QueueItemUpdate):
            if item.switch:
                return []
            pause_status_after = item.kwargs.get('pausestatus_after')
            if None is not pause_status_after:
                pause_status_after = int(pause_status_after)
            return [[
                """
                INSERT OR IGNORE INTO show_queue (tvid, prodid, priority, force,
                scheduled_update, skip_refresh, pausestatus_after,
                action_id, uid) VALUES (?,?,?,?,?,?,?,?,?)
                """, [item.show_obj.tvid, item.show_obj.prodid, item.priority, int(item.force),
                      int(item.scheduled_update), int(item.kwargs.get('skip_refresh', False)), pause_status_after,
                      item.action_id, item.uid]
            ]]
        elif isinstance(item, QueueItemRefresh):
            if item.switch:
                return []
            pause_status_after = item.kwargs.get('pausestatus_after')
            if None is not pause_status_after:
                pause_status_after = int(pause_status_after)
            return [[
                """
                INSERT OR IGNORE INTO show_queue (tvid, prodid, priority, force,
                scheduled_update, force_image_cache, pausestatus_after,
                action_id, uid) VALUES (?,?,?,?,?,?,?,?,?)
                """, [item.show_obj.tvid, item.show_obj.prodid, item.priority, int(item.force),
                      int(item.scheduled_update), int(item.force_image_cache), pause_status_after,
                      item.action_id, item.uid]
            ]]
        elif isinstance(item, QueueItemRename):
            return [[
                """
                INSERT OR IGNORE INTO show_queue (tvid, prodid, priority, scheduled_update, action_id, uid)
                VALUES (?,?,?,?,?,?)
                """, [item.show_obj.tvid, item.show_obj.prodid, item.priority, int(item.scheduled_update),
                      item.action_id, item.uid]
            ]]
        elif isinstance(item, QueueItemSubtitle):
            return [[
                """
                INSERT OR IGNORE INTO show_queue (tvid, prodid, priority, scheduled_update, action_id, uid)
                VALUES (?,?,?,?,?,?)
                """, [item.show_obj.tvid, item.show_obj.prodid, item.priority, int(item.scheduled_update),
                      item.action_id, item.uid]
            ]]
        elif isinstance(item, QueueItemAdd):
            return [[
                """
                INSERT OR IGNORE INTO show_queue (tvid, prodid, priority, scheduled_update,
                show_dir, default_status, quality, flatten_folders, lang,
                subtitles, anime, scene, paused,
                blocklist, allowlist, wanted_begin, wanted_latest,
                prune, tag, new_show, show_name, upgrade_once,
                action_id, uid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, [item.tvid, item.prodid, item.priority, int(item.scheduled_update),
                      item.showDir, item.default_status, item.quality, try_int(item.flatten_folders, None), item.lang,
                      item.subtitles, try_int(item.anime, None), try_int(item.scene, None), try_int(item.paused, None),
                      item.blocklist, item.allowlist, item.default_wanted_begin, item.default_wanted_latest,
                      item.prune, item.tag, int(item.new_show), item.show_name, int(item.upgrade_once),
                      item.action_id, item.uid]
            ]]
        return []

    def delete_item(self, item, finished_run=False):
        # type: (ShowQueueItem, bool) -> None
        if isinstance(item, QueueItemSwitchSource):
            try:
                my_db = db.DBConnection()
                if finished_run:
                    my_db.action('DELETE FROM tv_src_switch WHERE uid = ? AND status = ?', [item.uid, TVSWITCH_NORMAL])
                else:
                    my_db.action('DELETE FROM tv_src_switch WHERE uid = ?', [item.uid])
            except (BaseException, Exception) as e:
                logger.error('Exception deleting item %s from db: %s' % (item, ex(e)))
        else:
            generic_queue.GenericQueue.delete_item(self, item)

    def _delete_item_from_db_sql(self, item):
        # type: (ShowQueueItem) -> List[List]
        return [
            ['DELETE FROM show_queue WHERE uid = ?', [item.uid]]
        ]

    def _clear_queue(self, action_types=None, excluded_types=None):
        # type: (integer_types, List[integer_types]) -> None
        generic_queue.GenericQueue._clear_queue(self, action_types=action_types)

    def remove_from_queue(self, to_remove=None, force=False):
        # type: (List[integer_types], bool) -> None
        generic_queue.GenericQueue._remove_from_queue(self, to_remove=to_remove, force=force)

    def _is_in_queue(self, show_obj, actions):
        # type: (TVShow, Tuple[integer_types, ...]) -> bool
        """

        :param show_obj: show object
        :param actions:
        :return:
        """
        with self.lock:
            return any(1 for x in self.queue if x.action_id in actions and show_obj == x.show_obj)

    def _is_being_somethinged(self, show_obj, actions):
        # type: (TVShow, Tuple[integer_types, ...]) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param actions:
        :return:
        :rtype: bool
        """
        with self.lock:
            return None is not self.currentItem \
                   and show_obj == self.currentItem.show_obj \
                   and self.currentItem.action_id in actions

    def is_in_update_queue(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_in_queue(show_obj, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE,
                                            ShowQueueActions.WEBFORCEUPDATE))

    def is_in_refresh_queue(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_in_queue(show_obj, (ShowQueueActions.REFRESH,))

    def is_in_rename_queue(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_in_queue(show_obj, (ShowQueueActions.RENAME,))

    def is_in_subtitle_queue(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_in_queue(show_obj, (ShowQueueActions.SUBTITLE,))

    def is_being_added(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.ADD,))

    def is_being_updated(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE,
                                                     ShowQueueActions.WEBFORCEUPDATE))

    def is_being_refreshed(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.REFRESH,))

    def is_being_renamed(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.RENAME,))

    def is_being_subtitled(self, show_obj):
        # type: (TVShow) -> bool
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.SUBTITLE,))

    def is_show_update_running(self):
        """

        :return:
        :rtype: bool
        """
        with self.lock:
            return any(1 for x in self.queue + [self.currentItem]
                       if isinstance(x, ShowQueueItem) and x.scheduled_update)

    def is_show_being_switched(self, show_obj):
        # type: (TVShow) -> bool
        """
        check if show is being switched currently

        :param show_obj: show object
        """
        return self._is_being_somethinged(show_obj, (ShowQueueActions.SWITCH,))

    def is_show_switch_queued(self, show_obj):
        # type: (TVShow) -> bool
        """
        check if show is in switch queue

        :param show_obj: show object
        """
        return self._is_in_queue(show_obj, (ShowQueueActions.SWITCH,))

    def is_switch_running(self):
        # type: (...) -> bool
        with self.lock:
            return any(1 for x in self.queue + [self.currentItem] if isinstance(x, QueueItemSwitchSource))

    def _get_loading_showlist(self):
        """

        :return:
        :rtype: List
        """
        with self.lock:
            return [x for x in self.queue + [self.currentItem] if None is not x and x.is_loading]

    def queue_length(self):
        # type: (...) -> Dict[AnyStr, List[AnyStr, Dict]]
        """

        :return:
        """
        length = {'add': [], 'update': [], 'forceupdate': [], 'forceupdateweb': [], 'refresh': [], 'rename': [],
                  'subtitle': [], 'switch': []}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:  # type: ShowQueueItem
                if not cur_item:
                    continue
                result_item = {'name': cur_item.show_name, 'scheduled_update': cur_item.scheduled_update,
                               'uid': cur_item.uid}
                if isinstance(cur_item, QueueItemAdd):
                    length['add'].append(result_item)
                else:
                    result_item.update({
                        'tvid': cur_item.show_obj.tvid,
                        'prodid': cur_item.show_obj.prodid, 'tvid_prodid': cur_item.show_obj.tvid_prodid,
                        # legacy keys for api responses
                        'indexer': cur_item.show_obj.tvid, 'indexerid': cur_item.show_obj.prodid})
                    if isinstance(cur_item, QueueItemUpdate):
                        update_type = 'Normal'
                        if isinstance(cur_item, QueueItemForceUpdate):
                            update_type = 'Forced'
                        elif isinstance(cur_item, QueueItemForceUpdateWeb):
                            update_type = 'Forced Web'
                        result_item.update({'update_type': update_type})
                        length['update'].append(result_item)
                    elif isinstance(cur_item, QueueItemRefresh):
                        length['refresh'].append(result_item)
                    elif isinstance(cur_item, QueueItemRename):
                        length['rename'].append(result_item)
                    elif isinstance(cur_item, QueueItemSubtitle):
                        length['subtitle'].append(result_item)
                    elif isinstance(cur_item, QueueItemSwitchSource):
                        result_item.update({'new_tvid': cur_item.new_tvid, 'new_prodid': cur_item.new_prodid,
                                            'progress': cur_item.progress})
                        length['switch'].append(result_item)
            return length

    loading_showlist = property(_get_loading_showlist)

    def update_show(self,
                    show_obj,  # type: TVShow
                    force=False,  # type: bool
                    web=False,  # type: bool
                    scheduled_update=False,  # type: bool
                    priority=generic_queue.QueuePriorities.NORMAL,  # type: integer_types
                    uid=None,  # type: integer_types
                    add_to_db=True,  # type: bool
                    **kwargs  # type: Any
                    ):  # type: (...) -> Union[QueueItemUpdate, QueueItemForceUpdate, QueueItemForceUpdateWeb]
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param force:
        :type force: bool
        :param web:
        :type web: bool
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param uid:
        :param add_to_db:
        :param kwargs:
        :return:
        :rtype: QueueItemUpdate or QueueItemForceUpdateWeb or QueueItemForceUpdate
        """
        with self.lock:
            if self.is_being_added(show_obj):
                raise exceptions_helper.CantUpdateException(
                    'Show is still being added, wait until it is finished before you update.')

            if self.is_being_updated(show_obj):
                raise exceptions_helper.CantUpdateException(
                    'This show is already being updated, can\'t update again until it\'s done.')

            if self.is_in_update_queue(show_obj):
                raise exceptions_helper.CantUpdateException(
                    'This show is already being updated, can\'t update again until it\'s done.')

            if self.is_show_being_switched(show_obj):
                raise exceptions_helper.CantUpdateException('Show is in progress of being switched')
            if self.is_show_switch_queued(show_obj):
                raise exceptions_helper.CantUpdateException('Show is already queued to be switched')

            if not force:
                queue_item_obj = QueueItemUpdate(
                    show_obj, scheduled_update=scheduled_update, uid=uid, **kwargs)
            elif web:
                queue_item_obj = QueueItemForceUpdateWeb(
                    show_obj, scheduled_update=scheduled_update, priority=priority, uid=uid, **kwargs)
            else:
                queue_item_obj = QueueItemForceUpdate(
                    show_obj, scheduled_update=scheduled_update, uid=uid, **kwargs)

            self.add_item(queue_item_obj, add_to_db=add_to_db)

            return queue_item_obj

    def refresh_show(self, show_obj, force=False, scheduled_update=False, after_update=False,
                     priority=generic_queue.QueuePriorities.HIGH, force_image_cache=False, uid=None, add_to_db=True,
                     **kwargs):
        # type: (TVShow, bool, bool, bool, integer_types, bool, integer_types, bool, Any) -> Optional[QueueItemRefresh]
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param force:
        :type force: bool
        :param scheduled_update:
        :type scheduled_update: bool
        :param after_update:
        :type after_update:
        :param priority:
        :type priority: int
        :param force_image_cache:
        :type force_image_cache: bool
        :param uid:
        :param add_to_db:
        :param kwargs:
        :return:
        :rtype: QueueItemRefresh
        """
        with self.lock:
            if (self.is_being_refreshed(show_obj) or self.is_in_refresh_queue(show_obj)) and not force:
                raise exceptions_helper.CantRefreshException('This show is being refreshed, not refreshing again.')

            if ((not after_update and self.is_being_updated(show_obj))
                    or self.is_in_update_queue(show_obj)) and not force:
                logger.debug('Skipping this refresh as there is already an update queued or'
                             ' in progress and a refresh is done at the end of an update anyway.')
                return

            if self.is_show_being_switched(show_obj):
                raise exceptions_helper.CantRefreshException('Show is in progress of being switched')
            if self.is_show_switch_queued(show_obj):
                raise exceptions_helper.CantRefreshException('Show is already queued to be switched')

            queue_item_obj = QueueItemRefresh(show_obj, force=force, scheduled_update=scheduled_update,
                                              priority=priority, force_image_cache=force_image_cache, uid=uid, **kwargs)

            self.add_item(queue_item_obj, add_to_db=add_to_db)

            return queue_item_obj

    def rename_show_episodes(self, show_obj, uid=None, add_to_db=True):
        # type: (TVShow, integer_types, bool) -> QueueItemRename
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param uid:
        :param add_to_db:
        :return:
        :rtype: QueueItemRename
        """
        queue_item_obj = QueueItemRename(show_obj, uid=uid)

        self.add_item(queue_item_obj, add_to_db=add_to_db)

        return queue_item_obj

    def switch_show(self,
                    show_obj,  # type: TVShow
                    new_tvid,  # type: integer_types
                    new_prodid,  # type: integer_types
                    force_id=False,  # type: bool
                    uid=None,  # type: AnyStr
                    set_pause=False,  # type: bool
                    mark_wanted=False,  # type: bool
                    resume=False,  # type: bool
                    old_tvid=None,  # type: integer_types
                    old_prodid=None,  # type: integer_types
                    add_to_db=True  # type: bool
                    ):  # type: (...) -> QueueItemSwitchSource
        """
        :param show_obj:
        :param new_tvid:
        :param new_prodid:
        :param force_id:
        :param uid:
        :param set_pause:
        :param mark_wanted:
        :param resume:
        :param old_tvid:
        :param old_prodid:
        :param add_to_db:
        """
        with self.lock:
            if self.is_show_being_switched(show_obj):
                raise exceptions_helper.CantSwitchException('Show is in progress of being switched')
            if self.is_show_switch_queued(show_obj):
                raise exceptions_helper.CantSwitchException('Show is already queued to be switched')

            item = QueueItemSwitchSource(show_obj=show_obj, new_tvid=new_tvid, new_prodid=new_prodid, force_id=force_id,
                                         uid=uid, set_pause=set_pause, mark_wanted=mark_wanted, resume=resume,
                                         old_tvid=old_tvid, old_prodid=old_prodid)
            self.add_item(item, add_to_db=add_to_db)
            return item

    def download_subtitles(self, show_obj, uid=None, add_to_db=True):
        # type: (TVShow, integer_types, bool) -> QueueItemSubtitle
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param uid:
        :param add_to_db:
        :return:
        :rtype: QueueItemSubtitle
        """
        if sickgear.USE_SUBTITLES:
            queue_item_obj = QueueItemSubtitle(show_obj, uid=uid)

            self.add_item(queue_item_obj, add_to_db=add_to_db)

            return queue_item_obj

    def abort_show(self, show_obj):
        # type: (TVShow) -> None
        if show_obj:
            with self.lock:
                for c in ((self.currentItem and [self.currentItem]) or []) + self.queue:
                    if show_obj == getattr(c, 'show_obj', None):
                        try:
                            self.remove_from_queue([c.uid])
                        except (BaseException, Exception):
                            pass
                        try:
                            c.stop.set()
                        except (BaseException, Exception):
                            pass

    def add_show(self, tvid, prodid, show_dir,
                 quality=None, upgrade_once=False, wanted_begin=None, wanted_latest=None, tag=None,
                 paused=None, prune=None, default_status=None, scene=None, subtitles=None,
                 flatten_folders=None, anime=None, blocklist=None, allowlist=None,
                 show_name=None, new_show=False, lang='en', uid=None, add_to_db=True):
        """

        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :param show_dir: show dir
        :type show_dir: AnyStr
        :param quality:
        :type quality: None or int
        :param upgrade_once:
        :type upgrade_once: bool or None
        :param wanted_begin:
        :type wanted_begin: int or None
        :param wanted_latest:
        :type wanted_latest: int or None
        :param tag:
        :type tag: AnyStr or None
        :param paused:
        :type paused: None or int
        :param prune:
        :type prune: int or None
        :param default_status:
        :type default_status: int or None
        :param scene:
        :type scene: int or None
        :param subtitles:
        :type subtitles: int or None
        :param flatten_folders:
        :type flatten_folders: int or None
        :param anime:
        :type anime: int or None
        :param blocklist:
        :type blocklist: AnyStr or None
        :param allowlist:
        :type allowlist: AnyStr or None
        :param show_name:
        :type show_name: AnyStr or None
        :param new_show:
        :param lang:
        :type lang: AnyStr
        :param uid:
        :param add_to_db:
        :return:
        :rtype: QueueItemAdd
        """
        queue_item_obj = QueueItemAdd(tvid, prodid, show_dir, default_status, quality, flatten_folders, lang,
                                      subtitles, anime, scene, paused, blocklist, allowlist,
                                      wanted_begin, wanted_latest, prune, tag,
                                      new_show=new_show, show_name=show_name, upgrade_once=upgrade_once, uid=uid)

        self.add_item(queue_item_obj, add_to_db=add_to_db)

        return queue_item_obj


class ShowQueueActions(object):
    REFRESH = 1
    ADD = 2
    UPDATE = 3
    FORCEUPDATE = 4
    WEBFORCEUPDATE = 7
    RENAME = 5
    SUBTITLE = 6
    SWITCH = 10

    names = {REFRESH: 'Refresh',
             ADD: 'Add',
             UPDATE: 'Update',
             FORCEUPDATE: 'Force Update',
             WEBFORCEUPDATE: 'Force Web Update',
             RENAME: 'Rename',
             SUBTITLE: 'Subtitle',
             SWITCH: 'Switch Source'}


class ShowQueueItem(generic_queue.QueueItem):
    """
    Represents an item in the queue waiting to be executed

    Can be either:
    - show being added (may or may not be associated with a show object)
    - show being refreshed
    - show being updated
    - show being force updated
    - show being subtitled
    """

    def __init__(self, action_id, show_obj, scheduled_update=False, uid=None):
        # type: (integer_types, TVShow, bool, integer_types) -> None
        """

        :param action_id:
        :type action_id:
        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow or None
        :param scheduled_update:
        :type scheduled_update: bool
        :param uid:
        """
        generic_queue.QueueItem.__init__(self, ShowQueueActions.names[action_id], action_id, uid=uid)
        self.show_obj = show_obj  # type: sickgear.tv.TVShow
        self.scheduled_update = scheduled_update  # type: bool

    def is_in_queue(self):
        """
        :rtype: bool
        """
        return self in sickgear.show_queue_scheduler.action.queue + [
            sickgear.show_queue_scheduler.action.currentItem]

    def _get_name(self):
        """
        :rtype: AnyStr
        """
        if self.show_obj:
            return self.show_obj.name
        return ''

    def _is_loading(self):
        return False

    def __str__(self):
        return '<%s (%s)>' % (self.__class__.__name__, (self.show_obj and self.show_obj.name))

    def __repr__(self):
        return self.__str__()

    show_name = property(_get_name)

    is_loading = property(_is_loading)


class QueueItemAdd(ShowQueueItem):
    def __init__(self, tvid, prodid, show_dir, default_status, quality, flatten_folders, lang, subtitles, anime,
                 scene, paused, blocklist, allowlist, default_wanted_begin, default_wanted_latest, prune, tag,
                 scheduled_update=False, new_show=False, show_name=None, upgrade_once=False, uid=None):
        """

        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :param show_dir:
        :type show_dir: AnyStr
        :param default_status:
        :type default_status:
        :param quality:
        :type quality: int
        :param flatten_folders:
        :type flatten_folders:
        :param lang:
        :type lang:
        :param subtitles:
        :type subtitles:
        :param anime:
        :type anime:
        :param scene:
        :type scene:
        :param paused:
        :type paused:
        :param blocklist:
        :type blocklist:
        :param allowlist:
        :type allowlist:
        :param default_wanted_begin:
        :type default_wanted_begin:
        :param default_wanted_latest:
        :type default_wanted_latest:
        :param prune:
        :type prune:
        :param tag:
        :type tag:
        :param scheduled_update:
        :type scheduled_update:
        :param new_show:
        :type new_show:
        :param show_name:
        :type show_name: AnyStr or None
        :param upgrade_once:
        :type upgrade_once:
        :param uid:
        """
        self.tvid = tvid  # type: int
        self.prodid = prodid  # type: int
        self.allowlist = allowlist
        self.anime = anime
        self.blocklist = blocklist
        self.default_status = default_status
        self.default_wanted_begin = (0, default_wanted_begin)[isinstance(default_wanted_begin, integer_types)]
        self.default_wanted_latest = (0, default_wanted_latest)[isinstance(default_wanted_latest, integer_types)]
        self.flatten_folders = flatten_folders
        self.lang = lang
        self.new_show = new_show
        self.paused = paused
        self.prune = prune
        self.quality = quality  # type: int
        self.scene = scene
        self.show_obj = None
        self.showDir = show_dir  # type: AnyStr
        self.showname = show_name  # type: AnyStr or None
        self.subtitles = subtitles
        self.tag = tag
        self.upgrade_once = upgrade_once

        # this will initialize self.show_obj to None
        ShowQueueItem.__init__(self, ShowQueueActions.ADD, self.show_obj, scheduled_update, uid=uid)

        self.priority = generic_queue.QueuePriorities.VERYHIGH

    def _get_name(self):
        """
        :return: the show name if there is a show object created, if not returns
        the dir that the show is being added to.
        :rtype: AnyStr
        """
        if None is not self.showname:
            return self.showname
        if None is self.show_obj:
            return self.showDir
        return self.show_obj.name

    show_name = property(_get_name)

    def _is_loading(self):
        """
        :return: True if we've gotten far enough to have a show object, or False
        if we still only know the folder name.
        :rtype: bool
        """
        return None is self.show_obj

    is_loading = property(_is_loading)

    # if they gave a number to start or number to end as wanted, then change those eps to it
    def _get_wanted(self, db_obj, wanted_max, latest):
        # type (...) -> int

        latest_season = 0
        actual = 0
        upgradable = 0
        process_sql = True
        wanted_updates = []
        if latest:
            # find season number with latest aired episode
            latest_result = db_obj.select(
                """
                SELECT MAX(season) AS latest_season
                FROM tv_episodes
                WHERE season > 0 AND indexer = ? AND showid = ? AND status != ?
                """, [self.show_obj.tvid, self.show_obj.prodid, UNAIRED])
            if latest_result and None is not latest_result[0]['latest_season']:
                latest_season = int(latest_result[0]['latest_season'])
            else:
                process_sql = False

        if process_sql:
            if -1 == wanted_max:
                compare_op = ''  # equal, we only want the specific season
            else:
                compare_op = ('>', '<')[latest]  # less/more then equal season
            base_sql = """
            SELECT indexerid, season, episode, status 
            FROM tv_episodes 
            WHERE indexer = ? AND showid = ? AND season != 0 AND season %s= ? AND status != ?
            ORDER BY season%s, episode%s%s
            """ % (compare_op, ('', ' DESC')[latest], ('', ' DESC')[latest], (' LIMIT ?', '')[-1 == wanted_max])

            selected_res = db_obj.select(base_sql, [self.show_obj.tvid, self.show_obj.prodid,
                                                    (1, latest_season)[latest], UNAIRED] +
                                         ([wanted_max], [])[-1 == wanted_max])
            selected_ids = []
            for sr in selected_res:
                if sr['status'] in [SKIPPED]:
                    selected_ids.append(sr['indexerid'])
                    wanted_updates.append({'season': sr['season'], 'episode': sr['episode'],
                                           'status': sr['status']})
                elif sr['status'] not in [WANTED]:
                    cur_status, cur_quality = Quality.split_composite_status(int(sr['status']))
                    if sickgear.WANTEDLIST_CACHE.get_wantedlist(
                            self.quality, self.upgrade_once, cur_quality, cur_status,
                            unaired=(sickgear.SEARCH_UNAIRED and not sickgear.UNAIRED_RECENT_SEARCH_ONLY)):
                        upgradable += 1

            if selected_ids:
                update = 'UPDATE [tv_episodes] SET status = ? WHERE indexer = ? AND indexerid IN (%s)' % \
                         ','.join(['?'] * len(selected_ids))
                db_obj.action(update, [WANTED, self.show_obj.tvid] + selected_ids)

                # noinspection SqlResolve
                sql_result = db_obj.select('SELECT changes() as last FROM [tv_episodes]')

                for cur_row in sql_result:
                    actual = cur_row['last']
                    break

        action_log = 'didn\'t find any episodes that need to be set wanted'
        if actual:
            action_log = ('updated %s %s episodes > %s' % (
                (((('%s of %s' % (actual, wanted_max)),
                   ('%s of max %s limited' % (actual, wanted_max)))[10 == wanted_max]),
                 ('max %s available' % actual))[-1 == wanted_max],
                ('first season', 'latest')[latest],
                ', '.join([
                    ('S%02dE%02d=%s' % (a['season'], a['episode'], statusStrings[a['status']]))
                    for a in wanted_updates
                ])
            ))
        logger.log('Get wanted ' + action_log)
        return actual + upgradable

    def run(self):

        ShowQueueItem.run(self)

        logger.log('Starting to add show %s' % self.showDir)
        # make sure the TV info source IDs are valid
        try:

            tvinfo_config = sickgear.TVInfoAPI(self.tvid).api_params.copy()
            if self.lang:
                tvinfo_config['language'] = self.lang

            logger.log(f'{sickgear.TVInfoAPI(self.tvid).name}: {repr(tvinfo_config)}')

            t = sickgear.TVInfoAPI(self.tvid).setup(**tvinfo_config)
            s = t.get_show(self.prodid, load_episodes=False, language=self.lang)

            if getattr(t, 'show_not_found', False):
                logger.error(f'Show {self.show_name} was not found on {sickgear.TVInfoAPI(self.tvid).name},'
                             f' maybe show was deleted')
                self._finish_early()
                return

            # this usually only happens if they have an NFO in their show dir
            # which gave us a TV info source ID that has no proper english version of the show
            if None is getattr(s, 'seriesname', None):
                logger.error(f'Show in {self.showDir} has no name on {sickgear.TVInfoAPI(self.tvid).name},'
                             f' probably the wrong language used to search with.')
                ui.notifications.error('Unable to add show',
                                       'Show in %s has no name on %s, probably the wrong language.'
                                       ' Delete .nfo and add manually in the correct language.' %
                                       (self.showDir, sickgear.TVInfoAPI(self.tvid).name))
                self._finish_early()
                return
        except (BaseException, Exception):
            logger.error('Unable to find show ID:%s on TV info: %s' % (self.prodid, sickgear.TVInfoAPI(self.tvid).name))
            ui.notifications.error('Unable to add show',
                                   'Unable to look up the show in %s on %s using ID %s, not using the NFO.'
                                   ' Delete .nfo and try adding manually again.' %
                                   (self.showDir, sickgear.TVInfoAPI(self.tvid).name, self.prodid))
            self._finish_early()
            return

        try:
            show_exists = find_show_by_id({self.tvid: self.prodid}, no_exceptions=True)
            new_show_obj = show_exists or TVShow(self.tvid, self.prodid, self.lang)
            result = new_show_obj.load_from_tvinfo()

            self.show_obj = new_show_obj

            # set up initial values
            self.show_obj.location = self.showDir
            self.show_obj.quality = self.quality if self.quality else sickgear.QUALITY_DEFAULT
            self.show_obj.upgrade_once = self.upgrade_once
            self.show_obj.tag = self.tag if None is not self.tag else 'Show List'
            self.show_obj.paused = self.paused if None is not self.paused else sickgear.PAUSE_DEFAULT
            self.show_obj.prune = self.prune if None is not self.prune else 0
            self.show_obj.scene = self.scene if None is not self.scene else sickgear.SCENE_DEFAULT
            self.show_obj.subtitles = self.subtitles if None is not self.subtitles else sickgear.SUBTITLES_DEFAULT
            self.show_obj.flatten_folders = self.flatten_folders if None is not self.flatten_folders \
                else sickgear.FLATTEN_FOLDERS_DEFAULT
            self.show_obj.anime = self.anime if None is not self.anime else sickgear.ANIME_DEFAULT

            if self.show_obj.anime:
                self.show_obj.release_groups = AniGroupList(self.show_obj.tvid,
                                                            self.show_obj.prodid,
                                                            self.show_obj.tvid_prodid)
                if self.allowlist:
                    self.show_obj.release_groups.set_allow_keywords(self.allowlist)
                if self.blocklist:
                    self.show_obj.release_groups.set_block_keywords(self.blocklist)

            # be smartish about this
            if self.show_obj.genre and 'talk show' in self.show_obj.genre.lower():
                self.show_obj.air_by_date = 1
            if self.show_obj.genre and 'documentary' in self.show_obj.genre.lower():
                self.show_obj.air_by_date = 0
            if self.show_obj.classification and 'sports' in self.show_obj.classification.lower():
                self.show_obj.sports = 1

        except BaseTVinfoException as e:
            logger.error(f'Unable to add show due to an error with {sickgear.TVInfoAPI(self.tvid).name}: {ex(e)}')
            if self.show_obj:
                ui.notifications.error('Unable to add %s due to an error with %s'
                                       % (self.show_obj.unique_name, sickgear.TVInfoAPI(self.tvid).name))
            else:
                ui.notifications.error(
                    'Unable to add show due to an error with %s' % sickgear.TVInfoAPI(self.tvid).name)
            self._finish_early()
            return

        except exceptions_helper.MultipleShowObjectsException:
            logger.error('The show in %s is already in your show list, skipping' % self.showDir)
            ui.notifications.error('Show skipped', 'The show in %s is already in your show list' % self.showDir)
            self._finish_early()
            return

        except (BaseException, Exception) as e:
            logger.error('Error trying to add show: %s' % ex(e))
            logger.error(traceback.format_exc())
            self._finish_early()
            raise

        self.show_obj.load_imdb_info()

        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.error('Error saving the show to the database: %s' % ex(e))
            logger.error(traceback.format_exc())
            self._finish_early()
            raise

        if not show_exists:
            # add it to the show list if not already in it
            sickgear.showList.append(self.show_obj)
            sickgear.showDict[self.show_obj.sid_int] = self.show_obj
            sickgear.webserve.Home.make_showlist_unique_names()
            sickgear.MEMCACHE['history_tab'] = sickgear.webserve.History.menu_tab(
                sickgear.MEMCACHE['history_tab_limit'])

        try:
            self.show_obj.load_episodes_from_tvinfo(tvinfo_data=(None, result)[
                self.show_obj.prodid == getattr(result, 'id', None)])
        except (BaseException, Exception) as e:
            logger.error(f'Error with {sickgear.TVInfoAPI(self.show_obj.tvid).name},'
                         f' not creating episode list: {ex(e)}')
            logger.error(traceback.format_exc())

        try:
            self.show_obj.load_episodes_from_dir()
        except (BaseException, Exception) as e:
            logger.error('Error searching directory for episodes: %s' % ex(e))
            logger.error(traceback.format_exc())

        # if they gave a custom status then change all the eps to it
        my_db = db.DBConnection()
        if self.default_status != SKIPPED:
            logger.log('Setting all episodes to the specified default status: %s'
                       % sickgear.common.statusStrings[self.default_status])
            my_db.action(
                """
                UPDATE tv_episodes
                SET status = ?
                WHERE status = ? AND indexer = ? AND showid = ? AND season != 0
                """, [self.default_status, SKIPPED, self.show_obj.tvid, self.show_obj.prodid])

        items_wanted = self._get_wanted(my_db, self.default_wanted_begin, latest=False)
        items_wanted += self._get_wanted(my_db, self.default_wanted_latest, latest=True)

        self.show_obj.write_metadata()
        self.show_obj.update_metadata()
        self.show_obj.populate_cache()

        self.show_obj.flush_episodes()

        # load ids
        _ = self.show_obj.ids

        # if sickgear.USE_TRAKT:
        #     # if there are specific episodes that need to be added by trakt
        #     sickgear.trakt_checker_scheduler.action.manageNewShow(self.show_obj)
        #
        #     # add show to trakt.tv library
        #     if sickgear.TRAKT_SYNC:
        #         sickgear.trakt_checker_scheduler.action.addShowToTraktLibrary(self.show_obj)

        # Load XEM data to DB for show
        sickgear.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid, force=True)
        if self.show_obj.scene:
            # enable/disable scene flag based on if show has an explicit _scene_ mapping at XEM
            self.show_obj.scene = sickgear.scene_numbering.has_xem_scene_mapping(
                self.show_obj.tvid, self.show_obj.prodid)
        # if "scene" numbering is disabled during add show, output availability to log
        if None is not self.scene and not self.show_obj.scene and \
                self.show_obj.prodid in sickgear.scene_exceptions.MEMCACHE['release_map_xem'][self.show_obj.tvid]:
            logger.log('No scene number mappings found at TheXEM. Therefore, episode scene numbering disabled, '
                       'edit show and enable it to manually add custom numbers for search and media processing.')
        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.error('Error saving the show to the database: %s' % ex(e))
            logger.error(traceback.format_exc())
            self._finish_early()
            raise

        # update internal name cache
        name_cache.build_name_cache(self.show_obj)

        self.show_obj.load_episodes_from_db()

        map_indexers_to_show(self.show_obj, recheck=True)

        if self.show_obj.tvid in (TVINFO_TVRAGE, TVINFO_TVDB):
            # noinspection SqlResolve
            oh = my_db.select('SELECT resource FROM history WHERE indexer = 0 AND showid = ?', [self.show_obj.prodid])
            if oh:
                found = False
                for o in oh:
                    np = NameParser(file_name=True, indexer_lookup=False)
                    try:
                        pr = np.parse(o['resource'])
                    except (BaseException, Exception):
                        continue
                    if pr.show_obj.tvid == self.show_obj.tvid and pr.show_obj.prodid == self.show_obj.prodid:
                        found = True
                        break
                if found:
                    my_db.action('UPDATE history SET indexer = ? WHERE indexer = 0 AND showid = ?',
                                 [self.show_obj.tvid, self.show_obj.prodid])

        msg = ' the specified show into ' + self.showDir
        # if started with WANTED eps then run the backlog
        if WANTED == self.default_status or items_wanted:
            logger.log('Launching backlog for this show since episodes are WANTED')
            sickgear.search_backlog_scheduler.action.search_backlog([self.show_obj], prevent_same=True)
            ui.notifications.message('Show added/search', 'Adding and searching for episodes of' + msg)
        else:
            ui.notifications.message('Show added', 'Adding' + msg)

        self.finish()

    def _finish_early(self):
        if None is not self.show_obj:
            self.show_obj.delete_show()

        if self.new_show:
            # if adding a new show, delete the empty folder that was already created
            try:
                os.rmdir(self.showDir)
            except (BaseException, Exception):
                pass

        self.finish()

    def __str__(self):
        return '<%s (%s)>' % (self.__class__.__name__, '%s:%s%s' %
                              (self.tvid, self.prodid, ('', ' - %s ' % self.show_name)[None is not self.show_name]))

    def __repr__(self):
        return self.__str__()


class QueueItemRefresh(ShowQueueItem):
    def __init__(self, show_obj=None, force=False, scheduled_update=False, priority=generic_queue.QueuePriorities.HIGH,
                 force_image_cache=False, uid=None, switch=False, **kwargs):
        # type: (TVShow, bool, bool, integer_types, bool, integer_types, bool, Any) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param force:
        :type force: bool
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param force_image_cache:
        :type force_image_cache: bool
        :param uid:
        :param switch: switching show
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.REFRESH, show_obj, scheduled_update, uid=uid)

        # do refreshes first because they're quick
        self.priority = priority  # type: int

        # force refresh certain items
        self.force = force  # type: bool

        self.force_image_cache = force_image_cache  # type: bool

        self.switch = switch  # type: bool

        self.kwargs = kwargs

    def run(self):
        ShowQueueItem.run(self)

        logger.log('Performing refresh on %s' % self.show_obj.unique_name)

        self.show_obj.refresh_dir()
        self.show_obj.write_metadata(force=self.force)
        # if self.force:
        #    self.show_obj.update_metadata()
        self.show_obj.populate_cache(self.force_image_cache)

        # Load XEM data to DB for show
        if self.show_obj.prodid in sickgear.scene_exceptions.MEMCACHE['release_map_xem'][self.show_obj.tvid]:
            sickgear.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid)

        if 'pausestatus_after' in self.kwargs and None is not self.kwargs['pausestatus_after']:
            self.show_obj.paused = self.kwargs['pausestatus_after']
            self.show_obj.save_to_db()
        self.inProgress = False


class QueueItemRename(ShowQueueItem):
    def __init__(self, show_obj=None, scheduled_update=False, uid=None):
        # type: (TVShow, bool, integer_types) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param uid:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.RENAME, show_obj, scheduled_update, uid=uid)

    def run(self):

        ShowQueueItem.run(self)

        logger.log('Performing rename on %s' % self.show_obj.unique_name)

        try:
            _ = self.show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            logger.warning(f'Can\'t perform rename on {self.show_obj.unique_name} when the show directory is missing.')
            return

        ep_obj_rename_list = []

        ep_obj_list = self.show_obj.get_all_episodes(has_location=True)
        for cur_ep_obj in ep_obj_list:
            # Only want to rename if we have a location
            if cur_ep_obj.location:
                if cur_ep_obj.related_ep_obj:
                    # do we have one of multi-episodes in the rename list already
                    have_already = False
                    for cur_related_ep_obj in cur_ep_obj.related_ep_obj + [cur_ep_obj]:
                        if cur_related_ep_obj in ep_obj_rename_list:
                            have_already = True
                            break
                    if not have_already:
                        ep_obj_rename_list.append(cur_ep_obj)

                else:
                    ep_obj_rename_list.append(cur_ep_obj)

        for cur_ep_obj in ep_obj_rename_list:
            cur_ep_obj.rename()

        self.inProgress = False


class QueueItemSubtitle(ShowQueueItem):
    def __init__(self, show_obj=None, scheduled_update=False, uid=None):
        # type: (TVShow, bool, integer_types) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param uid:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.SUBTITLE, show_obj, scheduled_update, uid=uid)

    def run(self):
        ShowQueueItem.run(self)
        if not sickgear.USE_SUBTITLES:
            self.finish()
            return

        logger.log('Downloading subtitles for %s' % self.show_obj.unique_name)

        self.show_obj.download_subtitles()

        self.inProgress = False


class QueueItemUpdate(ShowQueueItem):
    def __init__(self, show_obj=None, scheduled_update=False, uid=None, switch=False, tvinfo_data=None, old_tvid=None,
                 old_prodid=None, **kwargs):
        # type: (TVShow, bool, AnyStr, bool, Optional[TVInfoShow], int, integer_types, Any) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param skip_refresh: skip queuing refresh task at the end
        :param switch: switching show
        :param tvinfo_data: tvinfo data for the show
        :param old_tvid: old tvid when switching
        :param old_prodid: old prodid when switching
        :param kwargs:
        :param uid:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.UPDATE, show_obj, scheduled_update, uid=uid)
        self.force = False  # type: bool
        self.force_web = False  # type: bool
        self.skip_refresh = kwargs.get('skip_refresh', False)  # type: bool
        self.switch = switch  # type: bool
        self.tvinfo_data = tvinfo_data  # type: Optional[TVInfoShow]
        self.old_tvid = old_tvid  # type: Optional[int]
        self.old_prodid = old_prodid  # type: Optional[integer_types]
        self.kwargs = kwargs

    def run(self):

        ShowQueueItem.run(self)
        last_update = datetime.date.fromordinal(self.show_obj.last_update_indexer)
        old_name = self.show_obj.name

        if not sickgear.TVInfoAPI(self.show_obj.tvid).config['active']:
            logger.log('TV info source %s is marked inactive, aborting update for show %s and continue with refresh.'
                       % (sickgear.TVInfoAPI(self.show_obj.tvid).config['name'], self.show_obj.name))
            sickgear.show_queue_scheduler.action.refresh_show(self.show_obj, self.force, self.scheduled_update,
                                                              after_update=True)
            return

        logger.log('Beginning update of %s' % self.show_obj.unique_name)

        logger.debug('Retrieving show info from %s' % sickgear.TVInfoAPI(self.show_obj.tvid).name)
        try:
            result = self.show_obj.load_from_tvinfo(cache=not self.force, tvinfo_data=self.tvinfo_data,
                                                    scheduled_update=self.scheduled_update, switch=self.switch)
            if result in (None, False):
                return
            elif not self.show_obj.prodid == getattr(self.tvinfo_data, 'id', None):
                self.tvinfo_data = result
        except BaseTVinfoAttributenotfound as e:
            logger.error(f'Data retrieved from {sickgear.TVInfoAPI(self.show_obj.tvid).name} was incomplete,'
                         f' aborting: {ex(e)}')
            return
        except BaseTVinfoError as e:
            logger.warning('Unable to contact %s, aborting: %s' % (sickgear.TVInfoAPI(self.show_obj.tvid).name, ex(e)))
            return

        if self.force_web:
            self.show_obj.load_imdb_info()

        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.error('Error saving the show to the database: %s' % ex(e))
            logger.error(traceback.format_exc())

        # get episode list from DB
        logger.debug('Loading all episodes from the database')
        db_ep_obj_list = self.show_obj.load_episodes_from_db(update=True)

        # get episode list from TVDB
        logger.debug('Loading all episodes from %s' % sickgear.TVInfoAPI(self.show_obj.tvid).name)
        try:
            tvinfo_ep_list = self.show_obj.load_episodes_from_tvinfo(cache=not self.force, update=True,
                                                                     tvinfo_data=self.tvinfo_data, switch=self.switch,
                                                                     old_tvid=self.old_tvid, old_prodid=self.old_prodid)
        except BaseTVinfoException as e:
            logger.error(f'Unable to get info from {sickgear.TVInfoAPI(self.show_obj.tvid).name},'
                         f' the show info will not be refreshed: {ex(e)}')
            tvinfo_ep_list = None

        if None is tvinfo_ep_list:
            logger.error('No data returned from %s, unable to update episodes for show: %s' %
                         (sickgear.TVInfoAPI(self.show_obj.tvid).name, self.show_obj.unique_name))
        elif not tvinfo_ep_list or 0 == len(tvinfo_ep_list):
            logger.warning('No episodes returned from %s for show: %s' %
                           (sickgear.TVInfoAPI(self.show_obj.tvid).name, self.show_obj.unique_name))
        else:
            # for each ep we found on TVDB delete it from the DB list
            for cur_season in tvinfo_ep_list:
                for cur_episode in tvinfo_ep_list[cur_season]:
                    logger.debug('Removing %sx%s from the DB list' % (cur_season, cur_episode))
                    if cur_season in db_ep_obj_list and cur_episode in db_ep_obj_list[cur_season]:
                        del db_ep_obj_list[cur_season][cur_episode]

            cl = []
            # for the remaining episodes in the DB list just delete them from the DB
            for cur_season in db_ep_obj_list:
                for cur_episode in db_ep_obj_list[cur_season]:
                    ep_obj = self.show_obj.get_episode(cur_season, cur_episode)  # type: Optional[TVEpisode]
                    status = sickgear.common.Quality.split_composite_status(ep_obj.status)[0]
                    if self.switch or should_delete_episode(status):
                        if self.switch:
                            cl.append(self.show_obj.switch_ep_change_sql(
                                self.old_tvid, self.old_prodid, cur_season, cur_episode, TVSWITCH_EP_DELETED))
                        logger.log(f'Permanently deleting episode {cur_season}x{cur_episode} from the database')
                        try:
                            cl.extend(ep_obj.delete_episode(return_sql=True))
                        except exceptions_helper.EpisodeDeletedException:
                            pass
                    else:
                        logger.log(f'Not deleting episode {cur_season}x{cur_episode} from the database'
                                   f' because status is: {statusStrings[status]}')

            if cl:
                my_db = db.DBConnection()
                my_db.mass_action(cl)

            # update indexer mapper once a month (using the day of the first ep as random date)
            update_over_month = (datetime.date.today() - last_update).days > 31
            try:
                if (self.scheduled_update or update_over_month) and tvinfo_ep_list.get(1, {}).get(1, False):
                    first_ep_airdate = self.show_obj.first_aired_regular_episode.airdate
                    day = (first_ep_airdate.day, 28)[28 < first_ep_airdate.day]
                    if datetime.date.today().day == day or update_over_month or \
                            -8 < (datetime.date.today() - first_ep_airdate).days < 31:
                        map_indexers_to_show(self.show_obj, force=True)
            except (BaseException, Exception):
                pass

        if self.priority != generic_queue.QueuePriorities.NORMAL:
            self.kwargs['priority'] = self.priority
        if self.kwargs.get('switch_src', False) or old_name != self.show_obj.name:
            sickgear.webserve.Home.make_showlist_unique_names()
            sickgear.MEMCACHE['history_tab'] = sickgear.webserve.History.menu_tab(
                sickgear.MEMCACHE['history_tab_limit'])
        if not getattr(self, 'skip_refresh', False):
            sickgear.show_queue_scheduler.action.refresh_show(self.show_obj, self.force, self.scheduled_update,
                                                              after_update=True, force_image_cache=self.force_web,
                                                              **self.kwargs)

    def finish(self):
        self.tvinfo_data = None
        super(QueueItemUpdate, self).finish()


class QueueItemForceUpdate(QueueItemUpdate):
    def __init__(self, show_obj=None, scheduled_update=False, **kwargs):
        # type: (TVShow, bool, Any) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param kwargs:
        :param uid:
        """
        QueueItemUpdate.__init__(self, show_obj, scheduled_update, **kwargs)
        self.action_id = ShowQueueActions.FORCEUPDATE
        self.force = True  # type: bool
        self.force_web = False  # type: bool
        self.kwargs = kwargs


class QueueItemForceUpdateWeb(QueueItemUpdate):
    def __init__(self, show_obj=None, scheduled_update=False, priority=generic_queue.QueuePriorities.NORMAL, **kwargs):
        # type: (TVShow, bool, integer_types, Any) -> None
        """

        :param show_obj: show object
        :type show_obj: sickgear.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param kwargs:
        :param uid:
        """
        QueueItemUpdate.__init__(self, show_obj, scheduled_update, **kwargs)
        self.action_id = ShowQueueActions.WEBFORCEUPDATE
        self.force = True  # type: bool
        self.force_web = True  # type: bool
        self.priority = priority  # type: int
        self.kwargs = kwargs


class QueueItemSwitchSource(ShowQueueItem):
    def __init__(self,
                 show_obj,  # type: TVShow
                 new_tvid,  # type: integer_types
                 new_prodid,  # type: integer_types
                 force_id=False,  # type: bool
                 uid=None,  # type: integer_types
                 set_pause=False,  # type: bool
                 mark_wanted=False,  # type: bool
                 resume=False,  # type: bool
                 old_tvid=None,  # type: integer_types
                 old_prodid=None,  # type: integer_types
                 **kwargs):
        """

        :param show_obj: TV Show object
        :param new_tvid: new tvid
        :param new_prodid: new prodid
        :param force_id: skip verification and forcibly use new id
        :param uid: uid
        :param set_pause: set pause
        :param mark_wanted: mark wanted after switch
        :param resume: resume unfinished switch (id already switched)
        :param old_tvid: old tvid if resume set
        :param old_prodid: old prodid if resume set
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.SWITCH, show_obj, uid=uid)
        self.new_tvid = new_tvid  # type: int
        self.new_prodid = new_prodid  # type: integer_types
        self.old_tvid = old_tvid or show_obj.tvid  # type: int
        self.old_prodid = old_prodid or show_obj.prodid  # type: integer_types
        self.force_id = force_id  # type: bool
        self.priority = SWITCH_PRIO  # type: int
        self.progress = 'Not Started'  # type: AnyStr
        self.set_pause = set_pause  # type: bool
        self.mark_wanted = mark_wanted  # type: bool
        self.resume = resume  # type: bool
        self.kwargs = kwargs  # type: Dict

    def _set_switch_tbl_status(self, status=TVSWITCH_NORMAL):
        # type: (integer_types) -> None
        """
        sets status in table or deletes the entry if status: TVSWITCH_NORMAL
        :param status:
        """
        my_db = db.DBConnection()
        if 0 == status:
            my_db.action('DELETE FROM tv_src_switch WHERE uid = ?',
                         [self.uid])
        else:
            my_db.action('UPDATE tv_src_switch SET status = ? WHERE uid = ?',
                         [status, self.uid])

    def _set_switch_id(self, new_id):
        # type: (integer_types) -> None
        """
        set the new prodid of the show in db
        :param new_id:
        """
        my_db = db.DBConnection()
        my_db.action('UPDATE tv_src_switch SET new_indexer_id = ? WHERE uid = ?',
                     [new_id, self.uid])

    def _check_same_id(self, new_prodid):
        # type: (integer_types) -> bool
        if new_prodid and self.old_tvid == self.new_tvid and new_prodid == self.old_prodid:
            if self.show_obj:
                which_show = self.show_obj.unique_name
            else:
                which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
            self._set_switch_tbl_status(TVSWITCH_SAME_ID)
            logger.error('Unchanged ids given, nothing to do for %s' % which_show)
            return True
        return False

    def run(self):
        ShowQueueItem.run(self)
        td = None
        if self.resume:
            logger.log('Resume switching show: %s' % self.show_obj.unique_name)
            self.progress = 'Resume switching show'
            with self.show_obj.lock:
                pausestatus_after = None
                if not self.set_pause:
                    self.show_obj.paused = False
                    if not self.mark_wanted:
                        self.show_obj.paused = True
                        pausestatus_after = False
                elif not self.show_obj.paused:
                    self.show_obj.paused = True
        else:
            logger.log('Start switching show: %s' % self.show_obj.unique_name)
            # verify show before switching
            self.progress = 'Verifying validity of new id'

            new_prodid = (self.new_prodid or self.show_obj.ids.get(self.new_tvid, {}).get('id'),
                          self.new_prodid)[self.force_id and self.new_prodid not in (None, 0)]
            if self._check_same_id(new_prodid):
                return
            if not new_prodid:
                if not self.force_id:
                    map_indexers_to_show(self.show_obj, recheck=True)
                if self.show_obj.ids.get(self.new_tvid, {}).get('id') not in (None, 0):
                    new_prodid = self.show_obj.ids.get(self.new_tvid)['id']

            if not new_prodid:
                if self.show_obj:
                    which_show = self.show_obj.unique_name
                else:
                    which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
                ui.notifications.message('TV info source switch: %s' % which_show,
                                         'Error: could not find a id for show on new tv info source')
                logger.warning('Error: could not find a id for show on new tv info source: %s' % which_show)
                self._set_switch_tbl_status(TVSWITCH_NO_NEW_ID)
                return

            if self._check_same_id(new_prodid):
                return

            try:
                m_show_obj = find_show_by_id({self.new_tvid: new_prodid}, no_mapped_ids=False, check_multishow=True)
            except exceptions_helper.MultipleShowObjectsException:
                msg = 'Duplicate shows in DB'
                if self.show_obj:
                    which_show = self.show_obj.unique_name
                else:
                    which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
                logger.warning('Duplicate shows in DB for show: %s' % which_show)
                ui.notifications.message('TV info source switch: %s' % which_show, 'Error: %s' % msg)

                self._set_switch_tbl_status(TVSWITCH_DUPLICATE_SHOW)
                return
            if not self.show_obj or (m_show_obj and self.show_obj is not m_show_obj):
                msg = 'Unable to find the specified show'
                if self.show_obj:
                    which_show = self.show_obj.unique_name
                else:
                    which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
                ui.notifications.message('TV info source switch: %s' % which_show, 'Error: %s' % msg)

                self._set_switch_tbl_status(TVSWITCH_SOURCE_NOT_FOUND_ERROR)
                logger.warning('Unable to find the specified show: %s' % which_show)
                return

            tvinfo_config = sickgear.TVInfoAPI(self.new_tvid).api_params.copy()
            tvinfo_config['cache'] = False
            tvinfo_config['language'] = self.show_obj._lang
            tvinfo_config['dvdorder'] = 0 != self.show_obj._dvdorder
            t = sickgear.TVInfoAPI(self.new_tvid).setup(**tvinfo_config)
            try:
                td = t.get_show(show_id=new_prodid, actors=True)
            except (BaseException, Exception):
                td = None
                if not self.force_id:
                    map_indexers_to_show(self.show_obj, recheck=True)
                    if new_prodid != self.show_obj.ids.get(self.new_tvid, {}).get('id') is not None:
                        new_prodid = self.show_obj.ids.get(self.new_tvid, {}).get('id')
                        try:
                            td = t.get_show(show_id=new_prodid, actors=True, language=self.show_obj.lang)
                        except (BaseException, Exception):
                            td = None
                            logger.warning(f'Failed to get new tv show id ({new_prodid})'
                                           f' from source {sickgear.TVInfoAPI(self.new_tvid).name}')
            if None is td:
                self._set_switch_tbl_status(TVSWITCH_NOT_FOUND_ERROR)
                msg = 'Show not found on new tv source'
                if self.show_obj:
                    which_show = self.show_obj.unique_name
                else:
                    which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
                ui.notifications.message('TV info source switch: %s' % which_show, 'Error: %s' % msg)
                logger.warning('show: %s not found on new tv source' % self.show_obj.tvid_prodid)
                return

            try:
                new_show_startyear = parser().parse(td[1][1].firstaired).year
                if 1900 > new_show_startyear:
                    new_show_startyear = None
            except (BaseException, Exception):
                new_show_startyear = None
            if not new_show_startyear:
                try:
                    new_show_startyear = parser().parse(td.firstaired).year
                except (BaseException, Exception):
                    new_show_startyear = None

            try:
                first_ep = self.show_obj.first_aired_regular_episode
                existing_show_startyear = first_ep and first_ep.airdate and first_ep.airdate.year
                if existing_show_startyear and 1900 > existing_show_startyear:
                    existing_show_startyear = None
            except (BaseException, Exception):
                existing_show_startyear = None
            if not existing_show_startyear:
                existing_show_startyear = self.show_obj.startyear

            if not self.force_id \
                    and not ((clean_show_name(td.seriesname.lower()) == clean_show_name(self.show_obj.name.lower()) or
                             any(1 for s, v in td.ids if v and v == self.show_obj.ids.get(s, {}).get('id')))
                             and (str(existing_show_startyear) == str(new_show_startyear)
                             or abs(try_int(existing_show_startyear, 10) - try_int(new_show_startyear, 1)) <= 1)):
                self._set_switch_tbl_status(TVSWITCH_VERIFY_ERROR)
                logger.warning('Failed to verify new ids for show %s' % self.show_obj.unique_name)
                msg = 'Failed to verify the show on new source'
                if self.show_obj:
                    which_show = self.show_obj.unique_name
                else:
                    which_show = '%s:%s' % (self.old_tvid, self.old_prodid)
                ui.notifications.message('TV info source switch: %s' % which_show, 'Error: %s' % msg)
                return
            # switch show to new id
            with self.show_obj.lock:
                try:
                    new_show_obj = find_show_by_id({self.new_tvid: new_prodid})
                except (BaseException, Exception):
                    new_show_obj = None
                if new_show_obj:
                    self._set_switch_tbl_status(TVSWITCH_ID_CONFLICT)
                    msg = 'Show %s new id conflicts with existing show: %s' % \
                          ('[%s (%s)]' % (self.show_obj.unique_name, self.show_obj.tvid_prodid),
                           '[%s (%s)]' % (new_show_obj.unique_name, new_show_obj.tvid_prodid))
                    logger.warning(msg)
                    return
                self.progress = 'Switching to new source'
                self._set_switch_id(new_prodid)
                self.show_obj.remove_character_images()
                self.show_obj._tvid = self.new_tvid
                self.show_obj._prodid = new_prodid
                new_tvid_prodid = TVidProdid({self.new_tvid: new_prodid})()
                old_tvid_prodid = TVidProdid({self.old_tvid: self.old_prodid})()
                for tp in (old_tvid_prodid, new_tvid_prodid):
                    try:
                        if tp in sickgear.switched_shows:
                            sickgear.switched_shows.pop(tp)
                    except (BaseException, Exception):
                        pass
                    try:
                        if tp in itervalues(sickgear.switched_shows):
                            sickgear.switched_shows = {k: v for k, v in iteritems(sickgear.switched_shows) if tp != v}
                    except (BaseException, Exception):
                        pass
                sickgear.switched_shows[TVidProdid({self.old_tvid: self.old_prodid})()] = \
                    TVidProdid({self.new_tvid: new_prodid})()
                pausestatus_after = None
                if not self.set_pause:
                    self.show_obj.paused = False
                    if not self.mark_wanted:
                        self.show_obj.paused = True
                        pausestatus_after = False
                elif not self.show_obj.paused:
                    self.show_obj.paused = True
                self.show_obj.switch_infosrc(self.old_tvid, self.old_prodid, update_show=False,
                                             pausestatus_after=pausestatus_after)

        # we directly update and refresh the show without queue as part of the switch
        self.progress = 'Updating from new source'
        update_show = QueueItemUpdate(show_obj=self.show_obj, skip_refresh=True, pausestatus_after=pausestatus_after,
                                      switch=True, tvinfo_data=td, old_tvid=self.old_tvid, old_prodid=self.old_prodid,
                                      switch_src=True)
        update_show.run()
        self.progress = 'Refreshing from disk'
        refresh_show = QueueItemRefresh(show_obj=self.show_obj, force_image_cache=True,
                                        pausestatus_after=pausestatus_after, switch=True, force=True)
        refresh_show.run()
        self.progress = 'Finished Switch'
        # now remove from switch tbl
        self._set_switch_tbl_status()
        logger.log('Finished switching show: %s' % self.show_obj.unique_name)
        ui.notifications.message('TV info source switch: %s' % self.show_obj.unique_name, 'Finished switching show')

    def __str__(self):
        return '<Show Switch Queue Item: %s (%s to %s)>' % \
               (self.show_obj.unique_name, sickgear.TVInfoAPI(self.old_tvid).name,
                (sickgear.TVInfoAPI(self.new_tvid).name, self.new_prodid)[self.old_tvid == self.new_tvid])

    def __repr__(self):
        return self.__str__()
