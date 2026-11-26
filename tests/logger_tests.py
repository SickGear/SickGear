import logging
import sys
import unittest
import unittest.mock
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sickgear
from sickgear import logger


def _rec(msg, args=(), exc_info=None):
    return logging.LogRecord('sickgear', logging.INFO, '', 0, msg, args, exc_info)


class RedactingFilterTests(unittest.TestCase):
    def setUp(self):
        self.orig = sickgear.GenericProvider.dedupe_auths
        self.set_auths(['abcdefghijklmnop', 'sh0rtkey'])

    def tearDown(self):
        sickgear.GenericProvider.dedupe_auths = self.orig
        logger.RedactingFilter.reset()

    @staticmethod
    def set_auths(auths):
        sickgear.GenericProvider.dedupe_auths = staticmethod(lambda keys=False: auths)
        logger.RedactingFilter.reset()

    def test_masks_secrets(self):
        rec = _rec('url?apikey=%s and {%r}', ('ABCDEFGHIJKLMNOP', 'sh0rtkey'))
        self.assertTrue(logger.RedactingFilter().filter(rec))
        self.assertEqual("url?apikey=ABCD********MNOP and {'sh0r****'}", rec.getMessage())

    def test_masks_traceback(self):
        try:
            raise ValueError('token sh0rtkey leaked')
        except ValueError:
            rec = _rec('boom', exc_info=sys.exc_info())
        logger.RedactingFilter().filter(rec)
        self.assertIn('sh0r****', rec.exc_text)
        self.assertNotIn('sh0rtkey', logging.Formatter().format(rec))

    def test_error_viewer_masked(self):
        from sickgear import classes
        classes.ErrorViewer.errors = []
        logger.log('ui error with sh0rtkey', logger.ERROR)
        self.assertEqual(1, len(classes.ErrorViewer.errors))
        self.assertNotIn('sh0rtkey', classes.ErrorViewer.errors[0].message)
        self.assertIn('sh0r****', classes.ErrorViewer.errors[0].message)

    def test_program_name_not_masked(self):
        self.set_auths(['SickGear', 'gear', 'sh0rtkey'])
        self.assertEqual('Starting SickGear with sickgear.py, sh0r****',
                         logger.RedactingFilter.mask_text('Starting SickGear with sickgear.py, sh0rtkey'))

    def test_no_secrets_loaded(self):
        self.set_auths([])
        self.assertEqual('startup line', logger.RedactingFilter.mask_text('startup line'))
        self.assertTrue(logger.RedactingFilter().filter(_rec('startup line')))
        self.set_auths(['sh0rtkey'])
        self.assertEqual(42, logger.RedactingFilter.mask_text(42))

    def test_log_line_while_reading_secrets_does_not_read_again(self):
        calls = []

        def auths(keys=False):
            calls.append(1)
            logger.RedactingFilter().filter(_rec('logged while secrets are read'))  # as a fetch inside would
            return ['sh0rtkey']
        sickgear.GenericProvider.dedupe_auths = staticmethod(auths)
        logger.RedactingFilter.reset()
        rec = _rec('key sh0rtkey')
        logger.RedactingFilter().filter(rec)
        self.assertEqual(1, len(calls))
        self.assertEqual('key sh0r****', rec.getMessage())

    def test_dedupe_auths_reads_held_url_not_property(self):
        from sickgear.providers import generic

        class Prov(generic.TorrentProvider):
            def _valid_home(self, *args, **kwargs):
                raise AssertionError('url property used, it fetches the home page')
        prov = Prov('TestProv')
        prov._url = 'https://site.example/rss?passkey=heldkey123'
        with unittest.mock.patch.object(sickgear.providers, 'sorted_sources', return_value=[prov]):
            self.assertIn('heldkey123', self.orig(True))

    def test_keys_from_a_login_are_masked(self):
        from sickgear.providers import generic
        prov = generic.TorrentProvider('TestProv')
        prov.user_authkey, prov.user_passkey, prov._token, prov._dkey = (
            'authkey1234567', 'passkey1234567', 'token12345678', 'dkey123456789')
        with unittest.mock.patch.object(sickgear.providers, 'sorted_sources', return_value=[prov]):
            masked, dupe_check = self.orig(True), self.orig(False)
        for cur_key in ('authkey1234567', 'passkey1234567', 'token12345678', 'dkey123456789'):
            self.assertIn(cur_key, masked)
            self.assertNotIn(cur_key, dupe_check)

    def test_key_in_an_address_is_masked_whatever_its_source(self):
        self.set_auths([])
        f = logger.RedactingFilter()
        for cur_msg, cur_masked in (
                ('Downloaded X from https://t.example/dl.php?id=12&passkey=0123456789abcdef',
                 'Downloaded X from https://t.example/dl.php?id=12&passkey=0123********cdef'),
                ('get ajax.php?action=browse&auth=a1b2c3d4e5&torrent_pass=zz99yy88xx',
                 'get ajax.php?action=browse&auth=a1b2c*****&torrent_pass=zz99y*****'),
                ('rss?rsskey=abcdef123456;x', 'rss?rsskey=abcd****3456;x'),
                ('oauth=abcdefgh keymap=abcdefgh id=1 key=abc', 'oauth=abcdefgh keymap=abcdefgh id=1 key=abc')):
            rec = _rec(cur_msg)
            f.filter(rec)
            self.assertEqual(cur_masked, rec.getMessage())

    def test_reset_picks_up_new_secret(self):
        f = logger.RedactingFilter()
        f.filter(_rec('warm cache'))
        self.set_auths(['newsecret99'])
        rec = _rec('key newsecret99')
        f.filter(rec)
        self.assertEqual('key newse*****', rec.getMessage())


class DedupeAuthsTests(unittest.TestCase):
    def test_rss_url_query_and_pushover_userkey(self):
        class Rss(object):
            url = 'https://feed.example/rss?user=bob&passkey=rsskey123456'
            username = 'bobby_tables'
            uid = '424242'

            @staticmethod
            def get_id():
                return 'rss'

        orig = sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY, sickgear.SAB_USERNAME
        sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY, sickgear.SAB_USERNAME = (
            (lambda: [Rss()]), 'userkey987', 'sabuser')
        try:
            auths = sickgear.GenericProvider.dedupe_auths(True)
            dupes = sickgear.GenericProvider.dedupe_auths()
        finally:
            sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY, sickgear.SAB_USERNAME = orig
        self.assertIn('rsskey123456', auths)
        self.assertIn('userkey987', auths)
        self.assertNotIn('bob', auths)
        self.assertIn('bobby_tables', auths)
        self.assertIn('424242', auths)
        self.assertIn('sabuser', auths)
        self.assertEqual([], dupes)


if '__main__' == __name__:
    unittest.main()
