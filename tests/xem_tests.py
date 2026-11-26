# coding=UTF-8
# Author: Dennis Lutter <lad1337@gmail.com>
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

import re
import sys
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import test_lib as test
import sickgear
from sickgear import db, scene_numbering
from sickgear.sgdatetime import SGDatetime
from sickgear.tv import TVShow


class XEMBasicTests(test.SickbeardTestDBCase):
    @staticmethod
    def load_shows_from_db():
        """
        Populates the showList with shows from the database
        """

        with test.db.DBConnection() as sg_db:
            sql_result = sg_db.select('SELECT indexer AS tvid, indexer_id AS prodid FROM tv_shows')

        for cur_result in sql_result:
            try:
                show_obj = TVShow(int(cur_result['tvid']), int(cur_result['prodid']))
                sickgear.showList.append(show_obj)
                sickgear.showDict[show_obj.sid_int] = show_obj
            except (BaseException, Exception):
                pass

    @staticmethod
    def test_formating():
        name = 'Game.of.Thrones.S03.720p.HDTV.x264-CtrlHD'
        release = 'Game of Thrones'

        # m = re.match('(?P<ep_ab_num>(?>\d{1,3})(?![ip])).+', name)

        escaped_name = re.sub('\\\\[\\s.-]', r'\\W+', re.escape(release))
        curRegex = '^' + escaped_name + r'\W+(?:(?:S\d[\dE._ -])|(?:\d\d?x)|(?:\d{4}\W\d\d\W\d\d)|(?:(?:part|pt)' \
                                        r'[\._ -]?(\d|[ivx]))|Season\W+\d+\W+|E\d+\W+|(?:\d{1,3}.+\d{1,}[a-zA-Z]{2}' \
                                        r'\W+[a-zA-Z]{3,}\W+\d{4}.+))'
        # print("Checking if show " + name + " matches " + curRegex)

        # noinspection PyUnusedLocal
        match = re.search(curRegex, name, re.I)
        # if match:
        #     print("Matched " + curRegex + " to " + name)


class XEMRefreshTests(test.SickbeardTestDBCase):
    """ the many calls of xem_refresh for the episodes of one show read the db once, and ask xem once a day """

    def setUp(self):
        super(XEMRefreshTests, self).setUp()
        scene_numbering._xem_next_check.clear()
        self.release_map_xem = sickgear.scene_exceptions.MEMCACHE.get('release_map_xem', {})
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = {1: [123456]}
        self.selects = []
        org_select = db.DBConnection.select

        def select(conn, query, *args, **kwargs):
            self.selects.append(query)
            return org_select(conn, query, *args, **kwargs)

        self.patches = [mock.patch.object(db.DBConnection, 'select', select),
                        mock.patch('sickgear.helpers.get_url', return_value=None)]
        self.get_url = [_p.start() for _p in self.patches][1]

    def tearDown(self):
        for cur_patch in self.patches:
            cur_patch.stop()
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = self.release_map_xem
        scene_numbering._xem_next_check.clear()
        super(XEMRefreshTests, self).tearDown()

    @staticmethod
    def refreshed_at(timestamp):
        with db.DBConnection() as sg_db:
            sg_db.upsert('xem_refresh', dict(last_refreshed=timestamp), dict(indexer=1, indexer_id=123456))

    def test_table_is_read_once(self):
        self.refreshed_at(SGDatetime.timestamp_near() - 60)
        for _ in range(5):
            scene_numbering.xem_refresh(1, 123456)
        self.assertEqual(1, len(self.selects))
        self.get_url.assert_not_called()

    def test_old_data_is_refreshed_once(self):
        self.refreshed_at(SGDatetime.timestamp_near() - 90000)
        for _ in range(5):
            scene_numbering.xem_refresh(1, 123456)
        self.assertEqual(1, len(self.selects))
        self.get_url.assert_called_once()

    def test_force_refreshes(self):
        self.refreshed_at(SGDatetime.timestamp_near() - 60)
        scene_numbering.xem_refresh(1, 123456)
        scene_numbering.xem_refresh(1, 123456, force=True)
        self.get_url.assert_called_once()

    def test_show_with_no_xem_mapping(self):
        scene_numbering.xem_refresh(1, 999)
        self.assertEqual([], self.selects)


if '__main__' == __name__:
    print('==================')
    print('STARTING - XEM Scene Numbering TESTS')
    print('==================')
    print('######################################################################')
    for cur_case in (XEMBasicTests, XEMRefreshTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
