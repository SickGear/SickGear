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

# Tunnel route for a provider that is blocked and has no ECH route, an HTTPS proxy whose settings come from data.txt
#
# !! The bytes of this file key its entry in the extdata data.txt. After ANY edit of this file, rerun the private
# !! generator for each ref that users run (e.g. --ref main --ref dev) and upload data.txt, else the tunnel stays off
# !! for that version (it fails closed and logs that the tunnel data needs an update)
#
# Each step fails closed
#   API, by pinned IP only, no server name sent, the cert hash must match a pin from the data
#   endpoints, only from the API discover answer or the data seeds, no server name sent, public CA and name check
#   the device login lives in memory, a new install or restart registers again, none of it is logged

import base64
import binascii
import concurrent.futures
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import random
import re
import socket
import ssl
import threading
import time

import certifi
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPDigestAuth

from _23 import quote

# noinspection PyUnreachableCode
if False:
    from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('sg.helper')
logger.addHandler(logging.NullHandler())

VERSION = b'\x01'
ITERATIONS = 200000
TIMEOUT = 15
REFRESH = 4 * 60 * 60  # shortcut: the reference client refreshes each 4 h, revisit with the measured login lifetime
RETRY_AFTER = 600  # seconds before a failed route is tried again
ENDPOINT_BACKOFF = (60, 300, 900)  # seconds an endpoint rests after its 1st, 2nd, 3rd and later failure

OFF, NO_DATA, READY, FAILED = 'off', 'no data', 'ready', 'failed'

_lock = threading.RLock()
_ctx = {}  # type: Dict[str, Any]
# every endpoint ever handed out, with its region, kept over a reset, so a proxy url that a session still holds
# after a rediscover or a data change gets the CA and name check too, never the session policy
_issued = {}  # type: Dict[Tuple[str, int], str]


def _reset():
    _ctx.clear()
    _ctx.update(obf_id=None, data=None, state=OFF, reason='', retry_at=0,
                session=None, device=None, auth_at=0, endpoints=[], creds=None)


_reset()


# data -----------------------------------------------------------------------------------------------------------------
def _key_master():
    # type: (...) -> bytes
    with open(f'{os.path.splitext(__file__)[0]}.py', 'rb') as fh:
        return hashlib.sha256(fh.read().replace(b'\r\n', b'\n')).digest()


def _keystream(key, salt, size):
    # type: (bytes, bytes, int) -> bytes
    out, n = b'', 0
    while len(out) < size:
        out += hmac.new(key, salt + n.to_bytes(4, 'big'), hashlib.sha256).digest()
        n += 1
    return out[:size]


def _unseal(master, blob):
    # type: (bytes, bytes) -> Optional[bytes]
    if len(blob) < 49 or VERSION != blob[:1]:
        return None
    salt, tag, cipher = blob[1:17], blob[17:49], blob[49:]
    keys = hashlib.pbkdf2_hmac('sha256', master, salt, ITERATIONS, 64)
    if not hmac.compare_digest(tag, hmac.new(keys[32:], VERSION + salt + cipher, hashlib.sha256).digest()):
        return None
    return bytes(a ^ b for a, b in zip(cipher, _keystream(keys[:32], salt, len(cipher))))


def _reveal(parts):
    # type: (List[List[str]]) -> bytes
    return bytes.fromhex(''.join(''.join(re.sub(rf'[\s{p[0]}]+', '', c[::-1]) for c in p[1:]) for p in parts))


def _valid_ip(ip):
    # type: (Any) -> bool
    try:
        ipaddress.ip_address(ip)
        return True
    except (ValueError, TypeError):
        return False


# values each call sends, in the order of the field names the data gives
_PARAM_COUNT = dict(RegisterSubscriber=2, RegisterDevice=3, Discover=2, SubscriberLogin=3, DeviceGeneratePassword=1)


