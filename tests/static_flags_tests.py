# coding=UTF-8
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
import os
import unittest
from unittest import mock

import test_lib as test

from tornado.web import StaticFileHandler
from sickgear.webserve import BaseStaticFileHandler

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'gui', 'slick'))


def resolve(url_path):
    # the path tornado hands to validate_absolute_path, using the native separator of this OS
    handler = BaseStaticFileHandler.__new__(BaseStaticFileHandler)
    with mock.patch.object(StaticFileHandler, 'validate_absolute_path', lambda _self, _root, path: path):
        return handler.validate_absolute_path(root, os.path.join(root, *url_path.split('/')))


def native(url_path):
    return os.path.join(root, *url_path.split('/'))


class StaticFlagsTests(test.SickbeardTestDBCase):

    def test_lang_png_maps_to_country_svg(self):
        self.assertEqual(native('images/flags/svg/gb.svg'), resolve('images/flags/svg/lang/en.png'))

    def test_country_png_maps_to_svg(self):
        self.assertEqual(native('images/flags/svg/gb.svg'), resolve('images/flags/gb.png'))

    def test_unknown_lang_maps_to_unknown_svg(self):
        self.assertEqual(native('images/flags/svg/unknown.svg'), resolve('images/flags/svg/lang/zz.png'))

    def test_non_flag_path_unchanged(self):
        self.assertEqual(native('images/ico/favicon.ico'), resolve('images/ico/favicon.ico'))


if '__main__' == __name__:
    print('==================')
    print('STARTING - Static flags TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(StaticFlagsTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
