import unittest
import test_lib as test

import sys, os.path
sys.path.insert(1, os.path.abspath('..'))

from sickbeard import show_name_helpers, scene_exceptions, common, name_cache

import sickbeard
from sickbeard import db
from sickbeard.databases import cache_db
from sickbeard.tv import TVShow as Show


class SceneTests(test.SickbeardTestDBCase):

    def _test_allPossibleShowNames(self, name, indexerid=0, expected=[]):
        s = Show(1, indexerid)
        s.name = name

        result = show_name_helpers.allPossibleShowNames(s)
        self.assertTrue(len(set(expected).intersection(set(result))) == len(expected))

    def _test_filterBadReleases(self, name, expected):
        result = show_name_helpers.filterBadReleases(name)
        self.assertEqual(result, expected)

    def test_allPossibleShowNames(self):
        #common.sceneExceptions[-1] = ['Exception Test']
        myDB = db.DBConnection("cache.db")
        myDB.action("INSERT INTO scene_exceptions (indexer_id, show_name, season) VALUES (?,?,?)", [-1, 'Exception Test', -1])
        common.countryList['Full Country Name'] = 'FCN'

        self._test_allPossibleShowNames('Show Name', expected=['Show Name'])
        self._test_allPossibleShowNames('Show Name', -1, expected=['Show Name', 'Exception Test'])
        self._test_allPossibleShowNames('Show Name FCN', expected=['Show Name FCN', 'Show Name (Full Country Name)'])
        self._test_allPossibleShowNames('Show Name (FCN)', expected=['Show Name (FCN)', 'Show Name (Full Country Name)'])
        self._test_allPossibleShowNames('Show Name Full Country Name', expected=['Show Name Full Country Name', 'Show Name (FCN)'])
        self._test_allPossibleShowNames('Show Name (Full Country Name)', expected=['Show Name (Full Country Name)', 'Show Name (FCN)'])

    def test_filterBadReleases(self):
        self._test_filterBadReleases('Show.S02.German.Stuff-Grp', False)
        self._test_filterBadReleases('Show.S02.Some.Stuff-Core2HD', False)
        self._test_filterBadReleases('Show.S02.Some.German.Stuff-Grp', False)
        #self._test_filterBadReleases('German.Show.S02.Some.Stuff-Grp', True)
        self._test_filterBadReleases('Show.S02.This.Is.German', False)


class SceneExceptionTestCase(test.SickbeardTestDBCase):

    def setUp(self):
        super(SceneExceptionTestCase, self).setUp()
        scene_exceptions.retrieve_exceptions()

    def test_sceneExceptionsEmpty(self):
        self.assertEqual(scene_exceptions.get_scene_exceptions(0), [])

    def test_sceneExceptionsBabylon5(self):
        self.assertEqual(sorted(scene_exceptions.get_scene_exceptions(70726)), ['Babylon 5', 'Babylon5'])

    def test_sceneExceptionByName(self):
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('Babylon5'), (70726, -1))
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('babylon 5'), (70726, -1))
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('Carlos 2010'), (164451, -1))

    def test_sceneExceptionByNameEmpty(self):
        self.assertEqual(scene_exceptions.get_scene_exception_by_name('nothing useful'), (None, None))

    def test_sceneExceptionsResetNameCache(self):
        # clear the exceptions
        myDB = db.DBConnection("cache.db")
        myDB.action("DELETE FROM scene_exceptions")

        # put something in the cache
        name_cache.addNameToCache('Cached Name', 0)

        # updating should not clear the cache this time since our exceptions didn't change
        scene_exceptions.retrieve_exceptions()
        self.assertEqual(name_cache.retrieveNameFromCache('Cached Name'), 0)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        suite = unittest.TestLoader().loadTestsFromName('scene_helpers_tests.SceneExceptionTestCase.test_' + sys.argv[1])
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(SceneTests)
        unittest.TextTestRunner(verbosity=2).run(suite)
        suite = unittest.TestLoader().loadTestsFromTestCase(SceneExceptionTestCase)
        unittest.TextTestRunner(verbosity=2).run(suite)
