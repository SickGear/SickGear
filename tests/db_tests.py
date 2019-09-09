# coding=UTF-8
# Author: Dennis Lutter <lad1337@gmail.com>
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

from __future__ import print_function
import unittest
import test_lib as test
from sickbeard import cache_db, mainDB, failed_db
from six import integer_types


class DBBasicTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(DBBasicTests, self).setUp()
        self.db = test.db.DBConnection()

    def is_testdb(self, version):
        if isinstance(version, integer_types):
            return 100000 <= version

    def test_select(self):
        self.db.select('SELECT * FROM tv_episodes WHERE showid = ? AND location != ""', [0000])
        self.db.close()
        self.assertEqual(cache_db.TEST_BASE_VERSION is not None, self.is_testdb(cache_db.MAX_DB_VERSION))
        self.assertEqual(mainDB.TEST_BASE_VERSION is not None, self.is_testdb(mainDB.MAX_DB_VERSION))
        self.assertEqual(failed_db.TEST_BASE_VERSION is not None, self.is_testdb(failed_db.MAX_DB_VERSION))


if '__main__' == __name__:
    print('==================')
    print('STARTING - DB TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(DBBasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
