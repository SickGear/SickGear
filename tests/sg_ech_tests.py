import socket
import sys
import threading
import time
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import certifi
import requests
from urllib3.contrib.resolver import BaseResolver, ManyResolver
from urllib3.contrib.resolver.factories import ResolverDescription
from urllib3.exceptions import HTTPError, MaxRetryError

import sg_ech
import sg_helpers
from sg_helpers import get_url

GOOD_ADDR = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.4', 443))


class _StubResolver(BaseResolver):
    protocol = None
    implementation = 'stub'

    def __init__(self, *patterns, **kwargs):
        super(_StubResolver, self).__init__(None, None, *patterns, **kwargs)

    def close(self):
        pass

    def is_available(self):
        return True


class _DeadResolver(_StubResolver):
    def getaddrinfo(self, host, port, family, type, proto=0, flags=0, *, quic_upgrade_via_dns_rr=False):
        raise MaxRetryError(None, '/')


class _GoodResolver(_StubResolver):
    def getaddrinfo(self, host, port, family, type, proto=0, flags=0, *, quic_upgrade_via_dns_rr=False):
        return [GOOD_ADDR]


class LimitedDohResolverTests(unittest.TestCase):

    def test_doh_resolver_accepts_hosts(self):
        resolver = ResolverDescription.from_url('doh+cloudflare://?hosts=a.org').new()
        try:
            self.assertTrue(resolver.support('a.org'))
            self.assertFalse(resolver.support('b.org'))
        finally:
            resolver.close()

    def test_doh_resolver_with_hosts_connects(self):
        # a closed local port, the lookup must fail as a connection error, not on a stray `patterns` argument
        resolver = ResolverDescription.from_url('doh://127.0.0.1:9/dns-query?hosts=a.org&timeout=2').new()
        try:
            with self.assertRaises((OSError, HTTPError)):
                resolver.getaddrinfo('a.org', 443, socket.AF_INET, socket.SOCK_STREAM)
        finally:
            resolver.close()

    def test_many_resolver_falls_through_down_server(self):
        resolver = ManyResolver(_DeadResolver('a.org'), _GoodResolver('a.org'))
        self.assertEqual([GOOD_ADDR], resolver.getaddrinfo('a.org', 443, socket.AF_UNSPEC, socket.SOCK_STREAM))


class SessionResolverTests(unittest.TestCase):

    host = 'www.torrentleech.org'

    def setUp(self):
        sg_ech.blocked_domains.clear()

    tearDown = setUp

    def test_no_blocked_system(self):
        self.assertIsNone(sg_ech.session_resolver(''))
        self.assertIsNone(sg_ech.session_resolver(None))

    def test_no_blocked_user(self):
        self.assertEqual('dou://1.1.1.1', sg_ech.session_resolver('dou://1.1.1.1'))

    def test_blocked_system(self):
        sg_ech.blocked_domains.add(self.host)
        self.assertEqual(['doh+cloudflare://?hosts=www.torrentleech.org', 'doh+quad9://?hosts=www.torrentleech.org',
                          'doh+google://?hosts=www.torrentleech.org', 'system://'], sg_ech.session_resolver(''))

    def test_blocked_two_hosts_sorted(self):
        sg_ech.blocked_domains.update({'z.org', 'a.org'})
        self.assertEqual('doh+cloudflare://?hosts=a.org,z.org', sg_ech.session_resolver('')[0])

    def test_blocked_user_doh_first(self):
        sg_ech.blocked_domains.add('h')
        self.assertEqual(['doh+quad9://?hosts=h', 'doh+cloudflare://?hosts=h', 'doh+google://?hosts=h',
                          'doh+quad9://'], sg_ech.session_resolver('doh+quad9://'))

    def test_blocked_user_not_doh_last(self):
        sg_ech.blocked_domains.add('h')
        self.assertEqual(['doh+cloudflare://?hosts=h', 'doh+quad9://?hosts=h', 'doh+google://?hosts=h',
                          'dou://1.1.1.1'], sg_ech.session_resolver('dou://1.1.1.1'))

    def test_blocked_user_doh_with_query(self):
        sg_ech.blocked_domains.add('h')
        result = sg_ech.session_resolver('doh://my.dns/dns-query?timeout=3')
        self.assertEqual('doh://my.dns/dns-query?timeout=3&hosts=h', result[0])
        self.assertEqual('doh://my.dns/dns-query?timeout=3', result[-1])