def _check(data):
    # type: (Dict) -> Dict
    """
    :return: data when every field has the form this code relies on, else raise ValueError
    """
    def need(ok):
        if not ok:
            raise ValueError
    need(isinstance(data.get('suffix'), str) and re.match(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', data['suffix']))
    pins = data.get('pins')
    need(isinstance(pins, dict) and pins and all(
        _valid_ip(ip) and isinstance(fp, str) and re.match(r'^[0-9a-f]{64}$', fp) for ip, fp in pins.items()))
    hosts = data.get('api_hosts')
    need(isinstance(hosts, dict) and all(
        isinstance(h, str) and h.endswith('.' + data['suffix']) and isinstance(ips, list) for h, ips in hosts.items()))
    need(isinstance(data.get('paths'), dict) and all(
        isinstance(data['paths'].get(k), str) and data['paths'][k].startswith('/') for k in (
            'RegisterSubscriber', 'SubscriberLogin', 'RegisterDevice', 'DeviceGeneratePassword', 'Discover')))
    client = data.get('client')
    need(isinstance(client, dict) and all(isinstance(client.get(k), str) and client[k] for k in (
        'api_login', 'api_password', 'client_version', 'kind', 'user_agent', 'label', 'os',
        'geo_format', 'mail_domain')) and '%s' in client['geo_format'] and client['mail_domain'].startswith('.'))
    need(isinstance(client.get('headers'), list) and all(
        isinstance(h, list) and 2 == len(h) and isinstance(h[0], str) and re.match(r'^[\w-]+$', h[0])
        and h[1] in ('client_version', 'os', 'user_agent') for h in client['headers']))
    params = data.get('params')
    need(isinstance(params, dict) and all(
        isinstance(params.get(k), list) and n == len(params[k]) and all(isinstance(p, str) for p in params[k])
        for k, n in _PARAM_COUNT.items()))
    need(isinstance(data.get('regions'), list) and data['regions'] and all(
        isinstance(r, str) and re.match(r'^[A-Z]{2}$', r) for r in data['regions']))
    seeds = data.get('seeds')
    need(isinstance(seeds, dict) and all(isinstance(v, list) and all(
        isinstance(e, list) and 2 == len(e) and _valid_ip(e[0]) and isinstance(e[1], int) and 0 < e[1] < 65536
        for e in v) for v in seeds.values()))
    return data


def load(obf):
    # type: (Optional[Dict]) -> bool
    """
    :param obf: the decoded data.txt that the providers fetch
    :return: True when the tunnel entry of this version decodes and checks out
    """
    with _lock:
        if obf is not None and id(obf) == _ctx['obf_id']:
            return None is not _ctx['data']
        _ctx['obf_id'] = id(obf) if obf is not None else None
        data = None
        if isinstance(obf, dict) and obf:
            master = _key_master()
            name = base64.b64encode(hmac.new(master, b'name', hashlib.sha256).digest()[:12]).decode()
            try:
                plain = _unseal(master, _reveal(obf[name])) if name in obf else None
                data = plain and _check(json.loads(plain.decode('utf-8')))
            except (ValueError, TypeError, KeyError, IndexError, binascii.Error, UnicodeDecodeError):
                data = None
        if data != _ctx['data']:
            keep = _ctx['data'] and data and all(_ctx['data'][k] == data[k] for k in ('pins', 'client', 'paths'))
            if not keep:
                _reset()
                _ctx['obf_id'] = id(obf) if obf is not None else None
            _ctx['data'] = data
        if not data:
            _ctx['state'], _ctx['reason'] = NO_DATA, 'tunnel data needs an update for this version'
        elif NO_DATA == _ctx['state']:
            _ctx['state'], _ctx['reason'] = OFF, ''
        return None is not data


# API ------------------------------------------------------------------------------------------------------------------
class _ApiError(Exception):
    def __init__(self, code):
        super().__init__(f'API code {code}')
        self.code = code


class _PinAdapter(HTTPAdapter):
    """ the server cert must have this hash, the CA check is off as the API cert is self-signed """
    def __init__(self, fingerprint, **kwargs):
        self.fingerprint = fingerprint
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['assert_fingerprint'] = self.fingerprint
        super().init_poolmanager(*args, **kwargs)


def _api_session():
    # type: (...) -> requests.Session
    data = _ctx['data']
    if not _ctx['session']:
        session = requests.Session()
        session.trust_env = False  # no proxy or CA from the environment
        session.verify = False  # each pinned IP has its own adapter, all other urls have no adapter of use
        session.adapters.clear()
        for ip, fingerprint in data['pins'].items():
            session.mount(f'https://{ip}/', _PinAdapter(fingerprint))
        session.auth = HTTPDigestAuth(data['client']['api_login'], data['client']['api_password'])
        _ctx['session'] = session
    return _ctx['session']


def _api(path_key, *values):
    # type: (str, str) -> Dict
    """
    :param values: the field values of the call, in the order of the field names in the data
    :return: the data of the answer, raise _ApiError for an API error code, OSError when no pinned IP answers
    """
    data = _ctx['data']
    client = data['client']
    params = dict(zip(data['params'][path_key], values))
    headers = dict({h: client[k] for h, k in client['headers']}, Accept='application/json')
    host_of = {ip: host for host, ips in data['api_hosts'].items() for ip in ips}
    ips = list(data['pins'])
    random.SystemRandom().shuffle(ips)
    session = _api_session()
    for ip in ips:
        try:
            resp = session.post(
                f'https://{ip}{data["paths"][path_key]}', data=params, timeout=TIMEOUT, allow_redirects=False,
                headers=dict(headers, Host=host_of.get(ip) or sorted(data['api_hosts'])[0]))
            if 200 != resp.status_code:
                continue
            answer = resp.json()
            code = int(next(iter(answer['return_code'])))
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError, StopIteration, OSError):
            continue
        if code:
            raise _ApiError(code)
        return answer.get('data') or {}
    raise OSError('no pinned API address answered')


def _sha1(text):
    # type: (str) -> str
    return hashlib.sha1(text.encode('utf-8')).hexdigest().upper()


def _register():
    client = _ctx['data']['client']
    email = f'{base64.b64encode(os.urandom(32)).decode()}@{client["kind"]}{client["mail_domain"]}'
    _ctx['session'] = None  # a new cookie jar
    _api('RegisterSubscriber', email, _sha1(email))
    device = _api('RegisterDevice', client['kind'], os.urandom(20).hex().upper(), client['label'])
    if not (isinstance(device.get('device_id'), str) and isinstance(device.get('device_password'), str)):
        raise OSError('device registration gave no login')
    _ctx['device'] = dict(email=email, device_id=device['device_id'])
    _ctx['creds'] = (_sha1(device['device_id']), device['device_password'])
    _ctx['auth_at'] = time.time()


def _refresh():
    client, device = _ctx['data']['client'], _ctx['device']
    try:
        _api('SubscriberLogin', device['email'], _sha1(device['email']), client['kind'])
        new = _api('DeviceGeneratePassword', device['device_id'])
        if not isinstance(new.get('device_password'), str):
            raise OSError('password refresh gave no password')
        _ctx['creds'] = (_ctx['creds'][0], new['device_password'])
        _ctx['auth_at'] = time.time()
    except (_ApiError, OSError):
        _register()


# endpoints ------------------------------------------------------------------------------------------------------------
def _name(region):
    # type: (str) -> str
    """ a name the endpoint wildcard cert covers, the check is against the cert, nothing is sent """
    return f'{region.lower()}0.{_ctx["data"]["suffix"]}'


def proxy_ssl_context():
    # type: (...) -> ssl.SSLContext
    """ the proxy TLS check, apart from the session verify setting, so a session with verify off cannot weaken it """
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.check_hostname = False  # urllib3 matches the name given by proxy_assert_hostname, no server name is sent
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _probe(endpoint):
    # type: (Dict) -> Optional[float]
    """
    :return: seconds to a TLS session that passes the CA and name check, None on any failure
    """
    suffix = _ctx['data']['suffix']
    start = time.time()
    try:
        ctx = proxy_ssl_context()
        with socket.create_connection((endpoint['ip'], endpoint['port']), timeout=TIMEOUT) as sock, \
                ctx.wrap_socket(sock, server_hostname=None) as tls:
            names = [v for k, v in tls.getpeercert().get('subjectAltName', ()) if 'DNS' == k]
        if f'*.{suffix}' not in names:
            return None
    except (OSError, ssl.SSLError):
        return None
    return time.time() - start


def _discover():
    data = _ctx['data']
    client = data['client']
    found = []
    for region in data['regions']:
        try:
            ips = _api('Discover', _ctx['creds'][0], client['geo_format'] % region)
            ips = [(e['ip'], int((e.get('ports') or [443])[0])) for e in ips.get('ips', [])
                   if isinstance(e, dict) and _valid_ip(e.get('ip'))]
        except (_ApiError, OSError, ValueError, TypeError, KeyError):
            ips = []
        for ip, port in ips or [tuple(e) for e in data['seeds'].get(region, [])]:
            if 0 < port < 65536 and not any(ip == e['ip'] for e in found):
                found.append(dict(region=region, ip=ip, port=port, fails=0, rest_until=0, rtt=None))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for endpoint, rtt in zip(found, pool.map(_probe, found)):
            endpoint['rtt'] = rtt
    _ctx['endpoints'] = sorted((e for e in found if None is not e['rtt']), key=lambda e: e['rtt'])


def _fail_state(reason):
    _ctx['state'], _ctx['reason'], _ctx['retry_at'] = FAILED, reason, time.time() + RETRY_AFTER


def _ready():
    # type: (...) -> bool
    """ register, refresh and discover as needed, False when the tunnel is not usable now """
    if not _ctx['data']:
        return False
    if FAILED == _ctx['state'] and time.time() < _ctx['retry_at']:
        return False
    try:
        if not _ctx['creds']:
            _register()
        elif REFRESH < time.time() - _ctx['auth_at']:
            _refresh()
    except (_ApiError, OSError):
        _ctx['creds'] = None
        _fail_state('tunnel login failed')
        return False
    now = time.time()
    if not any(now >= e['rest_until'] for e in _ctx['endpoints']):
        _discover()
        if not _ctx['endpoints']:
            _fail_state('no tunnel endpoint passed its check')
            return False
    _ctx['state'], _ctx['reason'] = READY, ''
    return True


# use by SickGear ------------------------------------------------------------------------------------------------------
def proxy(region=None):
    # type: (Optional[str]) -> Optional[str]
    """
    :param region: a region code to prefer, else the fastest endpoint
    :return: proxy url of the best endpoint at rest, None when the tunnel is not usable, state() tells why
    """
    with _lock:
        if not _ready():
            return None
        now = time.time()
        usable = [e for e in _ctx['endpoints'] if now >= e['rest_until']]
        usable.sort(key=lambda e: (region != e['region'], e['rtt']))
        login, password = (quote(x, safe='') for x in _ctx['creds'])
        endpoint = usable[0]
        _issued[(endpoint['ip'], endpoint['port'])] = endpoint['region']
        return f'https://{login}:{password}@{endpoint["ip"]}:{endpoint["port"]}'


def _address(proxy_url):
    # type: (Any) -> Optional[Tuple[str, int]]
    match = isinstance(proxy_url, str) and re.match(r'^https://[^@/]+@\[?([^\]/]+?)]?:(\d+)/?$', proxy_url)
    return match and (match.group(1), int(match.group(2))) or None


def _endpoint_of(proxy_url):
    # type: (Optional[str]) -> Optional[Dict]
    address = _address(proxy_url)
    for endpoint in (address and _ctx['endpoints']) or []:
        if (endpoint['ip'], endpoint['port']) == address:
            return endpoint


def is_tunnel(proxy_url):
    # type: (Any) -> bool
    with _lock:
        return _address(proxy_url) in _issued


def adapter_kwargs(proxy_url):
    # type: (str) -> Dict
    """
    :return: proxy manager kwargs for a tunnel proxy url, the CA and name check, else empty
    """
    with _lock:
        region = _issued.get(_address(proxy_url))
        if not region or not _ctx['data']:
            # an issued endpoint with no data left to name it, a name the cert can never have refuses the proxy
            return region and dict(proxy_ssl_context=proxy_ssl_context(), proxy_assert_hostname='invalid.') or {}
        return dict(proxy_ssl_context=proxy_ssl_context(), proxy_assert_hostname=_name(region))


def failed(proxy_url, status_code=None):
    # type: (str, Optional[int]) -> None
    """
    rest the endpoint of a failed request, a 407 also renews the login before the next use
    """
    with _lock:
        if 407 == status_code:
            _ctx['auth_at'] = 0
        endpoint = _endpoint_of(proxy_url)
        if endpoint:
            endpoint['rest_until'] = time.time() + ENDPOINT_BACKOFF[min(endpoint['fails'], len(ENDPOINT_BACKOFF) - 1)]
            endpoint['fails'] += 1


def endpoint_fault(error):
    # type: (BaseException) -> Any
    """
    :return: 407 for a login fault, True when the endpoint itself failed, False when the endpoint answered and the
     site failed behind it (the CONNECT answer code shows which), a site fault must not rest a good endpoint
    """
    code = re.search(r'Tunnel connection failed: (\d{3})', str(error))
    if code:
        return '407' == code.group(1) and 407
    return isinstance(error, requests.exceptions.ProxyError)


def succeeded(proxy_url):
    # type: (str) -> None
    with _lock:
        endpoint = _endpoint_of(proxy_url)
        if endpoint:
            endpoint['fails'] = 0


def state():
    # type: (...) -> Tuple[str, str]
    """
    :return: state and the reason of a state that is not ready, words fit for a log
    """
    with _lock:
        return _ctx['state'], _ctx['reason']


def scrub(text):
    # type: (Any) -> str
    """
    :return: text with the tunnel login and endpoint addresses replaced, for any log line about a tunnel request
    """
    text = str(text)
    with _lock:
        for secret in (_ctx['creds'] or ()):
            text = text.replace(quote(secret, safe=''), '***').replace(secret, '***')
        for n, endpoint in enumerate(_ctx['endpoints']):
            text = text.replace(endpoint['ip'], f'endpoint {n + 1}')
        for ip in (_ctx['data'] or {}).get('pins', {}):
            text = text.replace(ip, 'API')
    return re.sub(r'https://[^@\s/]+@', 'https://***@', text)
