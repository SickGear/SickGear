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

from __future__ import with_statement

import time
import os
import sys
import threading
import zipfile
import logging
import glob
import codecs

from logging.handlers import TimedRotatingFileHandler

import sickbeard
from sickbeard import classes
import sickbeard.helpers

try:
    from lib.send2trash import send2trash
except ImportError:
    pass

ERROR = logging.ERROR
WARNING = logging.WARNING
MESSAGE = logging.INFO
DEBUG = logging.DEBUG
DB = 5

reverseNames = {u'ERROR': ERROR,
                u'WARNING': WARNING,
                u'INFO': MESSAGE,
                u'DEBUG': DEBUG,
                u'DB': DB}


# send logging to null
class NullHandler(logging.Handler):
    def emit(self, record):
        pass


class SBRotatingLogHandler(object):
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_file_path = log_file
        self.cur_handler = None

        self.console_logging = False
        self.log_lock = threading.Lock()

    def __del__(self):
        pass

    def close_log(self, handler=None):
        if not handler:
            handler = self.cur_handler

        if handler:
            sb_logger = logging.getLogger('sickbeard')
            sub_logger = logging.getLogger('subliminal')
            imdb_logger = logging.getLogger('imdbpy')
            tornado_logger = logging.getLogger('tornado')
            feedcache_logger = logging.getLogger('feedcache')

            sb_logger.removeHandler(handler)
            sub_logger.removeHandler(handler)
            imdb_logger.removeHandler(handler)
            tornado_logger.removeHandler(handler)
            feedcache_logger.removeHandler(handler)

            handler.flush()
            handler.close()

    def init_logging(self, console_logging=False):

        if console_logging:
            self.console_logging = console_logging

        old_handler = None

        # get old handler in case we want to close it
        if self.cur_handler:
            old_handler = self.cur_handler
        else:

            # add a new logging level DB
            logging.addLevelName(5, 'DB')

            # only start console_logging on first initialize
            if self.console_logging:
                # define a Handler which writes INFO messages or higher to the sys.stderr
                console = logging.StreamHandler()

                console.setLevel(logging.INFO)
                if sickbeard.DEBUG:
                    console.setLevel(logging.DEBUG)

                # set a format which is simpler for console use
                console.setFormatter(DispatchingFormatter(
                    {'sickbeard': logging.Formatter(
                        '%(asctime)s %(levelname)s::%(message)s', '%H:%M:%S'),
                     'subliminal': logging.Formatter(
                         '%(asctime)s %(levelname)s::SUBLIMINAL :: %(message)s', '%H:%M:%S'),
                     'imdbpy': logging.Formatter(
                         '%(asctime)s %(levelname)s::IMDBPY :: %(message)s', '%H:%M:%S'),
                     'tornado.general': logging.Formatter(
                         '%(asctime)s %(levelname)s::TORNADO :: %(message)s', '%H:%M:%S'),
                     'tornado.application': logging.Formatter(
                         '%(asctime)s %(levelname)s::TORNADO :: %(message)s', '%H:%M:%S'),
                     'feedcache.cache': logging.Formatter(
                         '%(asctime)s %(levelname)s::FEEDCACHE :: %(message)s', '%H:%M:%S')},
                    logging.Formatter('%(message)s'), ))

                # add the handler to the root logger
                logging.getLogger('sickbeard').addHandler(console)
                logging.getLogger('tornado.general').addHandler(console)
                logging.getLogger('tornado.application').addHandler(console)
                logging.getLogger('subliminal').addHandler(console)
                logging.getLogger('imdbpy').addHandler(console)
                logging.getLogger('feedcache').addHandler(console)

        self.log_file_path = os.path.join(sickbeard.LOG_DIR, self.log_file)

        self.cur_handler = self._config_handler()
        logging.getLogger('sickbeard').addHandler(self.cur_handler)
        logging.getLogger('tornado.access').addHandler(NullHandler())
        logging.getLogger('tornado.general').addHandler(self.cur_handler)
        logging.getLogger('tornado.application').addHandler(self.cur_handler)
        logging.getLogger('subliminal').addHandler(self.cur_handler)
        logging.getLogger('imdbpy').addHandler(self.cur_handler)
        logging.getLogger('feedcache').addHandler(self.cur_handler)

        logging.getLogger('sickbeard').setLevel(DB)

        log_level = logging.WARNING
        if sickbeard.DEBUG:
            log_level = logging.DEBUG

        logging.getLogger('tornado.general').setLevel(log_level)
        logging.getLogger('tornado.application').setLevel(log_level)
        logging.getLogger('subliminal').setLevel(log_level)
        logging.getLogger('imdbpy').setLevel(log_level)
        logging.getLogger('feedcache').setLevel(log_level)

        # already logging in new log folder, close the old handler
        if old_handler:
            self.close_log(old_handler)
            #            old_handler.flush()
            #            old_handler.close()
            #            sb_logger = logging.getLogger('sickbeard')
            #            sub_logger = logging.getLogger('subliminal')
            #            imdb_logger = logging.getLogger('imdbpy')
            #            sb_logger.removeHandler(old_handler)
            #            subli_logger.removeHandler(old_handler)
            #            imdb_logger.removeHandler(old_handler)

    def _config_handler(self):
        """
        Configure a file handler to log at file_name and return it.
        """

        file_handler = TimedCompressedRotatingFileHandler(self.log_file_path, when='midnight',
                                                          backupCount=16, encoding='utf-8')
        file_handler.setLevel(reverseNames[sickbeard.FILE_LOGGING_PRESET])
        file_handler.setFormatter(DispatchingFormatter(
            {'sickbeard': logging.Formatter(
                '%(asctime)s %(levelname)-8s %(message)s', '%Y-%m-%d %H:%M:%S'),
             'subliminal': logging.Formatter(
                 '%(asctime)s %(levelname)-8s SUBLIMINAL :: %(message)s', '%Y-%m-%d %H:%M:%S'),
             'imdbpy': logging.Formatter(
                 '%(asctime)s %(levelname)-8s IMDBPY :: %(message)s', '%Y-%m-%d %H:%M:%S'),
             'tornado.general': logging.Formatter(
                 '%(asctime)s %(levelname)-8s TORNADO :: %(message)s', '%Y-%m-%d %H:%M:%S'),
             'tornado.application': logging.Formatter(
                 '%(asctime)s %(levelname)-8s TORNADO :: %(message)s', '%Y-%m-%d %H:%M:%S'),
             'feedcache.cache': logging.Formatter(
                 '%(asctime)s %(levelname)-8s FEEDCACHE :: %(message)s', '%Y-%m-%d %H:%M:%S')},
            logging.Formatter('%(message)s'), ))

        return file_handler

    def log(self, to_log, log_level=MESSAGE):

        with self.log_lock:

            out_line = '%s :: %s' % (threading.currentThread().getName(), to_log)

            sb_logger = logging.getLogger('sickbeard')
            setattr(sb_logger, 'db', lambda *args: sb_logger.log(DB, *args))

            # sub_logger = logging.getLogger('subliminal')
            # imdb_logger = logging.getLogger('imdbpy')
            # tornado_logger = logging.getLogger('tornado')
            # feedcache_logger = logging.getLogger('feedcache')

            try:
                if DEBUG == log_level:
                    sb_logger.debug(out_line)
                elif MESSAGE == log_level:
                    sb_logger.info(out_line)
                elif WARNING == log_level:
                    sb_logger.warning(out_line)
                elif ERROR == log_level:
                    sb_logger.error(out_line)
                    # add errors to the UI logger
                    classes.ErrorViewer.add(classes.UIError(out_line))
                elif DB == log_level:
                    sb_logger.db(out_line)
                else:
                    sb_logger.log(log_level, out_line)
            except ValueError:
                pass

    def log_error_and_exit(self, error_msg):
        log(error_msg, ERROR)

        if not self.console_logging:
            sys.exit(error_msg.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))
        else:
            sys.exit(1)


