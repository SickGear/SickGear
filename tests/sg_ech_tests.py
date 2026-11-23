import socket
import sys
import threading
import time
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from urllib3.contrib.resolver import BaseResolver, ManyResolver
from urllib3.contrib.resolver.factories import ResolverDescription
from urllib3.exceptions import HTTPError, MaxRetryError

import sg_ech

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
        self.hook = mock.Mock()
        self.patches = [mock.patch.object(sg_ech, 'on_route_change', self.hook)]
        self.probe(ip='172.66.134.33', no_sni=True, cloudflare=True, ech=True, backend=True)

    def tearDown(self):
        for cur_patch in self.patches:
            cur_patch.stop()
        sg_ech.blocked_domains.clear()
        sg_ech._checked.clear()

    def probe(self, ip, no_sni, cloudflare, ech, backend):
        if not self.patches[0].is_started:
            self.patches[0].start()
        for cur_name, cur_value in (('_resolve_ip', ip), ('_no_sni_handshake', no_sni), ('_is_cloudflare', cloudflare),
                                    ('_has_ech', ech), ('_ech_backend', backend)):
            self.patches.append(mock.patch.object(sg_ech, cur_name, return_value=cur_value))
            self.patches[-1].start()

    def reprobe(self, **kwargs):
        for cur_patch in self.patches[1:]:
            cur_patch.stop()
        del self.patches[1:]
        values = dict(ip='172.66.134.33', no_sni=True, cloudflare=True, ech=True, backend=True)
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

    def test_no_sni_fails(self):
        self.reprobe(no_sni=False)
        self.assert_nothing()

    def test_not_cloudflare(self):
        self.reprobe(cloudflare=False)
        self.assert_nothing()

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

    def test_concurrent_same_host_checks_once(self):
        calls = []

        def slow(ip):
            calls.append(ip)
            time.sleep(0.2)
            return True

        sg_ech._no_sni_handshake.side_effect = slow
        with self.assertLogs('sg.helper', 'INFO') as logs:
            threads = [threading.Thread(target=sg_ech.check_ssl_failure, args=(self.url, '')) for _ in range(5)]
            [_t.start() for _t in threads]
            [_t.join() for _t in threads]
        self.assertEqual(1, len(calls))
        self.assertEqual(1, len(logs.output))
        self.hook.assert_called_once_with()


class ProbeTests(unittest.TestCase):

    def test_is_cloudflare(self):
        self.assertTrue(sg_ech._is_cloudflare('172.66.134.33'))
        self.assertTrue(sg_ech._is_cloudflare('2606:4700:10::ac42:8621'))
        self.assertFalse(sg_ech._is_cloudflare('192.168.1.10'))
        self.assertFalse(sg_ech._is_cloudflare('not an ip'))


if '__main__' == __name__:
    unittest.main()
