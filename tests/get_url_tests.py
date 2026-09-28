import json
import os.path
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

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


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(GetUrlTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
