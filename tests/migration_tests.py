from __future__ import print_function
import sys
import os.path
import glob
import unittest
import test_lib as test
import sickbeard
from time import sleep
from sickbeard import db, logger
from sickbeard.databases.mainDB import MIN_DB_VERSION, MAX_DB_VERSION

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

sickbeard.SYS_ENCODING = 'UTF-8'


class MigrationBasicTests(test.SickbeardTestDBCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    @staticmethod
    def test_migrations():
        schema = {0: OldInitialSchema,  # sickbeard.mainDB.InitialSchema,
                  31: sickbeard.mainDB.AddAnimeTVShow,
                  32: sickbeard.mainDB.AddAbsoluteNumbering,
                  33: sickbeard.mainDB.AddSceneAbsoluteNumbering,
                  34: sickbeard.mainDB.AddAnimeAllowlistBlocklist,
                  35: sickbeard.mainDB.AddSceneAbsoluteNumbering2,
                  36: sickbeard.mainDB.AddXemRefresh,
                  37: sickbeard.mainDB.AddSceneToTvShows,
                  38: sickbeard.mainDB.AddIndexerMapping,
                  39: sickbeard.mainDB.AddVersionToTvEpisodes,
                  41: AddDefaultEpStatusToTvShows
                  }

        count = 1
        while count < len(schema):
            my_db = db.DBConnection()

            for version in sorted(schema.keys())[:count]:
                update = schema[version](my_db)
                update.execute()
                sleep(0.1)

            db.MigrationCode(my_db)
            my_db.close()
            for filename in glob.glob(os.path.join(test.TESTDIR, test.TESTDBNAME) + '*'):
                os.remove(filename)

            sleep(0.1)
            count += 1


# 0 -> 31
class OldInitialSchema(db.SchemaUpgrade):
    def execute(self):
        db.backup_database(self.connection, 'sickbeard.db', self.checkDBVersion())

        if not self.hasTable('tv_shows') and not self.hasTable('db_version'):
            queries = [
                'CREATE TABLE db_version (db_version INTEGER);',
                'CREATE TABLE history ('
                'action NUMERIC, date NUMERIC, showid NUMERIC, season NUMERIC, episode NUMERIC,'
                ' quality NUMERIC, resource TEXT, provider TEXT);',
                'CREATE TABLE imdb_info (indexer_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT,'
                ' year NUMERIC, akas TEXT, runtimes NUMERIC, genres TEXT, countries TEXT, country_codes TEXT,'
                ' certificates TEXT, rating TEXT, votes INTEGER, last_update NUMERIC);',
                'CREATE TABLE info (last_backlog NUMERIC, last_indexer NUMERIC, last_proper_search NUMERIC);',
                'CREATE TABLE scene_numbering(indexer TEXT, indexer_id INTEGER,'
                ' season INTEGER, episode INTEGER,scene_season INTEGER, scene_episode INTEGER,'
                ' PRIMARY KEY(indexer_id, season, episode));',
                'CREATE TABLE tv_shows (show_id INTEGER PRIMARY KEY, indexer_id NUMERIC, indexer NUMERIC,'
                ' show_name TEXT, location TEXT, network TEXT, genre TEXT, classification TEXT, runtime NUMERIC,'
                ' quality NUMERIC, airs TEXT, status TEXT, flatten_folders NUMERIC, paused NUMERIC,'
                ' startyear NUMERIC, air_by_date NUMERIC, lang TEXT, subtitles NUMERIC, notify_list TEXT,'
                ' imdb_id TEXT, last_update_indexer NUMERIC, dvdorder NUMERIC, archive_firstmatch NUMERIC,'
                ' rls_require_words TEXT, rls_ignore_words TEXT, sports NUMERIC);',
                'CREATE TABLE tv_episodes (episode_id INTEGER PRIMARY KEY, showid NUMERIC,'
                ' indexerid NUMERIC, indexer NUMERIC, name TEXT, season NUMERIC, episode NUMERIC,'
                ' description TEXT, airdate NUMERIC, hasnfo NUMERIC, hastbn NUMERIC, status NUMERIC,'
                ' location TEXT, file_size NUMERIC, release_name TEXT, subtitles TEXT, subtitles_searchcount NUMERIC,'
                ' subtitles_lastsearch TIMESTAMP, is_proper NUMERIC, scene_season NUMERIC, scene_episode NUMERIC);',
                'CREATE UNIQUE INDEX idx_indexer_id ON tv_shows (indexer_id);',
                'CREATE INDEX idx_showid ON tv_episodes (showid);',
                'CREATE INDEX idx_sta_epi_air ON tv_episodes (status,episode, airdate);',
                'CREATE INDEX idx_sta_epi_sta_air ON tv_episodes (season,episode, status, airdate);',
                'CREATE INDEX idx_status ON tv_episodes (status,season,episode,airdate);',
                'CREATE INDEX idx_tv_episodes_showid_airdate ON tv_episodes(showid,airdate);',
                'INSERT INTO db_version (db_version) VALUES (31);'
            ]
            for query in queries:
                self.connection.action(query)

        else:
            cur_db_version = self.checkDBVersion()

            if cur_db_version < MIN_DB_VERSION:
                logger.log_error_and_exit(
                    u'Your database version ('
                    + str(cur_db_version)
                    + ') is too old to migrate from what this version of SickGear supports ('
                    + str(MIN_DB_VERSION) + ').' + '\n'
                    + 'Upgrade using a previous version (tag) build 496 to build 501 of SickGear first or'
                      ' remove database file to begin fresh.'
                )

            if cur_db_version > MAX_DB_VERSION:
                logger.log_error_and_exit(
                    u'Your database version ('
                    + str(cur_db_version)
                    + ') has been incremented past what this version of SickGear supports ('
                    + str(MAX_DB_VERSION) + ').' + '\n'
                    + 'If you have used other forks of SickGear,'
                      ' your database may be unusable due to their modifications.'
                )

        return self.checkDBVersion()


class AddDefaultEpStatusToTvShows(db.SchemaUpgrade):
    def execute(self):
        self.addColumn('tv_shows', 'default_ep_status', 'TEXT', '')
        self.setDBVersion(41, check_db_version=False)


if '__main__' == __name__:
    print('==================')
    print('Starting - Migration Tests')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(MigrationBasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
