import json
import os.path
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import requests
from requests.models import Response

from cfscrape import CloudflareScraper

FS_URL = 'http://flaresolverr.test:8191'
MISMATCH = ('Error: Error solving the challenge. Message: invalid cookie domain: Cookie \'domain\' mismatch\n'
            '  (Session info: chrome=152.0.7977.82)')


def fs_response(status_code, payload):
    response = Response()
    response.status_code = status_code
    response.url = '%s/v1' % FS_URL
    response.encoding = 'utf-8'
    response._content = json.dumps(payload).encode('utf-8')
    return response


class FakeFlareSolverr(object):
    """Stands in for requests.Session.request, i.e. the POST that CloudflareScraper sends to FlareSolverr.
    Like the real browser, it fails the whole request when given a cookie whose domain is not the page's host."""
    def __init__(self, landing_host='www.example.org', error=None):
        self.landing_host = landing_host
        self.error = error
        self.posts = []

    def __call__(self, session, method, url, *args, **kwargs):
        params = kwargs.get('json') or {}
        self.posts.append(params)
        if self.error:
            return fs_response(500, {'status': 'error', 'message': self.error})
        for cookie in params.get('cookies') or []:
            if not self.landing_host.endswith(cookie['domain'].lstrip('.')):
                return fs_response(500, {'status': 'error', 'message': MISMATCH})
        return fs_response(200, {'status': 'ok', 'message': 'Challenge not detected!',
                                 'solution': {'url': 'https://%s/' % self.landing_host, 'status': 200,
                                              'response': '<html>ok</html>', 'cookies': []}})


class CloudflareScraperCookieTests(unittest.TestCase):

    def get_content(self, fake, url='https://www.example.org/search/tv/Show+S01E01/'):
        scraper = CloudflareScraper()
        scraper.test_flaresolverr = lambda url_solver: 'v1 3.5.2'
        scraper.cookies.set('cf_clearance', 'abc', domain='.example.org', path='/')
        # a third-party cookie left in the jar by a previously solved page
        scraper.cookies.set('_ad_id', 'xyz', domain='.ads.example.net', path='/')
        original = requests.Session.request
        requests.Session.request = lambda session, *args, **kwargs: fake(session, *args, **kwargs)
        try:
            return scraper.get_content('GET', url, FS_URL, 'UA', proxy_browser=True)
        finally:
            requests.Session.request = original

    def test_only_cookies_for_the_requested_host_are_sent(self):
        fake = FakeFlareSolverr()
        response = self.get_content(fake)
        self.assertTrue(response.ok)
        self.assertEqual(['.example.org'], [c['domain'] for c in fake.posts[0]['cookies']])

    def test_retry_without_cookies_when_the_site_moves_the_browser_to_another_host(self):
        # e.g. the site sometimes bounces a search to an ad domain before FlareSolverr sets cookies
        fake = FakeFlareSolverr(landing_host='www.ads.example.com')
        response = self.get_content(fake)
        self.assertTrue(response.ok)
        self.assertEqual(2, len(fake.posts))
        self.assertEqual([], fake.posts[1]['cookies'])

    def test_other_flaresolverr_errors_still_raise_without_retry(self):
        fake = FakeFlareSolverr(error='Error: Error solving the challenge. Timeout after 120.0 seconds.')
        self.assertRaises(ValueError, self.get_content, fake)
        self.assertEqual(1, len(fake.posts))


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(CloudflareScraperCookieTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
