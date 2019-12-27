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
from __future__ import with_statement

import os.path
import re
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import test_lib as test
import sickbeard
from sickbeard.tv import TVShow


class XEMBasicTests(test.SickbeardTestDBCase):
    @staticmethod
    def load_shows_from_db():
        """
        Populates the showList with shows from the database
        """

        my_db = test.db.DBConnection()
        sql_result = my_db.select('SELECT indexer AS tvid, indexer_id AS prodid FROM tv_shows')

        for cur_result in sql_result:
            try:
                show_obj = TVShow(int(cur_result['tvid']), int(cur_result['prodid']))
                sickbeard.showList.append(show_obj)
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
        # print(u"Checking if show " + name + " matches " + curRegex)

        # noinspection PyUnusedLocal
        match = re.search(curRegex, name, re.I)
        # if match:
        #     print(u"Matched " + curRegex + " to " + name)


if '__main__' == __name__:
    print('==================')
    print('STARTING - XEM Scene Numbering TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(XEMBasicTests)
