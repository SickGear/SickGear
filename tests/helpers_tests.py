import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import adba

import sickgear
from sickgear import anime, helpers
from sickgear.common import ARCHIVED, SNATCHED, SNATCHED_BEST, SNATCHED_PROPER, \
    DOWNLOADED, SKIPPED, IGNORED, UNAIRED, UNKNOWN, WANTED, Quality


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


class LanguageCodeTests(unittest.TestCase):
    def test_language_to_alpha2(self):
        # the table was made from, and replaces, the iso639 package: a name or three letter code to a two letter code
        from sg_lang_codes import language_to_alpha2
        for cur_value, cur_code in (('English', 'en'), ('eng', 'en'), ('en', 'en'), ('Castilian', 'es'),
                                    ('Norwegian Bokm\u00e5l', 'nb'), ('chi', 'zh'), ('zho', 'zh'), ('Punjabi', 'pa')):
            self.assertEqual(cur_code, language_to_alpha2.get(cur_value))
        # a language with no two letter code, a name that is not a reference name, and a wrong case, are not in it
        for cur_value in ('Filipino', 'fil', 'Greek', 'english'):
            self.assertNotIn(cur_value, language_to_alpha2)


class FlagCodeTests(unittest.TestCase):
    flags_dir = abspath(join(dirname(__file__), '..', 'gui', 'slick', 'images', 'flags'))

    def flag_of(self, name, lang_path=True):
        """ the name of the flag file that the flag file handler of webserve sends for a requested name """
        from os.path import basename, splitext
        from sickgear.webserve import BaseStaticFileHandler

        path = join(*([self.flags_dir] + ['svg', 'lang'] * lang_path + [f'{name}.png']))
        return splitext(basename(BaseStaticFileHandler.flag_file_path(path)))[0]

    def test_country_code_for_the_language_flag_path(self):
        from os.path import isfile
        from sg_lang_codes import alpha2_to_alpha3

        # a two letter name under /images/flags/svg/lang/ is read as a language first,
        # so a two letter country code that is also a language code gives the flag of another country
        self.assertEqual('ne', self.flag_of('kr'))
        self.assertEqual('ad', self.flag_of('ca'))
        # the three letter code of every country gives the flag of that country, in lower, upper and mixed case
        checked = 0
        for cur_alpha2, cur_alpha3 in alpha2_to_alpha3.items():
            if isfile(join(self.flags_dir, 'svg', f'{cur_alpha2}.svg')):
                checked += 1
                for cur_code in (cur_alpha3, cur_alpha3.upper(), cur_alpha3.title()):
                    self.assertEqual(cur_alpha2, self.flag_of(cur_code), msg=cur_code)
                    self.assertEqual(cur_alpha2, self.flag_of(cur_code, lang_path=False), msg=cur_code)
        self.assertGreater(checked, 200)
        self.assertEqual('kor', alpha2_to_alpha3['kr'])
        self.assertEqual('deu', alpha2_to_alpha3['de'])

    def test_flag_file_names(self):
        # a two letter country code in upper case, on the plain address
        self.assertEqual('us', self.flag_of('US', lang_path=False))
        # a flag file with a name in mixed case is still found
        self.assertEqual('Aragon', self.flag_of('Aragon', lang_path=False))
        self.assertEqual('gb-sct', self.flag_of('gb-sct', lang_path=False))
        # a name with no flag file
        self.assertEqual('unknown', self.flag_of('zzz'))
        self.assertEqual('unknown', self.flag_of('ZZZ', lang_path=False))

    def test_other_paths_are_not_changed(self):
        from sickgear.webserve import BaseStaticFileHandler

        path = join(dirname(self.flags_dir), 'network', 'KOR.png')
        self.assertEqual(path, BaseStaticFileHandler.flag_file_path(path))


class TouchFileTests(unittest.TestCase):
    """ a file date that cannot be set is logged with the file and the reason """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.file = join(self.tmp_dir, 'Show.s01e01.avi')
        open(self.file, 'w').close()

    def tearDown(self):
        os.chmod(self.file, stat.S_IWRITE)
        shutil.rmtree(self.tmp_dir)

    def test_read_only_file(self):
        os.chmod(self.file, stat.S_IREAD)
        with self.assertLogs('sg.helper', 'WARNING') as cur_log:
            self.assertFalse(helpers.touch_file(self.file, 1163122200))
        self.assertIn(self.file, cur_log.output[0])
        self.assertIn('Permission denied', cur_log.output[0])

    def test_writable_file(self):
        self.assertTrue(helpers.touch_file(self.file, 1163122200))
        self.assertEqual(1163122200, int(os.path.getmtime(self.file)))


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


