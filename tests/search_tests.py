import unittest
import sys
import os.path
from sickbeard.search import filter_release_name


sys.path.insert(1, os.path.abspath('..'))

class TestCase(unittest.TestCase):
    def test_filter_release_name(self):
        test_cases = [
            ('[HorribleSubs].Heavy.Object.-.08.[480p]', '[480p]', True),
            ('[HorribleSubs].Heavy.Object.-.08.[480p]', '480p', True),
            ('[HorribleSubs].Heavy.Object.-.08.[480p]', '[720p]', False),
            ('[HorribleSubs].Heavy.Object.-.08.[480p]', '720p', False),
            ('[HorribleSubs].Heavy.Object.-.08.[480p]', '', False),
        ]
        for name, filter_words, expected_result in test_cases:
            self.assertEqual(expected_result, filter_release_name(name, filter_words))

if __name__ == '__main__':
    unittest.main()
