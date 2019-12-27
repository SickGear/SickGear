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
from random import  randint

import sickbeard
from sickbeard.tv import TVEpisode, TVShow, TVidProdid, prodid_bitshift


class TVShowTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVShowTests, self).setUp()
        sickbeard.showList = []

    def test_init_indexerid(self):
        show_obj = TVShow(1, 1, 'en')
        self.assertEqual(show_obj.prodid, 1)

    def test_change_indexerid(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987

        show_obj.save_to_db()
        show_obj.load_from_db()

        show_obj.prodid = 2
        show_obj.save_to_db()
        show_obj.load_from_db()

        self.assertEqual(show_obj.prodid, 2)

    def test_set_name(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'newName'
        show_obj.save_to_db()
        show_obj.load_from_db()
        self.assertEqual(show_obj.name, 'newName')


class TVEpisodeTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVEpisodeTests, self).setUp()
        sickbeard.showList = []

    def test_init_empty_db(self):
        show_obj = TVShow(1, 1, 'en')
        ep_obj = TVEpisode(show_obj, 1, 1)
        ep_obj.name = 'asdasdasdajkaj'
        ep_obj.save_to_db()
        ep_obj.load_from_db(1, 1)
        self.assertEqual(ep_obj.name, 'asdasdasdajkaj')


class TVTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVTests, self).setUp()
        sickbeard.showList = []

    @staticmethod
    def test_getEpisode():
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987
        show_obj.save_to_db()
        sickbeard.showList = [show_obj]


class TVFormatPatternTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVFormatPatternTests, self).setUp()
        sickbeard.showList = []

    def test_getEpisode(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987
        sickbeard.showList = [show_obj]
        show_obj.sxe_ep_obj[1] = {}
        show_obj.sxe_ep_obj[1][1] = TVEpisode(show_obj, 1, 1, '16)')
        show_obj.sxe_ep_obj[1][1].dirty = False
        show_obj.sxe_ep_obj[1][1].name = None
        self.assertEqual(show_obj.sxe_ep_obj[1][1].dirty, False)
        self.assertEqual(
            show_obj.sxe_ep_obj[1][1]._format_pattern('%SN - %Sx%0E - %EN - %QN'),
            'show name - 1x01 - tba - Unknown')
        show_obj.sxe_ep_obj[1][1].dirty = False
        show_obj.sxe_ep_obj[1][1].name = 'ep name'
        self.assertEqual(show_obj.sxe_ep_obj[1][1].dirty, True)
        self.assertEqual(
            show_obj.sxe_ep_obj[1][1]._format_pattern('%SN - %Sx%0E - %EN - %QN'),
            'show name - 1x01 - ep name - Unknown')


class TVidProdidTests(test.SickbeardTestDBCase):
    @staticmethod
    def max_bits(b):
        return (1 << b) - 1

    def test_TVidProdid(self):
        max_tvid = self.max_bits(prodid_bitshift)
        max_prodid = self.max_bits(60)
        i = 0
        while 1000 > i:
            i += 1
            tvid = randint(1, max_tvid)
            prodid = randint(1, max_prodid)
            tvid_prodid_obj = TVidProdid({tvid: prodid})

            msg_vars = ': tvid = %s ; prodid = %s' % (tvid, prodid)

            self.assertEqual(tvid, tvid_prodid_obj.tvid, msg='dict tvid test%s' % msg_vars)
            self.assertEqual(prodid, tvid_prodid_obj.prodid, msg='dict prodid test%s' % msg_vars)

            self.assertEqual((tvid, prodid), tvid_prodid_obj.tuple, msg='tuple test%s' % msg_vars)
            self.assertEqual({tvid: prodid}, tvid_prodid_obj.dict, msg='dict test%s' % msg_vars)
            self.assertEqual([tvid, prodid], tvid_prodid_obj.list, msg='list test%s' % msg_vars)

            new_sid = prodid << prodid_bitshift | tvid
            self.assertEqual(new_sid, tvid_prodid_obj.int, msg='int test%s' % msg_vars)

            sid = tvid_prodid_obj.int
            reverse_obj = TVidProdid(sid)
            self.assertEqual(tvid, reverse_obj.tvid, msg='reverse int tvid test%s' % msg_vars)
            self.assertEqual(prodid, reverse_obj.prodid, msg='reverse int prodid test%s' % msg_vars)

            str_reverse_obj = TVidProdid('%s%s%s' % (tvid, TVidProdid.glue, prodid))
            self.assertEqual(tvid, str_reverse_obj.tvid, msg='reverse str tvid test%s' % msg_vars)
            self.assertEqual(prodid, str_reverse_obj.prodid, msg='reverse str prodid test%s' % msg_vars)


if '__main__' == __name__:
    print('==================')
    print('STARTING - TV TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVShowTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVEpisodeTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVFormatPatternTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVidProdidTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
