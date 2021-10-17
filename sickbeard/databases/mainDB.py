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
import os.path
import re

from .. import db, common, logger
from ..name_parser.parser import NameParser, InvalidNameException, InvalidShowException
import sickbeard
# noinspection PyPep8Naming
import encodingKludge as ek

from six import iteritems

MIN_DB_VERSION = 9  # oldest db version we support migrating from
MAX_DB_VERSION = 20015
TEST_BASE_VERSION = None  # the base production db version, only needed for TEST db versions (>=100000)


class MainSanityCheck(db.DBSanityCheck):
    def check(self):
        self.fix_missing_table_indexes()
        self.fix_duplicate_shows()
        self.fix_duplicate_episodes()
        self.fix_orphan_episodes()
        self.fix_unaired_episodes()
        self.fix_scene_exceptions()
        self.fix_orphan_not_found_show()
        self.fix_fallback_mapping()
        self.fix_indexer_mapping_tvdb()
        self.fix_episode_subtitles()

    def fix_episode_subtitles(self):
        if not self.connection.has_flag('fix_episode_subtitles'):
            cleaned = False
            cl = []

            ep_result = self.connection.select(
                'SELECT episode_id'
                ' FROM tv_episodes'
                ' WHERE subtitles LIKE "%,%"')

            ep_len, cur_p = len(ep_result), 0
            ep_step = ep_len / 100.0
            fix_msg = 'Fixing subtitles: %s'

            if ep_len:
                self.connection.upgrade_log(fix_msg % ('%s%%' % 0))

            for _cur_count, cur_ep in enumerate(ep_result):
                if cur_p < int(_cur_count / ep_step):
                    cur_p = int(_cur_count / ep_step)
                    self.connection.upgrade_log(fix_msg % ('%s%%' % cur_p))
                if not cleaned:
                    logger.log('Removing duplicate subtitles data in TV Episodes table, this WILL take some time')
                    cleaned = True

                sql_result = self.connection.select(
                    'SELECT SUBSTR(REPLACE(subtitles, ",,", ""), -2000) AS truncated_langs'
                    ' FROM tv_episodes'
                    ' WHERE episode_id = ? LIMIT 1', [cur_ep['episode_id']])

                for cur_result in sql_result:
                    raw_langs = re.sub(r',+', '', cur_result['truncated_langs'])
                    subt_value = ','.join(re.findall('[a-z]{2}', raw_langs))
                    cl.append(['UPDATE tv_episodes SET subtitles = ? WHERE episode_id = ?',
                               [(subt_value, '')[bool(len(raw_langs) % 2)], cur_ep['episode_id']]])

            if 0 < len(cl):
                self.connection.mass_action(cl)

                logger.log(u'Performing a vacuum on the database.', logger.DEBUG)
                self.connection.upgrade_log(fix_msg % 'VACUUM')
                self.connection.action('VACUUM')
                self.connection.upgrade_log(fix_msg % 'finished')

            self.connection.set_flag('fix_episode_subtitles')

    def fix_indexer_mapping_tvdb(self):
        if not self.connection.has_flag('fix_indexer_mapping_tvdb'):
            self.connection.action('DELETE FROM indexer_mapping WHERE mindexer = ?', [10001])
            self.connection.set_flag('fix_indexer_mapping_tvdb')

    def fix_duplicate_shows(self, column='indexer_id'):

        # This func would break with multi tv info sources and without tvid, so added check min db version to mitigate
        # Also, tv_show table had a unique index added at some time to prevent further dupes,
        # therefore, this func is kept to cleanse legacy data given that it's redundant for new row insertions
        if self.connection.checkDBVersion() < 20004:

            sql_result = self.connection.select(
                'SELECT show_id, %(col)s, COUNT(%(col)s) AS count FROM tv_shows GROUP BY %(col)s HAVING count > 1'
                % {'col': column})

            for cur_result in sql_result:

                logger.log(u'Duplicate show detected! %s: %s count: %s' % (
                    column, cur_result[column], cur_result['count']), logger.DEBUG)

                cur_dupe_results = self.connection.select(
                    'SELECT show_id, ' + column + ' FROM tv_shows WHERE ' + column + ' = ? LIMIT ?',
                    [cur_result[column], int(cur_result['count']) - 1]
                )

                cl = []
                for cur_dupe_id in cur_dupe_results:
                    logger.log(u'Deleting duplicate show with %s: %s show_id: %s' % (
                        column, cur_dupe_id[column], cur_dupe_id['show_id']))
                    cl.append(['DELETE FROM tv_shows WHERE show_id = ?', [cur_dupe_id['show_id']]])

                if 0 < len(cl):
                    self.connection.mass_action(cl)

            else:
                logger.log(u'No duplicate show, check passed')

    def fix_duplicate_episodes(self):

        # This func would break with multi tv info sources and without tvid, so added check min db version to mitigate
        # Also, tv_show table had a unique index added at some time to prevent further dupes,
        # therefore, this func is kept to cleanse legacy data given that it's redundant for new row insertions
        if self.connection.checkDBVersion() < 20007:

            sql_result = self.connection.select(
                'SELECT indexer AS tv_id, showid AS prod_id, season, episode, COUNT(showid) as count'
                ' FROM tv_episodes'
                ' GROUP BY tv_id, prod_id, season, episode'
                ' HAVING count > 1')

            for cur_result in sql_result:

                logger.log(u'Duplicate episode detected! prod_id: %s season: %s episode: %s count: %s' %
                           (cur_result['prod_id'], cur_result['season'], cur_result['episode'],
                            cur_result['count']), logger.DEBUG)

                cur_dupe_results = self.connection.select(
                    'SELECT episode_id'
                    ' FROM tv_episodes'
                    ' WHERE indexer = ? AND showid = ?'
                    ' AND season = ? AND episode = ?'
                    ' ORDER BY episode_id DESC LIMIT ?',
                    [cur_result['tv_id'], cur_result['prod_id'],
                     cur_result['season'], cur_result['episode'],
                     int(cur_result['count']) - 1]
                )

                cl = []
                for cur_dupe_id in cur_dupe_results:
                    logger.log(u'Deleting duplicate episode with episode_id: %s' % cur_dupe_id['episode_id'])
                    cl.append(['DELETE FROM tv_episodes WHERE episode_id = ?', [cur_dupe_id['episode_id']]])

                if 0 < len(cl):
                    self.connection.mass_action(cl)

            else:
                logger.log(u'No duplicate episode, check passed')

    def fix_orphan_episodes(self):

        sql_result = self.connection.select(
            'SELECT episode_id, showid, tv_shows.indexer_id'
            ' FROM tv_episodes'
            ' LEFT JOIN tv_shows ON tv_episodes.showid=tv_shows.indexer_id AND tv_episodes.indexer=tv_shows.indexer '
            ' WHERE tv_shows.indexer_id is NULL')

        cl = []
        for cur_result in sql_result:
            logger.log(u'Orphan episode detected! episode_id: %s showid: %s' % (
                cur_result['episode_id'], cur_result['showid']), logger.DEBUG)
            logger.log(u'Deleting orphan episode with episode_id: %s' % cur_result['episode_id'])
            cl.append(['DELETE FROM tv_episodes WHERE episode_id = ?', [cur_result['episode_id']]])

        if 0 < len(cl):
            self.connection.mass_action(cl)

        else:
            logger.log(u'No orphan episodes, check passed')

    def fix_missing_table_indexes(self):
        if not self.connection.select('PRAGMA index_info("idx_indexer_id")'):
            logger.log('Updating TV Shows table with index idx_indexer_id')
            self.connection.action('CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer, indexer_id);')

        if not self.connection.select('PRAGMA index_info("idx_tv_episodes_showid_airdate")'):
            logger.log('Updating TV Episode table with index idx_tv_episodes_showid_airdate')
            self.connection.action('CREATE INDEX idx_tv_episodes_showid_airdate'
                                   ' ON tv_episodes(indexer,showid,airdate);')

        if not self.connection.select('PRAGMA index_info("idx_status")'):
            logger.log('Updating TV Episode table with index idx_status')
            self.connection.action('CREATE INDEX idx_status ON tv_episodes (status, season, episode, airdate)')

        if not self.connection.select('PRAGMA index_info("idx_sta_epi_air")'):
            logger.log('Updating TV Episode table with index idx_sta_epi_air')
            self.connection.action('CREATE INDEX idx_sta_epi_air ON tv_episodes (status, episode, airdate)')

        if not self.connection.select('PRAGMA index_info("idx_sta_epi_sta_air")'):
            logger.log('Updating TV Episode table with index idx_sta_epi_sta_air')
            self.connection.action('CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season, episode, status, airdate)')

        if not self.connection.hasIndex('tv_episodes', 'idx_tv_ep_ids'):
            logger.log('Updating TV Episode table with index idx_tv_ep_ids')
            self.connection.action('CREATE INDEX idx_tv_ep_ids ON tv_episodes (indexer, showid)')

        if not self.connection.hasIndex('tv_episodes', 'idx_tv_episodes_unique'):
            self.connection.action('CREATE UNIQUE INDEX idx_tv_episodes_unique ON '
                                   'tv_episodes(indexer,showid,season,episode)')

        allowtbl, blocktbl = (('allow', 'block'), ('white', 'black'))[not self.connection.hasTable('blocklist')]
        for t in [('%slist' % allowtbl, 'show_id'), ('%slist' % blocktbl, 'show_id'),
                  ('history', 'showid'), ('scene_exceptions', 'indexer_id')]:
            if not self.connection.hasIndex('%s' % t[0], 'idx_id_indexer_%s' % t[0]):
                # noinspection SqlResolve
                self.connection.action('CREATE INDEX idx_id_indexer_%s ON %s (indexer, %s)' % (t[0], t[0], t[1]))

    def fix_unaired_episodes(self):

        cur_date = datetime.date.today() + datetime.timedelta(days=1)

        sql_result = self.connection.select(
            'SELECT episode_id, showid FROM tv_episodes WHERE status = ? or ( airdate > ? AND status in (?,?) ) or '
            '( airdate <= 1 AND status = ? )', ['', cur_date.toordinal(), common.SKIPPED, common.WANTED, common.WANTED])

        cl = []
        for cur_result in sql_result:
            logger.log(u'UNAIRED episode detected! episode_id: %s showid: %s' % (
                cur_result['episode_id'], cur_result['showid']), logger.DEBUG)
            logger.log(u'Fixing unaired episode status with episode_id: %s' % cur_result['episode_id'])
            cl.append(['UPDATE tv_episodes SET status = ? WHERE episode_id = ?',
                       [common.UNAIRED, cur_result['episode_id']]])

        if 0 < len(cl):
            self.connection.mass_action(cl)

        else:
            logger.log(u'No UNAIRED episodes, check passed')

    def fix_scene_exceptions(self):

        # noinspection SqlResolve
        sql_result = self.connection.select(
            'SELECT exception_id FROM scene_exceptions WHERE season = "null"')

        if 0 < len(sql_result):
            logger.log('Fixing invalid scene exceptions')
            # noinspection SqlResolve
            self.connection.action('UPDATE scene_exceptions SET season = -1 WHERE season = "null"')

    def fix_orphan_not_found_show(self):
        sql_result = self.connection.action(
            'DELETE FROM tv_shows_not_found'
            ' WHERE NOT EXISTS (SELECT NULL FROM tv_shows WHERE tv_shows_not_found.indexer == tv_shows.indexer AND'
            ' tv_shows_not_found.indexer_id == tv_shows.indexer_id)')
        if sql_result.rowcount:
            logger.log('Fixed orphaned not found shows')

    def fix_fallback_mapping(self):
        fallback_indexer = [i for i in sickbeard.TVInfoAPI().fallback_sources]
        if fallback_indexer:
            sql_result = self.connection.action(
                'DELETE FROM indexer_mapping WHERE mindexer IN (%s) OR indexer in (%s)' %
                (','.join(['?'] * len(fallback_indexer)), ','.join(['?'] * len(fallback_indexer))),
                fallback_indexer + fallback_indexer)
            if sql_result.rowcount:
                logger.log('Fixed fallback indexer mappings')


