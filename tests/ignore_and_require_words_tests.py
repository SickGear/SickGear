import os.path
import sys
import unittest

import sickbeard
from sickbeard import show_name_helpers

sys.path.insert(1, os.path.abspath('..'))


class TestCase(unittest.TestCase):

    cases_pass_wordlist_checks = [
        ('[GroupName].Show.Name.-.%02d.[null]', '', '', True),

        ('[GroupName].Show.Name.-.%02d.[ignore]', '', 'required', False),
        ('[GroupName].Show.Name.-.%02d.[required]', '', 'required', True),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', 'GroupName', True),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', '[GroupName]', True),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', 'Show.Name', True),
        ('[GroupName].Show.Name.-.%02d.[required]', 'not_ignored', 'required', True),
        ('[GroupName].Show.Name.-.%02d.[required]', '[not_ignored]', '[required]', True),

        ('[GroupName].Show.Name.-.%02d.[ignore]', '[ignore]', '', False),
        ('[GroupName].Show.Name.-.%02d.[required]', '[GroupName]', 'required', False),
        ('[GroupName].Show.Name.-.%02d.[required]', 'GroupName', 'required', False),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'ignore', 'GroupName', False),
        ('[GroupName].Show.Name.-.%02d.[required]', 'Show.Name', 'required', False),

        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: no_ignore', '', True),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'ignore', r'regex: \d?\d80p', True),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'ignore', r'regex: \[\d?\d80p\]', True),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: ignore', '', False),
        ('[GroupName].Show.Name.-.%02d.[ignore]', r'regex: \[ignore\]', '', False),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: ignore', 'required', False),

        # The following test is True because a boundary is added to each regex not overridden with the prefix param
        ('[GroupName].Show.ONEONE.-.%02d.[required]', 'regex: (one(two)?)', '', True),
        ('[GroupName].Show.ONETWO.-.%02d.[required]', 'regex: ((one)?two)', 'required', False),
        ('[GroupName].Show.TWO.-.%02d.[required]', 'regex: ((one)?two)', 'required', False),

        ('The.Spanish.Princess.-.%02d',
         r'regex:^(?:(?=.*?\bspanish\b)((?!spanish.?princess).)*|.*princess.*?spanish.*)$, ignore', '', True),
        ('Spanish.Princess.Spanish.-.%02d',
         r'regex:^(?:(?=.*?\bspanish\b)((?!spanish.?princess).)*|.*princess.*?spanish.*)$, ignore', '', False)
    ]

    cases_contains = [
        ('[GroupName].Show.Name.-.%02d.[illegal_regex]', 'regex:??illegal_regex', False),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'regex:(480|1080)p', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', r'regex:\[contains\]', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[contains]', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', 'contains', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[not_contains]', False),
        ('[GroupName].Show.Name.-.%02d.[null]', '', False)
    ]

    cases_not_contains = [
        ('[GroupName].Show.Name.-.%02d.[480p]', 'regex:(480|1080)p', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', r'regex:\[contains\]', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[contains]', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', 'contains', False),
        ('[GroupName].Show.Name.-.%02d.[not_contains]', '[blah_blah]', True),
        ('[GroupName].Show.Name.-.%02d.[null]', '', False)
    ]

    def test_pass_wordlist_checks(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_pass_wordlist_checks, isolated)[len(isolated)]
        for case_num, (name, ignore_list, require_list, expected_result) in enumerate(test_cases):
            name = name if '%02d' not in name else name % case_num
            sickbeard.IGNORE_WORDS = ignore_list
            sickbeard.REQUIRE_WORDS = require_list
            self.assertEqual(expected_result, show_name_helpers.pass_wordlist_checks(name, False),
                             'Expected %s with test: "%s" with ignore: "%s", require: "%s"' %
                             (expected_result, name, ignore_list, require_list))

    def test_contains_any(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_contains, isolated)[len(isolated)]
        for case_num, (name, csv_words, expected_result) in enumerate(test_cases):
            name = name if '%02d' not in name else name % case_num
            self.assertEqual(expected_result, self.call_contains_any(name, csv_words),
                             'Expected %s test: "%s" with csv_words: "%s"' %
                             (expected_result, name, csv_words))

    @staticmethod
    def call_contains_any(name, csv_words):
        re_extras = dict(re_prefix='.*', re_suffix='.*')
        match = show_name_helpers.contains_any(name, csv_words, **re_extras)
        return None is not match and match

    def test_not_contains_any(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_not_contains, isolated)[len(isolated)]
        for case_num, (name, csv_words, expected_result) in enumerate(test_cases):
            name = name if '%02d' not in name else name % case_num
            self.assertEqual(expected_result, self.call_not_contains_any(name, csv_words),
                             'Expected %s test: "%s" with csv_words:"%s"' %
                             (expected_result, name, csv_words))

    @staticmethod
    def call_not_contains_any(name, csv_words):
        re_extras = dict(re_prefix='.*', re_suffix='.*')
        match = show_name_helpers.not_contains_any(name, csv_words, **re_extras)
        return None is not match and match


if '__main__' == __name__:
    unittest.main()
