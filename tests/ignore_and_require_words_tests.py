import os.path
import sys
import unittest

import sickbeard
from sickbeard import show_name_helpers, helpers

sys.path.insert(1, os.path.abspath('..'))


class TVShow(object):
    def __init__(self, ei=set(), er=set(), i=set(), r=set(), ir=False, rr=False):
        self.rls_global_exclude_ignore = ei
        self.rls_global_exclude_require = er
        self.rls_ignore_words = i
        self.rls_ignore_words_regex = ir
        self.rls_require_words = r
        self.rls_require_words_regex = rr


class TestCase(unittest.TestCase):

    cases_pass_wordlist_checks = [
        ('[GroupName].Show.Name.-.%02d.[null]', '', '', True, TVShow()),

        ('[GroupName].Show.Name.-.%02d.[ignore]', '', 'required', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', '', 'required', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', 'GroupName', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', '[GroupName]', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[blahblah]', 'not_ignored', 'Show.Name', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', 'not_ignored', 'required', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', '[not_ignored]', '[required]', True, TVShow()),

        ('[GroupName].Show.Name.-.%02d.[ignore]', '[ignore]', '', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', '[GroupName]', 'required', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', 'GroupName', 'required', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'ignore', 'GroupName', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', 'Show.Name', 'required', False, TVShow()),

        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: no_ignore', '', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'ignore', r'regex: \d?\d80p', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'ignore', r'regex: \[\d?\d80p\]', True, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: ignore', '', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[ignore]', r'regex: \[ignore\]', '', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[ignore]', 'regex: ignore', 'required', False, TVShow()),

        # The following test is True because a boundary is added to each regex not overridden with the prefix param
        ('[GroupName].Show.ONEONE.-.%02d.[required]', 'regex: (one(two)?)', '', True, TVShow()),
        ('[GroupName].Show.ONETWO.-.%02d.[required]', 'regex: ((one)?two)', 'required', False, TVShow()),
        ('[GroupName].Show.TWO.-.%02d.[required]', 'regex: ((one)?two)', 'required', False, TVShow()),

        ('[GroupName].Show.TWO.-.%02d.[required]', '[GroupName]', '', True, TVShow(ei={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[something]', '[GroupName]', 'required', False, TVShow(er={'required'})),

        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '', False, TVShow(i={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '', True, TVShow(r={'required'})),

        ('The.Spanish.Princess.-.%02d',
         r'regex:^(?:(?=.*?\bspanish\b)((?!spanish.?princess).)*|.*princess.*?spanish.*)$, ignore', '', True, TVShow()),
        ('Spanish.Princess.Spanish.-.%02d',
         r'regex:^(?:(?=.*?\bspanish\b)((?!spanish.?princess).)*|.*princess.*?spanish.*)$, ignore', '', False, TVShow())
    ]

    cases_contains = [
        ('[GroupName].Show.Name.-.%02d.[illegal_regex]', 'regex:??illegal_regex', None),
        ('[GroupName].Show.Name.-.%02d.[480p]', 'regex:(480|1080)p', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', r'regex:\[contains\]', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[contains]', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', 'contains', True),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[not_contains]', False),
        ('[GroupName].Show.Name.-.%02d.[null]', '', None)
    ]

    cases_not_contains = [
        ('[GroupName].Show.Name.-.%02d.[480p]', 'regex:(480|1080)p', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', r'regex:\[contains\]', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', '[contains]', False),
        ('[GroupName].Show.Name.-.%02d.[contains]', 'contains', False),
        ('[GroupName].Show.Name.-.%02d.[not_contains]', '[blah_blah]', True),
        ('[GroupName].Show.Name.-.%02d.[null]', '', None)
    ]

    def test_pass_wordlist_checks(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_pass_wordlist_checks, isolated)[len(isolated)]
        for case_num, (name, ignore_list, require_list, expected_result, show_obj) in enumerate(test_cases):
            name = name if '%02d' not in name else name % case_num
            if ignore_list.startswith('regex:'):
                sickbeard.IGNORE_WORDS_REGEX = True
                ignore_list = ignore_list.replace('regex:', '')
            else:
                sickbeard.IGNORE_WORDS_REGEX = False
            sickbeard.IGNORE_WORDS = set(i.strip() for i in ignore_list.split(',') if i.strip())
            if require_list.startswith('regex:'):
                sickbeard.REQUIRE_WORDS_REGEX = True
                require_list = require_list.replace('regex:', '')
            else:
                sickbeard.REQUIRE_WORDS_REGEX = False
            sickbeard.REQUIRE_WORDS = set(r.strip() for r in require_list.split(',') if r.strip())
            self.assertEqual(expected_result, show_name_helpers.pass_wordlist_checks(name, False, show_obj=show_obj),
                             'Expected %s with test: "%s" with ignore: "%s", require: "%s"' %
                             (expected_result, name, ignore_list, require_list))

    def test_contains_any(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_contains, isolated)[len(isolated)]
        for case_num, (name, csv_words, expected_result) in enumerate(test_cases):
            s_words, s_regex = helpers.split_word_str(csv_words)
            name = name if '%02d' not in name else name % case_num
            self.assertEqual(expected_result, self.call_contains_any(name, s_words, rx=s_regex),
                             'Expected %s test: "%s" with csv_words: "%s"' %
                             (expected_result, name, csv_words))

    @staticmethod
    def call_contains_any(name, csv_words, *args, **kwargs):
        re_extras = dict(re_prefix='.*', re_suffix='.*')
        re_extras.update(kwargs)
        return show_name_helpers.contains_any(name, csv_words, *args, **re_extras)

    def test_not_contains_any(self):
        # default:[] or copy in a test case tuple to debug in isolation
        isolated = []

        test_cases = (self.cases_not_contains, isolated)[len(isolated)]
        for case_num, (name, csv_words, expected_result) in enumerate(test_cases):
            s_words, s_regex = helpers.split_word_str(csv_words)
            name = name if '%02d' not in name else name % case_num
            self.assertEqual(expected_result, self.call_not_contains_any(name, s_words, rx=s_regex),
                             'Expected %s test: "%s" with csv_words:"%s"' %
                             (expected_result, name, csv_words))

    @staticmethod
    def call_not_contains_any(name, csv_words, *args, **kwargs):
        re_extras = dict(re_prefix='.*', re_suffix='.*')
        re_extras.update(kwargs)
        return show_name_helpers.not_contains_any(name, csv_words, *args, **re_extras)


if '__main__' == __name__:
    unittest.main()