class CheckTests(unittest.TestCase):

    url = 'https://www.torrentleech.org/torrents/browse'
    host = 'www.torrentleech.org'

    def setUp(self):
        sg_ech.blocked_domains.clear()
        sg_ech._checked.clear()
        sg_ech._retry_at.clear()
        self.hook = mock.Mock()
        self.patches = [mock.patch.object(sg_ech, 'on_route_change', self.hook)]
        self.patches[0].start()
        self.probe(ip='172.66.134.33', outer=True, named=False, cloudflare=True, ech=True, backend=True)

    def tearDown(self):
        for cur_patch in self.patches:
            cur_patch.stop()
        sg_ech.blocked_domains.clear()
        sg_ech._checked.clear()
        sg_ech._retry_at.clear()

    def probe(self, ip, outer, named, cloudflare, ech, backend):
        for cur_name, cur_value in (('_resolve_ip', ip), ('_outer_name_handshake', outer), ('_named_handshake', named),
                                    ('_is_cloudflare', cloudflare), ('_has_ech', ech), ('_ech_backend', backend)):
            self.patches.append(mock.patch.object(sg_ech, cur_name, return_value=cur_value))
            self.patches[-1].start()

    def reprobe(self, **kwargs):
        for cur_patch in self.patches[1:]:
            cur_patch.stop()
        del self.patches[1:]
        values = dict(ip='172.66.134.33', outer=True, named=False, cloudflare=True, ech=True, backend=True)
        values.update(kwargs)
        self.probe(**values)

    def assert_nothing(self, url=None, user_resolver=''):
        with self.assertNoLogs('sg.helper', 'INFO'):
            self.assertEqual(sg_ech.NOTHING, sg_ech.check_ssl_failure(url or self.url, user_resolver))
        self.assertEqual(set(), sg_ech.blocked_domains)
        self.hook.assert_not_called()

    def test_routed(self):
        with self.assertLogs('sg.helper', 'INFO') as logs:
            self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))
        self.assertEqual({self.host}, sg_ech.blocked_domains)
        self.hook.assert_called_once_with()
        self.assertIn('ISP blocks www.torrentleech.org by name, the site has ECH on, www.torrentleech.org now looks up'
                      ' via DNS over HTTPS to use ECH', logs.output[0])

    def test_routed_calls_hook_once(self):
        with self.assertLogs('sg.helper', 'INFO') as logs:
            sg_ech.check_ssl_failure(self.url, '')
            self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))
        self.assertEqual(1, len(logs.output))
        self.hook.assert_called_once_with()

    def test_no_backend(self):
        self.reprobe(backend=False)
        with self.assertLogs('sg.helper', 'INFO') as logs:
            self.assertEqual(sg_ech.NO_BACKEND, sg_ech.check_ssl_failure(self.url, ''))
        self.assertEqual(set(), sg_ech.blocked_domains)
        self.hook.assert_not_called()
        self.assertIn('ISP blocks www.torrentleech.org by name, the site has ECH on, install rtls (pip install rtls)'
                      ' to get through', logs.output[0])

    def test_ech_off(self):
        self.reprobe(ech=False)
        with self.assertLogs('sg.helper', 'INFO') as logs:
            self.assertEqual(sg_ech.ECH_OFF, sg_ech.check_ssl_failure(self.url, ''))
        self.assertEqual(set(), sg_ech.blocked_domains)
        self.assertIn('ISP blocks www.torrentleech.org by name, the site is on Cloudflare with ECH off, its owner can'
                      ' turn ECH on, else use a proxy', logs.output[0])

    def test_ip_literal_and_localhost(self):
        self.assert_nothing('https://192.168.1.10:9117/api')
        self.assert_nothing('https://[::1]/api')
        self.assert_nothing('https://localhost/api')
        sg_ech._resolve_ip.assert_not_called()

    def test_no_ip(self):
        self.reprobe(ip=None)
        self.assert_nothing()

    def test_outer_name_fails(self):
        self.reprobe(outer=False)
        self.assert_nothing()

    def test_not_cloudflare(self):
        self.reprobe(cloudflare=False)
        self.assert_nothing()
        sg_ech._outer_name_handshake.assert_not_called()

    def test_not_cloudflare_kept_after_wait(self):
        self.reprobe(cloudflare=False)
        self.assert_nothing()
        with mock.patch.object(sg_ech.time, 'monotonic', return_value=time.monotonic() + sg_ech.RETRY_AFTER + 1):
            self.assert_nothing()
        self.assertEqual(1, sg_ech._is_cloudflare.call_count)

    def test_outer_name_fail_retried_later(self):
        self.reprobe(outer=False)
        self.assert_nothing()
        self.reprobe()
        with mock.patch.object(sg_ech.time, 'monotonic', return_value=time.monotonic() + sg_ech.RETRY_AFTER + 1):
            with self.assertLogs('sg.helper', 'INFO'):
                self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))

    def test_ech_unknown(self):
        self.reprobe(ech=None)
        self.assert_nothing()

    def test_user_doh_has_backend(self):
        self.assert_nothing(user_resolver='doh+cloudflare://')

    def test_user_doh_missing_backend(self):
        self.reprobe(backend=False)
        with self.assertLogs('sg.helper', 'INFO'):
            self.assertEqual(sg_ech.NO_BACKEND, sg_ech.check_ssl_failure(self.url, 'doh+cloudflare://'))

    def test_probe_exception_is_nothing(self):
        sg_ech._resolve_ip.side_effect = OSError('boom')
        self.assert_nothing()

    def test_transient_not_kept_for_run(self):
        self.reprobe(ech=None)
        self.assert_nothing()
        self.assert_nothing()  # inside the wait, no probe again
        self.assertEqual(1, sg_ech._has_ech.call_count)
        self.reprobe()
        with mock.patch.object(sg_ech.time, 'monotonic', return_value=time.monotonic() + sg_ech.RETRY_AFTER + 1):
            with self.assertLogs('sg.helper', 'INFO'):
                self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))

    def test_probe_exception_retried_later(self):
        sg_ech._resolve_ip.side_effect = OSError('boom')
        self.assert_nothing()
        sg_ech._resolve_ip.side_effect = None
        with mock.patch.object(sg_ech.time, 'monotonic', return_value=time.monotonic() + sg_ech.RETRY_AFTER + 1):
            with self.assertLogs('sg.helper', 'INFO'):
                self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))

    def test_user_switches_doh_to_system(self):
        self.assert_nothing(user_resolver='doh+cloudflare://')
        with self.assertLogs('sg.helper', 'INFO'):
            self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))

    def test_named_handshake_ok_is_not_a_block(self):
        self.reprobe(named=True)
        self.assert_nothing()
        sg_ech._has_ech.assert_not_called()
        self.reprobe()
        with mock.patch.object(sg_ech.time, 'monotonic', return_value=time.monotonic() + sg_ech.RETRY_AFTER + 1):
            with self.assertLogs('sg.helper', 'INFO'):
                self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure(self.url, ''))

    def test_concurrent_same_host_checks_once(self):
        calls = []

        def slow(ip):
            calls.append(ip)
            time.sleep(0.2)
            return True

        sg_ech._outer_name_handshake.side_effect = slow
        with self.assertLogs('sg.helper', 'INFO') as logs:
            threads = [threading.Thread(target=sg_ech.check_ssl_failure, args=(self.url, '')) for _ in range(5)]
            [_t.start() for _t in threads]
            [_t.join() for _t in threads]
        self.assertEqual(1, len(calls))
        self.assertEqual(1, len(logs.output))
        self.hook.assert_called_once_with()