class InitialSchema(db.SchemaUpgrade):
    # ======================
    # = Main DB Migrations =
    # ======================
    # Add new migrations at the bottom of the list; subclass the previous migration.
    # 0 -> 20009
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasTable('tv_shows') and not self.hasTable('db_version'):
            queries = [
                # anime allow and block list
                'CREATE TABLE allowlist (show_id INTEGER, range TEXT, keyword TEXT, indexer NUMERIC)',
                'CREATE TABLE blocklist (show_id INTEGER, range TEXT, keyword TEXT, indexer NUMERIC)',
                # db_version
                'CREATE TABLE db_version (db_version INTEGER)',
                'INSERT INTO db_version (db_version) VALUES (20008)',
                # flags
                'CREATE TABLE flags (flag PRIMARY KEY NOT NULL)',
                # history
                'CREATE TABLE history (action NUMERIC, date NUMERIC, showid NUMERIC, season NUMERIC, episode NUMERIC,'
                ' quality NUMERIC, resource TEXT, provider TEXT, version NUMERIC, hide NUMERIC DEFAULT 0)',
                # imdb_info
                'CREATE TABLE imdb_info (indexer_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC,'
                ' akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT,'
                ' rating TEXT, votes INTEGER, last_update NUMERIC)',
                # indexer_mapping
                'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER NOT NULL,'
                ' mindexer NUMERIC, date NUMERIC NOT NULL DEFAULT 0, status INTEGER NOT NULL DEFAULT 0,'
                ' PRIMARY KEY (indexer_id, indexer, mindexer))',
                'CREATE INDEX idx_mapping ON indexer_mapping (indexer_id, indexer)',
                # info
                'CREATE TABLE info (last_backlog NUMERIC, last_indexer NUMERIC, last_proper_search NUMERIC,'
                ' last_run_backlog NUMERIC NOT NULL DEFAULT 1)',
                # scene_exceptions
                'CREATE TABLE scene_exceptions (exception_id INTEGER PRIMARY KEY, indexer_id INTEGER KEY,'
                ' show_name TEXT, season NUMERIC, custom NUMERIC)',
                # scene_exceptions_refresh
                'CREATE TABLE scene_exceptions_refresh (list TEXT PRIMARY KEY, last_refreshed INTEGER)',
                # scene_numbering
                'CREATE TABLE scene_numbering (indexer TEXT, indexer_id INTEGER, season INTEGER, episode INTEGER,'
                ' scene_season INTEGER, scene_episode INTEGER, absolute_number NUMERIC, scene_absolute_number NUMERIC,'
                ' PRIMARY KEY (indexer_id, season, episode))',
                # tv_episodes
                'CREATE TABLE tv_episodes (episode_id INTEGER PRIMARY KEY, showid NUMERIC, indexerid NUMERIC,'
                ' indexer NUMERIC, name TEXT, season NUMERIC, episode NUMERIC, description TEXT, airdate NUMERIC,'
                ' hasnfo NUMERIC, hastbn NUMERIC, status NUMERIC, location TEXT, file_size NUMERIC, release_name TEXT,'
                ' subtitles TEXT, subtitles_searchcount NUMERIC, subtitles_lastsearch TIMESTAMP, is_proper NUMERIC,'
                ' scene_season NUMERIC, scene_episode NUMERIC, absolute_number NUMERIC, scene_absolute_number NUMERIC,'
                ' version NUMERIC, release_group TEXT)',
                'CREATE INDEX idx_showid ON tv_episodes (showid)',
                'CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes (showid,airdate)',
                'CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate)',
                'CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate)',
                'CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate)',
                # tv_episodes_watched
                'CREATE TABLE tv_episodes_watched (tvep_id NUMERIC NOT NULL, clientep_id TEXT, label TEXT,'
                ' played NUMERIC NOT NULL DEFAULT 0, date_watched NUMERIC NOT NULL, date_added NUMERIC,'
                ' status NUMERIC, location TEXT, file_size NUMERIC, hide INT NOT NULL DEFAULT 0)',
                # tv_shows
                'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, indexer_id NUMERIC, indexer NUMERIC,'
                ' show_name TEXT, location TEXT, network TEXT, genre TEXT, classification TEXT, runtime NUMERIC,'
                ' quality NUMERIC, airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC,'
                ' air_by_date NUMERIC, lang TEXT, subtitles NUMERIC, notify_list TEXT, imdb_id TEXT,'
                ' last_update_indexer NUMERIC, dvdorder NUMERIC, archive_firstmatch NUMERIC, rls_require_words TEXT,'
                ' rls_ignore_words TEXT, sports NUMERIC, anime NUMERIC, scene NUMERIC, overview TEXT, tag TEXT,'
                ' prune INT DEFAULT 0)',
                'CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id)',
                # tv_shows_not_found
                'CREATE TABLE tv_shows_not_found (indexer NUMERIC NOT NULL, indexer_id NUMERIC NOT NULL,'
                ' fail_count NUMERIC NOT NULL DEFAULT 0, last_check NUMERIC NOT NULL, last_success NUMERIC,'
                ' PRIMARY KEY (indexer_id, indexer))',
                # webdl_types
                'CREATE TABLE webdl_types (dname TEXT NOT NULL, regex TEXT NOT NULL)',
                # xem_refresh
                'CREATE TABLE xem_refresh (indexer TEXT, indexer_id INTEGER PRIMARY KEY, last_refreshed INTEGER)',
            ]
            for query in queries:
                self.connection.action(query)

        else:
            cur_db_version = self.checkDBVersion()

            if cur_db_version < MIN_DB_VERSION:
                logger.log_error_and_exit(
                    u'Your database version (' + str(cur_db_version)
                    + ') is too old to migrate from what this version of SickGear supports ('
                    + str(MIN_DB_VERSION) + ').' + "\n"
                    + 'Upgrade using a previous version (tag) build 496 to build 501 of SickGear'
                      ' first or remove database file to begin fresh.'
                                          )

            if cur_db_version > MAX_DB_VERSION:
                logger.log_error_and_exit(
                    u'Your database version (' + str(cur_db_version)
                    + ') has been incremented past what this version of SickGear supports ('
                    + str(MAX_DB_VERSION) + ').\n'
                    + 'If you have used other forks of SickGear,'
                      ' your database may be unusable due to their modifications.'
                                          )

        return self.checkDBVersion()


