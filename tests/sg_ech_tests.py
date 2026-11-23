import socket
import sys
import unittest
from os.path import abspath, dirname, join

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


if '__main__' == __name__:
    unittest.main()
