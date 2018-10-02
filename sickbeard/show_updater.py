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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import traceback

import sickbeard
from sickbeard import logger, exceptions, ui, db, network_timezones, failed_history, properFinder
from sickbeard.exceptions import ex


class ShowUpdater:
    def __init__(self):
        self.amActive = False

    def run(self, force=False):

        self.amActive = True

        try:
            update_datetime = datetime.datetime.now()
            update_date = update_datetime.date()

            # refresh network timezones
            try:
                network_timezones.update_network_dict()
            except Exception:
                logger.log('network timezone update error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # refresh webdl types
            try:
                properFinder.load_webdl_types()
            except (StandardError, Exception):
                logger.log('error loading webdl_types', logger.DEBUG)

            # update xem id lists
            try:
                sickbeard.scene_exceptions.get_xem_ids()
            except Exception:
                logger.log('xem id list update error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # update scene exceptions
            try:
                sickbeard.scene_exceptions.retrieve_exceptions()
            except Exception:
                logger.log('scene exceptions update error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # sure, why not?
            if sickbeard.USE_FAILED_DOWNLOADS:
                try:
                    failed_history.remove_old_history()
                except Exception:
                    logger.log('Failed History cleanup error', logger.ERROR)
                    logger.log(traceback.format_exc(), logger.ERROR)

            # clear the data of unused providers
            try:
                sickbeard.helpers.clear_unused_providers()
            except Exception:
                logger.log('unused provider cleanup error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # cleanup image cache
            try:
                sickbeard.helpers.cleanup_cache()
            except Exception:
                logger.log('image cache cleanup error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # cleanup manual search history
            sickbeard.search_queue.remove_old_fifo(sickbeard.search_queue.MANUAL_SEARCH_HISTORY)

            # add missing mapped ids
            if not sickbeard.background_mapping_task.is_alive():
                logger.log(u'Updating the Indexer mappings')
                import threading
                try:
                    sickbeard.background_mapping_task = threading.Thread(
                        name='LOAD-MAPPINGS', target=sickbeard.indexermapper.load_mapped_ids, kwargs={'update': True})
                    sickbeard.background_mapping_task.start()
                except Exception:
                    logger.log('missing mapped ids update error', logger.ERROR)
                    logger.log(traceback.format_exc(), logger.ERROR)

            logger.log(u'Doing full update on all shows')

            # clean out cache directory, remove everything > 12 hours old
            try:
                sickbeard.helpers.clearCache()
            except Exception:
                logger.log('cache dir cleanup error', logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            # select 10 'Ended' tv_shows updated more than 90 days ago
            # and all shows not updated more then 180 days ago to include in this update
            stale_should_update = []
            stale_update_date = (update_date - datetime.timedelta(days=90)).toordinal()
            stale_update_date_max = (update_date - datetime.timedelta(days=180)).toordinal()

            # last_update_date <= 90 days, sorted ASC because dates are ordinal
            my_db = db.DBConnection()
            sql_results = my_db.mass_action([
                ['SELECT indexer_id FROM tv_shows WHERE last_update_indexer <= ? AND ' +
                 'last_update_indexer >= ? ORDER BY last_update_indexer ASC LIMIT 10;',
                 [stale_update_date, stale_update_date_max]],
                ['SELECT indexer_id FROM tv_shows WHERE last_update_indexer < ?;', [stale_update_date_max]]])

            for sql_result in sql_results:
                for cur_result in sql_result:
                    stale_should_update.append(int(cur_result['indexer_id']))

            # start update process
            pi_list = []
            for curShow in sickbeard.showList:

                try:
                    # get next episode airdate
                    curShow.nextEpisode()

                    # if should_update returns True (not 'Ended') or show is selected stale 'Ended' then update,
                    # otherwise just refresh
                    if curShow.should_update(update_date=update_date) or curShow.indexerid in stale_should_update:
                        cur_queue_item = sickbeard.showQueueScheduler.action.updateShow(curShow, scheduled_update=True)
                    else:
                        logger.log(
                            u'Not updating episodes for show ' + curShow.name + ' because it\'s marked as ended and ' +
                            'last/next episode is not within the grace period.', logger.DEBUG)
                        cur_queue_item = sickbeard.showQueueScheduler.action.refreshShow(curShow, True, True, force_image_cache=True)

                    pi_list.append(cur_queue_item)

                except (exceptions.CantUpdateException, exceptions.CantRefreshException) as e:
                    logger.log(u'Automatic update failed: ' + ex(e), logger.ERROR)

            ui.ProgressIndicators.setIndicator('dailyUpdate', ui.QueueProgressIndicator('Daily Update', pi_list))

            logger.log(u'Added all shows to show queue for full update')

        finally:
            self.amActive = False

    def __del__(self):
        pass
