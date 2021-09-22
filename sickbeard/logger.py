#
#  This file is part of SickGear.
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

import codecs
import datetime
import logging
import glob
import os
import re
import sys
import threading
import time
import zipfile

from logging.handlers import TimedRotatingFileHandler

import sickbeard
from . import classes
from .sgdatetime import timestamp_near
from sg_helpers import md5_for_text, remove_file_perm

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Union

try:
    # noinspection PyUnresolvedReferences
    from lib.send2trash import send2trash
except ImportError:
    pass

# ERROR = 40, WARNING = 30, INFO = 20, DEBUG = 10
ERROR = logging.ERROR
WARNING = logging.WARNING
MESSAGE = logging.INFO
DEBUG = logging.DEBUG
DB = 5

reverseNames = {u'ERROR': ERROR, u'WARNING': WARNING, u'INFO': MESSAGE, u'DEBUG': DEBUG, u'DB': DB}


# suppress output with this handler
class NullHandler(logging.Handler):
    def emit(self, record):
        pass


class SBRotatingLogHandler(object):
    def __init__(self, log_file):
        """

        :param log_file: log file
        :type log_file: AnyStr
        """
        self.log_file = log_file  # type: AnyStr
        self.log_file_path = log_file  # type: AnyStr
        self.h_file = None
        self.h_console = None

        self.console_logging = False  # type: bool
        self.log_lock = threading.Lock()
        self.log_types = ['sickbeard', 'tornado.application', 'tornado.general', 'subliminal', 'adba', 'encodingKludge',
                          'tvdb.api', 'TVInfo']
        self.external_loggers = ['sg.helper', 'api_trakt', 'api_trakt.api']
        self.log_types_null = ['tornado.access']

    def __del__(self):
        pass

    def close_log(self, handler=None):
        """

        :param handler:
        :type handler:
        """
        handlers = []
        if not handler:
            if None is not self.h_console:
                handlers = [self.h_console]
            handlers += [self.h_file]
        elif not isinstance(handler, list):
            handlers = [handler]

        for handler in handlers:
            for logger_name in self.log_types + self.log_types_null + self.external_loggers:
                logging.getLogger(logger_name).removeHandler(handler)

            if type(handler) != type(logging.StreamHandler()):  # check exact type, not an inherited instance
                handler.flush()
                handler.close()

    def init_logging(self, console_logging=False):
        """

        :param console_logging: console logging
        :type console_logging: bool
        """
        self.console_logging |= console_logging
        self.log_file_path = os.path.join(sickbeard.LOG_DIR, self.log_file)

        # get old handler for post switch-over closure
        old_h_file = old_h_console = None
        if self.h_file or self.h_console:
            if self.h_file:
                old_h_file = self.h_file
            if self.h_console:
                old_h_console = self.h_console

        # add a new logging level DB
        logging.addLevelName(5, 'DB')

        if self.console_logging:
            # get a console handler to output INFO or higher messages to sys.stderr
            h_console = logging.StreamHandler()
            if None is not h_console.stream:
                h_console.setLevel((logging.INFO, logging.DEBUG)[sickbeard.DEBUG])
                h_console.setFormatter(DispatchingFormatter(self._formatters(), logging.Formatter('%(message)s'), ))
                self.h_console = h_console

            # add the handler to the root logger
            for logger_name in self.log_types + self.external_loggers:
                logging.getLogger(logger_name).addHandler(h_console)

        for logger_name in self.log_types_null:
            logging.getLogger(logger_name).addHandler(NullHandler())

        h_file = TimedCompressedRotatingFileHandler(self.log_file_path, logger=self)
        h_file.setLevel(reverseNames[sickbeard.FILE_LOGGING_PRESET])
        h_file.setFormatter(DispatchingFormatter(self._formatters(False), logging.Formatter('%(message)s'), ))
        self.h_file = h_file

        for logger_name in self.external_loggers:
            logging.getLogger(logger_name).addHandler(h_file)
            logging.getLogger(logger_name).setLevel(DEBUG)

        for logger_name in self.log_types:
            logging.getLogger(logger_name).addHandler(h_file)

        log_level = (logging.WARNING, logging.DEBUG)[sickbeard.DEBUG]
        for logger_name in [x for x in self.log_types if 'sickbeard' != x]:
            logging.getLogger(logger_name).setLevel(log_level)
        logging.getLogger('sickbeard').setLevel(DB)

        # as now logging in new log folder, close old handlers
        if old_h_file:
            self.close_log(old_h_file)
        if old_h_console:
            self.close_log(old_h_console)

    def _formatters(self, log_simple=True):
        """

        :param log_simple: simple log
        :type log_simple: bool
        :return:
        """
        fmt = {}
        for logger_name in self.log_types + self.external_loggers:
            source = ((re.sub(r'(.*\.\w\w\w).*$', r'\1', logger_name), logger_name)['sg.' in logger_name]
                      .upper() + ' :: ', '')['sickbeard' == logger_name]
            fmt.setdefault(logger_name, logging.Formatter(
                '%(asctime)s %(levelname)' + ('-8', '')[log_simple] + 's ' + source
                + '%(message)s', ('%Y-%m-%d ', '')[log_simple] + '%H:%M:%S'))

        return fmt

    def log(self, to_log, log_level=MESSAGE):
        # type: (Union[AnyStr, list], int) -> None
        """Log an item, or a list of items using log_lock so to_log list items are continuous in output.
        :param to_log: log message, list of log messages
        :param log_level: log level
        """
        with self.log_lock:
            self.output_log((to_log, [to_log])[not isinstance(to_log, list)], log_level)

    @staticmethod
    def output_log(log_list, log_level=MESSAGE):
        # type: (list, int) -> None
        """
        :param log_list: log message
        :param log_level: log level
        """
        mem_key = 'logger'
        for to_log in log_list:
            log_id = md5_for_text(to_log)
            now = int(timestamp_near(datetime.datetime.now()))
            expired = now > sickbeard.MEMCACHE.get(mem_key, {}).get(log_id, 0)
            sickbeard.MEMCACHE[mem_key] = {}
            sickbeard.MEMCACHE[mem_key][log_id] = 2 + now
            if not expired:
                continue

            out_line = '%s :: %s' % (threading.current_thread().name, to_log)

            sb_logger = logging.getLogger('sickbeard')
            setattr(sb_logger, 'db', lambda *args: sb_logger.log(DB, *args))

            # sub_logger = logging.getLogger('subliminal')
            # tornado_logger = logging.getLogger('tornado')

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
        """

        :param error_msg: error message
        :type error_msg: AnyStr
        """
        log(error_msg, ERROR)

        if not self.console_logging:
            sys.exit(error_msg.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))
        else:
            sys.exit(1)

    @staticmethod
    def reverse_readline(filename, buf_size=4096):
        """a generator that returns the lines of a file in reverse order
        :param filename: file name
        :type filename: AnyStr
        :param buf_size: buffer size
        :type buf_size: int or long
        """
        with codecs.open(filename, 'r', encoding='utf-8', errors='replace') as fh:
            segment = None
            offset = 0
            fh.seek(0, os.SEEK_END)
            file_size = remaining_size = fh.tell()
            while 0 < remaining_size:
                offset = min(file_size, offset + buf_size)
                fh.seek(file_size - offset)
                buf = fh.read(min(remaining_size, buf_size))
                remaining_size -= buf_size
                lines = buf.split('\n')
                # the first line of the buffer is probably not a complete line so
                # we'll save it and append it to the last line of the next buffer
                # we read
                if None is not segment:
                    # if the previous chunk starts right from the beginning of line
                    # do not concat the segment to the last line of new chunk
                    # instead, yield the segment first
                    if buf[-1] != '\n':
                        lines[-1] += segment
                    else:
                        yield segment + '\n'
                segment = lines[0]
                for index in range(len(lines) - 1, 0, -1):
                    if len(lines[index]):
                        yield lines[index] + '\n'
            yield None is not segment and segment + '\n' or ''