class ProbeTests(unittest.TestCase):

    def test_resolve_ip_error_is_silent(self):
        error = socket.gaierror(11001, 'getaddrinfo failed')
        with mock.patch.object(sg_ech.socket, 'getaddrinfo', side_effect=error), \
                mock.patch.object(threading, 'excepthook') as hook:
            self.assertIsNone(sg_ech._resolve_ip('nonexistent.invalid'))
        hook.assert_not_called()

    def test_named_handshake_uses_certifi_and_short_timeout(self):
        context = mock.MagicMock()
        with mock.patch.object(sg_ech.ssl, 'create_default_context', return_value=context), \
                mock.patch.object(sg_ech.socket, 'create_connection', side_effect=OSError('reset')) as connect:
            self.assertFalse(sg_ech._named_handshake('172.66.134.33', 'www.torrentleech.org'))
        context.load_verify_locations.assert_called_once_with(certifi.where())
        self.assertEqual(sg_ech.NAMED_TIMEOUT, connect.call_args.kwargs['timeout'])
        self.assertEqual(5, sg_ech.NAMED_TIMEOUT)

    def test_named_handshake_without_certifi_uses_os_store(self):
        context = mock.MagicMock()
        context.load_verify_locations.side_effect = FileNotFoundError('missing.pem')
        with mock.patch.object(sg_ech.ssl, 'create_default_context', return_value=context), \
                mock.patch.object(sg_ech.socket, 'create_connection', return_value=mock.MagicMock()):
            self.assertTrue(sg_ech._named_handshake('172.66.134.33', 'www.torrentleech.org'))

    def test_outer_name_handshake_sends_ech_outer_name(self):
        context = mock.MagicMock()
        with mock.patch.object(sg_ech.ssl, 'SSLContext', return_value=context), \
                mock.patch.object(sg_ech.socket, 'create_connection', return_value=mock.MagicMock()):
            self.assertTrue(sg_ech._outer_name_handshake('104.21.70.6'))
        self.assertEqual('cloudflare-ech.com', context.wrap_socket.call_args.kwargs['server_hostname'])

    def test_resolve_ip_times_out(self):
        def slow(*args, **kwargs):
            time.sleep(2)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.2.3.4', 443))]

        start = time.monotonic()
        with mock.patch.object(sg_ech, 'TIMEOUT', 0.2), mock.patch.object(sg_ech.socket, 'getaddrinfo', slow):
            self.assertIsNone(sg_ech._resolve_ip('slow.example'))
        self.assertLess(time.monotonic() - start, 1)

    def test_is_cloudflare(self):
        self.assertTrue(sg_ech._is_cloudflare('172.66.134.33'))
        self.assertTrue(sg_ech._is_cloudflare('2606:4700:10::ac42:8621'))
        self.assertFalse(sg_ech._is_cloudflare('192.168.1.10'))
        self.assertFalse(sg_ech._is_cloudflare('not an ip'))


