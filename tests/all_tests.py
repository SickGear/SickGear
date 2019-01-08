#!/usr/bin/env python2
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
if '__main__' == __name__:
    import warnings
    warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

    import glob
    import unittest
    import sys

    test_file_strings = [x for x in glob.glob('*_tests.py') if x not in __file__]
    module_strings = [file_string[0:len(file_string) - 3] for file_string in test_file_strings]
    suites = [unittest.defaultTestLoader.loadTestsFromName(file_string) for file_string in module_strings]
    testSuite = unittest.TestSuite(suites)

    print('==================')
    print('STARTING - ALL TESTS')
    print('==================')

    test_individually = False
    
    if not test_individually:
        print('this will include')
        for includedfiles in test_file_strings:
            print('- ' + includedfiles)

        text_runner = unittest.TextTestRunner().run(testSuite)
        if not text_runner.wasSuccessful():
            sys.exit(-1)
    else:
        complete_success = True
        for file_string in module_strings:
            testSuite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName(file_string)])
            print('- running ' + file_string)
            test_runner = unittest.TextTestRunner().run(testSuite)
            if complete_success and not test_runner.wasSuccessful():
                complete_success = False
        if not complete_success:
            sys.exit(-1)
