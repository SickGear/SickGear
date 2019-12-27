import unittest
import sys
import os.path

sys.path.insert(1, os.path.abspath('../lib'))

from sickbeard import helpers
from sickbeard.common import ARCHIVED, SNATCHED, SNATCHED_BEST, SNATCHED_PROPER, \
    DOWNLOADED, SKIPPED, IGNORED, UNAIRED, UNKNOWN, WANTED, Quality


sys.path.insert(1, os.path.abspath('..'))


class HelpersTests(unittest.TestCase):
    def test_replaceExtension(self):
        self.assertEqual(helpers.replace_extension('foo.avi', 'mkv'), 'foo.mkv')
        self.assertEqual(helpers.replace_extension('.vimrc', 'arglebargle'), '.vimrc')
        self.assertEqual(helpers.replace_extension('a.b.c', 'd'), 'a.b.d')
        self.assertEqual(helpers.replace_extension('', 'a'), '')
        self.assertEqual(helpers.replace_extension('foo.bar', ''), 'foo.')

    def test_sanitizeFileName(self):
        self.assertEqual(helpers.sanitize_filename('a/b/c'), 'a-b-c')
        self.assertEqual(helpers.sanitize_filename('abc'), 'abc')
        self.assertEqual(helpers.sanitize_filename('a"b'), 'ab')
        self.assertEqual(helpers.sanitize_filename('.a.b..'), 'a.b')

    def test_sizeof_fmt(self):
        self.assertEqual(helpers.sizeof_fmt(2), '2.0 bytes')
        self.assertEqual(helpers.sizeof_fmt(1024), '1.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2048), '2.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2 ** 20), '1.0 MB')
        self.assertEqual(helpers.sizeof_fmt(1234567), '1.2 MB')

    def test_remove_non_release_groups(self):
        test_names = {
            ('[HorribleSubs] Hidan no Aria AA - 08 [1080p]', True): '[HorribleSubs] Hidan no Aria AA - 08 [1080p]',
            ('The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN[rartv]', False):
                'The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN',
        }
        for test_name, test_result in test_names.items():
            self.assertEqual(test_result, helpers.remove_non_release_groups(test_name[0], test_name[1]))

    def test_should_delete_episode(self):
        test_cases = [
            ((SNATCHED, Quality.HDTV), False),
            ((SNATCHED_PROPER, Quality.HDTV), False),
            ((SNATCHED_BEST, Quality.HDTV), False),
            ((DOWNLOADED, Quality.HDTV), False),
            ((ARCHIVED, Quality.HDTV), False),
            ((ARCHIVED, Quality.NONE), False),
            ((SKIPPED, Quality.NONE), True),
            ((IGNORED, Quality.NONE), False),
            ((UNAIRED, Quality.NONE), True),
            ((UNKNOWN, Quality.NONE), True),
            ((WANTED, Quality.NONE), True),
        ]
        for c, b in test_cases:
            self.assertEqual(helpers.should_delete_episode(Quality.compositeStatus(*c)), b)


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(HelpersTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
