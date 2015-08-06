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


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(HelpersTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