# 9 -> 10
class AddSizeAndSceneNameFields(db.SchemaUpgrade):
    def execute(self):
        """
        This func is only for 9->10 where older db columns exist,
        those columns have since changed
        """
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_episodes', 'file_size'):
            self.addColumn('tv_episodes', 'file_size')

        if not self.hasColumn('tv_episodes', 'release_name'):
            self.addColumn('tv_episodes', 'release_name', 'TEXT', '')

        sql_result = self.connection.select('SELECT episode_id, location, file_size FROM tv_episodes')

        self.upgrade_log(u'Adding file size to all episodes in DB, please be patient')
        for cur_result in sql_result:
            if not cur_result['location']:
                continue

            # if there is no size yet then populate it for us
            if (not cur_result['file_size'] or not int(cur_result['file_size'])) \
                    and ek.ek(os.path.isfile, cur_result['location']):
                cur_size = ek.ek(os.path.getsize, cur_result['location'])
                self.connection.action('UPDATE tv_episodes SET file_size = ? WHERE episode_id = ?',
                                       [cur_size, int(cur_result['episode_id'])])

        # check each snatch to see if we can use it to get a release name from
        # noinspection SqlRedundantOrderingDirection
        history_sql_result = self.connection.select('SELECT * FROM history WHERE provider != -1 ORDER BY date ASC')

        self.upgrade_log(u'Adding release name to all episodes still in history')
        for cur_result in history_sql_result:
            # find the associated download, if there isn't one then ignore it
            # noinspection SqlResolve
            download_sql_result = self.connection.select(
                'SELECT resource'
                ' FROM history'
                ' WHERE provider = -1 AND showid = ? AND season = ? AND episode = ? AND date > ?',
                [cur_result['showid'], cur_result['season'], cur_result['episode'], cur_result['date']])
            if not download_sql_result:
                self.upgrade_log(u'Found a snatch in the history for ' + cur_result['resource']
                                 + ' but couldn\'t find the associated download, skipping it', logger.DEBUG)
                continue

            nzb_name = cur_result['resource']
            file_name = ek.ek(os.path.basename, download_sql_result[0]['resource'])

            # take the extension off the filename, it's not needed
            if '.' in file_name:
                file_name = file_name.rpartition('.')[0]

            # find the associated episode on disk
            # noinspection SqlResolve
            sql_result = self.connection.select(
                'SELECT episode_id, status'
                ' FROM tv_episodes'
                ' WHERE showid = ? AND season = ? AND episode = ? AND location != ""',
                [cur_result['showid'], cur_result['season'], cur_result['episode']])
            if not sql_result:
                logger.log(
                    u'The episode ' + nzb_name + ' was found in history but doesn\'t exist on disk anymore, skipping',
                    logger.DEBUG)
                continue

            # get the status/quality of the existing ep and make sure it's what we expect
            ep_status, ep_quality = common.Quality.splitCompositeStatus(int(sql_result[0]['status']))
            if ep_status != common.DOWNLOADED:
                continue

            if ep_quality != int(cur_result['quality']):
                continue

            # make sure this is actually a real release name and not a season pack or something
            for cur_name in (nzb_name, file_name):
                logger.log(u'Checking if ' + cur_name + ' is actually a good release name', logger.DEBUG)
                try:
                    np = NameParser(False)
                    parse_result = np.parse(cur_name)
                except (InvalidNameException, InvalidShowException):
                    continue

                if parse_result.series_name and parse_result.season_number is not None\
                        and parse_result.episode_numbers and parse_result.release_group:
                    # if all is well by this point we'll just put the release name into the database
                    self.connection.action('UPDATE tv_episodes SET release_name = ? WHERE episode_id = ?',
                                           [cur_name, sql_result[0]['episode_id']])
                    break

        # check each snatch to see if we can use it to get a release name from
        # noinspection SqlResolve
        empty_sql_result = self.connection.select('SELECT episode_id, location'
                                                  ' FROM tv_episodes'
                                                  ' WHERE release_name = ""')

        self.upgrade_log(u'Adding release name to all episodes with obvious scene filenames')
        for cur_result in empty_sql_result:

            ep_file_name = ek.ek(os.path.basename, cur_result['location'])
            ep_file_name = os.path.splitext(ep_file_name)[0]

            # only want to find real scene names here so anything with a space in it is out
            if ' ' in ep_file_name:
                continue

            try:
                np = NameParser(False)
                parse_result = np.parse(ep_file_name)
            except (InvalidNameException, InvalidShowException):
                continue

            if not parse_result.release_group:
                continue

            logger.log(
                u'Name ' + ep_file_name + ' gave release group of ' + parse_result.release_group + ', seems valid',
                logger.DEBUG)
            self.connection.action('UPDATE tv_episodes SET release_name = ? WHERE episode_id = ?',
                                   [ep_file_name, cur_result['episode_id']])

        self.incDBVersion()
        return self.checkDBVersion()


