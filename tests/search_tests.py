import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')

import unittest

from sickbeard import properFinder

import sickbeard
import test_lib as test

sickbeard.SYS_ENCODING = 'UTF-8'


class ProperTests(test.SickbeardTestDBCase):
    def check_webdl_type(self, cases):
        for c in cases:
            self.assertEqual(properFinder.get_webdl_type(*c[0]), c[1])

    def check_get_codec(self, cases):
        for c in cases:
            self.assertEqual(properFinder._get_codec(c[0]), c[1])

    def test_webdl_type(self):
        self.check_webdl_type([
            (('1080p.WEB.x264', 'The.Show.Name.S04E10.1080p.WEB.x264-GROUP'), 'webrip'),
            (('720p.WEB-DL.DD5.1.H.264', 'The.Show.Name.720p.WEB-DL.DD5.1.H.264-GROUP'), 'webdl'),
            (('1080p.AMZN.WEB-DL.DD5.1.H.264', 'The.Show.Name.1080p.AMZN.WEB-DL.DD5.1.H.264-GROUP'), 'Amazon'),
        ])

    def test_get_codec(self):
        self.check_get_codec([
            ('1080p.WEB.x264', '264'),
            ('720p.WEB.h264', '264'),
            ('HDTV.XviD', 'xvid'),
            ('720p.HEVC.x265', 'hevc'),
            ('1080p.HEVC.AC3', 'hevc'),
            ('10Bit.1080p.DD5.1.H.265', 'hevc'),
            ('720p.DD5.1.Widescreen.x265', 'hevc'),
        ])


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(ProperTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
