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

import unittest
import sys, os.path
import datetime
import re

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import test_lib as test
import sickbeard
from sickbeard.helpers import sanitizeSceneName
from sickbeard.name_parser.parser import NameParser
from sickbeard.tv import TVShow

class XEMBasicTests(test.SickbeardTestDBCase):
    def loadShowsFromDB(self):
        """
        Populates the showList with shows from the database
        """

        myDB = test.db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM tv_shows')

        for sqlShow in sqlResults:
            try:
                curShow = TVShow(int(sqlShow['indexer']), int(sqlShow['indexer_id']))
                sickbeard.showList.append(curShow)
            except Exception:
                pass

    def loadFromDB(self):
        """
        Populates the showList with shows from the database
        """

        myDB = test.db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM tv_shows')

        for sqlShow in sqlResults:
            try:
                curShow = TVShow(int(sqlShow['indexer']), int(sqlShow['indexer_id']))
                sickbeard.showList.append(curShow)
            except Exception as e:
                print('There was an error creating the show')

    def test_formating(self):
        name = 'Game.of.Thrones.S03.720p.HDTV.x264-CtrlHD'
        release = 'Game of Thrones'

        # m = re.match('(?P<ep_ab_num>(?>\d{1,3})(?![ip])).+', name)

        escaped_name = re.sub('\\\\[\\s.-]', '\W+', re.escape(release))
        curRegex = '^' + escaped_name + '\W+(?:(?:S\d[\dE._ -])|(?:\d\d?x)|(?:\d{4}\W\d\d\W\d\d)|(?:(?:part|pt)[\._ -]?(\d|[ivx]))|Season\W+\d+\W+|E\d+\W+|(?:\d{1,3}.+\d{1,}[a-zA-Z]{2}\W+[a-zA-Z]{3,}\W+\d{4}.+))'
        # print(u"Checking if show " + name + " matches " + curRegex)

        match = re.search(curRegex, name, re.I)
        # if match:
        #     print(u"Matched " + curRegex + " to " + name)


if __name__ == '__main__':
    print('==================')
    print('STARTING - XEM Scene Numbering TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(XEMBasicTests)