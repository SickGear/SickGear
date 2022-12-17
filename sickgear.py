#!/usr/bin/env python2
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

# Check needed software dependencies to nudge users to fix their setup
from __future__ import print_function
from __future__ import with_statement

import codecs
import datetime
import errno
import getopt
import os
import signal
import sys
import shutil
import time
import threading
import warnings

warnings.filterwarnings('ignore', module=r'.*bs4_parser.*', message='.*No parser was explicitly specified.*')
warnings.filterwarnings('ignore', module=r'.*Cheetah.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*fuzzywuzzy.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')
warnings.filterwarnings('ignore', module=r'.*zoneinfo.*', message='.*file or directory.*')
warnings.filterwarnings('ignore', message='.*deprecated in cryptography.*')

versions = [((2, 7, 9), (2, 7, 18)), ((3, 7, 1), (3, 8, 16)),
            ((3, 9, 0), (3, 9, 2)), ((3, 9, 4), (3, 9, 16)),
            ((3, 10, 0), (3, 11, 1))]  # inclusive version ranges
if not any(list(map(lambda v: v[0] <= sys.version_info[:3] <= v[1], versions))) and not int(os.environ.get('PYT', 0)):
    print('Python %s.%s.%s detected.' % sys.version_info[:3])
    print('Sorry, SickGear requires a Python version %s' % ', '.join(map(
        lambda r: '%s - %s' % tuple(map(lambda v: str(v).replace(',', '.')[1:-1], r)), versions)))
    sys.exit(1)

sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), 'lib')))
is_win = 'win' == sys.platform[0:3]

try:
    try:
        py_cache_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '__pycache__'))
        for pf in ['_cleaner.pyc', '_cleaner.pyo']:
            cleaner_file = os.path.normpath(os.path.join(os.path.normpath(os.path.dirname(__file__)), pf))
            if os.path.isfile(cleaner_file):
                os.remove(cleaner_file)
        if os.path.isdir(py_cache_path):
            shutil.rmtree(py_cache_path)
    except (BaseException, Exception):
        pass
    import _cleaner
    from sickbeard import piper
except (BaseException, Exception):
    pass

try:
    import Cheetah
except (BaseException, Exception):
    print('The Python module Cheetah is required')
    if is_win:
        print('(1) However, this first run may have just installed it, so try to simply rerun sickgear.py again')
        print('(2) If this output is a rerun of (1) then open a command line prompt and manually install using...')
    else:
        print('Manually install using...')
    print('cd <sickgear_installed_folder>')
    print('python -m pip install --user -r requirements.txt')
    print('python sickgear.py')
    sys.exit(1)

# Compatibility fixes for Windows
if is_win:
    codecs.register(lambda name: codecs.lookup('utf-8') if name == 'cp65001' else None)

# We only need this for compiling an EXE
from multiprocessing import freeze_support

from configobj import ConfigObj
# noinspection PyPep8Naming
from encodingKludge import EXIT_BAD_ENCODING, SYS_ENCODING
from exceptions_helper import ex
import sickbeard
from sickbeard import db, logger, name_cache, network_timezones
from sickbeard.event_queue import Events
from sickbeard.tv import TVShow
from sickbeard.webserveInit import WebServer

from six import integer_types, iteritems

throwaway = datetime.datetime.strptime('20110101', '%Y%m%d')
rollback_loaded = None

for signal_type in [signal.SIGTERM, signal.SIGINT] + ([] if not is_win else [signal.SIGBREAK]):
    signal.signal(signal_type, lambda signum, void: sickbeard.sig_handler(signum=signum, _=void))


