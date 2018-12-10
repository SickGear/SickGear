#!/usr/bin/env python2
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

import datetime
import errno
import getopt
import locale
import os
import signal
import sys
import shutil
import subprocess
import time
import threading
import warnings

warnings.filterwarnings('ignore', module=r'.*fuzzywuzzy.*')
warnings.filterwarnings('ignore', module=r'.*Cheetah.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')
warnings.filterwarnings('ignore', module=r'.*zoneinfo.*', message='.*file or directory.*')

if not (2, 7, 9) <= sys.version_info < (3, 0):
    print('Python %s.%s.%s detected.' % sys.version_info[:3])
    print('Sorry, SickGear requires Python 2.7.9 or higher. Python 3 is not supported.')
    sys.exit(1)

try:
    import _cleaner
except (StandardError, Exception):
    pass

try:
    import Cheetah

    if Cheetah.Version[0] < '2':
        raise ValueError
except ValueError:
    print('Sorry, requires Python module Cheetah 2.1.0 or newer.')
    sys.exit(1)
except (StandardError, Exception):
    print('The Python module Cheetah is required')
    sys.exit(1)

sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), 'lib')))
from lib.six import moves

# We only need this for compiling an EXE and I will just always do that on 2.6+
if sys.hexversion >= 0x020600F0:
    from multiprocessing import freeze_support  # @UnresolvedImport

import sickbeard
from sickbeard import db, logger, network_timezones, failed_history, name_cache
from sickbeard.tv import TVShow
from sickbeard.webserveInit import WebServer
from sickbeard.databases.mainDB import MIN_DB_VERSION, MAX_DB_VERSION
from sickbeard.event_queue import Events
from sickbeard.exceptions import ex
from lib.configobj import ConfigObj

throwaway = datetime.datetime.strptime('20110101', '%Y%m%d')
rollback_loaded = None

