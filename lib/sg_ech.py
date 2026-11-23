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
import time

import certifi
import requests
import urllib3.exceptions

from _23 import urlparse

# noinspection PyUnreachableCode
if False:
    from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger('sg.helper')
logger.addHandler(logging.NullHandler())

BUILTIN_DOH = ('doh+cloudflare://', 'doh+quad9://', 'doh+google://')
# DoH servers with a JSON API to read the HTTPS record, Quad9 has none
JSON_DOH = ('https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve')
TIMEOUT = 10
NAMED_TIMEOUT = 5  # a block that drops packets hangs, the edge just answered the outer name probe so 5 s is ample
ECH_OUTER = 'cloudflare-ech.com'  # the server name Cloudflare ECH sends in the clear
RETRY_AFTER = 600  # seconds before a check that gave no answer runs again

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
_checked = {}  # type: Dict[Tuple[str, bool], str]
_retry_at = {}  # type: Dict[Tuple[str, bool], float]
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
    :return: the first address of host from the DNS of the system, as the fetch that failed used, None on timeout
    """
    found = []

    def _lookup():
        try:
            found.extend(socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP))
        except (BaseException, Exception):
            pass

    # getaddrinfo has no timeout, a daemon thread that is left behind ends when the lookup does
    lookup = threading.Thread(target=_lookup, daemon=True)
    lookup.start()
    lookup.join(TIMEOUT)
    return found and found[0][4][0] or None


def _outer_name_handshake(ip):
    # type: (str) -> bool
    """
    :return: True if a TLS handshake to ip completes with the ECH outer name, the address and the name ECH sends are
     then not blocked. Not with no server name, as some Cloudflare edges reject a handshake that has none
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=ECH_OUTER):
                return True
    except (BaseException, Exception):
        return False


def _named_handshake(ip, host):
    # type: (str, str) -> bool
    """
    :return: True if a TLS handshake to ip with server name host completes with a valid certificate for host, the
     failed fetch was then not a block. A block resets the handshake or answers with a certificate not for host
    """
    context = ssl.create_default_context()
    # both stores, so a root missing from either one is not taken for a block, the OS store alone if certifi fails
    try:
        context.load_verify_locations(certifi.where())
    except (BaseException, Exception):
        pass
    try:
        with socket.create_connection((ip, 443), timeout=NAMED_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host):
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
    # type: (str, Optional[str]) -> Tuple[str, bool, str]
    """
    :return: outcome, True if it holds for the run, False if the check gave no answer and may run again later, and why
    """
    ip = _resolve_ip(host)
    if not ip:
        return NOTHING, False, 'no address from DNS'
    if not _is_cloudflare(ip):
        return NOTHING, True, f'{ip} is not Cloudflare'
    if not _outer_name_handshake(ip):
        return NOTHING, False, f'{ip} fails a handshake with the ECH outer name'
    if _named_handshake(ip, host):
        return NOTHING, False, f'{ip} completes a handshake with the name, not a block'
    ech = _has_ech(host, user_resolver)
    if None is ech:
        return NOTHING, False, 'no DoH server answers for the HTTPS record'
    if not ech:
        return ECH_OFF, True, 'no ECH config in the HTTPS record'
    if not _ech_backend():
        return NO_BACKEND, True, 'no TLS backend that can do ECH'
    # a DoH user setting already gives ECH its config, the failure is then something else
    if (user_resolver or '').startswith('doh'):
        return NOTHING, True, 'the DoH setting already gives ECH its config'
    return ROUTED, True, 'ECH on'


def is_ssl_error(error):
    # type: (BaseException) -> bool
    """
    :return: True if error, or an error it was raised from, is a failed TLS handshake
    """
    seen = set()
    while None is not error and id(error) not in seen:
        if isinstance(error, (requests.exceptions.SSLError, urllib3.exceptions.SSLError, ssl.SSLError)):
            return True
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return False


def check_ssl_failure(url, user_resolver):
    # type: (str, Optional[str]) -> str
    """
    find out if a TLS handshake failure on url is an ISP block by server name of a Cloudflare site, and what ECH
    can do about it. Each host is checked once per run and the outcome logged once, a check that gave no answer
    runs again after RETRY_AFTER seconds

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

    # the outcome differs with a DoH user setting, a change of setting checks again
    key = (host, (user_resolver or '').startswith('doh'))
    with _locks_lock:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        if key in _checked:
            return _checked[key]
        if time.monotonic() < _retry_at.get(key, 0):
            return NOTHING
        try:
            outcome, final, why = _outcome(host, user_resolver)
        except (BaseException, Exception) as e:
            outcome, final, why = NOTHING, False, f'check failed: {e}'
        logger.debug(f'ECH check of {host} gives {outcome}, {why}{("", ", may run again later")[not final]}')
        if final:
            _checked[key] = outcome
            _retry_at.pop(key, None)
        else:
            _retry_at[key] = time.monotonic() + RETRY_AFTER

        if ROUTED == outcome:
            blocked_domains.add(host)
            logger.info(f'ISP blocks {host} by name, the site has ECH on, {host} now looks up via DNS over HTTPS'
                        f' to use ECH')
            try:
                on_route_change()
            except (BaseException, Exception) as e:
                logger.debug(f'Failed to rebuild sessions for {host}: {e}')
        elif NO_BACKEND == outcome:
            logger.info(f'ISP blocks {host} by name, the site has ECH on, install rtls (pip install rtls)'
                        f' to get through')
        elif ECH_OFF == outcome:
            logger.info(f'ISP blocks {host} by name, the site is on Cloudflare with ECH off, its owner can turn ECH on,'
                        f' else use a proxy')
        return outcome