class SickGear(object):
    def __init__(self):
        # system event callback for shutdown/restart
        sickbeard.events = Events(self.shutdown)

        # daemon constants
        self.run_as_daemon = False
        self.create_pid = False
        self.pid_file = ''

        self.run_as_systemd = False
        self.console_logging = False

        # webserver constants
        self.webserver = None
        self.force_update = False
        self.forced_port = None
        self.no_launch = False

        self.web_options = None
        self.webhost = None
        self.start_port = None
        self.log_dir = None

    @staticmethod
    def help_message():
        """
        print help message for commandline options
        """
        global is_win
        help_msg = ['']
        help_msg += ['Usage: %s <option> <another option>\n' % sickbeard.MY_FULLNAME]
        help_msg += ['Options:\n']

        help_tmpl = '    %-10s%-17s%s'
        for ln in [
            ('-h', '--help', 'Prints this message'),
            ('-f', '--forceupdate', 'Force update all shows in the DB (from tvdb) on startup'),
            ('-q', '--quiet', 'Disables logging to console'),
            ('', '--nolaunch', 'Suppress launching web browser on startup')
        ]:
            help_msg += [help_tmpl % ln]

        if is_win:
            for ln in [
                ('-d', '--daemon', 'Running as daemon is not supported on Windows'),
                ('', '', 'On Windows, --daemon is substituted with: --quiet --nolaunch')
            ]:
                help_msg += [help_tmpl % ln]
        else:
            for ln in [
                ('-d', '--daemon', 'Run as double forked daemon (includes options --quiet --nolaunch)'),
                ('-s', '--systemd', 'Run as systemd service (includes options --quiet --nolaunch)'),
                ('', '--pidfile=<path>', 'Combined with --daemon creates a pidfile (full path including filename)')
            ]:
                help_msg += [help_tmpl % ln]

        for ln in [
            ('-p <port>', '--port=<port>', 'Override default/configured port to listen on'),
            ('', '--datadir=<path>', 'Override folder (full path) as location for'),
            ('', '', 'storing database, configfile, cache, logfiles'),
            ('', '', 'Default: %s' % sickbeard.PROG_DIR),
            ('', '--config=<path>', 'Override config filename (full path including filename)'),
            ('', '', 'to load configuration from'),
            ('', '', 'Default: config.ini in %s or --datadir location' % sickbeard.PROG_DIR),
            ('', '--noresize', 'Prevent resizing of the banner/posters even if PIL is installed')
        ]:
            help_msg += [help_tmpl % ln]

        return '\n'.join(help_msg)

    @staticmethod
    def execute_rollback(mo, max_v, load_msg):
        global rollback_loaded
        try:
            if None is rollback_loaded:
                rollback_loaded = db.get_rollback_module()
            if None is not rollback_loaded:
                rc = rollback_loaded.__dict__[mo]()
                rc.load_msg = load_msg
                rc.run(max_v)
            else:
                print(u'ERROR: Could not download Rollback Module.')
        except (BaseException, Exception):
            pass

    def start(self):
        global is_win
        # do some preliminary stuff
        sickbeard.MY_FULLNAME = os.path.normpath(os.path.abspath(__file__))
        sickbeard.MY_NAME = os.path.basename(sickbeard.MY_FULLNAME)
        sickbeard.PROG_DIR = os.path.dirname(sickbeard.MY_FULLNAME)
        sickbeard.DATA_DIR = sickbeard.PROG_DIR
        sickbeard.MY_ARGS = sys.argv[1:]
        if EXIT_BAD_ENCODING:
            print('Sorry, you MUST add the SickGear folder to the PYTHONPATH environment variable')
            print('or find another way to force Python to use %s for string encoding.' % SYS_ENCODING)
            sys.exit(1)
        sickbeard.SYS_ENCODING = SYS_ENCODING
        legacy_runner = globals().get('_legacy_sickbeard_runner')
        if not legacy_runner:
            import __main__
            legacy_runner = 'bear' in (getattr(__main__, '__file__', False) or '').split(os.sep)[-1].lower()
        sickbeard.MEMCACHE['DEPRECATE_SB_RUNNER'] = legacy_runner

        # Need console logging for sickgear.py and SickBeard-console.exe
        self.console_logging = (not hasattr(sys, 'frozen')) or (0 < sickbeard.MY_NAME.lower().find('-console'))

        # Rename the main thread
        threading.current_thread().name = 'MAIN'

        try:
            opts, args = getopt.getopt(sys.argv[1:], 'hfqdsp::',
                                       ['help', 'forceupdate', 'quiet', 'nolaunch', 'daemon', 'systemd', 'pidfile=',
                                        'port=', 'datadir=', 'config=', 'noresize', 'update-restart', 'update-pkg'])
        except getopt.GetoptError:
            sys.exit(self.help_message())

        for o, a in opts:
            # Prints help message
            if o in ('-h', '--help'):
                sys.exit(self.help_message())

            # For now we'll just silence the logging
            if o in ('-q', '--quiet'):
                self.console_logging = False

            # Should we update (from indexer) all shows in the DB right away?
            if o in ('-f', '--forceupdate'):
                self.force_update = True

            # Suppress launching web browser
            # Needed for OSes without default browser assigned
            # Prevent duplicate browser window when restarting in the app
            if o in ('--nolaunch',):
                self.no_launch = True

            # Override default/configured port
            if o in ('-p', '--port'):
                try:
                    self.forced_port = int(a)
                except ValueError:
                    sys.exit('Port: %s is not a number. Exiting.' % a)

            # Run as a double forked daemon
            if o in ('-d', '--daemon'):
                self.run_as_daemon = True
                # When running as daemon disable console_logging and don't start browser
                self.console_logging = False
                self.no_launch = True

                if is_win:
                    self.run_as_daemon = False

            # Run as a systemd service
            if o in ('-s', '--systemd') and not is_win:
                self.run_as_systemd = True
                self.run_as_daemon = False
                self.console_logging = False
                self.no_launch = True

            # Write a pidfile if requested
            if o in ('--pidfile',):
                self.create_pid = True
                self.pid_file = str(a)

                # If the pidfile already exists, sickbeard may still be running, so exit
                if os.path.exists(self.pid_file):
                    sys.exit('PID file: %s already exists. Exiting.' % self.pid_file)

            # Specify folder to load the config file from
            if o in ('--config',):
                sickbeard.CONFIG_FILE = os.path.abspath(a)

            # Specify folder to use as the data dir
            if o in ('--datadir',):
                sickbeard.DATA_DIR = os.path.abspath(a)

            # Prevent resizing of the banner/posters even if PIL is installed
            if o in ('--noresize',):
                sickbeard.NO_RESIZE = True

        # The pidfile is only useful in daemon mode, make sure we can write the file properly
        if self.create_pid:
            if self.run_as_daemon:
                pid_dir = os.path.dirname(self.pid_file)
                if not os.access(pid_dir, os.F_OK):
                    sys.exit(u"PID dir: %s doesn't exist. Exiting." % pid_dir)
                if not os.access(pid_dir, os.W_OK):
                    sys.exit(u'PID dir: %s must be writable (write permissions). Exiting.' % pid_dir)

            else:
                if self.console_logging:
                    print(u'Not running in daemon mode. PID file creation disabled')

                self.create_pid = False

        # If they don't specify a config file then put it in the data dir
        if not sickbeard.CONFIG_FILE:
            sickbeard.CONFIG_FILE = os.path.join(sickbeard.DATA_DIR, 'config.ini')

        # Make sure that we can create the data dir
        if not os.access(sickbeard.DATA_DIR, os.F_OK):
            try:
                os.makedirs(sickbeard.DATA_DIR, 0o744)
            except os.error:
                sys.exit(u'Unable to create data directory: %s Exiting.' % sickbeard.DATA_DIR)

        # Make sure we can write to the data dir
        if not os.access(sickbeard.DATA_DIR, os.W_OK):
            sys.exit(u'Data directory: %s must be writable (write permissions). Exiting.' % sickbeard.DATA_DIR)

        # Make sure we can write to the config file
        if not os.access(sickbeard.CONFIG_FILE, os.W_OK):
            if os.path.isfile(sickbeard.CONFIG_FILE):
                sys.exit(u'Config file: %s must be writeable (write permissions). Exiting.' % sickbeard.CONFIG_FILE)
            elif not os.access(os.path.dirname(sickbeard.CONFIG_FILE), os.W_OK):
                sys.exit(u'Config file directory: %s must be writeable (write permissions). Exiting'
                         % os.path.dirname(sickbeard.CONFIG_FILE))
        os.chdir(sickbeard.DATA_DIR)

        if self.console_logging:
            print(u'Starting up SickGear from %s' % sickbeard.CONFIG_FILE)

        # Load the config and publish it to the sickbeard package
        if not os.path.isfile(sickbeard.CONFIG_FILE):
            print(u'Unable to find "%s", all settings will be default!' % sickbeard.CONFIG_FILE)

        sickbeard.CFG = ConfigObj(sickbeard.CONFIG_FILE)
        try:
            stack_size = int(sickbeard.CFG['General']['stack_size'])
        except (BaseException, Exception):
            stack_size = None

        if stack_size:
            try:
                threading.stack_size(stack_size)
            except (BaseException, Exception) as er:
                print('Stack Size %s not set: %s' % (stack_size, ex(er)))

        if self.run_as_daemon:
            self.daemonize()

        # Get PID
        sickbeard.PID = os.getpid()

        # Initialize the config
        sickbeard.initialize(console_logging=self.console_logging)

        if self.forced_port:
            logger.log(u'Forcing web server to port %s' % self.forced_port)
            self.start_port = self.forced_port
        else:
            self.start_port = sickbeard.WEB_PORT

        if sickbeard.WEB_LOG:
            self.log_dir = sickbeard.LOG_DIR
        else:
            self.log_dir = None

        # sickbeard.WEB_HOST is available as a configuration value in various
        # places but is not configurable. It is supported here for historic reasons.
        if sickbeard.WEB_HOST and '0.0.0.0' != sickbeard.WEB_HOST:
            self.webhost = sickbeard.WEB_HOST
        else:
            self.webhost = (('0.0.0.0', '::')[sickbeard.WEB_IPV6], '')[sickbeard.WEB_IPV64]

        # web server options
        self.web_options = dict(
            host=self.webhost,
            port=int(self.start_port),
            web_root=sickbeard.WEB_ROOT,
            data_root=os.path.join(sickbeard.PROG_DIR, 'gui', sickbeard.GUI_NAME),
            log_dir=self.log_dir,
            username=sickbeard.WEB_USERNAME,
            password=sickbeard.WEB_PASSWORD,
            handle_reverse_proxy=sickbeard.HANDLE_REVERSE_PROXY,
            enable_https=False,
            https_cert=None,
            https_key=None,
        )
        if sickbeard.ENABLE_HTTPS:
            self.web_options.update(dict(
                enable_https=sickbeard.ENABLE_HTTPS,
                https_cert=os.path.join(sickbeard.PROG_DIR, sickbeard.HTTPS_CERT),
                https_key=os.path.join(sickbeard.PROG_DIR, sickbeard.HTTPS_KEY)
            ))

        # start web server
        try:
            # used to check if existing SG instances have been started
            sickbeard.helpers.wait_for_free_port(
                sickbeard.WEB_IPV6 and '::1' or self.web_options['host'], self.web_options['port'])

            self.webserver = WebServer(options=self.web_options)
            self.webserver.start()
            # wait for server thread to be started
            self.webserver.wait_server_start()
            sickbeard.started = True
        except (BaseException, Exception):
            logger.log(u'Unable to start web server, is something else running on port %d?' % self.start_port,
                       logger.ERROR)
            if self.run_as_systemd:
                self.exit(0)
            if sickbeard.LAUNCH_BROWSER and not self.no_launch:
                logger.log(u'Launching browser and exiting', logger.ERROR)
                sickbeard.launch_browser(self.start_port)
            self.exit(1)

        # Launch browser
        if sickbeard.LAUNCH_BROWSER and not self.no_launch:
            sickbeard.launch_browser(self.start_port)

        # send pid of sg instance to ui
        sickbeard.classes.loading_msg.set_msg_progress('Process-id', sickbeard.PID)

        # check all db versions
        for d, min_v, max_v, base_v, mo in [
            ('failed.db', sickbeard.failed_db.MIN_DB_VERSION, sickbeard.failed_db.MAX_DB_VERSION,
             sickbeard.failed_db.TEST_BASE_VERSION, 'FailedDb'),
            ('cache.db', sickbeard.cache_db.MIN_DB_VERSION, sickbeard.cache_db.MAX_DB_VERSION,
             sickbeard.cache_db.TEST_BASE_VERSION, 'CacheDb'),
            ('sickbeard.db', sickbeard.mainDB.MIN_DB_VERSION, sickbeard.mainDB.MAX_DB_VERSION,
             sickbeard.mainDB.TEST_BASE_VERSION, 'MainDb')
        ]:
            cur_db_version = db.DBConnection(d).checkDBVersion()

            # handling of standalone TEST db versions
            load_msg = 'Downgrading %s to production version' % d
            if 100000 <= cur_db_version != max_v:
                sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Rollback')
                print('Your [%s] database version (%s) is a test db version and doesn\'t match SickGear required '
                      'version (%s), downgrading to production db' % (d, cur_db_version, max_v))
                self.execute_rollback(mo, max_v, load_msg)
                cur_db_version = db.DBConnection(d).checkDBVersion()
                if 100000 <= cur_db_version:
                    print(u'Rollback to production failed.')
                    sys.exit(u'If you have used other forks, your database may be unusable due to their changes')
                if 100000 <= max_v and None is not base_v:
                    max_v = base_v  # set max_v to the needed base production db for test_db
                print(u'Rollback to production of [%s] successful.' % d)
                sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Finished')

            # handling of production version higher then current base of test db
            if isinstance(base_v, integer_types) and max_v >= 100000 > cur_db_version > base_v:
                sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Rollback')
                print('Your [%s] database version (%s) is a db version and doesn\'t match SickGear required '
                      'version (%s), downgrading to production base db' % (d, cur_db_version, max_v))
                self.execute_rollback(mo, base_v, load_msg)
                cur_db_version = db.DBConnection(d).checkDBVersion()
                if 100000 <= cur_db_version:
                    print(u'Rollback to production base failed.')
                    sys.exit(u'If you have used other forks, your database may be unusable due to their changes')
                if 100000 <= max_v and None is not base_v:
                    max_v = base_v  # set max_v to the needed base production db for test_db
                print(u'Rollback to production base of [%s] successful.' % d)
                sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Finished')

            # handling of production db versions
            if 0 < cur_db_version < 100000:
                if cur_db_version < min_v:
                    print(u'Your [%s] database version (%s) is too old to migrate from with this version of SickGear'
                          % (d, cur_db_version))
                    sys.exit(u'Upgrade using a previous version of SG first,'
                             + u' or start with no database file to begin fresh')
                if cur_db_version > max_v:
                    sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Rollback')
                    print(u'Your [%s] database version (%s) has been incremented past'
                          u' what this version of SickGear supports. Trying to rollback now. Please wait...' %
                          (d, cur_db_version))
                    self.execute_rollback(mo, max_v, load_msg)
                    if db.DBConnection(d).checkDBVersion() > max_v:
                        print(u'Rollback failed.')
                        sys.exit(u'If you have used other forks, your database may be unusable due to their changes')
                    print(u'Rollback of [%s] successful.' % d)
                    sickbeard.classes.loading_msg.set_msg_progress(load_msg, 'Finished')

        # migrate the config if it needs it
        from sickbeard.config import ConfigMigrator
        migrator = ConfigMigrator(sickbeard.CFG)
        if migrator.config_version > migrator.expected_config_version:
            self.execute_rollback('ConfigFile', migrator.expected_config_version, 'Downgrading config.ini')
            migrator = ConfigMigrator(sickbeard.CFG)
        migrator.migrate_config()

        # free memory
        global rollback_loaded
        rollback_loaded = None
        sickbeard.classes.loading_msg.message = 'Init SickGear'

        # Initialize the threads and other stuff
        sickbeard.initialize(console_logging=self.console_logging)

        # Check if we need to perform a restore first
        restore_dir = os.path.join(sickbeard.DATA_DIR, 'restore')
        if os.path.exists(restore_dir):
            sickbeard.classes.loading_msg.message = 'Restoring files'
            if self.restore(restore_dir, sickbeard.DATA_DIR):
                logger.log(u'Restore successful...')
            else:
                logger.log_error_and_exit(u'Restore FAILED!')

        # refresh network timezones
        sickbeard.classes.loading_msg.message = 'Checking network timezones'
        network_timezones.update_network_dict()

        update_arg = '--update-restart'
        manual_update_arg = '--update-pkg'
        if update_arg not in sickbeard.MY_ARGS and sickbeard.UPDATES_TODO \
                and (manual_update_arg in sickbeard.MY_ARGS or sickbeard.UPDATE_PACKAGES_AUTO):
            sickbeard.MEMCACHE['update_restart'] = piper.pip_update(
                sickbeard.classes.loading_msg, sickbeard.UPDATES_TODO, sickbeard.DATA_DIR)
            sickbeard.UPDATES_TODO = dict()
            sickbeard.save_config()

        if manual_update_arg in sickbeard.MY_ARGS:
            sickbeard.MY_ARGS.remove(manual_update_arg)

        if not sickbeard.MEMCACHE.get('update_restart'):
            # Build from the DB to start with
            sickbeard.classes.loading_msg.message = 'Loading shows from db'
            sickbeard.indexermapper.indexer_list = [i for i in sickbeard.TVInfoAPI().all_sources
                                                    if sickbeard.TVInfoAPI(i).config.get('show_url')
                                                    and True is not sickbeard.TVInfoAPI(i).config.get('people_only')]
            self.load_shows_from_db()
            sickbeard.MEMCACHE['history_tab'] = sickbeard.webserve.History.menu_tab(
                sickbeard.MEMCACHE['history_tab_limit'])
            if not db.DBConnection().has_flag('ignore_require_cleaned'):
                from sickbeard.show_updater import clean_ignore_require_words
                sickbeard.classes.loading_msg.message = 'Cleaning ignore/require words lists'
                clean_ignore_require_words()
                db.DBConnection().set_flag('ignore_require_cleaned')

        # Fire up threads
        sickbeard.classes.loading_msg.message = 'Starting threads'
        sickbeard.start()

        if sickbeard.MEMCACHE.get('update_restart'):
            sickbeard.MY_ARGS.append(update_arg)
            sickbeard.classes.loading_msg.message = 'Restarting SickGear after update'
            time.sleep(3)
            sickbeard.restart(soft=False)
            # restart wait loop
            while True:
                time.sleep(1)

        if update_arg in sickbeard.MY_ARGS:
            sickbeard.MY_ARGS.remove(update_arg)

        # Build internal name cache
        sickbeard.classes.loading_msg.message = 'Build name cache'
        name_cache.buildNameCache()

        # load all ids from xem
        sickbeard.classes.loading_msg.message = 'Loading xem data'
        startup_background_tasks = threading.Thread(name='XEMUPDATER', target=sickbeard.scene_exceptions.get_xem_ids)
        startup_background_tasks.start()

        sickbeard.classes.loading_msg.message = 'Checking history'
        # check history snatched_proper update
        if not db.DBConnection().has_flag('history_snatch_proper'):
            # noinspection PyUnresolvedReferences
            history_snatched_proper_task = threading.Thread(name='UPGRADE-HISTORY-ACTION',
                                                            target=sickbeard.history.history_snatched_proper_fix)
            history_snatched_proper_task.start()

        if not db.DBConnection().has_flag('kodi_nfo_default_removed'):
            sickbeard.metadata.kodi.remove_default_attr()
        if not db.DBConnection().has_flag('kodi_nfo_rebuild_uniqueid'):
            sickbeard.metadata.kodi.rebuild_nfo()

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM tv_src_switch WHERE status = 0')
        if sql_result:
            switching = True
            l_msg = 'Adding shows that are switching tv source to queue'
            total_result = len(sql_result)

            def q_switch(switch):
                try:
                    _show_obj = sickbeard.helpers.find_show_by_id({switch['new_indexer']: switch['new_indexer_id']})
                    if _show_obj:
                        sickbeard.show_queue_scheduler.action.switch_show(
                            show_obj=_show_obj,
                            new_tvid=switch['new_indexer'], new_prodid=switch['new_indexer_id'],
                            force_id=bool(switch['force_id']), uid=switch['uid'],
                            set_pause=bool(switch['set_pause']), mark_wanted=bool(switch['mark_wanted']), resume=True,
                            old_tvid=switch['old_indexer'], old_prodid=switch['old_indexer_id']
                        )
                except (BaseException, Exception):
                    pass

            sickbeard.classes.loading_msg.set_msg_progress(l_msg, '0/%s' % total_result)
            for i, cur_switch in enumerate(sql_result, 1):
                sickbeard.classes.loading_msg.set_msg_progress(l_msg, '%s/%s' % (i, total_result))
                try:
                    show_obj = sickbeard.helpers.find_show_by_id(
                        {cur_switch['old_indexer']: cur_switch['old_indexer_id']})
                except (BaseException, Exception):
                    if cur_switch['new_indexer_id']:
                        # show id was already switched, but not finished updated, so queue as update
                        q_switch(cur_switch)
                    continue
                if show_obj:
                    try:
                        sickbeard.show_queue_scheduler.action.switch_show(
                            show_obj=show_obj,
                            new_tvid=cur_switch['new_indexer'], new_prodid=cur_switch['new_indexer_id'],
                            force_id=bool(cur_switch['force_id']), uid=cur_switch['uid'],
                            set_pause=bool(cur_switch['set_pause']), mark_wanted=bool(cur_switch['mark_wanted'])
                        )
                    except (BaseException, Exception):
                        continue
                elif cur_switch['new_indexer_id']:
                    # show id was already switched, but not finished updated, so resume
                    q_switch(cur_switch)
        else:
            switching = False

        # Start an update if we're supposed to
        if not switching and (self.force_update or sickbeard.UPDATE_SHOWS_ON_START):
            sickbeard.classes.loading_msg.message = 'Starting a forced show update'
            sickbeard.show_update_scheduler.action.run()

        sickbeard.classes.loading_msg.message = 'Switching to default web server'
        time.sleep(2)
        self.webserver.switch_handlers()

        # main loop
        while 1:
            time.sleep(1)

    def daemonize(self):
        """
        Fork off as a daemon
        """
        # pylint: disable=E1101
        # Make a non-session-leader child process
        try:
            pid = os.fork()  # only available in UNIX
            if 0 != pid:
                self.exit(0)
        except OSError as er:
            sys.stderr.write('fork #1 failed: %d (%s)\n' % (er.errno, er.strerror))
            sys.exit(1)

        os.setsid()  # only available in UNIX

        # Make sure I can read my own files and shut out others
        prev = os.umask(0)
        os.umask(prev and int('077', 8))

        # Make the child a session-leader by detaching from the terminal
        try:
            pid = os.fork()  # only available in UNIX
            if 0 != pid:
                self.exit(0)
        except OSError as er:
            sys.stderr.write('fork #2 failed: %d (%s)\n' % (er.errno, er.strerror))
            sys.exit(1)

        # Write pid
        if self.create_pid:
            pid = str(os.getpid())
            logger.log(u'Writing PID: %s to %s' % (pid, self.pid_file))
            try:
                os.fdopen(os.open(self.pid_file, os.O_CREAT | os.O_WRONLY, 0o644), 'w').write('%s\n' % pid)
            except (BaseException, Exception) as er:
                logger.log_error_and_exit('Unable to write PID file: %s Error: %s [%s]' % (
                    self.pid_file, er.strerror, er.errno))

        # Redirect all output
        sys.stdout.flush()
        sys.stderr.flush()

        devnull = getattr(os, 'devnull', '/dev/null')
        stdin = open(devnull, 'r')
        stdout = open(devnull, 'a+')
        stderr = open(devnull, 'a+')
        os.dup2(stdin.fileno(), sys.stdin.fileno())
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        os.dup2(stderr.fileno(), sys.stderr.fileno())

    @staticmethod
    def remove_pid_file(pidfile):
        try:
            if os.path.exists(pidfile):
                os.remove(pidfile)

        except (IOError, OSError):
            return False

        return True

    @staticmethod
    def load_shows_from_db():
        """
        Populates the showList with shows from the database
        """

        logger.log(u'Loading initial show list')

        my_db = db.DBConnection(row_type='dict')
        sql_result = my_db.select(
            """
            SELECT tv_shows.indexer AS tv_id, tv_shows.indexer_id AS prod_id, tv_shows.*,
             ii.akas AS ii_akas, 
             ii.certificates AS ii_certificates,
             ii.countries AS ii_countries, ii.country_codes AS ii_country_codes,
             ii.genres AS ii_genres, ii.imdb_id AS ii_imdb_id,
             ii.indexer AS ii_indexer, ii.indexer_id AS ii_indexer_id,
             ii.last_update AS ii_ii_last_update,
             ii.rating AS ii_rating, ii.runtimes AS ii_runtimes,
             ii.is_mini_series AS ii_is_mini_series, ii.episode_count AS ii_episode_count,
             ii.title AS ii_title, ii.votes AS ii_votes, ii.year AS ii_year,
             tsnf.fail_count AS tsnf_fail_count, tsnf.indexer AS tsnf_indexer,
             tsnf.indexer_id AS tsnf_indexer_id, tsnf.last_check AS tsnf_last_check,
             tsnf.last_success AS tsnf_last_success
            FROM tv_shows
            LEFT JOIN imdb_info ii
             ON tv_shows.indexer = ii.indexer AND tv_shows.indexer_id = ii.indexer_id
            LEFT JOIN tv_shows_not_found tsnf
             ON tv_shows.indexer = tsnf.indexer AND tv_shows.indexer_id = tsnf.indexer_id
            """)
        sickbeard.showList = []
        sickbeard.showDict = {}
        for cur_result in sql_result:
            try:
                tv_id = int(cur_result['tv_id'])
                prod_id = int(cur_result['prod_id'])
                if cur_result['ii_indexer_id']:
                    imdb_info_sql = {_fk.replace('ii_', ''): _fv for _fk, _fv in iteritems(cur_result)
                                     if _fk.startswith('ii_')}
                else:
                    imdb_info_sql = None
                show_obj = TVShow(tv_id, prod_id, show_result=cur_result, imdb_info_result=imdb_info_sql)
                if cur_result['tsnf_indexer_id']:
                    failed_result = {_fk.replace('tsnf_', ''): _fv for _fk, _fv in iteritems(cur_result)
                                     if _fk.startswith('tsnf_')}
                    show_obj.helper_load_failed_db(sql_result=failed_result)
                sickbeard.showList.append(show_obj)
                sickbeard.showDict[show_obj.sid_int] = show_obj
                _ = show_obj.ids
            except (BaseException, Exception) as err:
                logger.log('There was an error creating the show in %s: %s' % (
                    cur_result['location'], ex(err)), logger.ERROR)
        sickbeard.webserve.Home.make_showlist_unique_names()

    @staticmethod
    def restore(src_dir, dst_dir):
        try:
            for filename in os.listdir(src_dir):
                src_file = os.path.join(src_dir, filename)
                dst_file = os.path.join(dst_dir, filename)
                bak_file = os.path.join(dst_dir, '%s.bak' % filename)
                shutil.move(dst_file, bak_file)
                shutil.move(src_file, dst_file)

            os.rmdir(src_dir)
            return True
        except (BaseException, Exception):
            return False

    def shutdown(self, ev_type):
        if sickbeard.started:
            # stop all tasks
            sickbeard.halt()

            # save all shows to DB
            sickbeard.save_all()

            # shutdown web server
            if self.webserver:
                logger.log('Shutting down Tornado')
                self.webserver.shut_down()
                try:
                    self.webserver.join(10)
                except (BaseException, Exception):
                    pass

            # if run as daemon delete the pidfile
            if self.run_as_daemon and self.create_pid:
                self.remove_pid_file(self.pid_file)

            if sickbeard.events.SystemEvent.RESTART == ev_type:

                popen_list = []

                if sickbeard.update_software_scheduler.action.install_type in ('git', 'source'):
                    popen_list = [sys.executable, sickbeard.MY_FULLNAME]

                if popen_list:
                    popen_list += sickbeard.MY_ARGS

                    if self.run_as_systemd:
                        logger.log(u'Restarting SickGear with exit(1) handler and %s' % popen_list)
                        logger.close()
                        self.exit(1)

                    if '--nolaunch' not in popen_list:
                        popen_list += ['--nolaunch']
                    logger.log(u'Restarting SickGear with %s' % popen_list)
                    logger.close()
                    from _23 import Popen
                    with Popen(popen_list, cwd=os.getcwd()):
                        self.exit(0)

        # system exit
        self.exit(0)

    @staticmethod
    def exit(code):
        # noinspection PyProtectedMember
        os._exit(code)


if '__main__' == __name__:
    freeze_support()
    try:
        try:
            # start SickGear
            SickGear().start()
        except IOError as e:
            if e.errno != errno.EINTR:
                raise
    except SystemExit as e:
        print('%s' % ex(e))
    except (BaseException, Exception) as e:
        import traceback
        print(traceback.format_exc())
        logger.log('SickGear.Start() exception caught %s: %s' % (ex(e), traceback.format_exc()))
