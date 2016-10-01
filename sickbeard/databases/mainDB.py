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

import sickbeard
import os.path

from sickbeard import db, common, logger

from sickbeard import encodingKludge as ek
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException

MIN_DB_VERSION = 9  # oldest db version we support migrating from
MAX_DB_VERSION = 20004


class MainSanityCheck(db.DBSanityCheck):
    def check(self):
        self.fix_missing_table_indexes()
        self.fix_duplicate_shows()
        self.fix_duplicate_episodes()
        self.fix_orphan_episodes()
        self.fix_unaired_episodes()

    def fix_duplicate_shows(self, column='indexer_id'):

        sql_results = self.connection.select(
            'SELECT show_id, ' + column + ', COUNT(' + column + ') as count FROM tv_shows GROUP BY ' + column + ' HAVING count > 1')

        for cur_duplicate in sql_results:

            logger.log(u'Duplicate show detected! %s: %s count: %s' % (column, cur_duplicate[column],
                                                                       cur_duplicate['count']), logger.DEBUG)

            cur_dupe_results = self.connection.select(
                'SELECT show_id, ' + column + ' FROM tv_shows WHERE ' + column + ' = ? LIMIT ?',
                [cur_duplicate[column], int(cur_duplicate['count']) - 1]
            )

            cl = []
            for cur_dupe_id in cur_dupe_results:
                logger.log(
                    u'Deleting duplicate show with %s: %s show_id: %s' % (column, cur_dupe_id[column],
                                                                          cur_dupe_id['show_id']))
                cl.append(['DELETE FROM tv_shows WHERE show_id = ?', [cur_dupe_id['show_id']]])

            if 0 < len(cl):
                self.connection.mass_action(cl)

        else:
            logger.log(u'No duplicate show, check passed')

    def fix_duplicate_episodes(self):

        sql_results = self.connection.select(
            'SELECT showid, season, episode, COUNT(showid) as count FROM tv_episodes GROUP BY showid, season, episode HAVING count > 1')

        for cur_duplicate in sql_results:

            logger.log(u'Duplicate episode detected! showid: %s season: %s episode: %s count: %s' %
                       (cur_duplicate['showid'], cur_duplicate['season'], cur_duplicate['episode'],
                        cur_duplicate['count']), logger.DEBUG)

            cur_dupe_results = self.connection.select(
                'SELECT episode_id FROM tv_episodes WHERE showid = ? AND season = ? and episode = ? ORDER BY episode_id DESC LIMIT ?',
                [cur_duplicate['showid'], cur_duplicate['season'], cur_duplicate['episode'],
                 int(cur_duplicate['count']) - 1]
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

        sql_results = self.connection.select(
            'SELECT episode_id, showid, tv_shows.indexer_id FROM tv_episodes LEFT JOIN tv_shows ON tv_episodes.showid=tv_shows.indexer_id WHERE tv_shows.indexer_id is NULL')

        cl = []
        for cur_orphan in sql_results:
            logger.log(u'Orphan episode detected! episode_id: %s showid: %s' % (cur_orphan['episode_id'],
                                                                                cur_orphan['showid']), logger.DEBUG)
            logger.log(u'Deleting orphan episode with episode_id: %s' % cur_orphan['episode_id'])
            cl.append(['DELETE FROM tv_episodes WHERE episode_id = ?', [cur_orphan['episode_id']]])

        if 0 < len(cl):
            self.connection.mass_action(cl)

        else:
            logger.log(u'No orphan episodes, check passed')

    def fix_missing_table_indexes(self):
        if not self.connection.select('PRAGMA index_info("idx_indexer_id")'):
            logger.log(u'Missing idx_indexer_id for TV Shows table detected!, fixing...')
            self.connection.action('CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id);')

        if not self.connection.select('PRAGMA index_info("idx_tv_episodes_showid_airdate")'):
            logger.log(u'Missing idx_tv_episodes_showid_airdate for TV Episodes table detected!, fixing...')
            self.connection.action('CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes(showid,airdate);')

        if not self.connection.select('PRAGMA index_info("idx_showid")'):
            logger.log(u'Missing idx_showid for TV Episodes table detected!, fixing...')
            self.connection.action('CREATE INDEX idx_showid ON tv_episodes (showid);')

        if not self.connection.select('PRAGMA index_info("idx_status")'):
            logger.log(u'Missing idx_status for TV Episodes table detected!, fixing...')
            self.connection.action('CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate)')

        if not self.connection.select('PRAGMA index_info("idx_sta_epi_air")'):
            logger.log(u'Missing idx_sta_epi_air for TV Episodes table detected!, fixing...')
            self.connection.action('CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate)')

        if not self.connection.select('PRAGMA index_info("idx_sta_epi_sta_air")'):
            logger.log(u'Missing idx_sta_epi_sta_air for TV Episodes table detected!, fixing...')
            self.connection.action('CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate)')

    def fix_unaired_episodes(self):

        cur_date = datetime.date.today() + datetime.timedelta(days=1)

        sql_results = self.connection.select(
            'SELECT episode_id, showid FROM tv_episodes WHERE status = ? or ( airdate > ? AND status in (?,?) ) or '
            '( airdate <= 1 AND status = ? )', ['', cur_date.toordinal(), common.SKIPPED, common.WANTED, common.WANTED])

        cl = []
        for cur_unaired in sql_results:
            logger.log(u'UNAIRED episode detected! episode_id: %s showid: %s' % (cur_unaired['episode_id'],
                                                                                 cur_unaired['showid']), logger.DEBUG)
            logger.log(u'Fixing unaired episode status with episode_id: %s' % cur_unaired['episode_id'])
            cl.append(['UPDATE tv_episodes SET status = ? WHERE episode_id = ?',
                                   [common.UNAIRED, cur_unaired['episode_id']]])

        if 0 < len(cl):
            self.connection.mass_action(cl)

        else:
            logger.log(u'No UNAIRED episodes, check passed')


# ======================
# = Main DB Migrations =
# ======================
# Add new migrations at the bottom of the list; subclass the previous migration.
# 0 -> 20003
class InitialSchema(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasTable('tv_shows') and not self.hasTable('db_version'):
            queries = [
                # original sick beard tables
                'CREATE TABLE db_version (db_version INTEGER);',
                'CREATE TABLE history (action NUMERIC, date NUMERIC, showid NUMERIC, season NUMERIC, episode NUMERIC, quality NUMERIC, resource TEXT, provider TEXT, version NUMERIC)',
                'CREATE TABLE info (last_backlog NUMERIC, last_indexer NUMERIC, last_proper_search NUMERIC)',
                'CREATE TABLE tv_episodes (episode_id INTEGER PRIMARY KEY, showid NUMERIC, indexerid NUMERIC, indexer NUMERIC, name TEXT, season NUMERIC, episode NUMERIC, description TEXT, airdate NUMERIC, hasnfo NUMERIC, hastbn NUMERIC, status NUMERIC, location TEXT, file_size NUMERIC, release_name TEXT, subtitles TEXT, subtitles_searchcount NUMERIC, subtitles_lastsearch TIMESTAMP, is_proper NUMERIC, scene_season NUMERIC, scene_episode NUMERIC, absolute_number NUMERIC, scene_absolute_number NUMERIC, version NUMERIC, release_group TEXT, trakt_watched NUMERIC)',
                'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, indexer_id NUMERIC, indexer NUMERIC, show_name TEXT, location TEXT, network TEXT, genre TEXT, classification TEXT, runtime NUMERIC, quality NUMERIC, airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC, air_by_date NUMERIC, lang TEXT, subtitles NUMERIC, notify_list TEXT, imdb_id TEXT, last_update_indexer NUMERIC, dvdorder NUMERIC, archive_firstmatch NUMERIC, rls_require_words TEXT, rls_ignore_words TEXT, sports NUMERIC, anime NUMERIC, scene NUMERIC, overview TEXT, tag TEXT)',
                'CREATE INDEX idx_showid ON tv_episodes (showid)',
                'CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes (showid,airdate)',
                'CREATE TABLE blacklist (show_id INTEGER, range TEXT, keyword TEXT)',
                'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER, mindexer NUMERIC, PRIMARY KEY (indexer_id, indexer))',
                'CREATE TABLE imdb_info (indexer_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC, akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT, rating TEXT, votes INTEGER, last_update NUMERIC)',
                'CREATE TABLE scene_numbering (indexer TEXT, indexer_id INTEGER, season INTEGER, episode INTEGER, scene_season INTEGER, scene_episode INTEGER, absolute_number NUMERIC, scene_absolute_number NUMERIC, PRIMARY KEY (indexer_id, season, episode))',
                'CREATE TABLE whitelist (show_id INTEGER, range TEXT, keyword TEXT)',
                'CREATE TABLE xem_refresh (indexer TEXT, indexer_id INTEGER PRIMARY KEY, last_refreshed INTEGER)',
                'CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id)',
                'CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate)',
                'CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate)',
                'CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate)',
                'INSERT INTO db_version (db_version) VALUES (20003)'
            ]
            for query in queries:
                self.connection.action(query)

        else:
            cur_db_version = self.checkDBVersion()

            if cur_db_version < MIN_DB_VERSION:
                logger.log_error_and_exit(u'Your database version ('
                                          + str(cur_db_version)
                                          + ') is too old to migrate from what this version of SickGear supports ('
                                          + str(MIN_DB_VERSION) + ').' + "\n"
                                          + 'Upgrade using a previous version (tag) build 496 to build 501 of SickGear first or remove database file to begin fresh.'
                                          )

            if cur_db_version > MAX_DB_VERSION:
                logger.log_error_and_exit(u'Your database version ('
                                          + str(cur_db_version)
                                          + ') has been incremented past what this version of SickGear supports ('
                                          + str(MAX_DB_VERSION) + ').' + "\n"
                                          + 'If you have used other forks of SickGear, your database may be unusable due to their modifications.'
                                          )

        return self.checkDBVersion()


# 9 -> 10
class AddSizeAndSceneNameFields(db.SchemaUpgrade):
    def execute(self):

        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_episodes', 'file_size'):
            self.addColumn('tv_episodes', 'file_size')

        if not self.hasColumn('tv_episodes', 'release_name'):
            self.addColumn('tv_episodes', 'release_name', 'TEXT', '')

        ep_results = self.connection.select('SELECT episode_id, location, file_size FROM tv_episodes')

        logger.log(u'Adding file size to all episodes in DB, please be patient')
        for cur_ep in ep_results:
            if not cur_ep['location']:
                continue

            # if there is no size yet then populate it for us
            if (not cur_ep['file_size'] or not int(cur_ep['file_size'])) and ek.ek(os.path.isfile, cur_ep['location']):
                cur_size = ek.ek(os.path.getsize, cur_ep['location'])
                self.connection.action('UPDATE tv_episodes SET file_size = ? WHERE episode_id = ?',
                                       [cur_size, int(cur_ep['episode_id'])])

        # check each snatch to see if we can use it to get a release name from
        history_results = self.connection.select('SELECT * FROM history WHERE provider != -1 ORDER BY date ASC')

        logger.log(u'Adding release name to all episodes still in history')
        for cur_result in history_results:
            # find the associated download, if there isn't one then ignore it
            download_results = self.connection.select(
                'SELECT resource FROM history WHERE provider = -1 AND showid = ? AND season = ? AND episode = ? AND date > ?',
                [cur_result['showid'], cur_result['season'], cur_result['episode'], cur_result['date']])
            if not download_results:
                logger.log(u'Found a snatch in the history for ' + cur_result[
                    'resource'] + ' but couldn\'t find the associated download, skipping it', logger.DEBUG)
                continue

            nzb_name = cur_result['resource']
            file_name = ek.ek(os.path.basename, download_results[0]['resource'])

            # take the extension off the filename, it's not needed
            if '.' in file_name:
                file_name = file_name.rpartition('.')[0]

            # find the associated episode on disk
            ep_results = self.connection.select(
                'SELECT episode_id, status FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ? AND location != ""',
                [cur_result['showid'], cur_result['season'], cur_result['episode']])
            if not ep_results:
                logger.log(
                    u'The episode ' + nzb_name + ' was found in history but doesn\'t exist on disk anymore, skipping',
                    logger.DEBUG)
                continue

            # get the status/quality of the existing ep and make sure it's what we expect
            ep_status, ep_quality = common.Quality.splitCompositeStatus(int(ep_results[0]['status']))
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
                                           [cur_name, ep_results[0]['episode_id']])
                    break

        # check each snatch to see if we can use it to get a release name from
        empty_results = self.connection.select('SELECT episode_id, location FROM tv_episodes WHERE release_name = ""')

        logger.log(u'Adding release name to all episodes with obvious scene filenames')
        for cur_result in empty_results:

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
            'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, location TEXT, show_name TEXT, tvdb_id NUMERIC, network TEXT, genre TEXT, runtime NUMERIC, quality NUMERIC, airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC, tvr_id NUMERIC, tvr_name TEXT, air_by_date NUMERIC, lang TEXT)')
        sql = 'INSERT INTO tv_shows(show_id, location, show_name, tvdb_id, network, genre, runtime, quality, airs, status, flatten_folders, paused, startyear, tvr_id, tvr_name, air_by_date, lang) SELECT show_id, location, show_name, tvdb_id, network, genre, runtime, quality, airs, status, seasonfolders, paused, startyear, tvr_id, tvr_name, air_by_date, lang FROM tmp_tv_shows'
        self.connection.action(sql)

        # flip the values to be opposite of what they were before
        self.connection.action('UPDATE tv_shows SET flatten_folders = 2 WHERE flatten_folders = 1')
        self.connection.action('UPDATE tv_shows SET flatten_folders = 1 WHERE flatten_folders = 0')
        self.connection.action('UPDATE tv_shows SET flatten_folders = 0 WHERE flatten_folders = 2')
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

    def _update_quality(self, old_quality):
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
        '''
        Unpack, Update, Return new quality values

        Unpack the composite archive/initial values.
        Update either qualities if needed.
        Then return the new compsite quality value.
        '''

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

        # update ANY -- shift existing qualities and add new 1080p qualities, note that rawHD was not added to the ANY template
        old_any = common.Quality.combineQualities(
            [common.Quality.SDTV, common.Quality.SDDVD, common.Quality.HDTV, common.Quality.HDWEBDL >> 2,
             common.Quality.HDBLURAY >> 3, common.Quality.UNKNOWN], [])
        new_any = common.Quality.combineQualities(
            [common.Quality.SDTV, common.Quality.SDDVD, common.Quality.HDTV, common.Quality.FULLHDTV,
             common.Quality.HDWEBDL, common.Quality.FULLHDWEBDL, common.Quality.HDBLURAY, common.Quality.FULLHDBLURAY,
             common.Quality.UNKNOWN], [])

        # update qualities (including templates)
        logger.log(u'[1/4] Updating pre-defined templates and the quality for each show...', logger.MESSAGE)
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

        # update status that are are within the old hdwebdl (1<<3 which is 8) and better -- exclude unknown (1<<15 which is 32768)
        logger.log(u'[2/4] Updating the status for the episodes within each show...', logger.MESSAGE)
        cl = []
        episodes = self.connection.select('SELECT * FROM tv_episodes WHERE status < 3276800 AND status >= 800')
        for cur_episode in episodes:
            cl.append(['UPDATE tv_episodes SET status = ? WHERE episode_id = ?',
                       [self._update_status(cur_episode['status']), cur_episode['episode_id']]])
        self.connection.mass_action(cl)

        # make two seperate passes through the history since snatched and downloaded (action & quality) may not always coordinate together

        # update previous history so it shows the correct action
        logger.log(u'[3/4] Updating history to reflect the correct action...', logger.MESSAGE)
        cl = []
        history_action = self.connection.select('SELECT * FROM history WHERE action < 3276800 AND action >= 800')
        for cur_entry in history_action:
            cl.append(['UPDATE history SET action = ? WHERE showid = ? AND date = ?',
                       [self._update_status(cur_entry['action']), cur_entry['showid'], cur_entry['date']]])
        self.connection.mass_action(cl)

        # update previous history so it shows the correct quality
        logger.log(u'[4/4] Updating history to reflect the correct quality...', logger.MESSAGE)
        cl = []
        history_quality = self.connection.select('SELECT * FROM history WHERE quality < 32768 AND quality >= 8')
        for cur_entry in history_quality:
            cl.append(['UPDATE history SET quality = ? WHERE showid = ? AND date = ?',
                       [self._update_quality(cur_entry['quality']), cur_entry['showid'], cur_entry['date']]])
        self.connection.mass_action(cl)

        self.incDBVersion()

        # cleanup and reduce db if any previous data was removed
        logger.log(u'Performing a vacuum on the database.', logger.DEBUG)
        self.connection.action('VACUUM')
        return self.checkDBVersion()


