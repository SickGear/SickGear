import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import requests

import sg_tunnel

SUFFIX = 'tunnel.example'
PIN_IP, SEED_IP = '192.0.2.10', '192.0.2.20'


def _payload():
    return dict(
        issued=1, suffix=SUFFIX, api_hosts={f'api.{SUFFIX}': [PIN_IP]}, pins={PIN_IP: 'a' * 64},
        paths=dict((k, f'/v1/{k.lower()}') for k in (
            'RegisterSubscriber', 'SubscriberLogin', 'RegisterDevice', 'DeviceGeneratePassword', 'Discover')),
        client=dict(api_login='l', api_password='p', client_version='1', kind='t', user_agent='ua',
                    label='d', os='o', geo_format='"%s",,', mail_domain='.mail.example',
                    headers=[['X-Version', 'client_version'], ['User-Agent', 'user_agent']]),
        params=dict((k, [f'f{n}' for n in range(c)]) for k, c in sg_tunnel._PARAM_COUNT.items()),
        regions=['EU'], seeds={'EU': [[SEED_IP, 443]]})


def _seal(master, plain):
    # the encryption of the private generator, so a test entry decodes like a real one
    salt = os.urandom(16)
    keys = hashlib.pbkdf2_hmac('sha256', master, salt, sg_tunnel.ITERATIONS, 64)
    cipher = bytes(a ^ b for a, b in zip(plain, sg_tunnel._keystream(keys[:32], salt, len(plain))))
    tag = hmac.new(keys[32:], sg_tunnel.VERSION + salt + cipher, hashlib.sha256).digest()
    return sg_tunnel.VERSION + salt + tag + cipher


def _entry(payload=None, blob=None):
    master = sg_tunnel._key_master()
    name = base64.b64encode(hmac.new(master, b'name', hashlib.sha256).digest()[:12]).decode()
    blob = blob or _seal(master, json.dumps(payload or _payload()).encode())
    text = blob.hex()
    return {name: [['gh'] + [text[i:i + 16][::-1] for i in range(0, len(text), 16)]],
            base64.b64encode(b'other entry!').decode(): [['xy', 'abc']]}


class DataTests(unittest.TestCase):

    def setUp(self):
        sg_tunnel._reset()
        sg_tunnel._issued.clear()

    def test_load_good_entry(self):
        self.assertTrue(sg_tunnel.load(_entry()))
        self.assertEqual(SUFFIX, sg_tunnel._ctx['data']['suffix'])
        self.assertEqual((sg_tunnel.OFF, ''), sg_tunnel.state())

    def test_load_tampered_entry_fails_closed(self):
        obf = _entry()
        name = next(iter(obf))
        chunk = obf[name][0][1]
        obf[name][0][1] = ('0' if '1' == chunk[0] else '1') + chunk[1:]
        self.assertFalse(sg_tunnel.load(obf))
        self.assertEqual(sg_tunnel.NO_DATA, sg_tunnel.state()[0])
        self.assertIsNone(sg_tunnel.proxy())

    def test_load_bad_field_fails_closed(self):
        for change in (dict(pins={'not an ip': 'a' * 64}), dict(suffix='bad suffix'),
                       dict(seeds={'EU': [[SEED_IP, 70000]]}), dict(params={'Discover': ['one']})):
            sg_tunnel._reset()
            self.assertFalse(sg_tunnel.load(_entry(dict(_payload(), **change))), change)

    def test_load_rejects_no_entry_and_non_dict(self):
        for obf in (None, {}, 'data', [], {'x': []}):
            sg_tunnel._reset()
            self.assertFalse(sg_tunnel.load(obf), obf)

    def test_crlf_checkout_gives_same_key(self):
        with open(sg_tunnel.__file__.replace('.pyc', '.py'), 'rb') as fh:
            raw = fh.read()
        crlf = raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        with mock.patch('builtins.open', mock.mock_open(read_data=crlf)):
            self.assertEqual(hashlib.sha256(raw.replace(b'\r\n', b'\n')).digest(), sg_tunnel._key_master())