class _RaisingSession(requests.Session):
    def __init__(self, error):
        super(_RaisingSession, self).__init__()
        self.error = error

    def request(self, method, url, *args, **kwargs):
        raise self.error


class HookFailureTests(unittest.TestCase):

    def setUp(self):
        sg_ech.blocked_domains.clear()
        sg_ech._checked.clear()
        sg_ech._retry_at.clear()

    tearDown = setUp

    def test_hook_exception_does_not_raise(self):
        with mock.patch.object(sg_ech, '_outcome', return_value=(sg_ech.ROUTED, True, 'ECH on')), \
                mock.patch.object(sg_ech, 'on_route_change', side_effect=RuntimeError('rebuild failed')):
            self.assertEqual(sg_ech.ROUTED, sg_ech.check_ssl_failure('https://blocked.example/', ''))


class GetUrlTests(unittest.TestCase):

    url = 'https://blocked.example/browse'

    def fetch(self, error):
        with mock.patch.object(sg_ech, 'check_ssl_failure', return_value=sg_ech.ROUTED) as check:
            with self.assertRaises(requests.exceptions.ConnectionError) as ctx:
                get_url(self.url, session=_RaisingSession(error), raise_exceptions=True, failure_monitor=False,
                        nocache=True, mute_connect_err=True)
        return check, ctx.exception

    def test_get_url_runs_check_on_ssl_error(self):
        check, error = self.fetch(requests.exceptions.SSLError('received corrupt message of type InvalidContentType'))
        check.assert_called_once_with(self.url, sg_helpers.DNS_RESOLVER)
        self.assertTrue(getattr(error, 'sg_ech_routed', False))

    def test_get_url_checks_the_host_a_redirect_failed_on(self):
        error = requests.exceptions.SSLError('received corrupt message of type InvalidContentType')
        error.request = mock.MagicMock(url='https://www.blocked.example/')
        check, _ = self.fetch(error)
        check.assert_called_once_with('https://www.blocked.example/', sg_helpers.DNS_RESOLVER)

    def test_get_url_no_check_on_plain_connection_error(self):
        check, error = self.fetch(requests.exceptions.ConnectionError('connection refused'))
        check.assert_not_called()
        self.assertFalse(getattr(error, 'sg_ech_routed', False))


