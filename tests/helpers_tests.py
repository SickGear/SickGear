import unittest
import sys
import os.path

from sickbeard import helpers


sys.path.insert(1, os.path.abspath('..'))


class HelpersTests(unittest.TestCase):
    def test_replaceExtension(self):
        self.assertEqual(helpers.replaceExtension('foo.avi', 'mkv'), 'foo.mkv')
        self.assertEqual(helpers.replaceExtension('.vimrc', 'arglebargle'), '.vimrc')
        self.assertEqual(helpers.replaceExtension('a.b.c', 'd'), 'a.b.d')
        self.assertEqual(helpers.replaceExtension('', 'a'), '')
        self.assertEqual(helpers.replaceExtension('foo.bar', ''), 'foo.')

    def test_sanitizeFileName(self):
        self.assertEqual(helpers.sanitizeFileName('a/b/c'), 'a-b-c')
        self.assertEqual(helpers.sanitizeFileName('abc'), 'abc')
        self.assertEqual(helpers.sanitizeFileName('a"b'), 'ab')
        self.assertEqual(helpers.sanitizeFileName('.a.b..'), 'a.b')

    def test_sizeof_fmt(self):
        self.assertEqual(helpers.sizeof_fmt(2), '2.0 bytes')
        self.assertEqual(helpers.sizeof_fmt(1024), '1.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2048), '2.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2 ** 20), '1.0 MB')
        self.assertEqual(helpers.sizeof_fmt(1234567), '1.2 MB')

    def test_remove_non_release_groups(self):
        test_names = {
            ('[HorribleSubs] Hidan no Aria AA - 08 [1080p]', True): '[HorribleSubs] Hidan no Aria AA - 08 [1080p]',
            ('The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN[rartv]', False): 'The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN',
        }
        for test_name, test_result in test_names.items():
            self.assertEqual(test_result, helpers.remove_non_release_groups(test_name[0], test_name[1]))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(HelpersTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
