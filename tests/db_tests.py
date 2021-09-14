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

    def tearDown(self):
        try:
            self.db.close()
        except (BaseException, Exception):
            pass
        super(DBBasicTests, self).tearDown()

    def is_testdb(self, version):
        if isinstance(version, integer_types):
            return 100000 <= version

    def test_select(self):
        self.db.select('SELECT * FROM tv_episodes WHERE showid = ? AND location != ""', [0000])
        self.db.close()
        self.assertEqual(cache_db.TEST_BASE_VERSION is not None, self.is_testdb(cache_db.MAX_DB_VERSION))
        self.assertEqual(mainDB.TEST_BASE_VERSION is not None, self.is_testdb(mainDB.MAX_DB_VERSION))
        self.assertEqual(failed_db.TEST_BASE_VERSION is not None, self.is_testdb(failed_db.MAX_DB_VERSION))

    def test_mass_action(self):
        field_list = ['show_id', 'indexer_id', 'indexer', 'show_name', 'location', 'network', 'genre', 'classification',
                      'runtime', 'quality', 'airs', 'status', 'flatten_folders', 'paused', 'startyear', 'air_by_date',
                      'lang', 'subtitles', 'notify_list', 'imdb_id', 'last_update_indexer', 'dvdorder',
                      'archive_firstmatch', 'rls_require_words', 'rls_ignore_words', 'sports', 'anime', 'scene',
                      'overview', 'tag', 'prune', 'rls_global_exclude_ignore', 'rls_global_exclude_require', 'airtime',
                      'network_id', 'network_is_stream', 'src_update_timestamp']
        insert_para = [123, 321, 1, 'Test Show', '', 'ABC', 'Comedy', '14', 45, 1, 'Mondays', 1, 0, 0, 2010, 0, 'en',
                       '', '', 'tt123456', 1234567, 0, 0, None, None, 0, 0, 0, 'Some Show', None, 0, None, None, 2000,
                       4, 0, 852645]
        result = self.db.mass_action([
            ['REPLACE INTO tv_shows (show_id, indexer_id, indexer, show_name, location, network, genre, classification,'
             ' runtime, quality, airs, status, flatten_folders, paused, startyear, air_by_date, lang, subtitles,'
             ' notify_list, imdb_id, last_update_indexer, dvdorder, archive_firstmatch, rls_require_words,'
             ' rls_ignore_words, sports, anime, scene, overview, tag, prune, rls_global_exclude_ignore,'
             ' rls_global_exclude_require, airtime, network_id, network_is_stream, src_update_timestamp)'
             ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
             insert_para],
            ['SELECT * FROM tv_shows WHERE show_id = ? AND indexer = ?', [123, 1]]
        ])
        for i, f in enumerate(field_list):
            self.assertEqual(str(result[-1][0][f]), str(insert_para[i]),
                             msg='Field %s: %s != %s' % (f, result[-1][0][f], insert_para[i]))


if '__main__' == __name__:
    print('==================')
    print('STARTING - DB TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(DBBasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