class ProviderRetryTests(unittest.TestCase):

    def setUp(self):
        import test_lib  # noqa: F401, sets up sickgear for a provider
        from sickgear.providers import generic
        self.generic = generic
        self.provider = generic.TorrentProvider('TestProv')
        self.provider.should_skip = lambda **kwargs: False
        self.provider.is_public_access = lambda: True
        self.provider.fails.save_list = lambda: None

    def fetch(self, error):
        with mock.patch.object(self.generic.helpers, 'get_url', side_effect=[error, 'data']) as fetch:
            return self.provider.get_url('https://blocked.example/'), fetch

    def test_routed_retries_once_with_new_session(self):
        error = requests.exceptions.ConnectionError('blocked')
        error.sg_ech_routed = True
        data, fetch = self.fetch(error)
        self.assertEqual('data', data)
        self.assertEqual(2, fetch.call_count)
        self.assertIs(self.provider.session, fetch.call_args.kwargs['session'])
        self.assertEqual(0, self.provider.failure_count)

    def test_first_fetch_tells_get_url_of_the_retry(self):
        error = requests.exceptions.ConnectionError('blocked')
        error.sg_ech_routed = True
        _, fetch = self.fetch(error)
        self.assertTrue(fetch.call_args_list[0].kwargs.get('ech_retry'))
        self.assertNotIn('ech_retry', fetch.call_args_list[1].kwargs)

    def test_runtime_rebuild_keeps_cookies_and_old_session_open(self):
        from sickgear import providers
        old_session = self.provider.session
        old_session.cookies.set('uid', '42', domain='blocked.example')
        old_session.close = mock.Mock()
        with mock.patch.object(providers, 'sorted_sources', return_value=[self.provider]):
            providers.apply_dns_resolver('', close=False)
        self.assertIsNot(old_session, self.provider.session)
        self.assertEqual('42', self.provider.session.cookies.get('uid', domain='blocked.example'))
        old_session.close.assert_not_called()

    def test_not_routed_counts_failure(self):
        # no tunnel data, the tunnel route is not usable and the direct error counts
        self.provider._provider_data = lambda: None
        data, fetch = self.fetch(requests.exceptions.ConnectionError('refused'))
        self.assertIsNone(data)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(1, self.provider.failure_count)

    def test_not_routed_tries_tunnel(self):
        tunnel = mock.Mock(return_value='tunnel data')
        self.provider._tunnel_get = tunnel
        with mock.patch.object(self.generic.helpers, 'get_url',
                               side_effect=requests.exceptions.ConnectionError('refused')) as fetch:
            data = self.provider.get_url('https://blocked.example/')
        self.assertEqual('tunnel data', data)
        self.assertEqual(1, fetch.call_count)
        self.assertIsInstance(tunnel.call_args.kwargs['cause'], requests.exceptions.ConnectionError)
        self.assertEqual(0, self.provider.failure_count)

    def test_direct_failure_logged_as_warning_only_when_tunnel_fails(self):
        for tunnel_result, warned in (('tunnel data', False),
                                      (requests.exceptions.ConnectionError('tunnel down too'), True)):
            self.provider._tunnel_on = False
            self.provider._tunnel_get = mock.Mock(side_effect=[tunnel_result])
            error = requests.exceptions.ConnectionError('refused')
            error.sg_connect_msg = 'Connection error msg:refused while loading URL https://blocked.example/'
            with mock.patch.object(self.generic.helpers, 'get_url', side_effect=error) as fetch,                     mock.patch.object(self.generic.logger, 'warning') as warning:
                self.provider.get_url('https://blocked.example/')
            self.assertTrue(fetch.call_args.kwargs['defer_connect_log'])
            self.assertEqual(warned, mock.call(error.sg_connect_msg) in warning.call_args_list, tunnel_result)

    def test_get_url_defers_connection_warning_to_debug(self):
        with mock.patch.object(sg_helpers.logger, 'warning') as warning,                 mock.patch.object(sg_helpers.logger, 'debug') as debug:
            with self.assertRaises(requests.exceptions.ConnectionError) as ctx:
                get_url('https://blocked.example/', session=_RaisingSession(
                    requests.exceptions.ConnectionError('refused')), raise_exceptions=True, failure_monitor=False,
                    defer_connect_log=True)
        self.assertIn('refused', ctx.exception.sg_connect_msg)
        self.assertFalse([c for c in warning.call_args_list if 'Connection error' in c.args[0]])
        self.assertIn(mock.call(ctx.exception.sg_connect_msg), debug.call_args_list)

    def download(self, tunnel_on, direct_ok, tunnel_ok):
        self.provider._tunnel_on = tunnel_on
        self.provider._provider_data = lambda: None
        calls = []

        def download_file(url, filename, **kwargs):
            route = ('direct', 'tunnel')['tunnel_proxy' in kwargs]
            calls.append(route)
            return (direct_ok, tunnel_ok)['tunnel' == route]
        with mock.patch.object(self.generic.helpers, 'download_file', side_effect=download_file),                 mock.patch.object(self.generic.sg_tunnel, 'proxy', return_value='https://u:p@192.0.2.1:443'),                 mock.patch.object(self.generic.sg_tunnel, 'load'),                 mock.patch.object(self.generic.sg_tunnel, 'succeeded'):
            ok = self.provider.download_file('https://blocked.example/dl/1', 'f.torrent', session=None)
        return ok, calls

    def test_download_tries_tunnel_after_direct_fails(self):
        self.assertEqual((True, ['direct', 'tunnel']), self.download(False, False, True))
        self.assertTrue(self.provider._tunnel_on)

    def test_download_tunnel_first_once_on(self):
        self.assertEqual((True, ['tunnel']), self.download(True, False, True))
        self.assertEqual((True, ['tunnel', 'direct']), self.download(True, True, False))

    def test_download_direct_only_with_user_proxy(self):
        with mock.patch.object(self.generic.sickgear, 'PROXY_SETTING', 'http://127.0.0.1:1'):
            self.assertEqual((False, ['direct']), self.download(False, False, True))

    def test_tunnel_first_then_direct_on_tunnel_failure(self):
        self.provider._tunnel_on = True
        self.provider._tunnel_get = mock.Mock(side_effect=requests.exceptions.ConnectionError('tunnel down'))
        with mock.patch.object(self.generic.helpers, 'get_url', return_value='direct data') as fetch:
            data = self.provider.get_url('https://blocked.example/')
        self.assertEqual('direct data', data)
        self.assertEqual(1, fetch.call_count)
        self.assertFalse(self.provider._tunnel_on)


