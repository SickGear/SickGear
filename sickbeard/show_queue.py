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
import os

import sickbeard

from sickbeard.common import SKIPPED, WANTED, UNAIRED, statusStrings
from sickbeard.tv import TVShow
from sickbeard import exceptions, logger, ui, db
from sickbeard import generic_queue
from sickbeard import name_cache
from sickbeard.exceptions import ex
from sickbeard.helpers import should_delete_episode
from sickbeard.blackandwhitelist import BlackAndWhiteList
from sickbeard import encodingKludge as ek


class ShowQueue(generic_queue.GenericQueue):
    def __init__(self):
        generic_queue.GenericQueue.__init__(self)
        self.queue_name = 'SHOWQUEUE'

    def _isInQueue(self, show, actions):
        with self.lock:
            return show in [x.show for x in self.queue if x.action_id in actions]

    def _isBeingSomethinged(self, show, actions):
        with self.lock:
            return self.currentItem != None and show == self.currentItem.show and \
                   self.currentItem.action_id in actions

    def isInUpdateQueue(self, show):
        return self._isInQueue(show, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE))

    def isInRefreshQueue(self, show):
        return self._isInQueue(show, (ShowQueueActions.REFRESH,))

    def isInRenameQueue(self, show):
        return self._isInQueue(show, (ShowQueueActions.RENAME,))

    def isInSubtitleQueue(self, show):
        return self._isInQueue(show, (ShowQueueActions.SUBTITLE,))

    def isBeingAdded(self, show):
        return self._isBeingSomethinged(show, (ShowQueueActions.ADD,))

    def isBeingUpdated(self, show):
        return self._isBeingSomethinged(show, (ShowQueueActions.UPDATE, ShowQueueActions.FORCEUPDATE))

    def isBeingRefreshed(self, show):
        return self._isBeingSomethinged(show, (ShowQueueActions.REFRESH,))

    def isBeingRenamed(self, show):
        return self._isBeingSomethinged(show, (ShowQueueActions.RENAME,))

    def isBeingSubtitled(self, show):
        return self._isBeingSomethinged(show, (ShowQueueActions.SUBTITLE,))

    def isShowUpdateRunning(self):
        with self.lock:
            for x in self.queue + [self.currentItem]:
                if isinstance(x, ShowQueueItem) and x.scheduled_update:
                    return True
            return False

    def _getLoadingShowList(self):
        with self.lock:
            return [x for x in self.queue + [self.currentItem] if x != None and x.isLoading]

    def queue_length(self):
        length = {'add': [], 'update': [], 'forceupdate': [], 'forceupdateweb': [], 'refresh': [], 'rename': [], 'subtitle': []}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:
                if isinstance(cur_item, QueueItemAdd):
                    length['add'].append({'name': cur_item.show_name, 'scheduled_update': cur_item.scheduled_update})
                elif isinstance(cur_item, QueueItemUpdate):
                    update_type = 'Normal'
                    if isinstance(cur_item, QueueItemForceUpdate):
                        update_type = 'Forced'
                    elif isinstance(cur_item, QueueItemForceUpdateWeb):
                        update_type = 'Forced Web'
                    length['update'].append({'name': cur_item.show_name, 'indexerid': cur_item.show.indexerid,
                                             'indexer': cur_item.show.indexer, 'scheduled_update': cur_item.scheduled_update,
                                             'update_type': update_type})
                elif isinstance(cur_item, QueueItemRefresh):
                    length['refresh'].append({'name': cur_item.show_name, 'indexerid': cur_item.show.indexerid,
                                             'indexer': cur_item.show.indexer, 'scheduled_update': cur_item.scheduled_update})
                elif isinstance(cur_item, QueueItemRename):
                    length['rename'].append({'name': cur_item.show_name, 'indexerid': cur_item.show.indexerid,
                                             'indexer': cur_item.show.indexer, 'scheduled_update': cur_item.scheduled_update})
                elif isinstance(cur_item, QueueItemSubtitle):
                    length['subtitle'].append({'name': cur_item.show_name, 'indexerid': cur_item.show.indexerid,
                                             'indexer': cur_item.show.indexer, 'scheduled_update': cur_item.scheduled_update})
            return length

    loadingShowList = property(_getLoadingShowList)

    def updateShow(self, show, force=False, web=False, scheduled_update=False,
                   priority=generic_queue.QueuePriorities.NORMAL, **kwargs):

        if self.isBeingAdded(show):
            raise exceptions.CantUpdateException(
                'Show is still being added, wait until it is finished before you update.')

        if self.isBeingUpdated(show):
            raise exceptions.CantUpdateException(
                'This show is already being updated, can\'t update again until it\'s done.')

        if self.isInUpdateQueue(show):
            raise exceptions.CantUpdateException(
                'This show is already being updated, can\'t update again until it\'s done.')

        if not force:
            queueItemObj = QueueItemUpdate(show, scheduled_update=scheduled_update, **kwargs)
        elif web:
            queueItemObj = QueueItemForceUpdateWeb(show, scheduled_update=scheduled_update, priority=priority, **kwargs)
        else:
            queueItemObj = QueueItemForceUpdate(show, scheduled_update=scheduled_update, **kwargs)

        self.add_item(queueItemObj)

        return queueItemObj

    def refreshShow(self, show, force=False, scheduled_update=False, after_update=False,
                    priority=generic_queue.QueuePriorities.HIGH, force_image_cache=False, **kwargs):

        if self.isBeingRefreshed(show) and not force:
            raise exceptions.CantRefreshException('This show is already being refreshed, not refreshing again.')

        if ((not after_update and self.isBeingUpdated(show)) or self.isInUpdateQueue(show)) and not force:
            logger.log(
                'Skipping this refresh as there is already an update queued or in progress and a refresh is done at the end of an update anyway.',
                logger.DEBUG)
            return

        queueItemObj = QueueItemRefresh(show, force=force, scheduled_update=scheduled_update, priority=priority,
                                        force_image_cache=force_image_cache, **kwargs)

        self.add_item(queueItemObj)

        return queueItemObj

    def renameShowEpisodes(self, show, force=False):

        queueItemObj = QueueItemRename(show)

        self.add_item(queueItemObj)

        return queueItemObj

    def downloadSubtitles(self, show, force=False):

        queueItemObj = QueueItemSubtitle(show)

        self.add_item(queueItemObj)

        return queueItemObj

    def addShow(self, indexer, indexer_id, showDir, default_status=None, quality=None, flatten_folders=None,
                lang='en', subtitles=None, anime=None, scene=None, paused=None, blacklist=None, whitelist=None,
                wanted_begin=None, wanted_latest=None, prune=None, tag=None,
                new_show=False, show_name=None, upgrade_once=False):
        queueItemObj = QueueItemAdd(indexer, indexer_id, showDir, default_status, quality, flatten_folders, lang,
                                    subtitles, anime, scene, paused, blacklist, whitelist,
                                    wanted_begin, wanted_latest, prune, tag,
                                    new_show=new_show, show_name=show_name, upgrade_once=upgrade_once)

        self.add_item(queueItemObj)

        return queueItemObj


