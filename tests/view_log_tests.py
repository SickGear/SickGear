import sys
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear.webserve import EventLogs


def _lines(text):
    return [f'{_l.strip()}\n' for _l in text.strip().splitlines()]


def _marks(text):
    # the page joins the lines, so an empty item adds nothing
    return [_l for _l in EventLogs.mark_runs(_lines(text)) if _l]


def _stops(lines):
    return [('log-stop', None)['log-stop' not in _l] for _l in lines]


class MarkRunsTests(unittest.TestCase):
    """ the log page marks each start of a run, the lines of the shutdown before it, and how long it was down """

    def test_restart(self):
        result = _marks("""
            2026-11-21 16:59:18 INFO     MAIN :: Loaded 599 shows in 1 second
            2026-11-21 16:59:16 INFO     TORNADO :: Starting SickGear on http://0.0.0.0:7081/
            2026-11-21 16:59:16 INFO     MAIN :: Forcing web server to port 7081
            2026-11-21 16:59:14 INFO     EVENT-QUEUE :: Restarting SickGear with ['sickgear.py']
            2026-11-21 16:59:14 INFO     EVENT-QUEUE :: Shutting down Tornado
            2026-11-21 16:59:14 INFO     RECENT-SEARCH :: a job that ends while the shutdown runs
            2026-11-21 16:59:13 INFO     EVENT-QUEUE :: Exiting threads
            2026-11-21 16:59:13 DEBUG    EVENT-QUEUE :: Shutdown ev_type:RESTART, sickgear.started:True
            2026-11-21 16:59:13 INFO     WEBSERVER_1 :: Trigger event restart
            2026-11-21 16:59:10 INFO     RECENT-SEARCH :: a line of the run before
            """)
        self.assertEqual('2026-11-21 16:59:18 INFO     MAIN :: Loaded 599 shows in 1 second\n', result[0])
        self.assertTrue(result[1].startswith('<span class="log-start">2026-11-21 16:59:16'))
        # the divider goes between the processes, below a line that the new process logged before its start line
        self.assertEqual('2026-11-21 16:59:16 INFO     MAIN :: Forcing web server to port 7081\n', result[2])
        self.assertEqual('<span class="log-run"><span>restart, down 3 seconds</span></span>', result[3])
        self.assertEqual(['log-stop', 'log-stop', None, 'log-stop', 'log-stop', 'log-stop', None], _stops(result[4:]))
        self.assertEqual('2026-11-21 16:59:10 INFO     RECENT-SEARCH :: a line of the run before\n', result[-1])

    def test_shutdown_and_masked_name(self):
        result = _marks("""
            2026-11-21 18:00:05 INFO     TORNADO :: Starting Sick**** on http://0.0.0.0:7081/
            2026-11-21 16:10:00 INFO     EVENT-QUEUE :: Shutting down Tornado
            2026-11-21 16:09:59 INFO     EVENT-QUEUE :: Exiting threads
            2026-11-21 16:09:58 INFO     SEARCHQUEUE :: a line of the run before
            """)
        self.assertEqual('<span class="log-run"><span>shutdown, down 1h 50 mins</span></span>', result[1])
        self.assertEqual(['log-stop', 'log-stop', None], _stops(result[2:]))

    def test_start_with_no_shutdown(self):
        result = _marks("""
            2026-11-21 16:59:16 INFO     TORNADO :: Starting SickGear on http://0.0.0.0:7081/
            2026-11-21 16:50:00 INFO     EVENT-QUEUE :: an event of the run before
            2026-11-21 16:49:00 INFO     RECENT-SEARCH :: a line of the run before
            """)
        self.assertEqual('<span class="log-run"><span>start, no shutdown logged</span></span>', result[1])
        self.assertEqual('2026-11-21 16:50:00 INFO     EVENT-QUEUE :: an event of the run before\n', result[2])
        self.assertEqual(3, len(result) - 1)

    def test_lines_with_no_start(self):
        lines = _lines("""
            2026-11-21 16:59:18 INFO     MAIN :: Loaded 599 shows in 1 second
            a line of a traceback
            """)
        self.assertEqual(lines, EventLogs.mark_runs(lines))


if '__main__' == __name__:
    unittest.main()