# 12 -> 13
class AddShowidTvdbidIndex(db.SchemaUpgrade):
    # Adding index on tvdb_id (tv_shows) and showid (tv_episodes) to speed up searches/queries

    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Checking for duplicate shows before adding unique index.')
        MainSanityCheck(self.connection).fix_duplicate_shows('tvdb_id')

        logger.log(u'Adding index on tvdb_id (tv_shows) and showid (tv_episodes) to speed up searches/queries.')
        if not self.hasTable('idx_showid'):
            self.connection.action('CREATE INDEX idx_showid ON tv_episodes (showid);')
        if not self.hasTable('idx_tvdb_id'):
            self.connection.action('CREATE UNIQUE INDEX idx_tvdb_id ON tv_shows (tvdb_id);')

        self.incDBVersion()
        return self.checkDBVersion()


# 13 -> 14
class AddLastUpdateTVDB(db.SchemaUpgrade):
    # Adding column last_update_tvdb to tv_shows for controlling nightly updates
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'last_update_tvdb'):
            logger.log(u'Adding column last_update_tvdb to tv_shows')
            self.addColumn('tv_shows', 'last_update_tvdb', default=1)

        self.incDBVersion()
        return self.checkDBVersion()


# 14 -> 15
class AddDBIncreaseTo15(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version to v%s' % self.checkDBVersion())
        self.incDBVersion()
        return self.checkDBVersion()


# 15 -> 16
class AddIMDbInfo(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Creating IMDb table imdb_info')
        self.connection.action(
            'CREATE TABLE imdb_info (tvdb_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC, akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT, rating TEXT, votes INTEGER, last_update NUMERIC)')

        if not self.hasColumn('tv_shows', 'imdb_id'):
            logger.log(u'Adding IMDb column imdb_id to tv_shows')
            self.addColumn('tv_shows', 'imdb_id')

        self.incDBVersion()
        return self.checkDBVersion()


# 16 -> 17
class AddProperNamingSupport(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'imdb_id')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words'):
            self.setDBVersion(5816)
            return self.checkDBVersion()

        if not self.hasColumn('tv_episodes', 'is_proper'):
            logger.log(u'Adding column is_proper to tv_episodes')
            self.addColumn('tv_episodes', 'is_proper')

        self.incDBVersion()
        return self.checkDBVersion()


# 17 -> 18
class AddEmailSubscriptionTable(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_episodes', 'is_proper')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words')\
                and self.hasColumn('tv_shows', 'skip_notices'):
            self.setDBVersion(5817)
            return self.checkDBVersion()

        if not self.hasColumn('tv_shows', 'notify_list'):
            logger.log(u'Adding column notify_list to tv_shows')
            self.addColumn('tv_shows', 'notify_list', 'TEXT', None)

        self.incDBVersion()
        return self.checkDBVersion()


# 18 -> 19
class AddProperSearch(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'notify_list')\
                and self.hasColumn('tv_shows', 'rls_require_words')\
                and self.hasColumn('tv_shows', 'rls_ignore_words')\
                and self.hasColumn('tv_shows', 'skip_notices')\
                and self.hasColumn('history', 'source'):
            self.setDBVersion(5818)
            return self.checkDBVersion()

        if not self.hasColumn('info', 'last_proper_search'):
            logger.log(u'Adding column last_proper_search to info')
            self.addColumn('info', 'last_proper_search', default=1)

        self.incDBVersion()
        return self.checkDBVersion()


# 19 -> 20
class AddDvdOrderOption(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'dvdorder'):
            logger.log(u'Adding column dvdorder to tv_shows')
            self.addColumn('tv_shows', 'dvdorder', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 20 -> 21
class AddSubtitlesSupport(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'subtitles'):
            logger.log(u'Adding subtitles to tv_shows and tv_episodes')
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

        logger.log(u'Converting TV Shows table to Indexer Scheme...')

        if self.hasTable('tmp_tv_shows'):
            logger.log(u'Removing temp tv show tables left behind from previous updates...')
            self.connection.action('DROP TABLE tmp_tv_shows')

        self.connection.action('ALTER TABLE tv_shows RENAME TO tmp_tv_shows')
        self.connection.action(
            'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, indexer_id NUMERIC, indexer NUMERIC, show_name TEXT, location TEXT, network TEXT, genre TEXT, classification TEXT, runtime NUMERIC, quality NUMERIC, airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC, startyear NUMERIC, air_by_date NUMERIC, lang TEXT, subtitles NUMERIC, notify_list TEXT, imdb_id TEXT, last_update_indexer NUMERIC, dvdorder NUMERIC)')
        self.connection.action(
            'INSERT INTO tv_shows(show_id, indexer_id, show_name, location, network, genre, runtime, quality, airs, status, flatten_folders, paused, startyear, air_by_date, lang, subtitles, notify_list, imdb_id, last_update_indexer, dvdorder) SELECT show_id, tvdb_id, show_name, location, network, genre, runtime, quality, airs, status, flatten_folders, paused, startyear, air_by_date, lang, subtitles, notify_list, imdb_id, last_update_tvdb, dvdorder FROM tmp_tv_shows')
        self.connection.action('DROP TABLE tmp_tv_shows')

        self.connection.action('CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id);')

        self.connection.action('UPDATE tv_shows SET classification = "Scripted"')
        self.connection.action('UPDATE tv_shows SET indexer = 1')

        self.incDBVersion()
        return self.checkDBVersion()


# 22 -> 23
class ConvertTVEpisodesToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Converting TV Episodes table to Indexer Scheme...')

        if self.hasTable('tmp_tv_episodes'):
            logger.log(u'Removing temp tv episode tables left behind from previous updates...')
            self.connection.action('DROP TABLE tmp_tv_episodes')

        self.connection.action('ALTER TABLE tv_episodes RENAME TO tmp_tv_episodes')
        self.connection.action(
            'CREATE TABLE tv_episodes (episode_id INTEGER PRIMARY KEY, showid NUMERIC, indexerid NUMERIC, indexer NUMERIC, name TEXT, season NUMERIC, episode NUMERIC, description TEXT, airdate NUMERIC, hasnfo NUMERIC, hastbn NUMERIC, status NUMERIC, location TEXT, file_size NUMERIC, release_name TEXT, subtitles TEXT, subtitles_searchcount NUMERIC, subtitles_lastsearch TIMESTAMP, is_proper NUMERIC)')
        self.connection.action(
            'INSERT INTO tv_episodes(episode_id, showid, indexerid, name, season, episode, description, airdate, hasnfo, hastbn, status, location, file_size, release_name, subtitles, subtitles_searchcount, subtitles_lastsearch, is_proper) SELECT episode_id, showid, tvdbid, name, season, episode, description, airdate, hasnfo, hastbn, status, location, file_size, release_name, subtitles, subtitles_searchcount, subtitles_lastsearch, is_proper FROM tmp_tv_episodes')
        self.connection.action('DROP TABLE tmp_tv_episodes')

        self.connection.action('CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes(showid,airdate);')
        self.connection.action('CREATE INDEX idx_showid ON tv_episodes (showid);')
        self.connection.action('CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate)')
        self.connection.action('CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate)')
        self.connection.action('CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate)')

        self.connection.action('UPDATE tv_episodes SET indexer = 1')

        self.incDBVersion()
        return self.checkDBVersion()


# 23 -> 24
class ConvertIMDBInfoToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Converting IMDB Info table to Indexer Scheme...')

        if self.hasTable('tmp_imdb_info'):
            logger.log(u'Removing temp imdb info tables left behind from previous updates...')
            self.connection.action('DROP TABLE tmp_imdb_info')

        self.connection.action('ALTER TABLE imdb_info RENAME TO tmp_imdb_info')
        self.connection.action(
            'CREATE TABLE imdb_info (indexer_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year NUMERIC, akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT, certificates TEXT, rating TEXT, votes INTEGER, last_update NUMERIC)')
        self.connection.action(
            'INSERT INTO imdb_info(indexer_id, imdb_id, title, year, akas, runtimes, genres, countries, country_codes, certificates, rating, votes, last_update) SELECT tvdb_id, imdb_id, title, year, akas, runtimes, genres, countries, country_codes, certificates, rating, votes, last_update FROM tmp_imdb_info')
        self.connection.action('DROP TABLE tmp_imdb_info')

        self.incDBVersion()
        return self.checkDBVersion()


# 24 -> 25
class ConvertInfoToIndexerScheme(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Converting Info table to Indexer Scheme...')

        if self.hasTable('tmp_info'):
            logger.log(u'Removing temp info tables left behind from previous updates...')
            self.connection.action('DROP TABLE tmp_info')

        self.connection.action('ALTER TABLE info RENAME TO tmp_info')
        self.connection.action(
            'CREATE TABLE info (last_backlog NUMERIC, last_indexer NUMERIC, last_proper_search NUMERIC)')
        self.connection.action(
            'INSERT INTO info(last_backlog, last_indexer, last_proper_search) SELECT last_backlog, last_tvdb, last_proper_search FROM tmp_info')
        self.connection.action('DROP TABLE tmp_info')

        self.incDBVersion()
        return self.checkDBVersion()


# 25 -> 26
class AddArchiveFirstMatchOption(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'archive_firstmatch'):
            logger.log(u'Adding column archive_firstmatch to tv_shows')
            self.addColumn('tv_shows', 'archive_firstmatch', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 26 -> 27
class AddSceneNumbering(db.SchemaUpgrade):

    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('scene_numbering'):
            self.connection.action('DROP TABLE scene_numbering')

        logger.log(u'Upgrading table scene_numbering ...', logger.MESSAGE)
        self.connection.action(
            'CREATE TABLE scene_numbering (indexer TEXT, indexer_id INTEGER, season INTEGER, episode INTEGER, scene_season INTEGER, scene_episode INTEGER, PRIMARY KEY (indexer_id,season,episode))')

        self.incDBVersion()
        return self.checkDBVersion()


# 27 -> 28
class ConvertIndexerToInteger(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        cl = []
        logger.log(u'Converting Indexer to Integer ...', logger.MESSAGE)
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

        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'rls_require_words'):
            logger.log(u'Adding column rls_require_words to tv_shows')
            self.addColumn('tv_shows', 'rls_require_words', 'TEXT', '')

        if not self.hasColumn('tv_shows', 'rls_ignore_words'):
            logger.log(u'Adding column rls_ignore_words to tv_shows')
            self.addColumn('tv_shows', 'rls_ignore_words', 'TEXT', '')

        self.incDBVersion()
        return self.checkDBVersion()


# 29 -> 30
class AddSportsOption(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'sports'):
            logger.log(u'Adding column sports to tv_shows')
            self.addColumn('tv_shows', 'sports', 'NUMERIC', '0')

        if self.hasColumn('tv_shows', 'air_by_date') and self.hasColumn('tv_shows', 'sports'):
            # update sports column
            logger.log(u'[4/4] Updating tv_shows to reflect the correct sports value...', logger.MESSAGE)
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

        logger.log(u'Adding columns scene_season and scene_episode to tvepisodes')
        self.addColumn('tv_episodes', 'scene_season', 'NUMERIC', 'NULL')
        self.addColumn('tv_episodes', 'scene_episode', 'NUMERIC', 'NULL')

        self.incDBVersion()
        return self.checkDBVersion()


# 31 -> 32
class AddAnimeTVShow(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding column anime to tv_episodes')
        self.addColumn('tv_shows', 'anime', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 32 -> 33
class AddAbsoluteNumbering(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding column absolute_number to tv_episodes')
        self.addColumn('tv_episodes', 'absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 33 -> 34
class AddSceneAbsoluteNumbering(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding columns absolute_number and scene_absolute_number to scene_numbering')
        self.addColumn('scene_numbering', 'absolute_number', 'NUMERIC', '0')
        self.addColumn('scene_numbering', 'scene_absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 34 -> 35
class AddAnimeBlacklistWhitelist(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        cl = []
        cl.append(['CREATE TABLE blacklist (show_id INTEGER, range TEXT, keyword TEXT)'])
        cl.append(['CREATE TABLE whitelist (show_id INTEGER, range TEXT, keyword TEXT)'])
        logger.log(u'Creating table blacklist whitelist')
        self.connection.mass_action(cl)

        self.incDBVersion()
        return self.checkDBVersion()


# 35 -> 36
class AddSceneAbsoluteNumbering2(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding column scene_absolute_number to tv_episodes')
        self.addColumn('tv_episodes', 'scene_absolute_number', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 36 -> 37
class AddXemRefresh(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Creating table xem_refresh')
        self.connection.action(
            'CREATE TABLE xem_refresh (indexer TEXT, indexer_id INTEGER PRIMARY KEY, last_refreshed INTEGER)')

        self.incDBVersion()
        return self.checkDBVersion()


# 37 -> 38
class AddSceneToTvShows(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding column scene to tv_shows')
        self.addColumn('tv_shows', 'scene', 'NUMERIC', '0')

        self.incDBVersion()
        return self.checkDBVersion()


# 38 -> 39
class AddIndexerMapping(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('indexer_mapping'):
            self.connection.action('DROP TABLE indexer_mapping')

        logger.log(u'Adding table indexer_mapping')
        self.connection.action(
            'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER, mindexer NUMERIC, PRIMARY KEY (indexer_id, indexer))')

        self.incDBVersion()
        return self.checkDBVersion()


# 39 -> 40
class AddVersionToTvEpisodes(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Adding columns release_group and version to tv_episodes')
        self.addColumn('tv_episodes', 'release_group', 'TEXT', '')
        self.addColumn('tv_episodes', 'version', 'NUMERIC', '-1')

        logger.log(u'Adding column version to history')
        self.addColumn('history', 'version', 'NUMERIC', '-1')

        self.incDBVersion()
        return self.checkDBVersion()


# 40 -> 10000
class BumpDatabaseVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version')

        self.setDBVersion(10000)
        return self.checkDBVersion()


# 41,42 -> 10001
class Migrate41(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version')

        self.setDBVersion(10001)
        return self.checkDBVersion()


# 4301 -> 10002
class Migrate4301(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version')

        self.setDBVersion(10002)
        return self.checkDBVersion()


# 4302,4400 -> 10003
class Migrate4302(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version')

        self.setDBVersion(10003)
        return self.checkDBVersion()


# 5816 - 5818 -> 15
class MigrateUpstream(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Migrate SickBeard DB v%s into v15' % str(self.checkDBVersion()).replace('58', ''))

        self.setDBVersion(15)
        return self.checkDBVersion()


# 10000 -> 20000
class SickGearDatabaseVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version to new SickGear standards')

        self.setDBVersion(20000)
        return self.checkDBVersion()


# 10001 -> 10000
class RemoveDefaultEpStatusFromTvShows(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Dropping redundant column default_ep_status from tv_shows')
        self.dropColumn('tv_shows', 'default_ep_status')

        self.setDBVersion(10000)
        return self.checkDBVersion()


# 10002 -> 10001
class RemoveMinorDBVersion(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Dropping redundant column db_minor_version from db_version')
        self.dropColumn('db_version', 'db_minor_version')

        self.setDBVersion(10001)
        return self.checkDBVersion()


# 10003 -> 10002
class RemoveMetadataSub(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasColumn('tv_shows', 'sub_use_sr_metadata'):
            logger.log(u'Dropping redundant column metadata sub')
            self.dropColumn('tv_shows', 'sub_use_sr_metadata')

        self.setDBVersion(10002)
        return self.checkDBVersion()


# 20000 -> 20001
class DBIncreaseTo20001(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        logger.log(u'Bumping database version to force a backup before new database code')

        self.connection.action('VACUUM')
        logger.log(u'Performed a vacuum on the database', logger.DEBUG)

        self.setDBVersion(20001)
        return self.checkDBVersion()


# 20001 -> 20002
class AddTvShowOverview(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'overview'):
            logger.log(u'Adding column overview to tv_shows')
            self.addColumn('tv_shows', 'overview', 'TEXT', '')

        self.setDBVersion(20002)
        return self.checkDBVersion()


# 20002 -> 20003
class AddTvShowTags(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if not self.hasColumn('tv_shows', 'tag'):
            logger.log(u'Adding tag to tv_shows')
            self.addColumn('tv_shows', 'tag', 'TEXT', 'Show List')

        self.setDBVersion(20003)
        return self.checkDBVersion()

# 20003 -> 20004
class ChangeMapIndexer(db.SchemaUpgrade):
    def execute(self):
        db.backup_database('sickbeard.db', self.checkDBVersion())

        if self.hasTable('indexer_mapping'):
            self.connection.action('DROP TABLE indexer_mapping')

        logger.log(u'Changing table indexer_mapping')
        self.connection.action(
            'CREATE TABLE indexer_mapping (indexer_id INTEGER, indexer NUMERIC, mindexer_id INTEGER NOT NULL, mindexer NUMERIC, date NUMERIC NOT NULL  DEFAULT 0, status INTEGER NOT NULL  DEFAULT 0, PRIMARY KEY (indexer_id, indexer, mindexer))')

        self.connection.action('CREATE INDEX IF NOT EXISTS idx_mapping ON indexer_mapping (indexer_id, indexer)')

        if not self.hasColumn('info', 'last_run_backlog'):
            logger.log('Adding last_run_backlog to info')
            self.addColumn('info', 'last_run_backlog', 'NUMERIC', 1)

        logger.log(u'Moving table scene_exceptions from cache.db to sickbeard.db')
        if self.hasTable('scene_exceptions_refresh'):
            self.connection.action('DROP TABLE scene_exceptions_refresh')
        self.connection.action('CREATE TABLE scene_exceptions_refresh (list TEXT PRIMARY KEY, last_refreshed INTEGER)')
        if self.hasTable('scene_exceptions'):
            self.connection.action('DROP TABLE scene_exceptions')
        self.connection.action('CREATE TABLE scene_exceptions (exception_id INTEGER PRIMARY KEY, indexer_id INTEGER KEY, show_name TEXT, season NUMERIC, custom NUMERIC)')

        try:
            cachedb = db.DBConnection(filename='cache.db')
            if cachedb.hasTable('scene_exceptions'):
                sqlResults = cachedb.action('SELECT * FROM scene_exceptions')
                cs = []
                for r in sqlResults:
                    cs.append(['INSERT OR REPLACE INTO scene_exceptions (exception_id, indexer_id, show_name, season, custom)'
                               ' VALUES (?,?,?,?,?)', [r['exception_id'], r['indexer_id'], r['show_name'],
                                                         r['season'], r['custom']]])

                if len(cs) > 0:
                    self.connection.mass_action(cs)
        except:
            pass

        keep_tables = {'scene_exceptions', 'scene_exceptions_refresh', 'info', 'indexer_mapping', 'blacklist',
                       'db_version', 'history', 'imdb_info', 'lastUpdate', 'scene_numbering', 'tv_episodes', 'tv_shows',
                       'whitelist', 'xem_refresh'}
        current_tables = set(self.listTables())
        remove_tables = list(current_tables - keep_tables)
        for table in remove_tables:
            self.connection.action('DROP TABLE [%s]' % table)

        self.connection.action('VACUUM')

        self.setDBVersion(20004)
        return self.checkDBVersion()
