import sys
import threading
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import requests

import sg_helpers
import sickgear
from sickgear import webserve
from sickgear.providers.generic import TorrentProvider
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


class LoginLogTests(unittest.TestCase):
    """ a login logs a debug line, so the log shows when a provider logs in """

    def test_login_is_logged(self):
        provider = TorrentProvider('Login Prov')
        provider.url_base, provider.username, provider.password = 'http://login.test/', 'user', 'pass'
        provider.should_skip = lambda *args, **kwargs: False
        for cur_reply, cur_logged in (('welcome', True), ('wrong password', False)):
            provider.get_url = lambda url, reply=cur_reply, **kwargs: reply
            with mock.patch('sickgear.providers.generic.logger') as log:
                self.assertEqual(cur_logged, bool(provider._authorised(
                    logged_in=(lambda y=None: 'welcome' == y), url='http://login.test/login')))
            self.assertEqual(cur_logged, mock.call('Login Prov logged in') in log.debug.call_args_list)


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


class CookieSettingTests(unittest.TestCase):
    """ a Cookies setting saved after a fetch is sent, the cookies remembered from that fetch do not replace it """

    def setUp(self):
        sent = self.sent = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                sent.append(self.headers.get('Cookie', ''))
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')

            def log_message(self, *args):
                pass

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%s/' % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_saved_cookie_is_sent(self):
        session, memcache = requests.Session(), {}
        for cur_value in ('old', 'new', 'new'):
            # as check_auth_cookie() adds the setting to the provider session before each fetch
            requests.utils.add_dict_to_cookiejar(session.cookies, {'sid': cur_value})
            self.assertEqual('ok', sg_helpers.get_url(self.url, session=session, memcache_cookies=memcache,
                                                      nocache=True))
        self.assertEqual(['sid=old', 'sid=new', 'sid=new'], self.sent)

    def test_remembered_cookie_is_added_to_a_new_session(self):
        memcache = {}
        sg_helpers.get_url(self.url, session=requests.Session(), memcache_cookies=memcache, nocache=True)
        self.assertEqual([''], self.sent)
        session = requests.Session()
        session.cookies.set('sid', 'kept')
        sg_helpers.get_url(self.url, session=session, memcache_cookies=memcache, nocache=True)
        sg_helpers.get_url(self.url, session=requests.Session(), memcache_cookies=memcache, nocache=True)
        self.assertEqual(['', 'sid=kept', 'sid=kept'], self.sent)


class LoginSettingSaveTests(unittest.TestCase):
    """ a saved change to a login setting lets the next search update the provider cache, it does not wait """

    def save(self, digest, form=None, **attrs):
        provider = TorrentProvider('Cookie Prov')
        provider.digest = 'uid=1;pass=old'
        for cur_attr, cur_value in attrs.items():
            setattr(provider, cur_attr, cur_value)
        provider.cache = mock.MagicMock()
        with mock.patch.object(sickgear.providers, 'sorted_sources', lambda: [provider]),                 mock.patch.multiple(sickgear, newznab_providers=[], torrent_rss_providers=[], save_config=mock.DEFAULT,
                                    USE_NZBS=False, USE_TORRENTS=False),                 mock.patch.object(webserve.helpers, 'clear_unused_providers'),                 mock.patch.object(webserve.threading, 'Thread'), mock.patch.object(webserve, 'ui'):
            webserve.ConfigProviders.save_providers(
                mock.MagicMock(), provider_order='%s:1' % provider.get_id(),
                **dict({'%s_digest' % provider.get_id(): digest}, **(form or {})))
        return provider

    def test_changed_cookie(self):
        provider = self.save('uid=1;pass=new')
        self.assertEqual('uid=1;pass=new', provider.digest)
        provider.cache.set_last_update.assert_called_once()

    def test_same_cookie(self):
        self.save('uid=1;pass=old').cache.set_last_update.assert_not_called()

    def test_no_change_for_a_login_value_that_is_not_a_setting(self):
        # e.g. a uid that a login gives, or an api key not saved yet, is not a change made on the page
        provider = self.save('uid=1;pass=old', uid='123', api_key=None)
        provider.cache.set_last_update.assert_not_called()
        self.assertEqual('123', provider.uid)

    def test_changed_uid_on_the_page(self):
        provider = self.save('uid=1;pass=old', form={'cookie_prov_uid': '456'}, uid='123')
        self.assertEqual('456', provider.uid)
        provider.cache.set_last_update.assert_called_once()


if '__main__' == __name__:
    for case in (MilkieLoginTests, LoginLogTests, JsonReplyLoginTests, CookieSettingTests, LoginSettingSaveTests):
        unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromTestCase(case))
