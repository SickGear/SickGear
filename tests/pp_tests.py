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

import os.path
import random
import sys
import test_lib as test
import unittest

import sickbeard
from sickbeard.helpers import real_path
from sickbeard.name_cache import addNameToCache
from sickbeard.postProcessor import PostProcessor
from sickbeard.processTV import ProcessTVShow
from sickbeard.tv import TVEpisode, TVShow

if 'win32' == sys.platform:
    root_folder_tests = [
        # root_dirs, path, expected
        ('1|C:\\dir', 'C:\\folder', None),
        ('1|c:\\dir', 'c:\\dir', 'c:\\dir'),
        ('1|c:\\dir2', 'c:\\dir2\\dir', 'c:\\dir2'),
        ('1|c:\\tv_complete|c:\\tv', 'c:\\tv', 'c:\\tv')
    ]
else:
    root_folder_tests = [
        # root_dirs, path, expected
        ('1|~/dir', '~/dir/dir', '~/dir'),
        ('1|/mnt/hdd/dir', '/mnt/hdd/folder', None),
        ('1|/mnt/hdd/dir', '/mnt/hdd/dir', '/mnt/hdd/dir'),
        ('1|/mnt/hdd/dir2', '/mnt/hdd/dir2/dir', '/mnt/hdd/dir2'),
        ('1|/mnt/hdd/tv_complete|/mnt/hdd/tv', '/mnt/hdd/tv', '/mnt/hdd/tv')
    ]


class PPInitTests(unittest.TestCase):

    def setUp(self):
        self.pp = PostProcessor(test.FILEPATH)

    def test_init_file_name(self):
        self.assertEqual(self.pp.file_name, test.FILENAME)

    def test_init_folder_name(self):
        self.assertEqual(self.pp.folder_name, test.SHOWNAME)


class PPBasicTests(test.SickbeardTestDBCase):

    def test_process(self):
        show = TVShow(1, 3)
        show.name = test.SHOWNAME
        show.location = test.SHOWDIR
        show.saveToDB()

        sickbeard.showList = [show]
        ep = TVEpisode(show, test.SEASON, test.EPISODE)
        ep.name = 'some ep name'
        ep.saveToDB()

        addNameToCache('show name', 3)
        sickbeard.PROCESS_METHOD = 'move'

        pp = PostProcessor(test.FILEPATH)
        self.assertTrue(pp.process())


class PPFolderTests(test.SickbeardTestDBCase):

    def test_root_folder(self):
        for root_dirs, path, expected in root_folder_tests:
            sickbeard.ROOT_DIRS = root_dirs
            self.assertEqual(expected and real_path(expected) or expected, ProcessTVShow.find_parent(path))


if '__main__' == __name__:

    print('===============================')
    print('STARTING - Post Processor TESTS')
    print('===============================')

    suite = unittest.TestLoader().loadTestsFromTestCase(PPInitTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    suite = unittest.TestLoader().loadTestsFromTestCase(PPBasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    suite = unittest.TestLoader().loadTestsFromTestCase(PPFolderTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print('===============================')