class LibImportTests(unittest.TestCase):
    # a module that is imported as both `lib.x` and `x` is two modules, each with its own classes and state,
    # e.g. `except x.SomeError` does not handle a raised `lib.x.SomeError`.
    # the rule is one name for each bundled module: `x`, never `lib.x`

    def test_lib_modules_are_loaded_once(self):
        from sickgear import webapi, webserve
        self.assertTrue(webapi and webserve)
        self.assertEqual([], sorted(_name for _name in list(sys.modules) if _name.startswith('lib.')))

    def test_no_import_has_a_lib_prefix(self):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        is_lib_import = re.compile(r"""^\s*#?\s*(from\s+lib[.\s]|import\s+lib\b)|__import__\(f?['"]lib\.""", re.M)
        try:
            # the files of the repo only, else a local file that is not in the repo fails the test
            names = subprocess.run(['git', 'ls-files', '-z', '--', '*.py', '*.tmpl'], cwd=base,
                                   capture_output=True, check=True).stdout.decode('utf-8').split('\0')
        except (OSError, subprocess.CalledProcessError):
            names = []
            for cur_dir, dir_names, file_names in os.walk(base):
                dir_names[:] = [_d for _d in dir_names if not _d.startswith('.') and '__pycache__' != _d]
                names += [os.path.relpath(os.path.join(cur_dir, _n), base) for _n in file_names
                          if _n.endswith(('.py', '.tmpl'))]
        found = []
        for cur_name in filter(None, names):
            cur_file = os.path.join(base, cur_name)
            if os.path.isfile(cur_file):
                with open(cur_file, encoding='utf-8', errors='replace') as fh:
                    if is_lib_import.search(fh.read()):
                        found.append(os.path.normpath(cur_name))
        self.assertEqual([], sorted(found))


class LazyImportTests(unittest.TestCase):
    @unittest.skipIf((3, 15) > sys.version_info[:2], 'lazy imports need Python 3.15 or newer')
    def test_start_does_not_load_optional_packages(self):
        # a name in a `__lazy_modules__` list must be the module name of its import statement, or it has no effect.
        # A new process, because other tests in this one can have used these modules
        root = abspath(join(dirname(__file__), '..'))
        code = ('import sys; sys.path.insert(1, %r); sys.path.insert(1, %r); '
                'import sickgear; from sickgear import anime, helpers, processTV, scene_exceptions, subtitles, tv, '
                'webapi, webserve; '
                # templates use this star import
                "exec('from sickgear.common import *', {}); "
                "print(sorted({_m.replace('lib.', '').split('.')[0] for _m in sys.modules} & {'hachoir', 'apprise', "
                "'subliminal', 'guessit', 'enzyme', 'rarfile', 'cryptography', 'adba'}))"
                ) % (root, join(root, 'lib'))
        result = subprocess.run([sys.executable, '-W', 'ignore', '-c', code], capture_output=True, text=True)
        self.assertEqual('[]', result.stdout.strip(), msg=result.stderr[-2000:])


class AniDBSessionFileTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_file_is_in_cache_folder(self):
        with mock.patch.multiple(sickgear, USE_ANIDB=True, ANIDB_USERNAME='user', ANIDB_PASSWORD='pw',
                                 ADBA_CONNECTION=None, CACHE_DIR=self.temp_dir):
            with mock.patch.object(adba, 'Connection'):
                anime.set_up_anidb_connection()
                self.assertEqual(os.path.join(self.temp_dir, 'anidb', 'session.cfg'),
                                 sickgear.ADBA_CONNECTION.SessionFile)

    def test_logout_with_no_session_file(self):
        # no __init__, it opens a network socket
        conn = adba.Connection.__new__(adba.Connection)
        conn.SessionFile = os.path.join(self.temp_dir, 'session.cfg')
        conn.handle = mock.Mock()
        self.assertIsNone(conn.logout())
        conn.handle.assert_not_called()


if '__main__' == __name__:
    for cur_case in (HelpersTests, FlagCodeTests, TouchFileTests, AniDBLockTests, AniDBSessionFileTests, LibImportTests, LazyImportTests, LanguageCodeTests):
        suite = unittest.TestLoader().loadTestsFromTestCase(cur_case)
        unittest.TextTestRunner(verbosity=2).run(suite)