class DispatchingFormatter(object):
    def __init__(self, formatters, default_formatter):
        self._formatters = formatters
        self._default_formatter = default_formatter

    def __del__(self):
        pass

    def format(self, record):
        formatter = self._formatters.get(record.name, self._default_formatter)
        return formatter.format(record)


class TimedCompressedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, log_file_path, logger=None, when='midnight', interval=1,
                 backup_count=16, encoding='utf-8', delay=False, utc=False):
        super(TimedCompressedRotatingFileHandler, self).__init__(log_file_path, when, interval,
                                                                 backup_count, encoding, delay, utc)
        self.logger_instance = logger

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

        example:
        logger.TimedCompressedRotatingFileHandler(sickbeard.logger.sb_log_instance.log_file_path, when='M', interval=2,
                                                  logger=sickbeard.logger.sb_log_instance).doRollover()
        """
        if not self.logger_instance:
            return

        # get the time that this sequence started at
        t = self.rolloverAt - self.interval
        start_time = time.localtime(t)
        file_name = self.baseFilename.rpartition('.')[0]
        dfn = '%s_%s.log' % (file_name, time.strftime(self.suffix, start_time))
        self.delete_logfile(dfn)

        self.logger_instance.close_log()
        self.logger_instance.h_file = self.logger_instance.h_console = None

        try:
            self.stream.close()
        except AttributeError:
            pass

        import encodingKludge
        try:
            encodingKludge.ek(os.rename, self.baseFilename, dfn)
        except (BaseException, Exception):
            pass

        self.logger_instance.init_logging()

        if self.encoding:
            self.stream = codecs.open(self.baseFilename, 'w', self.encoding)
        else:
            self.stream = open(self.baseFilename, 'w')

        zip_name = '%s.zip' % dfn.rpartition('.')[0]
        self.delete_logfile(zip_name)
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zip_fh:
            zip_fh.write(dfn, os.path.basename(dfn))

        self.delete_logfile(dfn)

        if 0 < self.backupCount:
            # find the oldest log file and delete it
            # phase out files named sickbeard.log in favour of sickgear.logs over backup_count days
            all_names = encodingKludge.ek(glob.glob, file_name + '_*') + \
                        encodingKludge.ek(glob.glob, encodingKludge.ek(os.path.join, encodingKludge.ek(
                            os.path.dirname, file_name), 'sickbeard_*'))
            if len(all_names) > self.backupCount:
                all_names.sort()
                self.delete_logfile(all_names[0])

        self.rolloverAt = self.rolloverAt + self.interval

    @staticmethod
    def delete_logfile(filepath):
        """

        :param filepath: file path
        :type filepath: AnyStr
        """
        if os.path.exists(filepath):
            if sickbeard.TRASH_ROTATE_LOGS:
                try:
                    send2trash(filepath)
                except OSError:
                    pass
            else:
                remove_file_perm(filepath)


sb_log_instance = SBRotatingLogHandler('sickgear.log')


def debug(to_log):
    # type: (AnyStr) -> None
    """ log message flagged as debug
    :param to_log: log message
    """
    sb_log_instance.log(to_log, DEBUG)


def warning(to_log):
    # type: (AnyStr) -> None
    """ log message flagged as warning
    :param to_log: log message
    """
    sb_log_instance.log(to_log, WARNING)


def error(to_log):
    # type: (AnyStr) -> None
    """ log message flagged as error
    :param to_log: log message
    """
    sb_log_instance.log(to_log, ERROR)


def log(to_log, log_level=MESSAGE):
    # type: (Union[AnyStr, list], int) -> None
    """
    :param to_log: log message
    :param log_level: log level
    """
    sb_log_instance.log(to_log, log_level)


def log_error_and_exit(error_msg):
    """

    :param error_msg: error message
    :type error_msg: AnyStr
    """
    sb_log_instance.log_error_and_exit(error_msg)


def load_log(load_msg, to_log, log_level=MESSAGE):
    """
    logs messages and adds log_level = MESSAGE messages as progress to loading page
    :param load_msg: base loading page message
    :param to_log: message to log to file and as progress for loading page
    :param log_level: log level (only level MESSAGE is also output as loading page progress)
    """
    if MESSAGE == log_level:
        sickbeard.classes.loading_msg.set_msg_progress(load_msg, to_log)
    log(to_log, log_level)


def close():
    sb_log_instance.close_log()


def log_set_level():
    if sb_log_instance.h_file:
        sb_log_instance.h_file.setLevel(reverseNames[sickbeard.FILE_LOGGING_PRESET])


def current_log_file():
    return os.path.join(sickbeard.LOG_DIR, sb_log_instance.log_file)
