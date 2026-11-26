import sys
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear.providers.milkie import MilkieProvider


class MilkieLoginTests(unittest.TestCase):
    """ an auth reply that is not the expected json fails the login, it does not raise """

    def check(self, login_resp, auth_resp, expected):
        provider = MilkieProvider()
        provider.get_url = lambda *args, **kwargs: auth_resp
        self.assertEqual(expected, provider.logged_in(login_resp))

    def test_bad_auth_reply(self):
        for auth_resp in ('not json', None, [], {'error': 'rate limited'}, {'user': None}, {'user': {}}):
            self.check({'token': 'tok'}, auth_resp, False)

    def test_bad_login_reply(self):
        for login_resp in ('not json', None, ['token'], {}):
            self.check(login_resp, {'user': {'apiKey': 'AAA'}}, False)

    def test_good_reply(self):
        for user in ({'apiKey': 'AAA'}, {'downloadKey': 'BBB'}):
            self.check({'token': 'tok'}, {'user': user}, True)

    def test_failed_login_with_json_reply(self):
        provider = MilkieProvider()
        provider.username, provider.password = 'user', 'pass'
        provider.should_skip = lambda *args, **kwargs: False
        provider.get_url = lambda url, **kwargs: (url == provider.urls['login'] and {'token': 'tok'}
                                                  or url == provider.urls['auth'] and 'not json' or None)
        self.assertFalse(provider._authorised())


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(MilkieLoginTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
