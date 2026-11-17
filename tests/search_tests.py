import sys
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')

import datetime
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sickgear
from sickgear import common, db, properFinder, search
from sickgear.tv import TVEpisode, TVShow
import test_lib as test

sickgear.SYS_ENCODING = 'UTF-8'


class ProperTests(test.SickbeardTestDBCase):
    def check_webdl_type(self, cases):
        for c in cases:
            self.assertEqual(properFinder.get_webdl_type(*c[0]), c[1])

    def test_webdl_type(self):
        self.check_webdl_type([
            (('1080p.WEB.x264', 'The.Show.Name.S04E10.1080p.WEB.x264-GROUP'), 'webrip'),
            (('720p.WEB-DL.DD5.1.H.264', 'The.Show.Name.720p.WEB-DL.DD5.1.H.264-GROUP'), 'webdl'),
            (('1080p.AMZN.WEB-DL.DD5.1.H.264', 'The.Show.Name.1080p.AMZN.WEB-DL.DD5.1.H.264-GROUP'), 'Amazon'),
        ])


class CanRejectTests(unittest.TestCase):
    """can_reject with predb.net and srrdb replies faked, no network used"""
    name = 'Show.Name.S01E01.720p.WEB.h264-GROUP'

    def setUp(self):
        self.calls = []
        self.replies = {}
        self.org_get_url, self.org_gap = search.helpers.get_url, search.PREDB_MIN_GAP
        search.helpers.get_url, search.PREDB_MIN_GAP = self.fake_get_url, 0
        search._predb_cache.clear()

    def tearDown(self):
        search.helpers.get_url, search.PREDB_MIN_GAP = self.org_get_url, self.org_gap
        search._predb_cache.clear()

    def fake_get_url(self, url, params=None, **kwargs):
        site = ('srrdb', 'predb')['predb' in url]
        self.calls += [(site, url, params)]
        return self.replies.get(site)

    def predb(self, status=0, pretime=1700000000, reason='', name=None):
        self.replies['predb'] = {'status': 'success', 'results': 1, 'data': [
            {'release': name or self.name, 'pretime': pretime, 'status': status, 'reason': reason}]}

    def srrdb(self, listed=True):
        self.replies['srrdb'] = {'results': [{'release': self.name}] if listed else []}

    def sites(self):
        return [c[0] for c in self.calls]

    def test_request(self):
        self.predb()
        search.can_reject(self.name)
        self.assertEqual(('predb', search.PREDB_API, {'type': 'pre', 'release': self.name}), self.calls[0])

    def test_listed_at_predb(self):
        self.predb()
        self.assertEqual((None, None), search.can_reject(self.name))
        self.assertEqual(['predb'], self.sites())

    def test_listed_with_other_case_and_separators(self):
        self.predb(name=self.name.lower().replace('.', ' '))
        self.assertEqual((None, None), search.can_reject(self.name))

    def test_nuked_wins_over_srrdb(self):
        self.predb(status=1, reason='bad.ivtc')
        self.srrdb()
        reject, url = search.can_reject(self.name)
        self.assertEqual('bad.ivtc', reject)
        self.assertIn('api.predb.net', url)
        self.assertEqual(['predb'], self.sites())

    def test_delpre_without_reason(self):
        self.predb(status=3)
        self.assertEqual('Reason not set', search.can_reject(self.name)[0])

    def test_unnuked_and_undelpre(self):
        for status in (2, 4):
            search._predb_cache.clear()
            self.predb(status=status, reason='fixed')
            self.assertEqual((None, None), search.can_reject(self.name))

    def test_not_at_predb_listed_at_srrdb(self):
        self.replies['predb'] = {'status': 'success', 'results': 0, 'message': 'No results found.'}
        self.srrdb()
        self.assertEqual((None, None), search.can_reject(self.name))
        self.assertEqual(['predb', 'srrdb'], self.sites())

    def test_not_listed_anywhere(self):
        self.replies['predb'] = {'status': 'success', 'results': 0, 'message': 'No results found.'}
        self.srrdb(listed=False)
        reject, url = search.can_reject(self.name)
        self.assertIs(True, reject)
        self.assertIn('predb', url)
        self.assertIn('srrdb', url)
        self.assertNotIn('Failed contact', url)

    def test_sites_unreadable(self):
        reject, url = search.can_reject(self.name)
        self.assertIs(True, reject)
        self.assertEqual(2, url.count('Failed contact'))

    def test_predb_error_status(self):
        self.replies['predb'] = {'status': 'error', 'message': 'Missing release name'}
        self.srrdb()
        self.assertEqual((None, None), search.can_reject(self.name))
        self.assertEqual(False, search.predb_release(self.name)[0])

    def test_found_release_is_reused(self):
        self.predb()
        search.can_reject(self.name)
        search.can_reject(self.name.upper())
        self.assertEqual(['predb'], self.sites())

    def test_failed_lookup_is_not_reused(self):
        search.predb_release(self.name)
        search.predb_release(self.name)
        self.assertEqual(['predb', 'predb'], self.sites())