class ShowQueueActions:
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

    def __init__(self, action_id, show, scheduled_update=False):
        generic_queue.QueueItem.__init__(self, ShowQueueActions.names[action_id], action_id)
        self.show = show
        self.scheduled_update = scheduled_update

    def isInQueue(self):
        return self in sickbeard.showQueueScheduler.action.queue + [
            sickbeard.showQueueScheduler.action.currentItem]  #@UndefinedVariable

    def _getName(self):
        return str(self.show.indexerid)

    def _isLoading(self):
        return False

    show_name = property(_getName)

    isLoading = property(_isLoading)


class QueueItemAdd(ShowQueueItem):
    def __init__(self, indexer, indexer_id, showDir, default_status, quality, flatten_folders, lang, subtitles, anime,
                 scene, paused, blacklist, whitelist, default_wanted_begin, default_wanted_latest, prune, tag,
                 scheduled_update=False, new_show=False, show_name=None, upgrade_once=False):

        self.indexer = indexer
        self.indexer_id = indexer_id
        self.showDir = showDir
        self.default_status = default_status
        self.default_wanted_begin = default_wanted_begin
        self.default_wanted_latest = default_wanted_latest
        self.quality = quality
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
        self.showname = show_name

        self.show = None

        # this will initialize self.show to None
        ShowQueueItem.__init__(self, ShowQueueActions.ADD, self.show, scheduled_update)

        self.priority = generic_queue.QueuePriorities.VERYHIGH

    def _getName(self):
        """
        Returns the show name if there is a show object created, if not returns
        the dir that the show is being added to.
        """
        if None is not self.showname:
            return self.showname
        if None is self.show:
            return self.showDir
        return self.show.name

    show_name = property(_getName)

    def _isLoading(self):
        """
        Returns True if we've gotten far enough to have a show object, or False
        if we still only know the folder name.
        """
        if self.show == None:
            return True
        return False

    isLoading = property(_isLoading)

    def run(self):

        ShowQueueItem.run(self)

        logger.log('Starting to add show %s' % self.showDir)
        # make sure the Indexer IDs are valid
        try:

            lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()
            if self.lang:
                lINDEXER_API_PARMS['language'] = self.lang

            logger.log(u'' + str(sickbeard.indexerApi(self.indexer).name) + ': ' + repr(lINDEXER_API_PARMS))

            t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)
            s = t[self.indexer_id, False]

            if getattr(t, 'show_not_found', False):
                logger.log('Show %s was not found on %s, maybe show was deleted' %
                           (self.show_name, sickbeard.indexerApi(self.indexer).name), logger.ERROR)
                self._finishEarly()
                return

            # this usually only happens if they have an NFO in their show dir which gave us a Indexer ID that has no proper english version of the show
            if getattr(s, 'seriesname', None) is None:
                logger.log('Show in %s has no name on %s, probably the wrong language used to search with.' %
                           (self.showDir, sickbeard.indexerApi(self.indexer).name), logger.ERROR)
                ui.notifications.error('Unable to add show',
                                       'Show in %s has no name on %s, probably the wrong language. Delete .nfo and add manually in the correct language.' %
                                       (self.showDir, sickbeard.indexerApi(self.indexer).name))
                self._finishEarly()
                return
        except Exception as e:
            logger.log('Unable to find show ID:%s on Indexer: %s' % (self.indexer_id, sickbeard.indexerApi(self.indexer).name),
                       logger.ERROR)
            ui.notifications.error('Unable to add show',
                                   'Unable to look up the show in %s on %s using ID %s, not using the NFO. Delete .nfo and try adding manually again.' %
                                   (self.showDir, sickbeard.indexerApi(self.indexer).name, self.indexer_id))
            self._finishEarly()
            return

        try:
            newShow = TVShow(self.indexer, self.indexer_id, self.lang)
            newShow.loadFromIndexer()

            self.show = newShow

            # set up initial values
            self.show.location = self.showDir
            self.show.subtitles = self.subtitles if None is not self.subtitles else sickbeard.SUBTITLES_DEFAULT
            self.show.quality = self.quality if self.quality else sickbeard.QUALITY_DEFAULT
            self.show.upgrade_once = self.upgrade_once
            self.show.flatten_folders = self.flatten_folders if None is not self.flatten_folders else sickbeard.FLATTEN_FOLDERS_DEFAULT
            self.show.anime = self.anime if None is not self.anime else sickbeard.ANIME_DEFAULT
            self.show.scene = self.scene if None is not self.scene else sickbeard.SCENE_DEFAULT
            self.show.paused = self.paused if None is not self.paused else False
            self.show.prune = self.prune if None is not self.prune else 0
            self.show.tag = self.tag if None is not self.tag else 'Show List'

            if self.show.anime:
                self.show.release_groups = BlackAndWhiteList(self.show.indexerid)
                if self.blacklist:
                    self.show.release_groups.set_black_keywords(self.blacklist)
                if self.whitelist:
                    self.show.release_groups.set_white_keywords(self.whitelist)

            # be smartish about this
            if self.show.genre and 'talk show' in self.show.genre.lower():
                self.show.air_by_date = 1
            if self.show.genre and 'documentary' in self.show.genre.lower():
                self.show.air_by_date = 0
            if self.show.classification and 'sports' in self.show.classification.lower():
                self.show.sports = 1

        except sickbeard.indexer_exception as e:
            logger.log(
                'Unable to add show due to an error with %s: %s' % (sickbeard.indexerApi(self.indexer).name, ex(e)),
                logger.ERROR)
            if self.show:
                ui.notifications.error(
                    'Unable to add %s due to an error with %s' % (self.show.name, sickbeard.indexerApi(self.indexer).name))
            else:
                ui.notifications.error(
                    'Unable to add show due to an error with %s' % sickbeard.indexerApi(self.indexer).name)
            self._finishEarly()
            return

        except exceptions.MultipleShowObjectsException:
            logger.log('The show in %s is already in your show list, skipping' % self.showDir, logger.ERROR)
            ui.notifications.error('Show skipped', 'The show in %s is already in your show list' % self.showDir)
            self._finishEarly()
            return

        except Exception as e:
            logger.log('Error trying to add show: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            self._finishEarly()
            raise

        self.show.load_imdb_info()

        try:
            self.show.saveToDB()
        except Exception as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            self._finishEarly()
            raise

        # add it to the show list
        sickbeard.showList.append(self.show)

        try:
            self.show.loadEpisodesFromIndexer()
        except Exception as e:
            logger.log(
                'Error with %s, not creating episode list: %s' % (sickbeard.indexerApi(self.show.indexer).name, ex(e)),
                logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        try:
            self.show.loadEpisodesFromDir()
        except Exception as e:
            logger.log('Error searching directory for episodes: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        # if they gave a custom status then change all the eps to it
        my_db = db.DBConnection()
        if self.default_status != SKIPPED:
            logger.log('Setting all episodes to the specified default status: %s' % sickbeard.common.statusStrings[self.default_status])
            my_db.action('UPDATE tv_episodes SET status = ? WHERE status = ? AND showid = ? AND season != 0',
                        [self.default_status, SKIPPED, self.show.indexerid])

        # if they gave a number to start or number to end as wanted, then change those eps to it
        def get_wanted(db_obj, wanted_max, latest):
            actual = 0
            if wanted_max:
                select_id = 'FROM [tv_episodes] t5 JOIN (SELECT t3.indexerid, t3.status, t3.season*1000000+t3.episode AS t3_se, t2.start_season FROM [tv_episodes] t3'\
                            + ' JOIN (SELECT t1.showid, M%s(t1.season) AS start_season' % ('IN', 'AX')[latest]\
                            + ', MAX(t1.airdate) AS airdate, t1.episode, t1.season*1000000+t1.episode AS se FROM [tv_episodes] t1'\
                            + ' WHERE %s=t1.showid' % self.show.indexerid\
                            + ' AND 0<t1.season AND t1.status NOT IN (%s)) AS t2' % UNAIRED\
                            + ' ON t2.showid=t3.showid AND 0<t3.season AND t2.se>=t3_se ORDER BY t3_se %sSC' % ('A', 'DE')[latest]\
                            + ' %s) as t4' % (' LIMIT %s' % wanted_max, '')[-1 == wanted_max]\
                            + ' ON t4.indexerid=t5.indexerid'\
                            + '%s' % ('', ' AND t4.start_season=t5.season')[-1 == wanted_max]\
                            + ' AND t4.status NOT IN (%s)' % ','.join([str(x) for x in sickbeard.common.Quality.DOWNLOADED + [WANTED]])
                select = 'SELECT t5.indexerid as indexerid, t5.season as season, t5.episode as episode, t5.status as status ' + select_id
                update = 'UPDATE [tv_episodes] SET status=%s WHERE indexerid IN (SELECT t5.indexerid %s)' % (WANTED, select_id)

                wanted_updates = db_obj.select(select)
                db_obj.action(update)
                result = db_obj.select('SELECT changes() as last FROM [tv_episodes]')
                for cur_result in result:
                    actual = cur_result['last']
                    break

                action_log = 'didn\'t find any episodes that need to be set wanted'
                if actual:
                    action_log = ('updated %s %s episodes > %s'
                                  % ((((('%s of %s' % (actual, wanted_max)), ('%s of max %s limited' % (actual, wanted_max)))[10 == wanted_max]), ('max %s available' % actual))[-1 == wanted_max],
                                     ('first season', 'latest')[latest],
                                     ','.join([('S%02dE%02d=%d' % (a['season'], a['episode'], a['status'])) for a in wanted_updates])))
                logger.log('Get wanted ' + action_log)
            return actual

        items_wanted = get_wanted(my_db, self.default_wanted_begin, latest=False)
        items_wanted += get_wanted(my_db, self.default_wanted_latest, latest=True)

        self.show.writeMetadata()
        self.show.updateMetadata()
        self.show.populateCache()

        self.show.flushEpisodes()

        # load ids
        self.show.ids

        # if sickbeard.USE_TRAKT:
        #     # if there are specific episodes that need to be added by trakt
        #     sickbeard.traktCheckerScheduler.action.manageNewShow(self.show)
        #
        #     # add show to trakt.tv library
        #     if sickbeard.TRAKT_SYNC:
        #         sickbeard.traktCheckerScheduler.action.addShowToTraktLibrary(self.show)

        # Load XEM data to DB for show
        sickbeard.scene_numbering.xem_refresh(self.show.indexerid, self.show.indexer, force=True)
        if self.show.scene:
            # enable/disable scene flag based on if show has an explicit _scene_ mapping at XEM
            self.show.scene = sickbeard.scene_numbering.has_xem_scene_mapping(
                self.show.indexerid, self.show.indexer)
        # if "scene" numbering is disabled during add show, output availability to log
        if None is not self.scene and not self.show.scene and \
                self.show.indexerid in sickbeard.scene_exceptions.xem_ids_list[self.show.indexer]:
            logger.log('No scene number mappings found at TheXEM. Therefore, episode scene numbering disabled, '
                       'edit show and enable it to manually add custom numbers for search and media processing.')
        try:
            self.show.saveToDB()
        except Exception as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)
            self._finishEarly()
            raise

        # update internal name cache
        name_cache.buildNameCache(self.show)

        self.show.loadEpisodesFromDB()

        msg = ' the specified show into ' + self.showDir
        # if started with WANTED eps then run the backlog
        if WANTED == self.default_status or items_wanted:
            logger.log('Launching backlog for this show since episodes are WANTED')
            sickbeard.backlogSearchScheduler.action.search_backlog([self.show])  #@UndefinedVariable
            ui.notifications.message('Show added/search', 'Adding and searching for episodes of' + msg)
        else:
            ui.notifications.message('Show added', 'Adding' + msg)

        self.finish()

    def _finishEarly(self):
        if self.show is not None:
            self.show.deleteShow()

        if self.new_show:
            # if we adding a new show, delete the empty folder that was already created
            try:
                ek.ek(os.rmdir, self.showDir)
            except (StandardError, Exception):
                pass

        self.finish()


class QueueItemRefresh(ShowQueueItem):
    def __init__(self, show=None, force=False, scheduled_update=False, priority=generic_queue.QueuePriorities.HIGH,
                 force_image_cache=False, **kwargs):
        ShowQueueItem.__init__(self, ShowQueueActions.REFRESH, show, scheduled_update)

        # do refreshes first because they're quick
        self.priority = priority

        # force refresh certain items
        self.force = force

        self.force_image_cache = force_image_cache

        self.kwargs = kwargs

    def run(self):
        ShowQueueItem.run(self)

        logger.log('Performing refresh on %s' % self.show.name)

        self.show.refreshDir()
        self.show.writeMetadata()
        #if self.force:
        #    self.show.updateMetadata()
        self.show.populateCache(self.force_image_cache)

        # Load XEM data to DB for show
        if self.show.indexerid in sickbeard.scene_exceptions.xem_ids_list[self.show.indexer]:
            sickbeard.scene_numbering.xem_refresh(self.show.indexerid, self.show.indexer)

        if 'pausestatus_after' in self.kwargs and self.kwargs['pausestatus_after'] is not None:
            self.show.paused = self.kwargs['pausestatus_after']
        self.inProgress = False


class QueueItemRename(ShowQueueItem):
    def __init__(self, show=None, scheduled_update=False):
        ShowQueueItem.__init__(self, ShowQueueActions.RENAME, show, scheduled_update)

    def run(self):

        ShowQueueItem.run(self)

        logger.log('Performing rename on %s' % self.show.name)

        try:
            show_loc = self.show.location
        except exceptions.ShowDirNotFoundException:
            logger.log('Can\'t perform rename on %s when the show directory is missing.' % self.show.name, logger.WARNING)
            return

        ep_obj_rename_list = []

        ep_obj_list = self.show.getAllEpisodes(has_location=True)
        for cur_ep_obj in ep_obj_list:
            # Only want to rename if we have a location
            if cur_ep_obj.location:
                if cur_ep_obj.relatedEps:
                    # do we have one of multi-episodes in the rename list already
                    have_already = False
                    for cur_related_ep in cur_ep_obj.relatedEps + [cur_ep_obj]:
                        if cur_related_ep in ep_obj_rename_list:
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
    def __init__(self, show=None, scheduled_update=False):
        ShowQueueItem.__init__(self, ShowQueueActions.SUBTITLE, show, scheduled_update)

    def run(self):
        ShowQueueItem.run(self)

        logger.log('Downloading subtitles for %s' % self.show.name)

        self.show.downloadSubtitles()

        self.inProgress = False


class QueueItemUpdate(ShowQueueItem):
    def __init__(self, show=None, scheduled_update=False, **kwargs):
        ShowQueueItem.__init__(self, ShowQueueActions.UPDATE, show, scheduled_update)
        self.force = False
        self.force_web = False
        self.kwargs = kwargs

    def run(self):

        ShowQueueItem.run(self)

        if not sickbeard.indexerApi(self.show.indexer).config['active']:
            logger.log('Indexer %s is marked inactive, aborting update for show %s and continue with refresh.' % (sickbeard.indexerApi(self.show.indexer).config['name'], self.show.name))
            sickbeard.showQueueScheduler.action.refreshShow(self.show, self.force, self.scheduled_update, after_update=True)
            return

        logger.log('Beginning update of %s' % self.show.name)

        logger.log('Retrieving show info from %s' % sickbeard.indexerApi(self.show.indexer).name, logger.DEBUG)
        try:
            result = self.show.loadFromIndexer(cache=not self.force)
            if None is not result:
                return
        except sickbeard.indexer_error as e:
            logger.log('Unable to contact %s, aborting: %s' % (sickbeard.indexerApi(self.show.indexer).name, ex(e)),
                       logger.WARNING)
            return
        except sickbeard.indexer_attributenotfound as e:
            logger.log('Data retrieved from %s was incomplete, aborting: %s' %
                       (sickbeard.indexerApi(self.show.indexer).name, ex(e)), logger.ERROR)
            return

        if self.force_web:
            self.show.load_imdb_info()

        try:
            self.show.saveToDB()
        except Exception as e:
            logger.log('Error saving the show to the database: %s' % ex(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.ERROR)

        # get episode list from DB
        logger.log('Loading all episodes from the database', logger.DEBUG)
        DBEpList = self.show.loadEpisodesFromDB(update=True)

        # get episode list from TVDB
        logger.log('Loading all episodes from %s' % sickbeard.indexerApi(self.show.indexer).name, logger.DEBUG)
        try:
            IndexerEpList = self.show.loadEpisodesFromIndexer(cache=not self.force, update=True)
        except sickbeard.indexer_exception as e:
            logger.log('Unable to get info from %s, the show info will not be refreshed: %s' %
                       (sickbeard.indexerApi(self.show.indexer).name, ex(e)), logger.ERROR)
            IndexerEpList = None

        if None is IndexerEpList:
            logger.log('No data returned from %s, unable to update episodes for show: %s' %
                       (sickbeard.indexerApi(self.show.indexer).name, self.show.name), logger.ERROR)
        elif not IndexerEpList or 0 == len(IndexerEpList):
            logger.log('No episodes returned from %s for show: %s' %
                       (sickbeard.indexerApi(self.show.indexer).name, self.show.name), logger.WARNING)
        else:
            # for each ep we found on TVDB delete it from the DB list
            for curSeason in IndexerEpList:
                for curEpisode in IndexerEpList[curSeason]:
                    logger.log('Removing %sx%s from the DB list' % (curSeason, curEpisode), logger.DEBUG)
                    if curSeason in DBEpList and curEpisode in DBEpList[curSeason]:
                        del DBEpList[curSeason][curEpisode]

            # for the remaining episodes in the DB list just delete them from the DB
            for curSeason in DBEpList:
                for curEpisode in DBEpList[curSeason]:
                    curEp = self.show.getEpisode(curSeason, curEpisode)
                    status = sickbeard.common.Quality.splitCompositeStatus(curEp.status)[0]
                    if should_delete_episode(status):
                        logger.log('Permanently deleting episode %sx%s from the database' %
                                   (curSeason, curEpisode), logger.MESSAGE)
                        try:
                            curEp.deleteEpisode()
                        except exceptions.EpisodeDeletedException:
                            pass
                    else:
                        logger.log('Not deleting episode %sx%s from the database because status is: %s' %
                                   (curSeason, curEpisode, statusStrings[status]), logger.MESSAGE)

        if self.priority != generic_queue.QueuePriorities.NORMAL:
            self.kwargs['priority'] = self.priority
        sickbeard.showQueueScheduler.action.refreshShow(self.show, self.force, self.scheduled_update, after_update=True,
                                                        force_image_cache=self.force_web, **self.kwargs)


class QueueItemForceUpdate(QueueItemUpdate):
    def __init__(self, show=None, scheduled_update=False, **kwargs):
        ShowQueueItem.__init__(self, ShowQueueActions.FORCEUPDATE, show, scheduled_update)
        self.force = True
        self.force_web = False
        self.kwargs = kwargs


class QueueItemForceUpdateWeb(QueueItemUpdate):
    def __init__(self, show=None, scheduled_update=False, priority=generic_queue.QueuePriorities.NORMAL, **kwargs):
        ShowQueueItem.__init__(self, ShowQueueActions.FORCEUPDATE, show, scheduled_update)
        self.force = True
        self.force_web = True
        self.priority = priority
        self.kwargs = kwargs