# 10 -> 11
class RenameSeasonFolders(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        # rename the column
        self.connection.action('ALTER TABLE tv_shows RENAME TO tmp_tv_shows')
        self.connection.action(
            'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, location TEXT, show_name TEXT, tvdb_id NUMERIC,'
            ' network TEXT, genre TEXT, runtime NUMERIC, quality NUMERIC, airs TEXT, status TEXT,'
            ' flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC, tvr_id NUMERIC, tvr_name TEXT,'
            ' air_by_date NUMERIC, lang TEXT)')
        # noinspection SqlResolve
        sql = 'INSERT INTO tv_shows(show_id, location, show_name, tvdb_id, network, genre, runtime,' \
              ' quality, airs, status, flatten_folders, paused, startyear, tvr_id, tvr_name, air_by_date, lang)' \
              ' SELECT show_id, location, show_name, tvdb_id, network, genre, runtime, quality, airs, status,' \
              ' seasonfolders, paused, startyear, tvr_id, tvr_name, air_by_date, lang FROM tmp_tv_shows'
        self.connection.action(sql)

        # flip the values to be opposite of what they were before
        self.connection.action('UPDATE tv_shows SET flatten_folders = 2 WHERE flatten_folders = 1')
        self.connection.action('UPDATE tv_shows SET flatten_folders = 1 WHERE flatten_folders = 0')
        self.connection.action('UPDATE tv_shows SET flatten_folders = 0 WHERE flatten_folders = 2')
        # noinspection SqlResolve
        self.connection.action('DROP TABLE tmp_tv_shows')

        self.incDBVersion()
        return self.checkDBVersion()


# 11 -> 12
class Add1080pAndRawHDQualities(db.SchemaUpgrade):
    """
    Add support for 1080p related qualities along with RawHD

    Quick overview of what the upgrade needs to do:

           quality   | old  | new
        --------------------------
        hdwebdl      | 1<<3 | 1<<5
        hdbluray     | 1<<4 | 1<<7
        fullhdbluray | 1<<5 | 1<<8
        --------------------------
        rawhdtv      |      | 1<<3
        fullhdtv     |      | 1<<4
        fullhdwebdl  |      | 1<<6
    """

    def _update_status(self, old_status):
        (status, quality) = common.Quality.splitCompositeStatus(old_status)
        return common.Quality.compositeStatus(status, self._update_quality(quality))

    @staticmethod
    def _update_quality(old_quality):
        """
        Update bitwise flags to reflect new quality values

        Check flag bits (clear old then set their new locations) starting
        with the highest bits so we dont overwrite data we need later on
        """

        result = old_quality
        # move fullhdbluray from 1<<5 to 1<<8 if set
        if result & (1 << 5):
            result &= ~(1 << 5)
            result |= 1 << 8
        # move hdbluray from 1<<4 to 1<<7 if set
        if result & (1 << 4):
            result &= ~(1 << 4)
            result |= 1 << 7
        # move hdwebdl from 1<<3 to 1<<5 if set
        if result & (1 << 3):
            result &= ~(1 << 3)
            result |= 1 << 5

        return result

    def _update_composite_qualities(self, status):
        """
        Unpack, Update, Return new quality values

        Unpack the composite archive/initial values.
        Update either qualities if needed.
        Then return the new compsite quality value.
        """

        best = (status & (0xffff << 16)) >> 16
        initial = status & 0xffff

        best = self._update_quality(best)
        initial = self._update_quality(initial)

        result = ((best << 16) | initial)
        return result

    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        # update the default quality so we dont grab the wrong qualities after migration
        sickbeard.QUALITY_DEFAULT = self._update_composite_qualities(sickbeard.QUALITY_DEFAULT)
        sickbeard.save_config()

        # upgrade previous HD to HD720p -- shift previous qualities to new placevalues
        old_hd = common.Quality.combineQualities(
            [common.Quality.HDTV, common.Quality.HDWEBDL >> 2, common.Quality.HDBLURAY >> 3], [])
        new_hd = common.Quality.combineQualities([common.Quality.HDTV, common.Quality.HDWEBDL,
                                                  common.Quality.HDBLURAY], [])

        # update ANY -- shift existing qualities and add new 1080p qualities,
        # note that rawHD was not added to the ANY template
        old_any = common.Quality.combineQualities(
            [common.Quality.SDTV, common.Quality.SDDVD, common.Quality.HDTV, common.Quality.HDWEBDL >> 2,
             common.Quality.HDBLURAY >> 3, common.Quality.UNKNOWN], [])
        new_any = common.Quality.combineQualities(
            [common.Quality.SDTV, common.Quality.SDDVD, common.Quality.HDTV, common.Quality.FULLHDTV,
             common.Quality.HDWEBDL, common.Quality.FULLHDWEBDL, common.Quality.HDBLURAY, common.Quality.FULLHDBLURAY,
             common.Quality.UNKNOWN], [])

        # update qualities (including templates)
        self.upgrade_log(u'[1/4] Updating pre-defined templates and the quality for each show...')
        cl = []
        shows = self.connection.select('SELECT * FROM tv_shows')
        for cur_show in shows:
            if old_hd == cur_show['quality']:
                new_quality = new_hd
            elif old_any == cur_show['quality']:
                new_quality = new_any
            else:
                new_quality = self._update_composite_qualities(cur_show['quality'])
            cl.append(['UPDATE tv_shows SET quality = ? WHERE show_id = ?', [new_quality, cur_show['show_id']]])
        self.connection.mass_action(cl)

        # update status that are are within the old hdwebdl
        # (1<<3 which is 8) and better -- exclude unknown (1<<15 which is 32768)
        self.upgrade_log(u'[2/4] Updating the status for the episodes within each show...')
        cl = []
        sql_result = self.connection.select('SELECT * FROM tv_episodes WHERE status < 3276800 AND status >= 800')
        for cur_result in sql_result:
            cl.append(['UPDATE tv_episodes SET status = ? WHERE episode_id = ?',
                       [self._update_status(cur_result['status']), cur_result['episode_id']]])
        self.connection.mass_action(cl)

        # make two seperate passes through the history since snatched and downloaded (action & quality)
        # may not always coordinate together

        # update previous history so it shows the correct action
        self.upgrade_log(u'[3/4] Updating history to reflect the correct action...')
        cl = []
        # noinspection SqlResolve
        history_action = self.connection.select('SELECT * FROM history WHERE action < 3276800 AND action >= 800')
        for cur_entry in history_action:
            cl.append(['UPDATE history SET action = ? WHERE showid = ? AND date = ?',
                       [self._update_status(cur_entry['action']), cur_entry['showid'], cur_entry['date']]])
        self.connection.mass_action(cl)

        # update previous history so it shows the correct quality
        self.upgrade_log(u'[4/4] Updating history to reflect the correct quality...')
        cl = []
        # noinspection SqlResolve
        history_quality = self.connection.select('SELECT * FROM history WHERE quality < 32768 AND quality >= 8')
        for cur_entry in history_quality:
            cl.append(['UPDATE history SET quality = ? WHERE showid = ? AND date = ?',
                       [self._update_quality(cur_entry['quality']), cur_entry['showid'], cur_entry['date']]])
        self.connection.mass_action(cl)

        self.incDBVersion()

        # cleanup and reduce db if any previous data was removed
        self.upgrade_log(u'Performing a vacuum on the database.', logger.DEBUG)
        self.connection.action('VACUUM')
        return self.checkDBVersion()


# 12 -> 13
class AddShowidTvdbidIndex(db.SchemaUpgrade):
    # Adding index on tvdb_id (tv_shows) and showid (tv_episodes) to speed up searches/queries

    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Checking for duplicate shows before adding unique index.')
        MainSanityCheck(self.connection).fix_duplicate_shows('tvdb_id')

        self.upgrade_log(u'Adding index on tvdb_id (tv_shows) and showid (tv_episodes) to speed up searches/queries.')
        if not self.hasTable('idx_showid'):
            self.connection.action('CREATE INDEX idx_showid ON tv_episodes (showid);')
        if not self.hasTable('idx_tvdb_id'):
            # noinspection SqlResolve
            self.connection.action('CREATE UNIQUE INDEX idx_tvdb_id ON tv_shows (tvdb_id);')

        self.incDBVersion()
        return self.checkDBVersion()


# 13 -> 14
class AddLastUpdateTVDB(db.SchemaUpgrade):
    # Adding column last_update_tvdb to tv_shows for controlling nightly updates
    def execute(self):

        if not self.hasColumn('tv_shows', 'last_update_tvdb'):
            self.upgrade_log(u'Adding column last_update_tvdb to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'last_update_tvdb', default=1)

        self.incDBVersion()
        return self.checkDBVersion()


# 14 -> 15
class AddDBIncreaseTo15(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version to v%s' % self.checkDBVersion())
        self.incDBVersion()
        return self.checkDBVersion()


# 15 -> 16
class AddIMDbInfo(db.SchemaUpgrade):
    def execute(self):

        db_backed_up = False
        if not self.hasTable('imdb_info'):
            self.upgrade_log(u'Creating IMDb table imdb_info')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            db_backed_up = True
            self.connection.action(
                'CREATE TABLE imdb_info (tvdb_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC,'
                ' akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT,'
                ' rating TEXT, votes INTEGER, last_update NUMERIC)')

        if not self.hasColumn('tv_shows', 'imdb_id'):
            self.upgrade_log(u'Adding IMDb column imdb_id to tv_shows')

            if not db_backed_up:
                db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'imdb_id')

        self.incDBVersion()
        return self.checkDBVersion()


# 16 -> 17
class AddProperNamingSupport(db.SchemaUpgrade):
    def execute(self):

        if not self.hasColumn('tv_shows', 'imdb_id')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words'):
            return self.setDBVersion(5816)

        if not self.hasColumn('tv_episodes', 'is_proper'):
            self.upgrade_log(u'Adding column is_proper to tv_episodes')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_episodes', 'is_proper')

        self.incDBVersion()
        return self.checkDBVersion()


# 17 -> 18
class AddEmailSubscriptionTable(db.SchemaUpgrade):
    def execute(self):

        if not self.hasColumn('tv_episodes', 'is_proper')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words')\
                and self.hasColumn('tv_shows', 'skip_notices'):
            return self.setDBVersion(5817)

        if not self.hasColumn('tv_shows', 'notify_list'):
            self.upgrade_log(u'Adding column notify_list to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'notify_list', 'TEXT', None)

        self.incDBVersion()
        return self.checkDBVersion()


# 18 -> 19
class AddProperSearch(db.SchemaUpgrade):
    def execute(self):
        if not self.hasColumn('tv_episodes', 'is_proper'):
            return self.setDBVersion(12)

        if not self.hasColumn('tv_shows', 'notify_list')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words')\
                and self.hasColumn('tv_shows', 'skip_notices')\
                and self.hasColumn('history', 'source'):
            return self.setDBVersion(5818)

        if not self.hasColumn('info', 'last_proper_search'):
            self.upgrade_log(u'Adding column last_proper_search to info')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('info', 'last_proper_search', default=1)

        self.incDBVersion()
        return self.checkDBVersion()


# 19 -> 20
class AddDvdOrderOption(db.SchemaUpgrade):
    def execute(self):
        if not self.hasColumn('tv_shows', 'dvdorder'):
            self.upgrade_log(u'Adding column dvdorder to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'dvdorder', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 20 -> 21
class AddSubtitlesSupport(db.SchemaUpgrade):
    def execute(self):
        if not self.hasColumn('tv_shows', 'subtitles'):
            self.upgrade_log(u'Adding subtitles to tv_shows and tv_episodes')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'subtitles')
            self.addColumn('tv_episodes', 'subtitles', 'TEXT', '')
            self.addColumn('tv_episodes', 'subtitles_searchcount')
            self.addColumn('tv_episodes', 'subtitles_lastsearch', 'TIMESTAMP', str(datetime.datetime.min))

        self.incDBVersion()
        return self.checkDBVersion()


# 21 -> 22
class ConvertTVShowsToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Converting TV Shows table to Indexer Scheme...')

        if self.hasTable('tmp_tv_shows'):
            self.upgrade_log(u'Removing temp tv show tables left behind from previous updates...')
            # noinspection SqlResolve
            self.connection.action('DROP TABLE tmp_tv_shows')

        self.connection.action('ALTER TABLE tv_shows RENAME TO tmp_tv_shows')
        self.connection.action(
            'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, indexer_id NUMERIC, indexer NUMERIC, show_name TEXT,'
            ' location TEXT, network TEXT, genre TEXT, classification TEXT, runtime NUMERIC, quality NUMERIC,'
            ' airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC, air_by_date NUMERIC,'
            ' lang TEXT, subtitles NUMERIC, notify_list TEXT, imdb_id TEXT,'
            ' last_update_indexer NUMERIC, dvdorder NUMERIC)')
        # noinspection SqlResolve
        self.connection.action(
            'INSERT INTO tv_shows(show_id, indexer_id, show_name, location, network, genre, runtime, quality, airs,'
            ' status, flatten_folders, paused, startyear, air_by_date, lang, subtitles, notify_list, imdb_id,'
            ' last_update_indexer, dvdorder)'
            ' SELECT show_id, tvdb_id, show_name, location, network, genre, runtime,'
            ' quality, airs, status, flatten_folders, paused, startyear, air_by_date, lang, subtitles, notify_list,'
            ' imdb_id, last_update_tvdb, dvdorder FROM tmp_tv_shows')
        # noinspection SqlResolve
        self.connection.action('DROP TABLE tmp_tv_shows')

        self.connection.action('CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id);')

        # noinspection SqlResolve,SqlConstantCondition
        self.connection.action('UPDATE tv_shows SET classification = "Scripted" WHERE 1=1')
        # noinspection SqlConstantCondition
        self.connection.action('UPDATE tv_shows SET indexer = 1 WHERE 1=1')

        self.incDBVersion()
        return self.checkDBVersion()


# 22 -> 23
class ConvertTVEpisodesToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Converting TV Episodes table to Indexer Scheme...')

        if self.hasTable('tmp_tv_episodes'):
            self.upgrade_log(u'Removing temp tv episode tables left behind from previous updates...')
            # noinspection SqlResolve
            self.connection.action('DROP TABLE tmp_tv_episodes')

        self.connection.action('ALTER TABLE tv_episodes RENAME TO tmp_tv_episodes')
        self.connection.action(
            'CREATE TABLE tv_episodes (episode_id INTEGER PRIMARY KEY, showid NUMERIC, indexerid NUMERIC,'
            ' indexer NUMERIC, name TEXT, season NUMERIC, episode NUMERIC, description TEXT, airdate NUMERIC,'
            ' hasnfo NUMERIC, hastbn NUMERIC, status NUMERIC, location TEXT, file_size NUMERIC, release_name TEXT,'
            ' subtitles TEXT, subtitles_searchcount NUMERIC, subtitles_lastsearch TIMESTAMP, is_proper NUMERIC)')
        # noinspection SqlResolve
        self.connection.action(
            'INSERT INTO tv_episodes(episode_id, showid, indexerid, name, season, episode, description, airdate,'
            ' hasnfo, hastbn, status, location, file_size, release_name, subtitles, subtitles_searchcount,'
            ' subtitles_lastsearch, is_proper) SELECT episode_id, showid, tvdbid, name, season, episode, description,'
            ' airdate, hasnfo, hastbn, status, location, file_size, release_name, subtitles, subtitles_searchcount,'
            ' subtitles_lastsearch, is_proper FROM tmp_tv_episodes')
        # noinspection SqlResolve
        self.connection.action('DROP TABLE tmp_tv_episodes')

        self.connection.action('CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes(showid,airdate);')
        self.connection.action('CREATE INDEX idx_showid ON tv_episodes (showid);')
        self.connection.action('CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate)')
        self.connection.action('CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate)')
        self.connection.action('CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate)')

        # noinspection SqlConstantCondition
        self.connection.action('UPDATE tv_episodes SET indexer = 1 WHERE 1=1')

        self.incDBVersion()
        return self.checkDBVersion()


# 23 -> 24
class ConvertIMDBInfoToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Converting IMDb Info table to Indexer Scheme...')

        if self.hasTable('tmp_imdb_info'):
            self.upgrade_log(u'Removing temp imdb info tables left behind from previous updates...')
            # noinspection SqlResolve
            self.connection.action('DROP TABLE tmp_imdb_info')

        self.connection.action('ALTER TABLE imdb_info RENAME TO tmp_imdb_info')
        self.connection.action(
            'CREATE TABLE imdb_info (indexer_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC, akas TEXT,'
            ' runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT, rating TEXT,'
            ' votes INTEGER, last_update NUMERIC)')
        # noinspection SqlResolve
        self.connection.action(
            'INSERT INTO imdb_info(indexer_id, imdb_id, title, year, akas, runtimes, genres, countries, country_codes,'
            ' certificates, rating, votes, last_update) SELECT tvdb_id, imdb_id, title, year, akas, runtimes, genres,'
            ' countries, country_codes, certificates, rating, votes, last_update FROM tmp_imdb_info')
        # noinspection SqlResolve
        self.connection.action('DROP TABLE tmp_imdb_info')

        self.incDBVersion()
        return self.checkDBVersion()


# 24 -> 25
class ConvertInfoToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Converting Info table to Indexer Scheme...')

        if self.hasTable('tmp_info'):
            self.upgrade_log(u'Removing temp info tables left behind from previous updates...')
            # noinspection SqlResolve
            self.connection.action('DROP TABLE tmp_info')

        self.connection.action('ALTER TABLE info RENAME TO tmp_info')
        self.connection.action(
            'CREATE TABLE info (last_backlog NUMERIC, last_indexer NUMERIC, last_proper_search NUMERIC)')
        # noinspection SqlResolve
        self.connection.action(
            'INSERT INTO info(last_backlog, last_indexer, last_proper_search)'
            ' SELECT last_backlog, last_tvdb, last_proper_search FROM tmp_info')
        # noinspection SqlResolve
        self.connection.action('DROP TABLE tmp_info')

        self.incDBVersion()
        return self.checkDBVersion()


# 25 -> 26
class AddArchiveFirstMatchOption(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'archive_firstmatch'):
            self.upgrade_log(u'Adding column archive_firstmatch to tv_shows')
            self.addColumn('tv_shows', 'archive_firstmatch', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 26 -> 27
class AddSceneNumbering(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('scene_numbering'):
            self.connection.action('DROP TABLE scene_numbering')

        self.upgrade_log(u'Upgrading table scene_numbering ...')
        self.connection.action(
            'CREATE TABLE scene_numbering (indexer TEXT, indexer_id INTEGER, season INTEGER, episode INTEGER,'
            ' scene_season INTEGER, scene_episode INTEGER,'
            ' PRIMARY KEY (indexer_id,season,episode))')

        self.incDBVersion()
        return self.checkDBVersion()


# 27 -> 28
class ConvertIndexerToInteger(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        cl = []
        self.upgrade_log(u'Converting Indexer to Integer ...')
        cl.append(['UPDATE tv_shows SET indexer = ? WHERE LOWER(indexer) = ?', ['1', 'tvdb']])
        cl.append(['UPDATE tv_shows SET indexer = ? WHERE LOWER(indexer) = ?', ['2', 'tvrage']])
        cl.append(['UPDATE tv_episodes SET indexer = ? WHERE LOWER(indexer) = ?', ['1', 'tvdb']])
        cl.append(['UPDATE tv_episodes SET indexer = ? WHERE LOWER(indexer) = ?', ['2', 'tvrage']])
        cl.append(['UPDATE scene_numbering SET indexer = ? WHERE LOWER(indexer) = ?', ['1', 'tvdb']])
        cl.append(['UPDATE scene_numbering SET indexer = ? WHERE LOWER(indexer) = ?', ['2', 'tvrage']])

        self.connection.mass_action(cl)

        self.incDBVersion()
        return self.checkDBVersion()


# 28 -> 29
class AddRequireAndIgnoreWords(db.SchemaUpgrade):
    # Adding column rls_require_words and rls_ignore_words to tv_shows
    def execute(self):
        if self.hasColumn('tv_shows', 'rls_require_words') and self.hasColumn('tv_shows', 'rls_ignore_words'):
            self.incDBVersion()
            return self.checkDBVersion()

        db_backed_up = False
        if not self.hasColumn('tv_shows', 'rls_require_words'):
            self.upgrade_log(u'Adding column rls_require_words to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            db_backed_up = True
            self.addColumn('tv_shows', 'rls_require_words', 'TEXT', '')

        if not self.hasColumn('tv_shows', 'rls_ignore_words'):
            self.upgrade_log(u'Adding column rls_ignore_words to tv_shows')
            if not db_backed_up:
                db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'rls_ignore_words', 'TEXT', '')

        self.incDBVersion()
        return self.checkDBVersion()


# 29 -> 30
class AddSportsOption(db.SchemaUpgrade):
    def execute(self):
        db_backed_up = False
        if not self.hasColumn('tv_shows', 'sports'):
            self.upgrade_log(u'Adding column sports to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            db_backed_up = True
            self.addColumn('tv_shows', 'sports', 'NUMERIC', '0')

        if self.hasColumn('tv_shows', 'air_by_date') and self.hasColumn('tv_shows', 'sports'):
            # update sports column
            self.upgrade_log(u'[4/4] Updating tv_shows to reflect the correct sports value...')
            if not db_backed_up:
                db.backup_database('sickbeard.db', self.checkDBVersion())
            cl = []
            history_quality = self.connection.select(
                'SELECT * FROM tv_shows WHERE LOWER(classification) = "sports" AND air_by_date = 1 AND sports = 0')
            for cur_entry in history_quality:
                cl.append(['UPDATE tv_shows SET sports = ? WHERE show_id = ?',
                           [cur_entry['air_by_date'], cur_entry['show_id']]])
                cl.append(['UPDATE tv_shows SET air_by_date = 0 WHERE show_id = ?', [cur_entry['show_id']]])
            self.connection.mass_action(cl)

        self.incDBVersion()
        return self.checkDBVersion()


# 30 -> 31
class AddSceneNumberingToTvEpisodes(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding columns scene_season and scene_episode to tvepisodes')
        self.addColumn('tv_episodes', 'scene_season', 'NUMERIC', 'NULL')
        self.addColumn('tv_episodes', 'scene_episode', 'NUMERIC', 'NULL')

        self.incDBVersion()
        return self.checkDBVersion()


# 31 -> 32
class AddAnimeTVShow(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding column anime to tv_episodes')
        self.addColumn('tv_shows', 'anime', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 32 -> 33
class AddAbsoluteNumbering(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding column absolute_number to tv_episodes')
        self.addColumn('tv_episodes', 'absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 33 -> 34
class AddSceneAbsoluteNumbering(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding columns absolute_number and scene_absolute_number to scene_numbering')
        self.addColumn('scene_numbering', 'absolute_number', 'NUMERIC', '0')
        self.addColumn('scene_numbering', 'scene_absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 34 -> 35
class AddAnimeAllowlistBlocklist(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        cl = [['CREATE TABLE allowlist (show_id INTEGER, range TEXT, keyword TEXT, indexer NUMERIC)'],
              ['CREATE TABLE blocklist (show_id INTEGER, range TEXT, keyword TEXT, indexer NUMERIC)']]
        self.upgrade_log(u'Creating tables for anime allow and block lists')
        self.connection.mass_action(cl)

        self.incDBVersion()
        return self.checkDBVersion()


# 35 -> 36
class AddSceneAbsoluteNumbering2(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding column scene_absolute_number to tv_episodes')
        self.addColumn('tv_episodes', 'scene_absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 36 -> 37
class AddXemRefresh(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Creating table xem_refresh')
        self.connection.action(
            'CREATE TABLE xem_refresh (indexer TEXT, indexer_id INTEGER PRIMARY KEY, last_refreshed INTEGER)')

        self.incDBVersion()
        return self.checkDBVersion()


# 37 -> 38
class AddSceneToTvShows(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding column scene to tv_shows')
        self.addColumn('tv_shows', 'scene', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 38 -> 39
class AddIndexerMapping(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('indexer_mapping'):
            self.connection.action('DROP TABLE indexer_mapping')

        self.upgrade_log(u'Adding table indexer_mapping')
        self.connection.action(
            'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER, mindexer NUMERIC,'
            ' PRIMARY KEY (indexer_id, indexer))')

        self.incDBVersion()
        return self.checkDBVersion()


# 39 -> 40
class AddVersionToTvEpisodes(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Adding columns release_group and version to tv_episodes')
        self.addColumn('tv_episodes', 'release_group', 'TEXT', '')
        self.addColumn('tv_episodes', 'version', 'NUMERIC', '-1')

        self.upgrade_log(u'Adding column version to history')
        self.addColumn('history', 'version', 'NUMERIC', '-1')

        self.incDBVersion()
        return self.checkDBVersion()


# 40 -> 10000
class BumpDatabaseVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(10000)


# 41,42 -> 10001
class Migrate41(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(10001)


# 43,44 -> 10001
class Migrate43(db.SchemaUpgrade):
    def execute(self):

        db_backed_up = False
        db_chg = None
        table = 'tmdb_info'
        if self.hasTable(table):
            db.backup_database('sickbeard.db', self.checkDBVersion())
            db_backed_up = True
            self.upgrade_log(u'Dropping redundant table tmdb_info')
            # noinspection SqlResolve
            self.connection.action('DROP TABLE [%s]' % table)
            db_chg = True

        if self.hasColumn('tv_shows', 'tmdb_id'):
            if not db_backed_up:
                db.backup_database('sickbeard.db', self.checkDBVersion())
                db_backed_up = True
            self.upgrade_log(u'Dropping redundant tmdb_info refs')
            self.dropColumn('tv_shows', 'tmdb_id')
            db_chg = True

        if not self.hasTable('db_version'):
            if not db_backed_up:
                db.backup_database('sickbeard.db', self.checkDBVersion())
            self.connection.action('PRAGMA user_version = 0')
            self.connection.action('CREATE TABLE db_version (db_version INTEGER);')
            self.connection.action('INSERT INTO db_version (db_version) VALUES (0);')

        if not db_chg:
            self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(10001)


# 4301 -> 10002
class Migrate4301(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(10002)


# 4302,4400 -> 10003
class Migrate4302(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(10003)


# 5816 - 5818 -> 15
class MigrateUpstream(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Migrate SickBeard db v%s into v15' % str(self.checkDBVersion()).replace('58', ''))

        return self.setDBVersion(15)


# 10000 -> 20000
class SickGearDatabaseVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version to new SickGear standards')

        return self.setDBVersion(20000)


# 10001 -> 10000
class RemoveDefaultEpStatusFromTvShows(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Dropping redundant column default_ep_status from tv_shows')
        self.dropColumn('tv_shows', 'default_ep_status')

        return self.setDBVersion(10000)


# 10002 -> 10001
class RemoveMinorDBVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Dropping redundant column db_minor_version from db_version')
        self.dropColumn('db_version', 'db_minor_version')

        return self.setDBVersion(10001)


# 10003 -> 10002
class RemoveMetadataSub(db.SchemaUpgrade):
    def execute(self):
        if self.hasColumn('tv_shows', 'sub_use_sr_metadata'):
            self.upgrade_log(u'Dropping redundant column metadata sub')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.dropColumn('tv_shows', 'sub_use_sr_metadata')

        return self.setDBVersion(10002)


# 20000 -> 20001
class DBIncreaseTo20001(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log(u'Bumping database version to force a backup before new database code')

        self.connection.action('VACUUM')
        self.upgrade_log(u'Performed a vacuum on the database', logger.DEBUG)

        return self.setDBVersion(20001)


# 20001 -> 20002
class AddTvShowOverview(db.SchemaUpgrade):
    def execute(self):
        if not self.hasColumn('tv_shows', 'overview'):
            self.upgrade_log(u'Adding column overview to tv_shows')
            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'overview', 'TEXT', '')

        return self.setDBVersion(20002)


# 20002 -> 20003
class AddTvShowTags(db.SchemaUpgrade):
    def execute(self):
        if not self.hasColumn('tv_shows', 'tag'):
            self.upgrade_log(u'Adding tag to tv_shows')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'tag', 'TEXT', 'Show List')

        return self.setDBVersion(20003)


# 20003 -> 20004
class ChangeMapIndexer(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('indexer_mapping'):
            self.connection.action('DROP TABLE indexer_mapping')

        self.upgrade_log(u'Changing table indexer_mapping')
        self.connection.action(
            'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER NOT NULL,'
            ' mindexer NUMERIC, date NUMERIC NOT NULL  DEFAULT 0, status INTEGER NOT NULL  DEFAULT 0,'
            ' PRIMARY KEY (indexer_id, indexer, mindexer))')

        self.connection.action('CREATE INDEX IF NOT EXISTS idx_mapping ON indexer_mapping (indexer_id, indexer)')

        if not self.hasColumn('info', 'last_run_backlog'):
            self.upgrade_log('Adding last_run_backlog to info')
            self.addColumn('info', 'last_run_backlog', 'NUMERIC', 1)

        self.upgrade_log(u'Moving table scene_exceptions from cache.db to sickbeard.db')
        if self.hasTable('scene_exceptions_refresh'):
            self.connection.action('DROP TABLE scene_exceptions_refresh')
        self.connection.action('CREATE TABLE scene_exceptions_refresh (list TEXT PRIMARY KEY, last_refreshed INTEGER)')
        if self.hasTable('scene_exceptions'):
            self.connection.action('DROP TABLE scene_exceptions')
        self.connection.action('CREATE TABLE scene_exceptions (exception_id INTEGER PRIMARY KEY,'
                               ' indexer_id INTEGER KEY, show_name TEXT, season NUMERIC, custom NUMERIC)')

        try:
            cachedb = db.DBConnection(filename='cache.db')
            if cachedb.hasTable('scene_exceptions'):
                sql_result = cachedb.action('SELECT * FROM scene_exceptions')
                cs = []
                for cur_result in sql_result:
                    cs.append(
                        ['INSERT OR REPLACE INTO scene_exceptions (exception_id, indexer_id, show_name, season, custom)'
                         ' VALUES (?,?,?,?,?)',
                         [cur_result['exception_id'], cur_result['indexer_id'],
                          cur_result['show_name'], cur_result['season'], cur_result['custom']]])

                if 0 < len(cs):
                    self.connection.mass_action(cs)
        except (BaseException, Exception):
            pass

        keep_tables = {'allowlist', 'blocklist', 'whitelist', 'blacklist',
                       'scene_exceptions', 'scene_exceptions_refresh', 'info', 'indexer_mapping',
                       'db_version', 'history', 'imdb_info', 'lastUpdate', 'scene_numbering', 'tv_episodes', 'tv_shows',
                       'xem_refresh'}
        current_tables = set(self.listTables())
        remove_tables = list(current_tables - keep_tables)
        for table in remove_tables:
            # noinspection SqlResolve
            self.connection.action('DROP TABLE [%s]' % table)

        self.connection.action('VACUUM')

        return self.setDBVersion(20004)


# 20004 -> 20005
class AddShowNotFoundCounter(db.SchemaUpgrade):
    def execute(self):
        if not self.hasTable('tv_shows_not_found'):
            self.upgrade_log(u'Adding table tv_shows_not_found')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.connection.action(
                'CREATE TABLE tv_shows_not_found (indexer NUMERIC NOT NULL, indexer_id NUMERIC NOT NULL,'
                ' fail_count NUMERIC NOT NULL DEFAULT 0, last_check NUMERIC NOT NULL, last_success NUMERIC,'
                ' PRIMARY KEY (indexer_id, indexer))')

        return self.setDBVersion(20005)


# 20005 -> 20006
class AddFlagTable(db.SchemaUpgrade):
    def execute(self):
        if not self.hasTable('flags'):
            self.upgrade_log(u'Adding table flags')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.connection.action('CREATE TABLE flags (flag  PRIMARY KEY  NOT NULL )')

        return self.setDBVersion(20006)


# 20006 -> 20007
class DBIncreaseTo20007(db.SchemaUpgrade):
    def execute(self):

        self.upgrade_log(u'Bumping database version')

        return self.setDBVersion(20007)


# 20007 -> 20008
class AddWebdlTypesTable(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())
        self.connection.action('CREATE TABLE webdl_types (dname TEXT NOT NULL , regex TEXT NOT NULL )')

        return self.setDBVersion(20008)


# 20008 -> 20009
class AddWatched(db.SchemaUpgrade):
    def execute(self):
        # remove old table from version 20007
        if self.hasTable('tv_episodes_watched') and not self.hasColumn('tv_episodes_watched', 'clientep_id'):
            self.connection.action('DROP TABLE tv_episodes_watched')
            self.connection.action('VACUUM')

        if not self.hasTable('tv_episodes_watched'):
            self.upgrade_log(u'Adding table tv_episodes_watched')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.connection.action(
                'CREATE TABLE tv_episodes_watched (tvep_id NUMERIC NOT NULL, clientep_id TEXT, label TEXT,'
                ' played NUMERIC DEFAULT 0 NOT NULL, date_watched NUMERIC NOT NULL, date_added NUMERIC,'
                ' status NUMERIC, location TEXT, file_size NUMERIC, hide INT default 0 not null)'
                )

        return self.setDBVersion(20009)


# 20009 -> 20010
class AddPrune(db.SchemaUpgrade):
    def execute(self):

        if not self.hasColumn('tv_shows', 'prune'):
            self.upgrade_log('Adding prune to tv_shows')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'prune', 'INT', 0)

        return self.setDBVersion(20010)


# 20010 -> 20011
class AddIndexerToTables(db.SchemaUpgrade):
    def execute(self):
        sickbeard.helpers.upgrade_new_naming()
        db.backup_database('sickbeard.db', self.checkDBVersion())
        show_ids = {s['prod_id']: s['tv_id'] for s in
                    self.connection.select('SELECT indexer AS tv_id, indexer_id AS prod_id FROM tv_shows')}

        allowtbl, blocktbl = (('allow', 'block'), ('white', 'black'))[not self.connection.hasTable('blocklist')]
        allowtbl, blocktbl = '%slist' % allowtbl, '%slist' % blocktbl
        columns = {allowtbl: 'show_id, range, keyword, indexer',
                   blocktbl: 'show_id, range, keyword, indexer',
                   'history': 'action, date, showid, season, episode, quality, resource, provider, version, indexer',
                   'scene_exceptions': 'exception_id , indexer_id, show_name, season, custom, indexer'}

        # add missing indexer column
        for t in [(allowtbl, 'show_id'), (blocktbl, 'show_id'),
                  ('history', 'showid'), ('scene_exceptions', 'indexer_id')]:
            if not self.hasColumn(t[0], 'indexer'):
                self.upgrade_log(u'Adding TV info support to %s table' % t[0])
                self.addColumn(t[0], 'indexer')
                cl = []
                for s_id, i in iteritems(show_ids):
                    # noinspection SqlResolve
                    cl.append(['UPDATE %s SET indexer = ? WHERE %s = ?' % (t[0], t[1]), [i, s_id]])
                self.connection.mass_action(cl)
                # noinspection SqlResolve
                self.connection.action('CREATE INDEX idx_id_indexer_%s ON %s (indexer, %s)' % (t[0], t[0], t[1]))

            if 'history' != t[0]:
                # remove any unknown ids (exception history table)
                # noinspection SqlResolve
                self.connection.action('DELETE FROM %s WHERE indexer = ?' % t[0], [0])
                if 0 < self.connection.connection.total_changes:
                    self.upgrade_log('Removed orphaned data from %s' % t[0])

            if self.connection.hasTable('backup_%s' % t[0]):
                self.upgrade_log('Adding backup data to %s' % t[0])
                self.connection.action('REPLACE INTO %s SELECT %s FROM %s' % ('%s (%s)' % (t[0], columns[t[0]]),
                                                                              columns[t[0]], 'backup_%s' % t[0]))
                self.connection.removeTable('backup_%s' % t[0])

        # recreate tables that have wrong primary key = indexer_id without indexer
        self.upgrade_log('Adding TV info support to scene_numbering')
        # noinspection SqlResolve
        self.connection.mass_action([['ALTER TABLE scene_numbering RENAME TO tmp_scene_numbering'],
                                     ['CREATE TABLE scene_numbering (indexer TEXT, indexer_id INTEGER, season INTEGER, '
                                      'episode INTEGER, scene_season INTEGER, scene_episode INTEGER, '
                                      'absolute_number NUMERIC, scene_absolute_number NUMERIC, '
                                      'PRIMARY KEY (indexer,indexer_id,season,episode))'],
                                     ['REPLACE INTO scene_numbering (indexer, indexer_id, '
                                      'season, episode, scene_season, scene_episode, absolute_number, '
                                      'scene_absolute_number) SELECT "0" AS indexer, indexer_id, '
                                      'season, episode, scene_season, scene_episode, absolute_number, '
                                      'scene_absolute_number FROM tmp_scene_numbering'],
                                     ['DROP TABLE tmp_scene_numbering']])

        cl = []
        for s_id, i in iteritems(show_ids):
            cl.append(['UPDATE scene_numbering SET indexer = ? WHERE indexer_id = ?', [i, s_id]])
        cl.append(['DELETE FROM scene_numbering WHERE indexer = ?', [0]])
        self.connection.mass_action(cl)

        self.upgrade_log('Adding TV info support to imdb_info')
        # noinspection SqlResolve
        self.connection.mass_action([['ALTER TABLE imdb_info RENAME TO tmp_imdb_info'],
                                     ['CREATE TABLE imdb_info (indexer NUMERIC, indexer_id NUMERIC, imdb_id TEXT, '
                                      'title TEXT, year NUMERIC, akas TEXT, runtimes NUMERIC, genres TEXT, '
                                      'countries TEXT, country_codes TEXT, certificates TEXT, rating TEXT, '
                                      'votes INTEGER, last_update NUMERIC, PRIMARY KEY (indexer,indexer_id))'],
                                     ['REPLACE INTO imdb_info (indexer, indexer_id, imdb_id, '
                                      'title, year, akas, runtimes, genres, countries, country_codes, certificates, '
                                      'rating, votes, last_update) SELECT "0" AS indexer, indexer_id, imdb_id, '
                                      'title, year, akas, runtimes, genres, countries, country_codes, certificates, '
                                      'rating, votes, last_update FROM tmp_imdb_info'],
                                     ['DROP TABLE tmp_imdb_info']])

        cl = []
        for s_id, i in iteritems(show_ids):
            cl.append(['UPDATE imdb_info SET indexer = ? WHERE indexer_id = ?', [i, s_id]])
        cl.append(['DELETE FROM imdb_info WHERE indexer = ?', [0]])
        self.connection.mass_action(cl)
        self.connection.action('CREATE INDEX idx_id_indexer_imdb_info ON imdb_info (indexer,indexer_id)')

        if self.connection.hasTable('backup_imdb_info'):
            self.upgrade_log('Adding backup data to imdb_info')
            # noinspection SqlResolve
            self.connection.action('REPLACE INTO imdb_info (indexer, indexer_id, imdb_id, title, year, akas, '
                                   'runtimes, genres, countries, country_codes, certificates, rating, votes, '
                                   'last_update) SELECT indexer, indexer_id, imdb_id, title, year, akas, runtimes, '
                                   'genres, countries, country_codes, certificates, rating, votes, last_update '
                                   'FROM backup_imdb_info')
            self.connection.removeTable('backup_imdb_info')

        # remove an index of an no longer existing column
        self.upgrade_log('Changing/Re-Creating Indexes')
        if self.connection.hasIndex('tv_shows', 'idx_tvdb_id'):
            self.connection.removeIndex('tv_shows', 'idx_tvdb_id')

        if self.connection.hasIndex('tv_shows', 'idx_indexer_id'):
            self.connection.removeIndex('tv_shows', 'idx_indexer_id')
        self.connection.action('CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer,indexer_id)')

        if self.connection.hasIndex('tv_episodes', 'idx_showid'):
            self.connection.removeIndex('tv_episodes', 'idx_showid')

        if self.connection.hasIndex('tv_episodes', 'idx_tv_episodes_showid_airdate'):
            self.connection.removeIndex('tv_episodes', 'idx_tv_episodes_showid_airdate')
        self.connection.action('CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes(indexer,showid,airdate)')

        if not self.connection.hasIndex('tv_episodes', 'idx_tv_episodes_unique'):
            self.connection.action('CREATE UNIQUE INDEX idx_tv_episodes_unique ON '
                                   'tv_episodes(indexer,showid,season,episode)')

        if self.connection.hasTable('backup_tv_episodes'):
            self.upgrade_log('Adding backup data to tv_episodes')
            # noinspection SqlResolve
            self.connection.action('REPLACE INTO tv_episodes (episode_id, showid, indexerid, indexer, name, season, '
                                   'episode, description, airdate, hasnfo, hastbn, status, location, file_size, '
                                   'release_name, subtitles, subtitles_searchcount, subtitles_lastsearch, is_proper, '
                                   'scene_season, scene_episode, absolute_number, scene_absolute_number, '
                                   'release_group, version) SELECT episode_id, showid, indexerid, indexer, name, '
                                   'season, episode, description, airdate, hasnfo, hastbn, status, location, '
                                   'file_size, release_name, subtitles, subtitles_searchcount, subtitles_lastsearch, '
                                   'is_proper, scene_season, scene_episode, absolute_number, scene_absolute_number, '
                                   'release_group, version FROM backup_tv_episodes')
            self.connection.removeTable('backup_tv_episodes')

        if self.connection.hasTable('backup_tv_shows'):
            self.upgrade_log('Adding backup data to tv_shows')
            # noinspection SqlResolve
            self.connection.action('REPLACE INTO tv_shows (show_id, indexer_id, indexer, show_name, location, '
                                   'network, genre, classification, runtime, quality, airs, status, flatten_folders, '
                                   'paused, startyear, air_by_date, lang, subtitles, notify_list, imdb_id, '
                                   'last_update_indexer, dvdorder, archive_firstmatch, rls_require_words, '
                                   'rls_ignore_words, sports, anime, scene, overview, tag, prune) '
                                   'SELECT show_id, indexer_id, '
                                   'indexer, show_name, location, network, genre, classification, runtime, quality, '
                                   'airs, status, flatten_folders, paused, startyear, air_by_date, lang, subtitles, '
                                   'notify_list, imdb_id, last_update_indexer, dvdorder, archive_firstmatch, '
                                   'rls_require_words, rls_ignore_words, sports, anime, scene, overview, tag, prune '
                                   'FROM backup_tv_shows')
            self.connection.removeTable('backup_tv_shows')

        self.connection.action('VACUUM')

        return self.setDBVersion(20011)


# 20011 -> 20012
class AddShowExludeGlobals(db.SchemaUpgrade):
    def execute(self):

        if not self.hasColumn('tv_shows', 'rls_global_exclude_ignore'):
            self.upgrade_log('Adding rls_global_exclude_ignore, rls_global_exclude_require to tv_shows')

            db.backup_database('sickbeard.db', self.checkDBVersion())
            self.addColumn('tv_shows', 'rls_global_exclude_ignore', data_type='TEXT', default='')
            self.addColumn('tv_shows', 'rls_global_exclude_require', data_type='TEXT', default='')

        if self.hasTable('tv_shows_exclude_backup'):
            self.upgrade_log('Adding rls_global_exclude_ignore, rls_global_exclude_require from backup to tv_shows')
            # noinspection SqlResolve
            self.connection.mass_action([['UPDATE tv_shows SET rls_global_exclude_ignore = '
                                          '(SELECT te.rls_global_exclude_ignore FROM tv_shows_exclude_backup te WHERE '
                                          'te.show_id = tv_shows.show_id AND te.indexer = tv_shows.indexer), '
                                          'rls_global_exclude_require = (SELECT te.rls_global_exclude_require FROM '
                                          'tv_shows_exclude_backup te WHERE te.show_id = tv_shows.show_id AND '
                                          'te.indexer = tv_shows.indexer) WHERE EXISTS (SELECT 1 FROM '
                                          'tv_shows_exclude_backup WHERE tv_shows.show_id = '
                                          'tv_shows_exclude_backup.show_id AND '
                                          'tv_shows.indexer = tv_shows_exclude_backup.indexer)'],
                                         ['DROP TABLE tv_shows_exclude_backup']
                                         ])

        return self.setDBVersion(20012)


# 20012 -> 20013
class RenameAllowBlockListTables(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.connection.hasTable('blocklist'):
            self.upgrade_log('Renaming allow/block list tables')

            for old, new in (('black', 'block'), ('white', 'allow')):
                # noinspection SqlResolve
                self.connection.mass_action([
                    ['ALTER TABLE %slist RENAME TO tmp_%slist' % (old, new)],
                    ['CREATE TABLE %slist (show_id INTEGER, range TEXT, keyword TEXT, indexer NUMERIC)' % new],
                    ['INSERT INTO %slist(show_id, range, keyword, indexer)'
                     ' SELECT show_id, range, keyword, indexer FROM tmp_%slist' % (new, new)],
                    ['DROP TABLE tmp_%slist' % new]
                ])

        return self.setDBVersion(20013)


# 20013 -> 20014
class AddHistoryHideColumn(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('history', 'hide'):
            self.upgrade_log('Adding hide column to history')
            self.addColumn('history', 'hide', default=0, set_default=True)

            if self.hasTable('history_hide_backup'):
                self.upgrade_log('Restoring hide status in history from backup')
                # noinspection SqlResolve
                self.connection.mass_action([
                    [
                        """
                        UPDATE history SET hide = (SELECT hide FROM history_hide_backup as hh WHERE
                        hh.ROWID = history.ROWID AND hh.showid = history.showid AND hh.indexer = history.indexer AND
                        hh.season = history.season AND hh.episode = history.episode AND hh.action = history.action AND
                        hh.date = history.date)
                        """
                    ],
                    ['DROP TABLE history_hide_backup']
                ])

        return self.setDBVersion(20014)


# 20014 -> 20015
class ChangeShowData(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        self.upgrade_log('Adding new data columns to tv_shows')
        self.addColumns('tv_shows', [('timezone', 'TEXT', ''), ('airtime', 'NUMERIC'),
                                     ('network_country', 'TEXT', ''), ('network_country_code', 'TEXT', ''),
                                     ('network_id', 'NUMERIC'), ('network_is_stream', 'INTEGER'),
                                     ('src_update_timestamp', 'INTEGER')])

        self.upgrade_log('Adding new data columns to tv_episodes')
        self.addColumns('tv_episodes', [('timezone', 'TEXT', ''), ('airtime', 'NUMERIC'),
                                        ('runtime', 'NUMERIC', 0), ('timestamp', 'NUMERIC'),
                                        ('network', 'TEXT', ''), ('network_country', 'TEXT', ''),
                                        ('network_country_code', 'TEXT', ''), ('network_id', 'NUMERIC'),
                                        ('network_is_stream', 'INTEGER')])

        if not self.hasColumn('imdb_info', 'is_mini_series'):
            self.upgrade_log('Adding new data columns to imdb_info')
            self.addColumns('imdb_info', [('is_mini_series', 'INTEGER', 0), ('episode_count', 'NUMERIC')])

        self.upgrade_log('Adding Character and Persons tables')

        table_create_sql = {
            'castlist': [
                [
                    """
                    CREATE TABLE castlist
                    (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    indexer      NUMERIC NOT NULL,
                    indexer_id   NUMERIC NOT NULL,
                    character_id NUMERIC NOT NULL,
                    sort_order   NUMERIC DEFAULT 0 NOT NULL,
                    updated      NUMERIC
                    );
                    """
                ],
            ],
            'idx_castlist': [
                ['CREATE INDEX idx_castlist ON castlist (indexer, indexer_Id);'],
                ['CREATE UNIQUE INDEX idx_unique_castlist ON castlist (indexer, indexer_id, character_id);']
            ],
            'characters': [
                [
                    """
                    CREATE TABLE characters
                    (
                    id         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name       TEXT,
                    bio        TEXT,
                    thumb_url  TEXT,
                    image_url  TEXT,
                    updated    NUMERIC
                    );
                    """
                ]
            ],
            'character_ids': [
                [
                    """
                    CREATE TABLE character_ids
                    (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    src          NUMERIC NOT NULL,
                    src_id       NUMERIC NOT NULL,
                    character_id NUMERIC NOT NULL
                    );
                    """
                ],
            ],
            'idx_character_ids': [
                ['CREATE UNIQUE INDEX idx_unique_character_ids ON character_ids (src, character_id);'],
                ['CREATE INDEX idx_character_ids ON character_ids (character_id);']
            ],
            'character_person_map': [
                [
                    """
                    CREATE TABLE character_person_map
                    (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id NUMERIC NOT NULL,
                    person_id    NUMERIC NOT NULL
                    );
                    """
                ],
            ],
            'idx_character_person_map': [
                ['CREATE INDEX idx_character_person_map_character ON character_person_map (character_id);'],
                ['CREATE INDEX idx_character_person_map_person ON character_person_map (person_id);'],
                ['CREATE UNIQUE INDEX idx_unique_character_person ON character_person_map (character_id, person_id);']
            ],
            'character_person_years': [
                [
                    """CREATE TABLE character_person_years
                       (
                       character_id NUMERIC NOT NULL,
                       person_id    NUMERIC NOT NULL,
                       start_year   NUMERIC,
                       end_year     NUMERIC
                       );
                       """
                 ],
            ],
            'idx_character_person_years': [
                ['CREATE UNIQUE INDEX idx_unique_character_person_years '
                 'ON character_person_years (character_id, person_id)'],
                ['CREATE INDEX idx_character_person_years ON character_person_years (character_id)'],
            ],
            'persons': [
                [
                    """
                    CREATE TABLE persons
                    (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT,
                    gender     INTEGER,
                    birthdate  NUMERIC,
                    deathdate  NUMERIC,
                    birthplace TEXT,
                    deathplace TEXT,
                    height     NUMERIC,
                    realname   TEXT,
                    nicknames  TEXT,
                    akas       TEXT,
                    homepage   TEXT,
                    bio        TEXT,
                    thumb_url  TEXT,
                    image_url  TEXT,
                    updated    NUMERIC
                    );
                    """
                ]
            ],
            'person_ids': [
                [
                    """
                    CREATE TABLE person_ids
                    (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    src       INTEGER NOT NULL, 
                    src_id    TEXT NOT NULL,
                    person_id NUMERIC NOT NULL
                    );
                    """
                ],
            ],
            'idx_person_ids': [
                ['CREATE UNIQUE INDEX idx_unique_person_ids ON person_ids (src, person_id);'],
                ['CREATE INDEX idx_person_ids ON person_ids (person_id);']
            ],
            'tv_src_switch': [
                [
                    """
                    CREATE TABLE tv_src_switch
                    (
                    old_indexer    NUMERIC NOT NULL,
                    old_indexer_id NUMERIC NOT NULL,
                    new_indexer    NUMERIC NOT NULL,
                    new_indexer_id NUMERIC,
                    force_id       NUMERIC DEFAULT 0 NOT NULL,
                    set_pause      INTEGER DEFAULT 0 NOT NULL,
                    mark_wanted    INTEGER DEFAULT 0 NOT NULL,
                    status         NUMERIC DEFAULT 0 NOT NULL,
                    action_id      INTEGER NOT NULL,
                    uid            NUMERIC NOT NULL
                    );
                    """
                ],
            ],
            'idx_tv_src_switch': [
                ['CREATE UNIQUE INDEX idx_unique_tv_src_switch ON tv_src_switch (old_indexer, old_indexer_id);']
            ],
            'switch_ep_result': [
                [
                    """
                    CREATE TABLE switch_ep_result 
                    (
                    old_indexer    NUMERIC NOT NULL,
                    old_indexer_id NUMERIC NOT NULL,
                    new_indexer    NUMERIC NOT NULL,
                    new_indexer_id NUMERIC NOT NULL,
                    season         NUMERIC NOT NULL,
                    episode        NUMERIC NOT NULL,
                    reason         NUMERIC DEFAULT 0
                    );
                    """
                ],
            ],
            'idx_switch_ep_result': [
                ['CREATE INDEX idx_switch_ep_result ON switch_ep_result (new_indexer, new_indexer_id);'],
                ["""CREATE INDEX idx_unique_switch_ep_result
                    ON switch_ep_result (new_indexer, new_indexer_id, season, episode, reason);"""],
                ['CREATE INDEX idx_switch_ep_result_old ON switch_ep_result (old_indexer, old_indexer_id);'],
            ],
        }

        cl = []
        tables = self.list_tables()
        for t in ('castlist', 'characters', 'character_ids', 'persons', 'person_ids', 'character_person_map',
                  'character_person_years', 'tv_src_switch', 'switch_ep_result'):
            if 'backup_%s' % t in tables:
                # noinspection SqlResolve
                cl.append(['ALTER TABLE backup_%s RENAME TO %s' % (t, t)])
            elif t not in tables:
                cl.extend(table_create_sql[t])
            if 'idx_%s' % t in table_create_sql:
                cl.extend(table_create_sql['idx_%s' % t])

        cl.extend(sickbeard.tv.TVShow.orphaned_cast_sql())

        if cl:
            self.connection.mass_action(cl)
            self.connection.action('VACUUM')

        return self.setDBVersion(20015)
