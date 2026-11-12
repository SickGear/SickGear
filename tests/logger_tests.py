import logging
import os.path
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

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

        orig = sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY
        sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY = (lambda: [Rss()]), 'userkey987'
        try:
            auths = sickgear.GenericProvider.dedupe_auths(True)
            dupes = sickgear.GenericProvider.dedupe_auths()
        finally:
            sickgear.providers.sorted_sources, sickgear.PUSHOVER_USERKEY = orig
        self.assertIn('rsskey123456', auths)
        self.assertIn('userkey987', auths)
        self.assertNotIn('bob', auths)
        self.assertIn('bobby_tables', auths)
        self.assertIn('424242', auths)
        self.assertEqual([], dupes)


if '__main__' == __name__:
    unittest.main()
