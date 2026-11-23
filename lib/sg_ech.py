# coding=utf-8
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

# Encrypted Client Hello (ECH) route past an ISP that blocks a site by the server name in the TLS handshake.
# A blocked domain is looked up via DNS over HTTPS (DoH), that gives the ECH config, and the name is then hidden

import ipaddress
import logging
import socket
import ssl
import threading

import requests

from _23 import urlparse

# noinspection PyUnreachableCode
if False:
    from typing import Dict, List, Optional, Union

logger = logging.getLogger('sg.helper')
logger.addHandler(logging.NullHandler())

BUILTIN_DOH = ('doh+cloudflare://', 'doh+quad9://', 'doh+google://')
# DoH servers with a JSON API to read the HTTPS record, Quad9 has none
JSON_DOH = ('https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve')
TIMEOUT = 10

ROUTED, NO_BACKEND, ECH_OFF, NOTHING = 'routed', 'no_backend', 'ech_off', 'nothing'

# shortcut: hardcoded Cloudflare ranges from cloudflare.com/ips-v4 and ips-v6 (2026-11-23), refresh when Cloudflare
# changes them
CLOUDFLARE_NETS = tuple(ipaddress.ip_network(_n) for _n in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32', '2a06:98c0::/29',
    '2c0f:f248::/32'))

blocked_domains = set()  # host names that go via DoH for this run
_checked = {}  # type: Dict[str, str]
_locks = {}  # type: Dict[str, threading.Lock]
_locks_lock = threading.Lock()


def on_route_change():
    # type: (...) -> None
    """
    called after a domain is added to blocked_domains, SickGear sets this to rebuild the provider sessions
    """


def session_resolver(user_resolver):
    # type: (Optional[str]) -> Union[None, str, List[str]]
    """
    :param user_resolver: resolver url of the user setting, empty for system DNS
    :return: the resolver for a session, the user setting as is when no domain is blocked, else a DoH chain limited
     to the blocked domains, then the user setting (or system DNS) for all else
    """
    if not blocked_domains:
        return user_resolver or None

    hosts = 'hosts=%s' % ','.join(sorted(blocked_domains))
    chain = ([user_resolver] if (user_resolver or '').startswith('doh') else []) \
        + [_r for _r in BUILTIN_DOH if _r != user_resolver]
    return ['%s%s%s' % (_r, ('?', '&')['?' in _r], hosts) for _r in chain] + [user_resolver or 'system://']


def _resolve_ip(host):
    # type: (str) -> Optional[str]
    """
    :return: the first address of host from the DNS of the system, as the fetch that failed used
    """
    for cur_info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
        return cur_info[4][0]


def _no_sni_handshake(ip):
    # type: (str) -> bool
    """
    :return: True if a TLS handshake to ip completes with no server name, the address is then not blocked
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock):
                return True
    except (BaseException, Exception):
        return False


def _is_cloudflare(ip):
    # type: (str) -> bool
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in _n for _n in CLOUDFLARE_NETS if _n.version == address.version)


def _has_ech(host, user_resolver):
    # type: (str, Optional[str]) -> Optional[bool]
    """
    :param user_resolver: unused, DoH resolver urls of the user setting give no JSON API to read the record with
    :return: True if the HTTPS record of host has an ECH config, False if not, None if no DoH server answers
    """
    for cur_url in JSON_DOH:
        try:
            response = requests.get(cur_url, params={'name': host, 'type': 'HTTPS'},
                                    headers={'accept': 'application/dns-json'}, timeout=TIMEOUT)
            answers = response.json().get('Answer') or []
        except (BaseException, Exception):
            continue
        return any(65 == _a.get('type') and 'ech=' in (_a.get('data') or '') for _a in answers)


def _ech_backend():
    # type: (...) -> bool
    """
    :return: True if a TLS backend that can do ECH is installed, rtls or utls
    """
    from urllib3.contrib.anytls import BACKEND
    return BACKEND in ('rtls', 'utls')


def _outcome(host, user_resolver):
    # type: (str, Optional[str]) -> str
    ip = _resolve_ip(host)
    if not ip or not _no_sni_handshake(ip) or not _is_cloudflare(ip):
        return NOTHING
    ech = _has_ech(host, user_resolver)
    if None is ech:
        return NOTHING
    if not ech:
        return ECH_OFF
    if not _ech_backend():
        return NO_BACKEND
    # a DoH user setting already gives ECH its config, the failure is then something else
    return (ROUTED, NOTHING)[(user_resolver or '').startswith('doh')]


def check_ssl_failure(url, user_resolver):
    # type: (str, Optional[str]) -> str
    """
    find out if a TLS handshake failure on url is an ISP block by server name of a Cloudflare site, and what ECH
    can do about it. Each host is checked once per run, the outcome is logged once

    :param url: url of the fetch that failed
    :param user_resolver: resolver url of the user setting, empty for system DNS
    :return: one of ROUTED, NO_BACKEND, ECH_OFF, NOTHING
    """
    host = (urlparse(url).hostname or '').lower()
    if not host or 'localhost' == host:
        return NOTHING
    try:
        ipaddress.ip_address(host)
        return NOTHING
    except ValueError:
        pass

    with _locks_lock:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        if host in _checked:
            return _checked[host]
        try:
            outcome = _outcome(host, user_resolver)
        except (BaseException, Exception):
            outcome = NOTHING
        _checked[host] = outcome

        if ROUTED == outcome:
            blocked_domains.add(host)
            logger.info(f'ISP blocks {host} by name, the site has ECH on, {host} now looks up via DNS over HTTPS'
                        f' to use ECH')
            on_route_change()
        elif NO_BACKEND == outcome:
            logger.info(f'ISP blocks {host} by name, the site has ECH on, install rtls (pip install rtls)'
                        f' to get through')
        elif ECH_OFF == outcome:
            logger.info(f'ISP blocks {host} by name, the site is on Cloudflare with ECH off, its owner can turn ECH on,'
                        f' else use a proxy')
        return outcome
