import sys
import os.path
import glob
import unittest
import test_lib as test
import sickbeard
from time import sleep
from sickbeard import db

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

sickbeard.SYS_ENCODING = 'UTF-8'


class MigrationBasicTests(test.SickbeardTestDBCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_migrations(self):
        schema = {
                    0: sickbeard.mainDB.InitialSchema,
                    31: sickbeard.mainDB.AddAnimeTVShow,
                    32: sickbeard.mainDB.AddAbsoluteNumbering,
                    33: sickbeard.mainDB.AddSceneAbsoluteNumbering,
                    34: sickbeard.mainDB.AddAnimeBlacklistWhitelist,
                    35: sickbeard.mainDB.AddSceneAbsoluteNumbering2,
                    36: sickbeard.mainDB.AddXemRefresh,
                    37: sickbeard.mainDB.AddSceneToTvShows,
                    38: sickbeard.mainDB.AddIndexerMapping,
                    39: sickbeard.mainDB.AddVersionToTvEpisodes,
                    41: AddDefaultEpStatusToTvShows,
                }

        count = 1
        while count < len(schema.keys()):
            myDB = db.DBConnection()

            for version in sorted(schema.keys())[:count]:
                update = schema[version](myDB)
                update.execute()
                sleep(0.1)

            db.MigrationCode(myDB)
            myDB.close()
            for filename in glob.glob(os.path.join(test.TESTDIR, test.TESTDBNAME) +'*'):
                os.remove(filename)

            sleep(0.1)
            count += 1


class AddDefaultEpStatusToTvShows(db.SchemaUpgrade):
    def execute(self):
        self.addColumn("tv_shows", "default_ep_status", "TEXT", "")
        self.setDBVersion(41)


if __name__ == '__main__':
    print "=================="
    print "STARTING - MIGRATION TESTS"
    print "=================="
    print "######################################################################"
    suite = unittest.TestLoader().loadTestsFromTestCase(MigrationBasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
