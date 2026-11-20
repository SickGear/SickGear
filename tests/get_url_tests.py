import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import requests
from requests.models import Response

from sg_helpers import get_url


class FakeSession(requests.Session):
    def __init__(self, content):
        super(FakeSession, self).__init__()
        self.content = content if isinstance(content, bytes) else content.encode('utf-8')

    def request(self, method, url, *args, **kwargs):
        response = Response()
        response.status_code = 200
        response.url = str(url)
        response.encoding = 'utf-8'
        response._content = self.content
        return response


class SignatureProvider(object):
    @staticmethod
    def _has_signature(data=None):
        return data and 'example.org' in data


def fs_reply_no_challenge(page):
    return json.dumps({'status': 'ok', 'message': 'Challenge not detected!',
                       'solution': {'url': 'https://example.org/', 'status': 200, 'response': page}}).encode('utf-8')


class GetUrlTests(unittest.TestCase):
    @staticmethod
    def get_url(content, **kwargs):
        return get_url('https://example.org/', session=FakeSession(content), nocache=True, **kwargs)

    def test_page(self):
        page = '<html><body><table id="results"></table></body></html>'
        self.assertEqual(page, self.get_url(page))

    def test_provider_page(self):
        page = '<html><body><table id="results"></table></body></html>'
        self.assertEqual(page, self.get_url(page, provider=SignatureProvider))

    def test_provider_page_with_signature(self):
        page = '<html><head><title>Site</title></head><body><a href="https://example.org/"></a></body></html>'
        self.assertEqual(page, self.get_url(page, provider=SignatureProvider))

    def test_proxy_browser_page(self):
        page = '<html><body><table id="results"></table></body></html>'
        self.assertEqual(page, self.get_url(fs_reply_no_challenge(page), proxy_browser=True))

    def test_proxy_browser_json_document(self):
        page = ('<html><head><meta name="color-scheme" content="light dark"></head><body>'
                '<pre style="word-wrap: break-word; white-space: pre-wrap;">'
                '[{"name":"Show S01E01 &amp; more","seeders":"5"}]</pre></body></html>')
        self.assertEqual([{'name': 'Show S01E01 & more', 'seeders': '5'}],
                         self.get_url(fs_reply_no_challenge(page), proxy_browser=True, parse_json=True))

    def test_proxy_browser_page_with_provider_signature(self):
        page = '<html><head><title>Site</title></head><body><table class="table2"></table></body></html>'
        self.assertEqual(page, self.get_url(fs_reply_no_challenge(page), proxy_browser=True, provider=SignatureProvider))

    def test_json_without_proxy_browser(self):
        self.assertEqual([{'name': 'Show S01E01'}],
                         self.get_url(b'[{"name":"Show S01E01"}]', parse_json=True))

    def test_cache_adapter_is_mounted_once_per_session(self):
        session = FakeSession('page')
        get_url('https://example.org/', session=session)
        adapter = session.adapters['https://']
        get_url('https://example.org/', session=session)
        self.assertIs(adapter, session.adapters['https://'])


class SharedPoolTests(unittest.TestCase):
    """ requests with no session of the caller reuse a connection, each of them used to open a new one """

    def setUp(self):
        connections = self.connections = set()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                connections.add(self.client_address)
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%s/' % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_no_session_no_cache(self):
        self.assertEqual(['ok'] * 5, [get_url(self.url, nocache=True) for _ in range(5)])
        self.assertEqual(1, len(self.connections))

    def test_no_session_with_cache(self):
        self.assertEqual(['ok'] * 5, [get_url(self.url) for _ in range(5)])
        self.assertEqual(1, len(self.connections))

    def test_session_of_the_caller_keeps_its_own_adapter(self):
        session = requests.Session()
        adapter = session.adapters['http://']
        self.assertEqual('ok', get_url(self.url, session=session, nocache=True))
        self.assertIs(adapter, session.adapters['http://'])


if '__main__' == __name__:
    for cur_case in (GetUrlTests, SharedPoolTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
