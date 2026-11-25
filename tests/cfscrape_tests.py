import socket
import sys
import unittest
from unittest import mock
from os.path import abspath, dirname, join
sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from requests.models import PreparedRequest, Response
import sg_helpers
from cfscrape import CloudflareScraper, FlareSolverrError


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


def _closed_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class FlareSolverrDownTests(unittest.TestCase):

    def setUp(self):
        self.solver = 'http://127.0.0.1:%s' % _closed_port()
        sg_helpers._flaresolverr_logged.clear()

    def test_solver_down_raises_one_named_error_without_context(self):
        with self.assertRaises(FlareSolverrError) as caught:
            CloudflareScraper().test_flaresolverr(self.solver)
        self.assertIn(self.solver, str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        self.assertIsInstance(caught.exception, ValueError)  # callers that catch ValueError still do

    def test_get_url_logs_solver_down_once_as_one_line(self):
        with mock.patch.object(sg_helpers.logger, 'warning') as warning,                 mock.patch.object(sg_helpers.logger, 'debug') as debug:
            for _ in range(2):
                sg_helpers.get_url('http://127.0.0.1:%s/' % _closed_port(), session=CloudflareScraper(),
                                   proxy_browser=True, url_solver=self.solver, failure_monitor=False)
        lines = [c.args[0] for c in warning.call_args_list]
        self.assertEqual(1, len(lines), lines)
        self.assertIn('FlareSolverr software not found', lines[0])
        self.assertNotIn('Traceback', lines[0])
        self.assertTrue(any('FlareSolverr software not found' in c.args[0] for c in debug.call_args_list))



if '__main__' == __name__:
    print('==================')
    print('STARTING - cfscrape TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(SolutionResponseTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