class WantedEpisodesTests(test.SickbeardTestDBCase):
    """ a search for wanted episodes makes episode objects for wanted episodes only """

    def setUp(self):
        super(WantedEpisodesTests, self).setUp()
        sickgear.WANTEDLIST_CACHE = common.WantedQualities()
        # load episodes from the db, the test lib replaces the loader with one that does nothing
        self.fake_specify_episode = TVEpisode.specify_episode
        TVEpisode.specify_episode = test.org_specify_episode
        self.release_map_xem = sickgear.scene_exceptions.MEMCACHE.get('release_map_xem', {})
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = {}
        self.show_obj = TVShow(1, 123456, 'en')
        self.show_obj.quality = common.Quality.combine_qualities([common.Quality.HDTV], [])
        self.show_obj.sxe_ep_obj = {}
        downloaded = common.Quality.composite_status(common.DOWNLOADED, common.Quality.HDTV)
        airdate = datetime.date.today().toordinal() - 30
        with db.DBConnection() as sg_db:
            sg_db.mass_action([[
                'INSERT INTO tv_episodes (indexer, showid, indexerid, season, episode, status, airdate, subtitles)'
                ' VALUES (1, 123456, ?, 1, ?, ?, ?, "")',
                [1000 + ep_num, ep_num, (downloaded, common.WANTED)[3 == ep_num], airdate]] for ep_num in range(1, 6)])

    def tearDown(self):
        TVEpisode.specify_episode = self.fake_specify_episode
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = self.release_map_xem
        super(WantedEpisodesTests, self).tearDown()

    def wanted(self):
        return search.wanted_episodes(self.show_obj, datetime.date.fromordinal(1))

    def test_only_wanted_episode_is_loaded(self):
        self.assertEqual([(1, 3)], [(_ep.season, _ep.episode) for _ep in self.wanted()])
        self.assertEqual({1: [3]}, {_s: list(_e) for _s, _e in self.show_obj.sxe_ep_obj.items()})
        self.assertEqual({1: {1, 2, 4, 5}}, self.show_obj.unwanted_sxe)

    def test_unwanted_episode_without_object_is_refused(self):
        self.wanted()
        self.assertFalse(self.show_obj.want_episode(1, 2, common.Quality.HDTV))
        self.assertTrue(self.show_obj.want_episode(1, 3, common.Quality.HDTV))
        self.assertEqual({1: [3]}, {_s: list(_e) for _s, _e in self.show_obj.sxe_ep_obj.items()})

    def test_loaded_episode_status_is_used(self):
        # a loaded episode with a status that is newer than its db row
        ep_obj = self.show_obj.get_episode(1, 2)
        ep_obj.status = common.WANTED
        self.assertEqual([(1, 2), (1, 3)], [(_ep.season, _ep.episode) for _ep in self.wanted()])

    def test_episode_that_becomes_wanted(self):
        self.wanted()
        with db.DBConnection() as sg_db:
            sg_db.action('UPDATE tv_episodes SET status = ? WHERE showid = 123456 AND episode = 4', [common.WANTED])
        self.assertEqual([(1, 3), (1, 4)], [(_ep.season, _ep.episode) for _ep in self.wanted()])
        self.assertEqual({1: {1, 2, 5}}, self.show_obj.unwanted_sxe)


if '__main__' == __name__:
    for cur_case in (ProperTests, CanRejectTests, WantedEpisodesTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