class DispatchingFormatter:
    def __init__(self, formatters, default_formatter):
        self._formatters = formatters
        self._default_formatter = default_formatter

    def __del__(self):
        pass

    def format(self, record):
        formatter = self._formatters.get(record.name, self._default_formatter)
        return formatter.format(record)


class TimedCompressedRotatingFileHandler(TimedRotatingFileHandler):
    """
       Extended version of TimedRotatingFileHandler that compress logs on rollover.
       by Angel Freire <cuerty at gmail dot com>
    """
    def doRollover(self):
        """
        do a rollover; in this case, a date/time stamp is appended to the filename
        when the rollover happens.  However, you want the file to be named for the
        start of the interval, not the current time.  If there is a backup count,
        then we have to get a list of matching filenames, sort them and remove
        the one with the oldest suffix.

        This method is modified from the one in TimedRotatingFileHandler.

        """
        self.stream.close()
        # get the time that this sequence started at and make it a TimeTuple
        t = self.rolloverAt - self.interval
        time_tuple = time.localtime(t)
        file_name = self.baseFilename.rpartition('.')[0]
        dfn = '%s_%s.log' % (file_name, time.strftime(self.suffix, time_tuple))
        self.delete_logfile(dfn)
        try:
            ek.ek(os.rename, self.baseFilename, dfn)
        except (StandardError, Exception):
            pass
        if 0 < self.backupCount:
            # find the oldest log file and delete it
            s = glob.glob(file_name + '_*')
            if len(s) > self.backupCount:
                s.sort()
                self.delete_logfile(s[0])
        # print "%s -> %s" % (self.baseFilename, dfn)
        if self.encoding:
            self.stream = codecs.open(self.baseFilename, 'w', self.encoding)
        else:
            self.stream = open(self.baseFilename, 'w')
        self.rolloverAt = self.rolloverAt + self.interval
        zip_name = '%s.zip' % dfn.rpartition('.')[0]
        self.delete_logfile(zip_name)
        zip_fh = zipfile.ZipFile(zip_name, 'w')
        zip_fh.write(dfn, os.path.basename(dfn), zipfile.ZIP_DEFLATED)
        zip_fh.close()
        self.delete_logfile(dfn)

    @staticmethod
    def delete_logfile(filepath):
        if os.path.exists(filepath):
            if sickbeard.TRASH_ROTATE_LOGS:
                send2trash(filepath)
            else:
                sickbeard.helpers.remove_file_failed(filepath)


sb_log_instance = SBRotatingLogHandler('sickbeard.log')


def log(to_log, log_level=MESSAGE):
    sb_log_instance.log(to_log, log_level)


def log_error_and_exit(error_msg):
    sb_log_instance.log_error_and_exit(error_msg)


def close():
    sb_log_instance.close_log()


def log_set_level():
    if sb_log_instance.cur_handler:
        sb_log_instance.cur_handler.setLevel(reverseNames[sickbeard.FILE_LOGGING_PRESET])


def current_log_file():
    return os.path.join(sickbeard.LOG_DIR, sb_log_instance.log_file)
