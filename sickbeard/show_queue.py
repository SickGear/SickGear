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
import os
import traceback

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex

import sickbeard
from . import logger, ui, db, generic_queue, name_cache
from .anime import BlackAndWhiteList
from .common import SKIPPED, WANTED, UNAIRED, Quality, statusStrings
from .helpers import should_delete_episode
from .indexermapper import map_indexers_to_show
from .indexers.indexer_config import TVINFO_TVDB, TVINFO_TVRAGE
from .indexers.indexer_exceptions import check_exception_type, ExceptionTuples
from .name_parser.parser import NameParser
from .tv import TVShow
from six import integer_types

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, List


DAILY_SHOW_UPDATE_FINISHED_EVENT = 1


class ShowQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self)
        self.queue_name = 'SHOWQUEUE'
        self.daily_update_running = False
        if not db.DBConnection().has_flag('kodi_nfo_uid'):
            self.add_event(DAILY_SHOW_UPDATE_FINISHED_EVENT, sickbeard.metadata.kodi.set_nfo_uid_updated)

    def check_events(self):
        if self.daily_update_running and \
                not (self.isShowUpdateRunning() or sickbeard.showUpdateScheduler.action.amActive):
            self.execute_events(DAILY_SHOW_UPDATE_FINISHED_EVENT)
            self.daily_update_running = False

    def _isInQueue(self, show_obj, actions):
        # type: (TVShow, tuple) -> bool
        """

        :param show_obj: show object
        :param actions:
        :return:
        """
        with self.lock:
            return show_obj in [x.show_obj for x in self.queue if x.action_id in actions]

    def _isBeingSomethinged(self, show_obj, actions):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param actions:
        :return:
        :rtype: bool
        """
        with self.lock:
            return None is not self.currentItem \
                   and show_obj == self.currentItem.show_obj \
                   and self.currentItem.action_id in actions

    def isInUpdateQueue(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isInQueue(show_obj, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE))

    def isInRefreshQueue(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isInQueue(show_obj, (ShowQueueActions.REFRESH,))

    def isInRenameQueue(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isInQueue(show_obj, (ShowQueueActions.RENAME,))

    def isInSubtitleQueue(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isInQueue(show_obj, (ShowQueueActions.SUBTITLE,))

    def isBeingAdded(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isBeingSomethinged(show_obj, (ShowQueueActions.ADD,))

    def isBeingUpdated(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isBeingSomethinged(show_obj, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE))

    def isBeingRefreshed(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isBeingSomethinged(show_obj, (ShowQueueActions.REFRESH,))

    def isBeingRenamed(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isBeingSomethinged(show_obj, (ShowQueueActions.RENAME,))

    def isBeingSubtitled(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        return self._isBeingSomethinged(show_obj, (ShowQueueActions.SUBTITLE,))

    def isShowUpdateRunning(self):
        """

        :return:
        :rtype: bool
        """
        with self.lock:
            for x in self.queue + [self.currentItem]:
                if isinstance(x, ShowQueueItem) and x.scheduled_update:
                    return True
            return False

    def _getLoadingShowList(self):
        """

        :return:
        :rtype: List
        """
        with self.lock:
            return [x for x in self.queue + [self.currentItem] if None is not x and x.isLoading]

    def queue_length(self):
        # type: (...) -> Dict[AnyStr, List[AnyStr, Dict]]
        """

        :return:
        """
        length = dict(add=[], update=[], forceupdate=[], forceupdateweb=[], refresh=[], rename=[], subtitle=[])
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:  # type: ShowQueueItem
                if not cur_item:
                    continue
                result_item = dict(name=cur_item.show_name, scheduled_update=cur_item.scheduled_update)
                if isinstance(cur_item, QueueItemAdd):
                    length['add'].append(result_item)
                else:
                    result_item.update(dict(
                        tvid=cur_item.show_obj.tvid,
                        prodid=cur_item.show_obj.prodid, tvid_prodid=cur_item.show_obj.tvid_prodid,
                        # legacy keys for api responses
                        indexer=cur_item.show_obj.tvid, indexerid=cur_item.show_obj.prodid))
                    if isinstance(cur_item, QueueItemUpdate):
                        update_type = 'Normal'
                        if isinstance(cur_item, QueueItemForceUpdate):
                            update_type = 'Forced'
                        elif isinstance(cur_item, QueueItemForceUpdateWeb):
                            update_type = 'Forced Web'
                        result_item.update(dict(update_type=update_type))
                        length['update'].append(result_item)
                    elif isinstance(cur_item, QueueItemRefresh):
                        length['refresh'].append(result_item)
                    elif isinstance(cur_item, QueueItemRename):
                        length['rename'].append(result_item)
                    elif isinstance(cur_item, QueueItemSubtitle):
                        length['subtitle'].append(result_item)
            return length

    loadingShowList = property(_getLoadingShowList)

    def updateShow(self, show_obj, force=False, web=False, scheduled_update=False,
                   priority=generic_queue.QueuePriorities.NORMAL, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param force:
        :type force: bool
        :param web:
        :type web: bool
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param kwargs:
        :return:
        :rtype: QueueItemUpdate or QueueItemForceUpdateWeb or QueueItemForceUpdate
        """
        if self.isBeingAdded(show_obj):
            raise exceptions_helper.CantUpdateException(
                'Show is still being added, wait until it is finished before you update.')

        if self.isBeingUpdated(show_obj):
            raise exceptions_helper.CantUpdateException(
                'This show is already being updated, can\'t update again until it\'s done.')

        if self.isInUpdateQueue(show_obj):
            raise exceptions_helper.CantUpdateException(
                'This show is already being updated, can\'t update again until it\'s done.')

        if not force:
            queue_item_obj = QueueItemUpdate(
                show_obj, scheduled_update=scheduled_update, **kwargs)
        elif web:
            queue_item_obj = QueueItemForceUpdateWeb(
                show_obj, scheduled_update=scheduled_update, priority=priority, **kwargs)
        else:
            queue_item_obj = QueueItemForceUpdate(
                show_obj, scheduled_update=scheduled_update, **kwargs)

        self.add_item(queue_item_obj)

        return queue_item_obj

    def refreshShow(self, show_obj, force=False, scheduled_update=False, after_update=False,
                    priority=generic_queue.QueuePriorities.HIGH, force_image_cache=False, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
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
        :param kwargs:
        :return:
        :rtype: QueueItemRefresh
        """
        if self.isBeingRefreshed(show_obj) and not force:
            raise exceptions_helper.CantRefreshException('This show is already being refreshed, not refreshing again.')

        if ((not after_update and self.isBeingUpdated(show_obj)) or self.isInUpdateQueue(show_obj)) and not force:
            logger.log('Skipping this refresh as there is already an update queued or'
                       ' in progress and a refresh is done at the end of an update anyway.', logger.DEBUG)
            return

        queue_item_obj = QueueItemRefresh(show_obj, force=force, scheduled_update=scheduled_update, priority=priority,
                                          force_image_cache=force_image_cache, **kwargs)

        self.add_item(queue_item_obj)

        return queue_item_obj

    def renameShowEpisodes(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: QueueItemRename
        """
        queue_item_obj = QueueItemRename(show_obj)

        self.add_item(queue_item_obj)

        return queue_item_obj

    def download_subtitles(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: QueueItemSubtitle
        """
        queue_item_obj = QueueItemSubtitle(show_obj)

        self.add_item(queue_item_obj)

        return queue_item_obj

    def addShow(self, tvid, prodid, show_dir, default_status=None, quality=None, flatten_folders=None,
                lang='en', subtitles=None, anime=None, scene=None, paused=None, blacklist=None, whitelist=None,
                wanted_begin=None, wanted_latest=None, prune=None, tag=None,
                new_show=False, show_name=None, upgrade_once=False):
        """

        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :param show_dir: show dir
        :type show_dir: AnyStr
        :param default_status:
        :type default_status: int or None
        :param quality:
        :type quality: None or int
        :param flatten_folders:
        :type flatten_folders: int or None
        :param lang:
        :type lang: AnyStr
        :param subtitles:
        :type subtitles: int or None
        :param anime:
        :type anime: int or None
        :param scene:
        :type scene: int or None
        :param paused:
        :type paused: None or int
        :param blacklist:
        :type blacklist: AnyStr or None
        :param whitelist:
        :type whitelist: AnyStr or None
        :param wanted_begin:
        :type wanted_begin: int or None
        :param wanted_latest:
        :type wanted_latest: int or None
        :param prune:
        :type prune: int or None
        :param tag:
        :type tag: AnyStr or None
        :param new_show:
        :type new_show: AnyStr or None
        :param show_name:
        :type show_name: AnyStr or None
        :param upgrade_once:
        :type upgrade_once: bool or None
        :return:
        :rtype: QueueItemAdd
        """
        queue_item_obj = QueueItemAdd(tvid, prodid, show_dir, default_status, quality, flatten_folders, lang,
                                      subtitles, anime, scene, paused, blacklist, whitelist,
                                      wanted_begin, wanted_latest, prune, tag,
                                      new_show=new_show, show_name=show_name, upgrade_once=upgrade_once)

        self.add_item(queue_item_obj)

        return queue_item_obj


class ShowQueueActions(object):
    REFRESH = 1
    ADD = 2
    UPDATE = 3
    FORCEUPDATE = 4
    RENAME = 5
    SUBTITLE = 6

    names = {REFRESH: 'Refresh',
             ADD: 'Add',
             UPDATE: 'Update',
             FORCEUPDATE: 'Force Update',
             RENAME: 'Rename',
             SUBTITLE: 'Subtitle'}


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

    def __init__(self, action_id, show_obj, scheduled_update=False):
        """

        :param action_id:
        :type action_id:
        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow or None
        :param scheduled_update:
        :type scheduled_update: bool
        """
        generic_queue.QueueItem.__init__(self, ShowQueueActions.names[action_id], action_id)
        self.show_obj = show_obj  # type: sickbeard.tv.TVShow
        self.scheduled_update = scheduled_update  # type: bool

    def isInQueue(self):
        """
        :rtype: bool
        """
        return self in sickbeard.showQueueScheduler.action.queue + [
            sickbeard.showQueueScheduler.action.currentItem]

    def _getName(self):
        """
        :rtype: AnyStr
        """
        if self.show_obj:
            return self.show_obj.name
        return ''

    def _isLoading(self):
        return False

    show_name = property(_getName)

    isLoading = property(_isLoading)


class QueueItemAdd(ShowQueueItem):
    def __init__(self, tvid, prodid, show_dir, default_status, quality, flatten_folders, lang, subtitles, anime,
                 scene, paused, blacklist, whitelist, default_wanted_begin, default_wanted_latest, prune, tag,
                 scheduled_update=False, new_show=False, show_name=None, upgrade_once=False):
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
        :param blacklist:
        :type blacklist:
        :param whitelist:
        :type whitelist:
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
        """
        self.tvid = tvid  # type: int
        self.prodid = prodid  # type: int
        self.showDir = show_dir  # type: AnyStr
        self.default_status = default_status
        self.default_wanted_begin = (0, default_wanted_begin)[isinstance(default_wanted_begin, integer_types)]
        self.default_wanted_latest = (0, default_wanted_latest)[isinstance(default_wanted_latest, integer_types)]
        self.quality = quality  # type: int
        self.upgrade_once = upgrade_once
        self.flatten_folders = flatten_folders
        self.lang = lang
        self.subtitles = subtitles
        self.anime = anime
        self.scene = scene
        self.paused = paused
        self.blacklist = blacklist
        self.whitelist = whitelist
        self.prune = prune
        self.tag = tag
        self.new_show = new_show
        self.showname = show_name  # type: AnyStr or None

        self.show_obj = None

        # this will initialize self.show_obj to None
        ShowQueueItem.__init__(self, ShowQueueActions.ADD, self.show_obj, scheduled_update)

        self.priority = generic_queue.QueuePriorities.VERYHIGH

    def _getName(self):
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

    show_name = property(_getName)

    def _isLoading(self):
        """
        :return: True if we've gotten far enough to have a show object, or False
        if we still only know the folder name.
        :rtype: bool
        """
        if None is self.show_obj:
            return True
        return False

    isLoading = property(_isLoading)

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
            latest_result = db_obj.select('SELECT MAX(season) AS latest_season FROM tv_episodes WHERE season > 0 '
                                          'AND indexer = ? AND showid = ? AND status != ?',
                                          [self.show_obj.tvid, self.show_obj.prodid, UNAIRED])
            if latest_result and None is not latest_result[0]['latest_season']:
                latest_season = int(latest_result[0]['latest_season'])
            else:
                process_sql = False

        if process_sql:
            if -1 == wanted_max:
                compare_op = ''  # equal, we only want the specific season
            else:
                compare_op = ('>', '<')[latest]  # less/more then equal season
            base_sql = 'SELECT indexerid, season, episode, status FROM tv_episodes WHERE indexer = ?' \
                       ' AND showid = ? AND season != 0 AND season %s= ? AND status != ?' \
                       ' ORDER BY season%s, episode%s%s' % \
                       (compare_op, ('', ' DESC')[latest], ('', ' DESC')[latest],
                        (' LIMIT ?', '')[-1 == wanted_max])

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
                    cur_status, cur_quality = Quality.splitCompositeStatus(int(sr['status']))
                    if sickbeard.WANTEDLIST_CACHE.get_wantedlist(
                            self.quality, self.upgrade_once, cur_quality, cur_status,
                            unaired=(sickbeard.SEARCH_UNAIRED and not sickbeard.UNAIRED_RECENT_SEARCH_ONLY)):
                        upgradable += 1

            if selected_ids:
                update = 'UPDATE [tv_episodes] SET status = ? WHERE indexer = ? AND indexerid IN (%s)' % \
                         ','.join(['?'] * len(selected_ids))
                db_obj.action(update, [WANTED, self.show_obj.tvid] + selected_ids)

                # noinspection SqlResolve
                result = db_obj.select('SELECT changes() as last FROM [tv_episodes]')

                for cur_result in result:
                    actual = cur_result['last']
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

            tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
            if self.lang:
                tvinfo_config['language'] = self.lang

            logger.log(u'' + str(sickbeard.TVInfoAPI(self.tvid).name) + ': ' + repr(tvinfo_config))

            t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
            s = t[self.prodid, False]

            if getattr(t, 'show_not_found', False):
                logger.log('Show %s was not found on %s, maybe show was deleted' %
                           (self.show_name, sickbeard.TVInfoAPI(self.tvid).name), logger.ERROR)
                self._finishEarly()
                return

            # this usually only happens if they have an NFO in their show dir
            # which gave us a TV info source ID that has no proper english version of the show
            if None is getattr(s, 'seriesname', None):
                logger.log('Show in %s has no name on %s, probably the wrong language used to search with.' %
                           (self.showDir, sickbeard.TVInfoAPI(self.tvid).name), logger.ERROR)
                ui.notifications.error('Unable to add show',
                                       'Show in %s has no name on %s, probably the wrong language.'
                                       ' Delete .nfo and add manually in the correct language.' %
                                       (self.showDir, sickbeard.TVInfoAPI(self.tvid).name))
                self._finishEarly()
                return
        except (BaseException, Exception):
            logger.log('Unable to find show ID:%s on TV info: %s' % (self.prodid, sickbeard.TVInfoAPI(self.tvid).name),
                       logger.ERROR)
            ui.notifications.error('Unable to add show',
                                   'Unable to look up the show in %s on %s using ID %s, not using the NFO.'
                                   ' Delete .nfo and try adding manually again.' %
                                   (self.showDir, sickbeard.TVInfoAPI(self.tvid).name, self.prodid))
            self._finishEarly()
            return

        try:
            new_show_obj = TVShow(self.tvid, self.prodid, self.lang)
            new_show_obj.load_from_tvinfo()

            self.show_obj = new_show_obj

            # set up initial values
            self.show_obj.location = self.showDir
            self.show_obj.subtitles = self.subtitles if None is not self.subtitles else sickbeard.SUBTITLES_DEFAULT
            self.show_obj.quality = self.quality if self.quality else sickbeard.QUALITY_DEFAULT
            self.show_obj.upgrade_once = self.upgrade_once
            self.show_obj.flatten_folders = self.flatten_folders if None is not self.flatten_folders \
                else sickbeard.FLATTEN_FOLDERS_DEFAULT
            self.show_obj.anime = self.anime if None is not self.anime else sickbeard.ANIME_DEFAULT
            self.show_obj.scene = self.scene if None is not self.scene else sickbeard.SCENE_DEFAULT
            self.show_obj.paused = self.paused if None is not self.paused else False
            self.show_obj.prune = self.prune if None is not self.prune else 0
            self.show_obj.tag = self.tag if None is not self.tag else 'Show List'

            if self.show_obj.anime:
                self.show_obj.release_groups = BlackAndWhiteList(self.show_obj.tvid,
                                                                 self.show_obj.prodid,
                                                                 self.show_obj.tvid_prodid)
                if self.blacklist:
                    self.show_obj.release_groups.set_black_keywords(self.blacklist)
                if self.whitelist:
                    self.show_obj.release_groups.set_white_keywords(self.whitelist)

            # be smartish about this
            if self.show_obj.genre and 'talk show' in self.show_obj.genre.lower():
                self.show_obj.air_by_date = 1
            if self.show_obj.genre and 'documentary' in self.show_obj.genre.lower():
                self.show_obj.air_by_date = 0
            if self.show_obj.classification and 'sports' in self.show_obj.classification.lower():
                self.show_obj.sports = 1

        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_exception):
                logger.log(
                    'Unable to add show due to an error with %s: %s' % (sickbeard.TVInfoAPI(self.tvid).name, ex(e)),
                    logger.ERROR)
                if self.show_obj:
                    ui.notifications.error('Unable to add %s due to an error with %s'
                                           % (self.show_obj.name, sickbeard.TVInfoAPI(self.tvid).name))
                else:
                    ui.notifications.error(
                        'Unable to add show due to an error with %s' % sickbeard.TVInfoAPI(self.tvid).name)
                self._finishEarly()
                return

            elif check_exception_type(e, exceptions_helper.MultipleShowObjectsException):
                logger.log('The show in %s is already in your show list, skipping' % self.showDir, logger.ERROR)
                ui.notifications.error('Show skipped', 'The show in %s is already in your show list' % self.showDir)
                self._finishEarly()
                return

            else:
                logger.log('Error trying to add show: %s' % ex(e), logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)
                self._finishEarly()
                raise

        self.show_obj.load_imdb_info()

        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            self._finishEarly()
            raise

        # add it to the show list
        sickbeard.showList.append(self.show_obj)

        try:
            self.show_obj.load_episodes_from_tvinfo()
        except (BaseException, Exception) as e:
            logger.log(
                'Error with %s, not creating episode list: %s' % (sickbeard.TVInfoAPI(self.show_obj.tvid).name, ex(e)),
                logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        try:
            self.show_obj.load_episodes_from_dir()
        except (BaseException, Exception) as e:
            logger.log('Error searching directory for episodes: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        # if they gave a custom status then change all the eps to it
        my_db = db.DBConnection()
        if self.default_status != SKIPPED:
            logger.log('Setting all episodes to the specified default status: %s'
                       % sickbeard.common.statusStrings[self.default_status])
            my_db.action('UPDATE tv_episodes'
                         ' SET status = ?'
                         ' WHERE status = ?'
                         ' AND indexer = ? AND showid = ?'
                         ' AND season != 0',
                         [self.default_status, SKIPPED,
                          self.show_obj.tvid, self.show_obj.prodid])

        items_wanted = self._get_wanted(my_db, self.default_wanted_begin, latest=False)
        items_wanted += self._get_wanted(my_db, self.default_wanted_latest, latest=True)

        self.show_obj.write_metadata()
        self.show_obj.update_metadata()
        self.show_obj.populate_cache()

        self.show_obj.flush_episodes()

        # load ids
        _ = self.show_obj.ids

        # if sickbeard.USE_TRAKT:
        #     # if there are specific episodes that need to be added by trakt
        #     sickbeard.traktCheckerScheduler.action.manageNewShow(self.show_obj)
        #
        #     # add show to trakt.tv library
        #     if sickbeard.TRAKT_SYNC:
        #         sickbeard.traktCheckerScheduler.action.addShowToTraktLibrary(self.show_obj)

        # Load XEM data to DB for show
        sickbeard.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid, force=True)
        if self.show_obj.scene:
            # enable/disable scene flag based on if show has an explicit _scene_ mapping at XEM
            self.show_obj.scene = sickbeard.scene_numbering.has_xem_scene_mapping(
                self.show_obj.tvid, self.show_obj.prodid)
        # if "scene" numbering is disabled during add show, output availability to log
        if None is not self.scene and not self.show_obj.scene and \
                self.show_obj.prodid in sickbeard.scene_exceptions.xem_ids_list[self.show_obj.tvid]:
            logger.log('No scene number mappings found at TheXEM. Therefore, episode scene numbering disabled, '
                       'edit show and enable it to manually add custom numbers for search and media processing.')
        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            self._finishEarly()
            raise

        # update internal name cache
        name_cache.buildNameCache(self.show_obj)

        self.show_obj.load_episodes_from_db()

        if self.show_obj.tvid in (TVINFO_TVRAGE, TVINFO_TVDB):
            # noinspection SqlResolve
            oh = my_db.select('SELECT resource FROM history WHERE indexer = 0 AND showid = ?', [self.show_obj.prodid])
            if oh:
                found = False
                for o in oh:
                    np = NameParser(file_name=True, indexer_lookup=False, try_scene_exceptions=True)
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
            sickbeard.backlogSearchScheduler.action.search_backlog([self.show_obj])
            ui.notifications.message('Show added/search', 'Adding and searching for episodes of' + msg)
        else:
            ui.notifications.message('Show added', 'Adding' + msg)

        self.finish()

    def _finishEarly(self):
        if None is not self.show_obj:
            self.show_obj.delete_show()

        if self.new_show:
            # if we adding a new show, delete the empty folder that was already created
            try:
                ek.ek(os.rmdir, self.showDir)
            except (BaseException, Exception):
                pass

        self.finish()


class QueueItemRefresh(ShowQueueItem):
    def __init__(self, show_obj=None, force=False, scheduled_update=False, priority=generic_queue.QueuePriorities.HIGH,
                 force_image_cache=False, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param force:
        :type force: bool
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param force_image_cache:
        :type force_image_cache: bool
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.REFRESH, show_obj, scheduled_update)

        # do refreshes first because they're quick
        self.priority = priority  # type: int

        # force refresh certain items
        self.force = force  # type: bool

        self.force_image_cache = force_image_cache  # type: bool

        self.kwargs = kwargs

    def run(self):
        ShowQueueItem.run(self)

        logger.log('Performing refresh on %s' % self.show_obj.name)

        self.show_obj.refresh_dir()
        self.show_obj.write_metadata(force=self.force)
        # if self.force:
        #    self.show_obj.update_metadata()
        self.show_obj.populate_cache(self.force_image_cache)

        # Load XEM data to DB for show
        if self.show_obj.prodid in sickbeard.scene_exceptions.xem_ids_list[self.show_obj.tvid]:
            sickbeard.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid)

        if 'pausestatus_after' in self.kwargs and None is not self.kwargs['pausestatus_after']:
            self.show_obj.paused = self.kwargs['pausestatus_after']
        self.inProgress = False


class QueueItemRename(ShowQueueItem):
    def __init__(self, show_obj=None, scheduled_update=False):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        """
        ShowQueueItem.__init__(self, ShowQueueActions.RENAME, show_obj, scheduled_update)

    def run(self):

        ShowQueueItem.run(self)

        logger.log('Performing rename on %s' % self.show_obj.name)

        try:
            _ = self.show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            logger.log('Can\'t perform rename on %s when the show directory is missing.'
                       % self.show_obj.name, logger.WARNING)
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
    def __init__(self, show_obj=None, scheduled_update=False):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        """
        ShowQueueItem.__init__(self, ShowQueueActions.SUBTITLE, show_obj, scheduled_update)

    def run(self):
        ShowQueueItem.run(self)

        logger.log('Downloading subtitles for %s' % self.show_obj.name)

        self.show_obj.download_subtitles()

        self.inProgress = False


class QueueItemUpdate(ShowQueueItem):
    def __init__(self, show_obj=None, scheduled_update=False, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.UPDATE, show_obj, scheduled_update)
        self.force = False  # type: bool
        self.force_web = False  # type: bool
        self.kwargs = kwargs

    def run(self):

        ShowQueueItem.run(self)
        last_update = datetime.date.fromordinal(self.show_obj.last_update_indexer)

        if not sickbeard.TVInfoAPI(self.show_obj.tvid).config['active']:
            logger.log('TV info source %s is marked inactive, aborting update for show %s and continue with refresh.'
                       % (sickbeard.TVInfoAPI(self.show_obj.tvid).config['name'], self.show_obj.name))
            sickbeard.showQueueScheduler.action.refreshShow(self.show_obj, self.force, self.scheduled_update,
                                                            after_update=True)
            return

        logger.log('Beginning update of %s' % self.show_obj.name)

        logger.log('Retrieving show info from %s' % sickbeard.TVInfoAPI(self.show_obj.tvid).name, logger.DEBUG)
        try:
            result = self.show_obj.load_from_tvinfo(cache=not self.force)
            if None is not result:
                return
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log('Unable to contact %s, aborting: %s' % (sickbeard.TVInfoAPI(self.show_obj.tvid).name, ex(e)),
                           logger.WARNING)
                return
            elif check_exception_type(e, ExceptionTuples.tvinfo_attributenotfound):
                logger.log('Data retrieved from %s was incomplete, aborting: %s' %
                           (sickbeard.TVInfoAPI(self.show_obj.tvid).name, ex(e)), logger.ERROR)
                return
            else:
                raise e

        if self.force_web:
            self.show_obj.load_imdb_info()

        try:
            self.show_obj.save_to_db()
        except (BaseException, Exception) as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        # get episode list from DB
        logger.log('Loading all episodes from the database', logger.DEBUG)
        db_ep_obj_list = self.show_obj.load_episodes_from_db(update=True)

        # get episode list from TVDB
        logger.log('Loading all episodes from %s' % sickbeard.TVInfoAPI(self.show_obj.tvid).name, logger.DEBUG)
        try:
            tvinfo_ep_list = self.show_obj.load_episodes_from_tvinfo(cache=not self.force, update=True)
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_exception):
                logger.log('Unable to get info from %s, the show info will not be refreshed: %s' %
                           (sickbeard.TVInfoAPI(self.show_obj.tvid).name, ex(e)), logger.ERROR)
                tvinfo_ep_list = None
            else:
                raise e

        if None is tvinfo_ep_list:
            logger.log('No data returned from %s, unable to update episodes for show: %s' %
                       (sickbeard.TVInfoAPI(self.show_obj.tvid).name, self.show_obj.name), logger.ERROR)
        elif not tvinfo_ep_list or 0 == len(tvinfo_ep_list):
            logger.log('No episodes returned from %s for show: %s' %
                       (sickbeard.TVInfoAPI(self.show_obj.tvid).name, self.show_obj.name), logger.WARNING)
        else:
            # for each ep we found on TVDB delete it from the DB list
            for cur_season in tvinfo_ep_list:
                for cur_episode in tvinfo_ep_list[cur_season]:
                    logger.log('Removing %sx%s from the DB list' % (cur_season, cur_episode), logger.DEBUG)
                    if cur_season in db_ep_obj_list and cur_episode in db_ep_obj_list[cur_season]:
                        del db_ep_obj_list[cur_season][cur_episode]

            # for the remaining episodes in the DB list just delete them from the DB
            for cur_season in db_ep_obj_list:
                for cur_episode in db_ep_obj_list[cur_season]:
                    ep_obj = self.show_obj.get_episode(cur_season, cur_episode)
                    status = sickbeard.common.Quality.splitCompositeStatus(ep_obj.status)[0]
                    if should_delete_episode(status):
                        logger.log('Permanently deleting episode %sx%s from the database' %
                                   (cur_season, cur_episode), logger.MESSAGE)
                        try:
                            ep_obj.delete_episode()
                        except exceptions_helper.EpisodeDeletedException:
                            pass
                    else:
                        logger.log('Not deleting episode %sx%s from the database because status is: %s' %
                                   (cur_season, cur_episode, statusStrings[status]), logger.MESSAGE)

            # update indexer mapper once a month (using the day of the first ep as random date)
            update_over_month = (datetime.date.today() - last_update).days > 31
            if (self.scheduled_update or update_over_month) and tvinfo_ep_list.get(1, {}).get(1, False):
                first_ep_airdate = self.show_obj.get_episode(1, 1, no_create=True).airdate
                day = (first_ep_airdate.day, 28)[28 < first_ep_airdate.day]
                if datetime.date.today().day == day or update_over_month or \
                        -8 < (datetime.date.today() - first_ep_airdate).days < 31:
                    map_indexers_to_show(self.show_obj, force=True)

        if self.priority != generic_queue.QueuePriorities.NORMAL:
            self.kwargs['priority'] = self.priority
        sickbeard.showQueueScheduler.action.refreshShow(self.show_obj, self.force, self.scheduled_update,
                                                        after_update=True, force_image_cache=self.force_web,
                                                        **self.kwargs)


class QueueItemForceUpdate(QueueItemUpdate):
    def __init__(self, show_obj=None, scheduled_update=False, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.FORCEUPDATE, show_obj, scheduled_update)
        self.force = True  # type: bool
        self.force_web = False  # type: bool
        self.kwargs = kwargs


class QueueItemForceUpdateWeb(QueueItemUpdate):
    def __init__(self, show_obj=None, scheduled_update=False, priority=generic_queue.QueuePriorities.NORMAL, **kwargs):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :param scheduled_update:
        :type scheduled_update: bool
        :param priority:
        :type priority: int
        :param kwargs:
        """
        ShowQueueItem.__init__(self, ShowQueueActions.FORCEUPDATE, show_obj, scheduled_update)
        self.force = True  # type: bool
        self.force_web = True  # type: bool
        self.priority = priority  # type: int
        self.kwargs = kwargs