signal.signal(signal.SIGINT, sickbeard.sig_handler)
signal.signal(signal.SIGTERM, sickbeard.sig_handler)
if 'win32' == sys.platform:
    signal.signal(signal.SIGBREAK, sickbeard.sig_handler)


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

        if 'win32' == sys.platform:
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
    def execute_rollback(mo, max_v):
        global rollback_loaded
        try:
            if None is rollback_loaded:
                rollback_loaded = db.get_rollback_module()
            if None is not rollback_loaded:
                rollback_loaded.__dict__[mo]().run(max_v)
            else:
                print(u'ERROR: Could not download Rollback Module.')
        except (StandardError, Exception):
            pass

    def start(self):
        # do some preliminary stuff
        sickbeard.MY_FULLNAME = os.path.normpath(os.path.abspath(__file__))
        sickbeard.MY_NAME = os.path.basename(sickbeard.MY_FULLNAME)
        sickbeard.PROG_DIR = os.path.dirname(sickbeard.MY_FULLNAME)
        sickbeard.DATA_DIR = sickbeard.PROG_DIR
        sickbeard.MY_ARGS = sys.argv[1:]
        sickbeard.SYS_ENCODING = None

        try:
            locale.setlocale(locale.LC_ALL, '')
        except (locale.Error, IOError):
            pass
        try:
            sickbeard.SYS_ENCODING = locale.getpreferredencoding()
        except (locale.Error, IOError):
            pass

        # For OSes that are poorly configured I'll just randomly force UTF-8
        if not sickbeard.SYS_ENCODING or sickbeard.SYS_ENCODING in ('ANSI_X3.4-1968', 'US-ASCII', 'ASCII'):
            sickbeard.SYS_ENCODING = 'UTF-8'

        if not hasattr(sys, 'setdefaultencoding'):
            moves.reload_module(sys)

        try:
            # pylint: disable=E1101
            # On non-unicode builds this raises an AttributeError, if encoding type is not valid it throws a LookupError
            sys.setdefaultencoding(sickbeard.SYS_ENCODING)
        except (StandardError, Exception):
            print('Sorry, you MUST add the SickGear folder to the PYTHONPATH environment variable')
            print('or find another way to force Python to use %s for string encoding.' % sickbeard.SYS_ENCODING)
            sys.exit(1)

        # Need console logging for SickBeard.py and SickBeard-console.exe
        self.console_logging = (not hasattr(sys, 'frozen')) or (sickbeard.MY_NAME.lower().find('-console') > 0)

        # Rename the main thread
        threading.currentThread().name = 'MAIN'

        try:
            opts, args = getopt.getopt(sys.argv[1:], 'hfqdsp::',
                                       ['help', 'forceupdate', 'quiet', 'nolaunch', 'daemon', 'systemd', 'pidfile=',
                                        'port=', 'datadir=', 'config=', 'noresize'])  # @UnusedVariable
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

                if 'win32' == sys.platform:
                    self.run_as_daemon = False

            # Run as a systemd service
            if o in ('-s', '--systemd') and 'win32' != sys.platform:
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
        except (StandardError, Exception):
            stack_size = None

        if stack_size:
            try:
                threading.stack_size(stack_size)
            except (StandardError, Exception) as er:
                print('Stack Size %s not set: %s' % (stack_size, er.message))

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
            if cur_db_version >= 100000 and cur_db_version != max_v:
                print('Your [%s] database version (%s) is a test db version and doesn\'t match SickGear required '
                      'version (%s), downgrading to production db' % (d, cur_db_version, max_v))
                self.execute_rollback(mo, max_v)
                cur_db_version = db.DBConnection(d).checkDBVersion()
                if cur_db_version >= 100000:
                    print(u'Rollback to production failed.')
                    sys.exit(u'If you have used other forks, your database may be unusable due to their changes')
                if 100000 <= max_v and None is not base_v:
                    max_v = base_v  # set max_v to the needed base production db for test_db
                print(u'Rollback to production of [%s] successful.' % d)

            # handling of production db versions
            if 0 < cur_db_version < 100000:
                if cur_db_version < min_v:
                    print(u'Your [%s] database version (%s) is too old to migrate from with this version of SickGear'
                          % (d, cur_db_version))
                    sys.exit(u'Upgrade using a previous version of SG first,'
                             + u' or start with no database file to begin fresh')
                if cur_db_version > max_v:
                    print(u'Your [%s] database version (%s) has been incremented past'
                          u' what this version of SickGear supports. Trying to rollback now. Please wait...' %
                          (d, cur_db_version))
                    self.execute_rollback(mo, max_v)
                    if db.DBConnection(d).checkDBVersion() > max_v:
                        print(u'Rollback failed.')
                        sys.exit(u'If you have used other forks, your database may be unusable due to their changes')
                    print(u'Rollback of [%s] successful.' % d)

        # free memory
        global rollback_loaded
        rollback_loaded = None

        # Initialize the config and our threads
        sickbeard.initialize(console_logging=self.console_logging)

        if self.run_as_daemon:
            self.daemonize()

        # Get PID
        sickbeard.PID = os.getpid()

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
        if sickbeard.WEB_HOST and sickbeard.WEB_HOST != '0.0.0.0':
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

            self.webserver = WebServer(self.web_options)
            self.webserver.start()
        except (StandardError, Exception):
            logger.log(u'Unable to start web server, is something else running on port %d?' % self.start_port,
                       logger.ERROR)
            if self.run_as_systemd:
                self.exit(0)
            if sickbeard.LAUNCH_BROWSER and not self.no_launch:
                logger.log(u'Launching browser and exiting', logger.ERROR)
                sickbeard.launch_browser(self.start_port)
            self.exit(1)

        # Check if we need to perform a restore first
        restore_dir = os.path.join(sickbeard.DATA_DIR, 'restore')
        if os.path.exists(restore_dir):
            if self.restore(restore_dir, sickbeard.DATA_DIR):
                logger.log(u'Restore successful...')
            else:
                logger.log_error_and_exit(u'Restore FAILED!')

        # Build from the DB to start with
        self.load_shows_from_db()

        # Fire up all our threads
        sickbeard.start()

        # Build internal name cache
        name_cache.buildNameCache()

        # refresh network timezones
        network_timezones.update_network_dict()

        # load all ids from xem
        startup_background_tasks = threading.Thread(name='FETCH-XEMDATA', target=sickbeard.scene_exceptions.get_xem_ids)
        startup_background_tasks.start()

        # check history snatched_proper update
        if not db.DBConnection().has_flag('history_snatch_proper'):
            # noinspection PyUnresolvedReferences
            history_snatched_proper_task = threading.Thread(name='UPGRADE-HISTORY-ACTION',
                                                            target=sickbeard.history.history_snatched_proper_fix)
            history_snatched_proper_task.start()

        if sickbeard.USE_FAILED_DOWNLOADS:
            failed_history.remove_old_history()

        # Start an update if we're supposed to
        if self.force_update or sickbeard.UPDATE_SHOWS_ON_START:
            sickbeard.showUpdateScheduler.action.run(force=True)  # @UndefinedVariable

        # Launch browser
        if sickbeard.LAUNCH_BROWSER and not self.no_launch:
            sickbeard.launch_browser(self.start_port)

        # main loop
        while True:
            time.sleep(1)

    def daemonize(self):
        """
        Fork off as a daemon
        """
        # pylint: disable=E1101
        # Make a non-session-leader child process
        try:
            pid = os.fork()  # @UndefinedVariable - only available in UNIX
            if pid != 0:
                self.exit(0)
        except OSError as er:
            sys.stderr.write('fork #1 failed: %d (%s)\n' % (er.errno, er.strerror))
            sys.exit(1)

        os.setsid()  # @UndefinedVariable - only available in UNIX

        # Make sure I can read my own files and shut out others
        prev = os.umask(0)
        os.umask(prev and int('077', 8))

        # Make the child a session-leader by detaching from the terminal
        try:
            pid = os.fork()  # @UndefinedVariable - only available in UNIX
            if pid != 0:
                self.exit(0)
        except OSError as er:
            sys.stderr.write('fork #2 failed: %d (%s)\n' % (er.errno, er.strerror))
            sys.exit(1)

        # Write pid
        if self.create_pid:
            pid = str(os.getpid())
            logger.log(u'Writing PID: %s to %s' % (pid, self.pid_file))
            try:
                open(self.pid_file, 'w').write('%s\n' % pid)
            except IOError as er:
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

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM tv_shows')

        sickbeard.showList = []
        for sqlShow in sql_results:
            try:
                cur_show = TVShow(int(sqlShow['indexer']), int(sqlShow['indexer_id']))
                cur_show.nextEpisode()
                sickbeard.showList.append(cur_show)
            except Exception as er:
                logger.log('There was an error creating the show in %s: %s' % (
                    sqlShow['location'], str(er).decode('utf-8', 'replace')), logger.ERROR)

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
        except (StandardError, Exception):
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
                except (StandardError, Exception):
                    pass

            # if run as daemon delete the pidfile
            if self.run_as_daemon and self.create_pid:
                self.remove_pid_file(self.pid_file)

            if sickbeard.events.SystemEvent.RESTART == ev_type:

                install_type = sickbeard.versionCheckScheduler.action.install_type

                popen_list = []

                if install_type in ('git', 'source'):
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
                    subprocess.Popen(popen_list, cwd=os.getcwd())

        # system exit
        self.exit(0)

    @staticmethod
    def exit(code):
        os._exit(code)


if __name__ == '__main__':
    if sys.hexversion >= 0x020600F0:
        freeze_support()
    try:
        try:
            # start SickGear
            SickGear().start()
        except IOError as e:
            if e.errno != errno.EINTR:
                raise
    except Exception as e:
        logger.log('SickGear.Start() exception caught %s' % ex(e))
