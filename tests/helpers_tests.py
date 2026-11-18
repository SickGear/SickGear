import threading
import unittest
import sys
import os.path
from unittest import mock

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import adba
from sickgear import helpers
from sickgear.common import ARCHIVED, SNATCHED, SNATCHED_BEST, SNATCHED_PROPER, \
    DOWNLOADED, SKIPPED, IGNORED, UNAIRED, UNKNOWN, WANTED, Quality


sys.path.insert(1, os.path.abspath('..'))


class HelpersTests(unittest.TestCase):
    def setUp(self):
        super(HelpersTests, self).setUp()
        self.orig_u_key = helpers.unique_key1

    def tearDown(self):
        super(HelpersTests, self).tearDown()
        helpers.unique_key1 = self.orig_u_key

    def test_replaceExtension(self):
        self.assertEqual(helpers.replace_extension('foo.avi', 'mkv'), 'foo.mkv')
        self.assertEqual(helpers.replace_extension('.vimrc', 'arglebargle'), '.vimrc')
        self.assertEqual(helpers.replace_extension('a.b.c', 'd'), 'a.b.d')
        self.assertEqual(helpers.replace_extension('', 'a'), '')
        self.assertEqual(helpers.replace_extension('foo.bar', ''), 'foo.')

    def test_sanitizeFileName(self):
        self.assertEqual(helpers.sanitize_filename('a/b/c'), 'a-b-c')
        self.assertEqual(helpers.sanitize_filename('abc'), 'abc')
        self.assertEqual(helpers.sanitize_filename('a"b'), 'ab')
        self.assertEqual(helpers.sanitize_filename('.a.b..'), 'a.b')

    def test_sizeof_fmt(self):
        self.assertEqual(helpers.sizeof_fmt(2), '2.0 bytes')
        self.assertEqual(helpers.sizeof_fmt(1024), '1.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2048), '2.0 KB')
        self.assertEqual(helpers.sizeof_fmt(2 ** 20), '1.0 MB')
        self.assertEqual(helpers.sizeof_fmt(1234567), '1.2 MB')

    def test_remove_non_release_groups(self):
        test_names = {
            ('[HorribleSubs] Hidan no Aria AA - 08 [1080p]', True): '[HorribleSubs] Hidan no Aria AA - 08 [1080p]',
            ('The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN[rartv]', False):
                'The.Last.Man.On.Earth.S02E08.No.Bull.1080p.WEB-DL.DD5.1.H264-BTN',
        }
        for test_name, test_result in test_names.items():
            self.assertEqual(test_result, helpers.remove_non_release_groups(test_name[0], test_name[1]))

    def test_should_delete_episode(self):
        test_cases = [
            ((SNATCHED, Quality.HDTV), False),
            ((SNATCHED_PROPER, Quality.HDTV), False),
            ((SNATCHED_BEST, Quality.HDTV), False),
            ((DOWNLOADED, Quality.HDTV), False),
            ((ARCHIVED, Quality.HDTV), False),
            ((ARCHIVED, Quality.NONE), False),
            ((SKIPPED, Quality.NONE), True),
            ((IGNORED, Quality.NONE), False),
            ((UNAIRED, Quality.NONE), True),
            ((UNKNOWN, Quality.NONE), True),
            ((WANTED, Quality.NONE), True),
        ]
        for c, b in test_cases:
            self.assertEqual(helpers.should_delete_episode(Quality.composite_status(*c)), b)

    def test_encrypt(self):
        helpers.unique_key1 = '0x12d48f154876c16164a1646'
        crypt_test = [
            {'param': ('Test', 0, False), 'result': 'Test'},
            {'param': ('Test', 1, False), 'result': 'ZB1CRg=='},
            {'param': ('ZB1CRg==', 1, True), 'result': 'Test'},
        ]
        for t in crypt_test:
            self.assertEqual(t['result'], helpers.encrypt(*t['param']))


class AniDBLockTests(unittest.TestCase):
    """ a command that raises gives the connection lock back, a kept lock blocks the shutdown of the app """

    def setUp(self):
        # no __init__, it opens a network socket
        self.conn = adba.Connection.__new__(adba.Connection)
        self.conn.lock = threading.RLock()
        self.conn.mode = 1
        self.conn.keepAlive = False
        self.conn.counter = self.conn.counterAge = 0
        self.conn.link = mock.Mock(session=None)

    def lock_is_free(self):
        result = []
        other_thread = threading.Thread(target=lambda: result.append(self.conn.lock.acquire(timeout=2)))
        other_thread.start()
        other_thread.join()
        return result[0]

    def test_handle_releases_lock_on_error(self):
        self.conn.link.request.side_effect = OSError('network is down')
        with self.assertRaises(OSError):
            self.conn.handle(mock.Mock(command='LOGOUT'), None)
        self.assertTrue(self.lock_is_free())

    def test_stop_ends_keep_alive_thread(self):
        threading.Thread.__init__(self.conn, daemon=True)
        self.conn.keepAlive = True
        self.conn._keep_alive_stop = threading.Event()
        self.conn._keep_alive = mock.Mock()
        self.conn.logout = mock.Mock()
        self.conn.start()
        self.conn.stop()
        self.conn.join(2)
        self.assertFalse(self.conn.is_alive())
        self.conn.logout.assert_called_once()

    def test_stop_ends_link_thread(self):
        self.conn._keep_alive_stop = threading.Event()
        for cur_logout in (mock.Mock(), mock.Mock(side_effect=OSError('network is down'))):
            # a logout that does nothing, as with a session that is not logged in, and a logout that fails
            self.conn.logout = cur_logout
            self.conn.link = mock.Mock(_quiting=False)
            try:
                self.conn.stop()
            except OSError:
                pass
            self.conn.link.stop.assert_called_once()

        # a logout that did stop the link thread
        self.conn.logout = mock.Mock()
        self.conn.link = mock.Mock(_quiting=True)
        self.conn.stop()
        self.conn.link.stop.assert_not_called()

    def test_authed_releases_lock_on_error(self):
        self.conn._reAuthenticate = mock.Mock(side_effect=OSError('network is down'))
        with self.assertRaises(OSError):
            self.conn.authed(reAuthenticate=True)
        self.assertTrue(self.lock_is_free())


if '__main__' == __name__:
    for cur_case in (HelpersTests, AniDBLockTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
