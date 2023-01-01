import os.path
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))

import sickbeard
from sickbeard import helpers, show_name_helpers


class TVShow(object):
    def __init__(self, i=None, r=None, ir=False, rr=False, ei=None, er=None):
        i = i or set()
        r = r or set()
        ei = ei or set()
        er = er or set()
        self.rls_ignore_words = i
        self.rls_ignore_words_regex = ir
        self.rls_require_words = r
        self.rls_require_words_regex = rr
        self.rls_global_exclude_ignore = ei
        self.rls_global_exclude_require = er


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
        ('[GroupName].Show.Name.-.%02d.[required]', '[not_ignored]', 'something,[required]', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', '[not_ignored]', r'regex:something,\[required\]', False, TVShow()),
        ('[GroupName].Show.Name.-.%02d.[required]', '[not_ignored]', r'regex:(something|\[required\])', True, TVShow()),

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

        # show specific ignore word tests
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         False, TVShow(i={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', 'required',
         False, TVShow(i={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'nothing', 'required',
         False, TVShow(i={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'nothing', '',
         False, TVShow(i={'[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         False, TVShow(i={'nothing', '[GroupName]'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         True, TVShow(i={'nothing', 'notthis'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', 'GroupName',
         True, TVShow(i={'nothing', 'notthis'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'something', 'GroupName',
         True, TVShow(i={'nothing', 'notthis'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', 'regex:GroupName',
         True, TVShow(i={'nothing', 'notthis'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'regex:something', 'regex:GroupName',
         True, TVShow(i={'nothing', 'notthis'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         False, TVShow(i={r'\[GroupName\]'}, ir=True)),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         False, TVShow(i={'nothing', r'\[GroupName\]'}, ir=True)),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', '', '',
         True, TVShow(i={'nothing', 'nothis'}, ir=True)),

        # show specific require word tests
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '',
         True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'something',
         True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'nothing',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something',
         True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something,nothing',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'nothing',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:notthis', 'something',
         True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:notthis', 'nothing',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:notthis,nothing',
         'something', True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:notthis,nothing', 'nothing',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'something', 'something',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:something', 'something',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'regex:something,nothing', 'something',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:something',
         True, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'something,thistoo',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:something,thistoo',
         False, TVShow(r={'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '',
         True, TVShow(r={'nothing', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '',
         True, TVShow(r={'required'}, rr=True)),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '',
         True, TVShow(r={'nothing', 'required'}, rr=True)),

        # global and show specific require words
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'Group,Show, TWO',
         False, TVShow(r={'nothing', 'nothing2', 'required'})),  # `Group` is a partial word and not acceptable
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'GROUPNAME, SHOW, TWOO',
         False, TVShow(r={'nothing', 'nothing2', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'GroupName,Show, TWO',
         True, TVShow(r={'nothing', 'nothing2', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'GROUPNAME, SHOW,TWO',
         True, TVShow(r={'nothing', 'nothing2', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'GroupName, Show,TWO',
         True, TVShow(r={'nothing', 'nothing2', 'something', 'nothing3'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'GroupName, Show,TWO',
         False, TVShow(r={'noth', 'noth2', 'some', 'nothing3'})),  # partial word and not acceptable

        # show specific required and ignore words
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', '',
         True, TVShow(r={'required'}, i={'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'something',
         True, TVShow(r={'required'}, i={'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'nothing',
         False, TVShow(r={'required'}, i={'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something',
         False, TVShow(r={'required'}, i={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something',
         False, TVShow(r={'required', 'else'}, i={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something',
         True, TVShow(r={'required', 'else'}, i={'some'})),  # partial word and not acceptable
        ('[GroupName].Show.TWO.-.%02d.[something]-required', 'notthis', 'something',
         True, TVShow(r={'required', 'else'}, i={'nothing'})),

        # test global require exclude lists
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'required,something,nothing',
         True, TVShow(er={'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:required,something,nothing',
         True, TVShow(er={'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'required,something,nothing',
         True, TVShow(er={'nothing', 'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:required,something,nothing',
         True, TVShow(er={'nothing', 'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'required,something,nothing',
         False, TVShow(er={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:required,something,nothing',
         False, TVShow(er={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'required,something,nothing',
         False, TVShow(er={'something', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[something]-required', '', 'regex:required,something,nothing',
         False, TVShow(er={'something', 'required'})),

        # test global ignore exclude lists
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'GroupName', '',
         True, TVShow(ei={'GroupName'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'nothing,GroupName', '',
         True, TVShow(ei={'GroupName'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'regex:nothing,GroupName', '',
         True, TVShow(ei={'GroupName'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'required,GroupName', '',
         True, TVShow(ei={'GroupName', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'regex:required,GroupName', '',
         True, TVShow(ei={'GroupName', 'required'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'GroupName', '',
         True, TVShow(ei={'GroupName', 'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'nothing,GroupName', '',
         True, TVShow(ei={'GroupName', 'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'regex:nothing,GroupName', '',
         True, TVShow(ei={'GroupName', 'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'GroupName', '',
         False, TVShow(ei={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'nothing,GroupName', '',
         False, TVShow(ei={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'GroupName,required', '',
         False, TVShow(ei={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'required,GroupName', '',
         False, TVShow(ei={'something'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'GroupName', '',
         False, TVShow(ei={'something', 'nothing'})),
        ('[GroupName].Show.TWO.-.%02d.[required]-[GroupName]', 'regex:nothing,GroupName', '',
         False, TVShow(ei={'something', 'nothing'})),

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
