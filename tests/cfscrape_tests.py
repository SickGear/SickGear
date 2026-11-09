import unittest

import sys
import os.path
sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

from requests.models import PreparedRequest, Response

from cfscrape import CloudflareScraper


def _challenge(url):
    request = PreparedRequest()
    request.prepare(method='GET', url=url)
    response = Response()
    response.status_code = 403
    response.url = url
    response.request = request
    return response


def _solver(solution):
    response = Response()
    response.status_code = 200
    response.encoding = 'utf-8'
    response._content = ('{"status": "ok", "message": "Challenge not detected!", "solution": %s}' % solution).encode()
    return response


class SolutionResponseTests(unittest.TestCase):

    def test_json_api_page_is_unwrapped_from_browser_markup(self):
        url = 'https://example.com/q.php?q=show'
        solver = _solver('{"url": "%s", "status": 200, "headers": {}, "response": '
                         '"<html><head><meta name=\\"color-scheme\\" content=\\"light dark\\"><meta charset=\\"utf-8\\">'
                         '</head><body><pre>[{\\"name\\":\\"Show S01E01 &amp; more\\",\\"seeders\\":\\"5\\"}]</pre>'
                         '<div class=\\"json-formatter-container\\"></div></body></html>"}' % url)
        response = CloudflareScraper.solution_response(solver, _challenge(url))
        self.assertEqual(200, response.status_code)
        self.assertEqual(url, response.url)
        self.assertEqual([{'name': 'Show S01E01 & more', 'seeders': '5'}], response.json())

    def test_html_page_is_returned_unchanged(self):
        url = 'https://example.com/'
        solver = _solver('{"url": "%s", "status": 200, "headers": {}, '
                         '"response": "<html><head><title>Site</title></head><body>ok</body></html>"}' % url)
        response = CloudflareScraper.solution_response(solver, _challenge(url))
        self.assertEqual('<html><head><title>Site</title></head><body>ok</body></html>', response.text)

    def test_reply_without_solution_is_returned_as_is(self):
        solver = _solver('null')
        self.assertIs(solver, CloudflareScraper.solution_response(solver, _challenge('https://example.com/')))


if '__main__' == __name__:
    print('==================')
    print('STARTING - cfscrape TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(SolutionResponseTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