class RouteTests(unittest.TestCase):

    def setUp(self):
        sg_tunnel._reset()
        sg_tunnel._issued.clear()
        sg_tunnel.load(_entry())
        self.calls = []

        def api(path_key, *values):
            self.calls.append(path_key)
            if 'RegisterDevice' == path_key:
                return dict(device_id='dev', device_password='pw:/@x')
            if 'DeviceGeneratePassword' == path_key:
                return dict(device_password='new')
            if 'Discover' == path_key:
                raise sg_tunnel._ApiError(801)
            return {}
        patches = [mock.patch.object(sg_tunnel, '_api', side_effect=api),
                   mock.patch.object(sg_tunnel, '_probe', return_value=0.1)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_proxy_registers_and_uses_seed_on_discover_error(self):
        proxy = sg_tunnel.proxy()
        self.assertEqual(['RegisterSubscriber', 'RegisterDevice', 'Discover'], self.calls)
        self.assertTrue(proxy.endswith(f'@{SEED_IP}:443'))
        self.assertNotIn('pw:/@x', proxy)  # quoted
        self.assertEqual(sg_tunnel.READY, sg_tunnel.state()[0])

    def test_adapter_kwargs_check_proxy_cert_by_name(self):
        proxy = sg_tunnel.proxy()
        kwargs = sg_tunnel.adapter_kwargs(proxy)
        self.assertEqual(f'eu0.{SUFFIX}', kwargs['proxy_assert_hostname'])
        self.assertEqual(sg_tunnel.ssl.CERT_REQUIRED, kwargs['proxy_ssl_context'].verify_mode)
        self.assertEqual({}, sg_tunnel.adapter_kwargs('https://u:p@198.51.100.1:443'))

    def test_issued_proxy_without_data_is_refused(self):
        proxy = sg_tunnel.proxy()
        sg_tunnel.load({'x': []})
        self.assertEqual('invalid.', sg_tunnel.adapter_kwargs(proxy)['proxy_assert_hostname'])
        self.assertTrue(sg_tunnel.is_tunnel(proxy))

    def test_failed_rests_endpoint_then_rediscovers(self):
        proxy = sg_tunnel.proxy()
        sg_tunnel.failed(proxy)
        self.assertTrue(sg_tunnel._endpoint_of(proxy)['rest_until'] > 0)
        sg_tunnel.proxy()
        self.assertEqual(2, self.calls.count('Discover'))

    def test_407_refreshes_login(self):
        proxy = sg_tunnel.proxy()
        sg_tunnel.failed(proxy, 407)
        sg_tunnel.proxy()
        self.assertIn('DeviceGeneratePassword', self.calls)
        self.assertEqual('new', sg_tunnel._ctx['creds'][1])

    def test_login_failure_waits_before_retry(self):
        sg_tunnel._api.side_effect = OSError('no pinned API address answered')
        self.assertIsNone(sg_tunnel.proxy())
        self.assertEqual((sg_tunnel.FAILED, 'tunnel login failed'), sg_tunnel.state())
        sg_tunnel._api.reset_mock()
        self.assertIsNone(sg_tunnel.proxy())
        sg_tunnel._api.assert_not_called()

    def test_scrub_hides_login_and_addresses(self):
        proxy = sg_tunnel.proxy()
        text = sg_tunnel.scrub(f'ProxyError for {proxy} via {PIN_IP}')
        self.assertNotIn(SEED_IP, text)
        self.assertNotIn(PIN_IP, text)
        self.assertNotIn('pw', text)
        self.assertNotIn(sg_tunnel._ctx['creds'][0], text)


class FaultTests(unittest.TestCase):

    def test_endpoint_fault(self):
        proxy_error = requests.exceptions.ProxyError
        self.assertEqual(407, sg_tunnel.endpoint_fault(proxy_error(
            "ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 407 Proxy Auth'))")))
        self.assertFalse(sg_tunnel.endpoint_fault(proxy_error(
            "ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 502 Bad Gateway'))")))
        self.assertTrue(sg_tunnel.endpoint_fault(proxy_error(
            "ProxyError('Unable to connect to proxy', ConnectTimeoutError('timed out'))")))
        self.assertFalse(sg_tunnel.endpoint_fault(requests.exceptions.ConnectionError('refused')))


if '__main__' == __name__:
    unittest.main()
