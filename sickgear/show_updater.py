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

import exceptions_helper
from exceptions_helper import ex

import sickgear
from . import db, logger, network_timezones, properFinder, ui
from .scheduler import Job
from .config import backup_config

# noinspection PyUnreachableCode
if False:
    from sickgear.tv import TVShow


def clean_ignore_require_words():
    """
    removes duplicate ignore/require words from shows and global lists
    """
    try:
        for s in sickgear.showList:  # type: TVShow
            # test before set to prevent dirty setter from setting unchanged shows to dirty
            if s.rls_ignore_words - sickgear.IGNORE_WORDS != s.rls_ignore_words:
                s.rls_ignore_words -= sickgear.IGNORE_WORDS
                if 0 == len(s.rls_ignore_words):
                    s.rls_ignore_words_regex = False
            if s.rls_require_words - sickgear.REQUIRE_WORDS != s.rls_require_words:
                s.rls_require_words -= sickgear.REQUIRE_WORDS
                if 0 == len(s.rls_require_words):
                    s.rls_require_words_regex = False
            if s.rls_global_exclude_ignore & sickgear.IGNORE_WORDS != s.rls_global_exclude_ignore:
                s.rls_global_exclude_ignore &= sickgear.IGNORE_WORDS
            if s.rls_global_exclude_require & sickgear.REQUIRE_WORDS != s.rls_global_exclude_require:
                s.rls_global_exclude_require &= sickgear.REQUIRE_WORDS
            if s.dirty:
                s.save_to_db()
    except (BaseException, Exception):
        pass


