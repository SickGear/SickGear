import sys
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear.providers.milkie import MilkieProvider
from sickgear.providers.nebulance import NebulanceProvider
from sickgear.providers.speedapp import SpeedAppProvider
from sickgear.providers.speedcd import SpeedCDProvider


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
        provider.enabled, provider.username, provider.password = True, 'user', 'pass'
        provider.should_skip = lambda *args, **kwargs: False
        provider.get_url = lambda url, **kwargs: (url == provider.urls['login'] and {'token': 'tok'}
                                                  or url == provider.urls['auth'] and 'not json' or None)
        self.assertFalse(provider._authorised())


class JsonReplyLoginTests(unittest.TestCase):
    """ a login step reply that is not the expected json fails the login, it does not raise """
    bad_replies = ('not json', None, [], {}, {'response': None}, {'Fs': None}, [None])

    @staticmethod
    def prepare(provider, get_url):
        provider.enabled, provider.username, provider.password = True, 'user', 'pass'
        provider.should_skip = lambda *args, **kwargs: False
        provider.save_main_config = lambda *args, **kwargs: None
        provider.get_url = get_url
        return provider

    def test_nebulance_user_reply(self):
        for reply in self.bad_replies:
            provider = self.prepare(NebulanceProvider(), lambda url, **kwargs: reply)
            provider.has_all_cookies = lambda *args, **kwargs: True
            self.assertFalse(provider._authorised())

    def test_speedcd_login_reply(self):
        for reply in self.bad_replies:
            provider = self.prepare(SpeedCDProvider(), lambda url, **kwargs: (
                reply if url.endswith('checkpoint/API') else '<html>speed</html>'))
            provider.digest = ''
            self.assertFalse(provider._authorised())

    def test_speedapp_categories_reply(self):
        for item in self.bad_replies:
            provider = self.prepare(SpeedAppProvider(), lambda url, **kwargs: (
                [item, {'id': 41, 'name': 'TV HD'}] if url == provider.urls['cats']
                else {'scopes': list(provider.perms)}))
            self.assertTrue(provider.logged_in({'scopes': list(provider.perms)}))
            self.assertEqual([41], provider.categories['Cache'])


if '__main__' == __name__:
    for case in (MilkieLoginTests, JsonReplyLoginTests):
        unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromTestCase(case))
