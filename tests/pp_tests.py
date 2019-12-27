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
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

import os.path
import sys
import test_lib as test
import unittest

import sickbeard
from sickbeard.helpers import real_path
from sickbeard.name_cache import addNameToCache
from sickbeard.postProcessor import PostProcessor
from sickbeard.processTV import ProcessTVShow
from sickbeard.tv import TVEpisode, TVShow, logger
from sickbeard.indexers.indexer_config import TVINFO_TVDB, TVINFO_TVMAZE

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

script_tests = [{'name': 'TheTVdb',
                 'EXTRA_SCRIPTS': 'extra_script.py',
                 'SG_EXTRA_SCRIPTS': 'sg_extra_script.py',
                 'file_path': '/mnt/hdd/folder/',
                 'tvid': TVINFO_TVDB,
                 'result': [False, False]},
                {'name': 'TVMaze',
                 'EXTRA_SCRIPTS': 'extra_script.py',
                 'SG_EXTRA_SCRIPTS': 'sg_extra_script.py',
                 'file_path': '/mnt/hdd/folder/',
                 'tvid': TVINFO_TVMAZE,
                 'result': [True, False]},
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
        show_obj = TVShow(1, 3)
        show_obj.tvid = TVINFO_TVDB
        show_obj.name = test.SHOWNAME
        show_obj.location = test.SHOWDIR
        show_obj.save_to_db()

        sickbeard.showList = [show_obj]
        ep_obj = TVEpisode(show_obj, test.SEASON, test.EPISODE)
        ep_obj.name = 'some ep name'
        ep_obj.release_name = 'test setter'
        ep_obj.save_to_db()

        addNameToCache('show name', tvid=TVINFO_TVDB, prodid=3)
        sickbeard.PROCESS_METHOD = 'move'

        pp = PostProcessor(test.FILEPATH)
        self.assertTrue(pp.process())


class PPFolderTests(test.SickbeardTestDBCase):

    def test_root_folder(self):
        for root_dirs, path, expected in root_folder_tests:
            sickbeard.ROOT_DIRS = root_dirs
            self.assertEqual(expected and real_path(expected) or expected, ProcessTVShow.find_parent(path))


class PPTest(PostProcessor):

    def __init__(self, file_path, nzb_name=None, process_method=None, force_replace=None, use_trash=None,
                 webhandler=None, show_obj=None):
        super(PPTest, self).__init__(file_path, nzb_name, process_method, force_replace,
                                     use_trash, webhandler, show_obj)
        self.has_errors = []
        self.current_script = None
        self.current_script_num = -1

    def _execute_extra_scripts(self, script_name, ep_obj, new_call=False):
        if self.current_script != script_name:
            self.current_script_num += 1
            self.has_errors.append(False)
        self.current_script = script_name
        super(PPTest, self)._execute_extra_scripts(script_name, ep_obj, new_call)

    def _log(self, message, level=logger.MESSAGE):
        if logger.ERROR == level:
            self.has_errors[self.current_script_num] = True
        if 'Script result: ' in message and 'ERROR' in message:
            self.has_errors[self.current_script_num] = True
        super(PPTest, self)._log(message, level)


class PPScriptTests(test.SickbeardTestDBCase):

    @staticmethod
    def _create_ep(tvid):
        show_obj = TVShow(tvid, 3)
        show_obj.name = test.SHOWNAME
        show_obj.location = test.SHOWDIR
        show_obj.save_to_db()

        sickbeard.showList = [show_obj]
        ep_obj = TVEpisode(show_obj, test.SEASON, test.EPISODE)
        ep_obj.name = 'some ep name'
        ep_obj.location = '/mnt/hdd/folder/the show/season 01/the show - s01e01 - name.mkv'
        ep_obj.save_to_db()
        return ep_obj

    @staticmethod
    def _remove_show(ep_obj):
        ep_obj.show_obj.delete_show()

    def test_extra_script(self):
        self.longMessage = True
        base_path = os.path.join(test.TESTDIR, 'scripts')

        for t in script_tests:
            self.has_errors = []
            self.current_script = None
            self.current_script_num = -1
            sickbeard.EXTRA_SCRIPTS = ['%s %s' % (sys.executable, os.path.join(base_path, t['EXTRA_SCRIPTS']))]
            sickbeard.SG_EXTRA_SCRIPTS = ['%s %s' % (sys.executable, os.path.join(base_path, t['SG_EXTRA_SCRIPTS']))]
            pp = PPTest(t['file_path'])
            ep_obj = self._create_ep(t['tvid'])
            pp._run_extra_scripts(ep_obj)
            self.assertEqual(t['result'], pp.has_errors, msg='Test Case: %s' % t['name'])
            self._remove_show(ep_obj)


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
    suite = unittest.TestLoader().loadTestsFromTestCase(PPScriptTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print('===============================')