class ShowUpdater(Job):
    def __init__(self):
        super(ShowUpdater, self).__init__(self.job_run, kwargs={})

    @staticmethod
    def job_run():

        try:
            update_datetime = datetime.datetime.now()
            update_date = update_datetime.date()

            # backup db's
            if sickgear.db.db_supports_backup and 0 < sickgear.BACKUP_DB_MAX_COUNT:
                logger.log('backing up all db\'s')
                try:
                    backup_success = sickgear.db.backup_all_dbs(
                        sickgear.BACKUP_DB_PATH or os.path.join(sickgear.DATA_DIR, 'backup'))
                    if isinstance(backup_success, tuple) and backup_success[0]:
                        # backup config.ini
                        backup_config()
                except (BaseException, Exception):
                    logger.error('backup db error')

            # refresh network timezones
            try:
                network_timezones.update_network_dict()
            except (BaseException, Exception):
                logger.error('network timezone update error')
                logger.error(traceback.format_exc())

            # refresh webdl types
            try:
                properFinder.load_webdl_types()
            except (BaseException, Exception):
                logger.debug('error loading webdl_types')

            # update xem id lists
            try:
                sickgear.scene_exceptions.ReleaseMap().fetch_xem_ids()
            except (BaseException, Exception):
                logger.error('xem id list update error')
                logger.error(traceback.format_exc())

            # update scene exceptions
            try:
                sickgear.scene_exceptions.ReleaseMap().fetch_exceptions()
            except (BaseException, Exception):
                logger.error('scene exceptions update error')
                logger.error(traceback.format_exc())

            # clear the data of unused providers
            try:
                sickgear.helpers.clear_unused_providers()
            except (BaseException, Exception):
                logger.error('unused provider cleanup error')
                logger.error(traceback.format_exc())

            # cleanup image cache
            try:
                sickgear.helpers.cleanup_cache()
            except (BaseException, Exception):
                logger.error('image cache cleanup error')
                logger.error(traceback.format_exc())

            # check tvinfo cache
            try:
                for i in sickgear.TVInfoAPI().all_sources:
                    sickgear.TVInfoAPI(i).setup().check_cache()
            except (BaseException, Exception):
                logger.error('tvinfo cache check error')
                logger.error(traceback.format_exc())

            # cleanup tvinfo cache
            try:
                for i in sickgear.TVInfoAPI().all_sources:
                    sickgear.TVInfoAPI(i).setup().clean_cache()
            except (BaseException, Exception):
                logger.error('tvinfo cache cleanup error')
                logger.error(traceback.format_exc())

            # cleanup ignore and require lists
            try:
                clean_ignore_require_words()
            except (BaseException, Exception):
                logger.error('ignore, require words cleanup error')
                logger.error(traceback.format_exc())

            # cleanup manual search history
            sickgear.search_queue.remove_old_fifo(sickgear.search_queue.MANUAL_SEARCH_HISTORY)

            # add missing mapped ids
            if not sickgear.background_mapping_task.is_alive():
                logger.log('Updating the TV info mappings')
                import threading
                try:
                    sickgear.background_mapping_task = threading.Thread(
                        name='MAPPINGUPDATES', target=sickgear.indexermapper.load_mapped_ids, kwargs={'update': True})
                    sickgear.background_mapping_task.start()
                except (BaseException, Exception):
                    logger.error('missing mapped ids update error')
                    logger.error(traceback.format_exc())

            logger.log('Doing full update on all shows')

            # clean out cache directory, remove everything > 12 hours old
            try:
                sickgear.helpers.clear_cache()
            except (BaseException, Exception):
                logger.error('cache dir cleanup error')
                logger.error(traceback.format_exc())

            # select 10 'Ended' tv_shows updated more than 90 days ago
            # and all shows not updated more than 180 days ago to include in this update
            stale_should_update = []
            stale_update_date = (update_date - datetime.timedelta(days=90)).toordinal()
            stale_update_date_max = (update_date - datetime.timedelta(days=180)).toordinal()

            # last_update_date <= 90 days, sorted ASC because dates are ordinal
            from sickgear.tv import TVidProdid
            my_db = db.DBConnection()
            # noinspection SqlRedundantOrderingDirection
            mass_sql_result = my_db.mass_action([
                ['SELECT indexer || ? || indexer_id AS tvid_prodid'
                 ' FROM tv_shows'
                 ' WHERE last_update_indexer <= ?'
                 ' AND last_update_indexer >= ?'
                 ' ORDER BY last_update_indexer ASC LIMIT 10;',
                 [TVidProdid.glue, stale_update_date, stale_update_date_max]],
                ['SELECT indexer || ? || indexer_id AS tvid_prodid'
                 ' FROM tv_shows'
                 ' WHERE last_update_indexer < ?;',
                 [TVidProdid.glue, stale_update_date_max]]])

            for sql_result in mass_sql_result:
                for cur_result in sql_result:
                    stale_should_update.append(cur_result['tvid_prodid'])

            # start update process
            show_updates = {}
            for src in sickgear.TVInfoAPI().search_sources:
                tvinfo_config = sickgear.TVInfoAPI(src).api_params.copy()
                t = sickgear.TVInfoAPI(src).setup(**tvinfo_config)
                show_updates.update({src: t.get_updated_shows()})

            pi_list = []
            for cur_show_obj in sickgear.showList:  # type: sickgear.tv.TVShow

                try:
                    # if should_update returns True (not 'Ended') or show is selected stale 'Ended' then update,
                    # otherwise just refresh
                    if cur_show_obj.should_update(
                            update_date=update_date,
                            last_indexer_change=show_updates.get(cur_show_obj.tvid, {}).get(cur_show_obj.prodid)) \
                            or cur_show_obj.tvid_prodid in stale_should_update:
                        cur_queue_item = sickgear.show_queue_scheduler.action.update_show(
                            cur_show_obj, scheduled_update=True)
                    else:
                        logger.debug(f'Not updating episodes for show {cur_show_obj.unique_name} because it\'s'
                                     f' marked as ended and last/next episode is not within the grace period.')
                        cur_queue_item = sickgear.show_queue_scheduler.action.refresh_show(cur_show_obj, True, True)

                    pi_list.append(cur_queue_item)

                except (exceptions_helper.CantUpdateException, exceptions_helper.CantRefreshException) as e:
                    logger.error(f'Automatic update failed: {ex(e)}')

            if len(pi_list):
                sickgear.show_queue_scheduler.action.daily_update_running = True

            ui.ProgressIndicators.set_indicator('dailyUpdate', ui.QueueProgressIndicator('Daily Update', pi_list))

            logger.log('Added all shows to show queue for full update')

        except(BaseException, Exception):
            pass

    def __del__(self):
        pass