class EchRetryLogTests(unittest.TestCase):
    """ a routed failure of a fetch that its caller retries is a debug line and no failure count, else a warning and a
    count, as the retry logs and counts its own """

    url = 'https://blocked.example/browse'

    def fetch(self, ech_retry):
        lines, counts = [], []
        with mock.patch.object(sg_ech, 'check_ssl_failure', return_value=sg_ech.ROUTED),                 mock.patch.object(sg_helpers.logger, 'warning', side_effect=lambda m: lines.append('warning')),                 mock.patch.object(sg_helpers.logger, 'debug', side_effect=lambda m: lines.append('debug')),                 mock.patch.object(sg_helpers.DOMAIN_FAILURES, 'inc_failure_count',
                                  side_effect=lambda *a: counts.append(a)),                 mock.patch.object(sg_helpers, 'save_failure'):
            with self.assertRaises(requests.exceptions.ConnectionError):
                get_url(self.url, raise_exceptions=True, nocache=True, ech_retry=ech_retry,
                        session=_RaisingSession(requests.exceptions.SSLError('received corrupt message')))
        return 'warning' in lines, len(counts)

    def test_retried_is_debug_and_not_counted(self):
        self.assertEqual((False, 0), self.fetch(True))

    def test_not_retried_is_a_warning_and_counted(self):
        self.assertEqual((True, 1), self.fetch(False))


if '__main__' == __name__:
    unittest.main()
