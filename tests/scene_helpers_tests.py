# coding=utf-8
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')

import unittest
import test_lib as test

import sys
import os.path
sys.path.insert(1, os.path.abspath('..'))

from sickbeard import show_name_helpers, scene_exceptions, common, name_cache
from sickbeard.indexers.indexer_config import TVINFO_TVDB

import sickbeard
from sickbeard import db
from sickbeard.tv import TVShow


class SceneTests(test.SickbeardTestDBCase):

    def _test_allPossibleShowNames(self, name, prodid=0, expected=None, season=-1):
        expected = (expected, [])[None is expected]
        s = TVShow(TVINFO_TVDB, prodid)
        s.tvid = TVINFO_TVDB
        s.name = name

        result = show_name_helpers.allPossibleShowNames(s, season=season)
        self.assertTrue(len(set(expected).intersection(set(result))) == len(expected))

    def _test_pass_wordlist_checks(self, name, expected):
        result = show_name_helpers.pass_wordlist_checks(name)
        self.assertEqual(result, expected)

    def test_allPossibleShowNames(self):
        # common.sceneExceptions[-1] = ['Exception Test']
        my_db = db.DBConnection()
        my_db.mass_action([
            ['INSERT INTO scene_exceptions (indexer, indexer_id, show_name, season) VALUES (?,?,?,?)',
             [TVINFO_TVDB, -1, 'Exception Test', -1]],
            ['INSERT INTO scene_exceptions (indexer, indexer_id, show_name, season) VALUES (?,?,?,?)',
             [TVINFO_TVDB, -1, 'Season Test', 19]]
                           ])
        common.countryList['Full Country Name'] = 'FCN'

        self._test_allPossibleShowNames('Show Name', expected=['Show Name'])
        self._test_allPossibleShowNames('Show Name', -1, expected=['Show Name', 'Exception Test'])
        self._test_allPossibleShowNames('Show Name FCN', expected=['Show Name FCN', 'Show Name (Full Country Name)'])
        self._test_allPossibleShowNames(
            'Show Name (FCN)', expected=['Show Name (FCN)', 'Show Name (Full Country Name)'])
        self._test_allPossibleShowNames(
            'Show Name Full Country Name', expected=['Show Name Full Country Name', 'Show Name (FCN)'])
        self._test_allPossibleShowNames(
            'Show Name (Full Country Name)', expected=['Show Name (Full Country Name)', 'Show Name (FCN)'])
        self._test_allPossibleShowNames('Show Name', -1, expected=['Season Test'], season=19)

    def test_pass_wordlist_checks(self):
        self._test_pass_wordlist_checks('Show.S02.German.Stuff-Grp', False)
        self._test_pass_wordlist_checks('Show.S02.Some.Stuff-Core2HD', False)
        self._test_pass_wordlist_checks('Show.S02.Some.German.Stuff-Grp', False)
        # self._test_pass_wordlist_checks('German.Show.S02.Some.Stuff-Grp', True)
        self._test_pass_wordlist_checks('Show.S02.This.Is.German', False)


class SceneExceptionTestCase(test.SickbeardTestDBCase):

    def setUp(self):
        super(SceneExceptionTestCase, self).setUp()

        sickbeard.showList = []
        sickbeard.showDict = {}
        for s in [TVShow(TVINFO_TVDB, 79604), TVShow(TVINFO_TVDB, 251085), TVShow(TVINFO_TVDB, 78744)]:
            sickbeard.showList.append(s)
            sickbeard.showDict[s.sid_int] = s
        sickbeard.webserve.Home.make_showlist_unique_names()
        scene_exceptions.retrieve_exceptions()
        name_cache.buildNameCache()

    def test_sceneExceptionsEmpty(self):
        self.assertEqual(scene_exceptions.get_scene_exceptions(0, 0), [])

    def test_sceneExceptionsBlack_Lagoon(self):
        self.assertEqual(sorted(scene_exceptions.get_scene_exceptions(1, 79604)), ['Black-Lagoon'])

    def test_sceneExceptionByName(self):
        self.assertEqual(scene_exceptions.get_scene_exception_by_name(
            'Black-Lagoon'), [1, 79604, -1])
        self.assertEqual(scene_exceptions.get_scene_exception_by_name(
            'Black Lagoon: The Second Barrage'), [1, 79604, 2])
        self.assertEqual(scene_exceptions.get_scene_exception_by_name(
            'Rokka no Yuusha'), [None, None, None])

    def test_sceneExceptionByNameAnime(self):
        sickbeard.showList = []
        sickbeard.showDict = {}
        for s in [TVShow(TVINFO_TVDB, 79604), TVShow(TVINFO_TVDB, 295243)]:
            s.anime = 1
            sickbeard.showList.append(s)
            sickbeard.showDict[s.sid_int] = s
        scene_exceptions.retrieve_exceptions()
        name_cache.buildNameCache()
        self.assertEqual(scene_exceptions.get_scene_exception_by_name(u'ブラック・ラグーン'), [1, 79604, -1])
        self.assertEqual(scene_exceptions.get_scene_exception_by_name(u'Burakku Ragūn'), [1, 79604, -1])
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('Rokka no Yuusha'), [1, 295243, -1])

    def test_sceneExceptionByNameEmpty(self):
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('nothing useful'), [None, None, None])

    def test_sceneExceptionsResetNameCache(self):
        # clear the exceptions
        my_db = db.DBConnection()
        # noinspection SqlConstantCondition
        my_db.action('DELETE FROM scene_exceptions WHERE 1=1')

        # put something in the cache
        name_cache.addNameToCache('Cached Name', prodid=0)

        # updating should not clear the cache this time since our exceptions didn't change
        scene_exceptions.retrieve_exceptions()
        self.assertEqual(name_cache.retrieveNameFromCache('Cached Name'), (0, 0))


if '__main__' == __name__:
    if 1 < len(sys.argv):
        suite = unittest.TestLoader().loadTestsFromName(
            'scene_helpers_tests.SceneExceptionTestCase.test_' + sys.argv[1])
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(SceneTests)
        unittest.TextTestRunner(verbosity=2).run(suite)
        suite = unittest.TestLoader().loadTestsFromTestCase(SceneExceptionTestCase)
        unittest.TextTestRunner(verbosity=2).run(suite)
