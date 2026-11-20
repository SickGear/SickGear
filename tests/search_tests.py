import sys
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')

import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sickgear
from sickgear import properFinder, search
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


if '__main__' == __name__:
    for cur_case in (ProperTests, CanRejectTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
