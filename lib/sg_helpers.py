# encoding:utf-8
# ---------------
# functions are placed here to remove cyclic import issues from placement in helpers
#
from __future__ import division
import ast
import codecs
import datetime
import getpass
import hashlib
import io
import logging
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback

from exceptions_helper import ex, ConnectionSkipException
from lib.cachecontrol import CacheControl, caches
from lib.tmdbsimple.configuration import Configuration
from lib.tmdbsimple.genres import Genres
from cfscrape import CloudflareScraper
from send2trash import send2trash

# noinspection PyPep8Naming
import encodingKludge as ek
import requests

from _23 import decode_bytes, filter_list, html_unescape, list_range, \
    ordered_dict, Popen, scandir, urlparse, urlsplit, urlunparse
from six import integer_types, iteritems, iterkeys, itervalues, moves, PY2, string_types, text_type

import zipfile
# py7z hardwired removed, see comment below
py7zr = None

# noinspection PyUnreachableCode
if False:
    from _23 import DirEntry
    from lxml_etree import etree
    try:
        # py7z hardwired removed because Python 3.9 interpretor crashes with a process kill signal 9 when memory is
        # low/exhausted during a native 7z compress action on Linux. Therefore, the native functions cannot be trusted.
        # `import` moved to this non-runtime scope to preserve code resolution in case reinstated at a later PY release
        # noinspection PyUnresolvedReferences,PyPackageRequirements
        import py7zr
    except ImportError:
        py7zr = None
    # sickbeard is strictly used here for resolution, this is only possible because
    # this section is not used at runtime which would create circular reference issues
    # noinspection PyPep8Naming
    from sickbeard import db, notifiers as NOTIFIERS
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, Generator, NoReturn, integer_types, Iterable, Iterator, List, Optional, \
        Tuple, Union

html_convert_fractions = {0: '', 25: '&frac14;', 50: '&frac12;', 75: '&frac34;', 100: 1}

PROG_DIR = ek.ek(os.path.join, os.path.dirname(os.path.normpath(os.path.abspath(__file__))), '..')

# Mapping error status codes to official W3C names
http_error_code = {
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',
    308: 'Permanent Redirect',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request-URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    429: 'Too Many Requests',
    431: 'Request Header Fields Too Large',
    444: 'No Response',
    451: 'Unavailable For Legal Reasons',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    511: 'Network Authentication Required'}

logger = logging.getLogger('sg.helper')
logger.addHandler(logging.NullHandler())

USER_AGENT = ''
CACHE_DIR = None
DATA_DIR = None
PROXY_SETTING = None
TRASH_REMOVE_SHOW = False
REMOVE_FILENAME_CHARS = None
MEMCACHE = {}
FLARESOLVERR_HOST = None

# noinspection PyRedeclaration
db = None
# noinspection PyRedeclaration
NOTIFIERS = None


class ConnectionFailTypes(object):
    http = 1
    connection = 2
    connection_timeout = 3
    timeout = 4
    other = 5
    limit = 6
    nodata = 7

    names = {http: 'http', timeout: 'timeout',
             connection: 'connection', connection_timeout: 'connection_timeout',
             nodata: 'nodata', other: 'other', limit: 'limit'}

    def __init__(self):
        pass


class ConnectionFail(object):
    def __init__(self, fail_type=ConnectionFailTypes.other, code=None, fail_time=None):
        self.code = code
        self.fail_type = fail_type
        self.fail_time = (datetime.datetime.now(), fail_time)[isinstance(fail_time, datetime.datetime)]


class ConnectionFailDict(object):
    def __init__(self):
        self.domain_list = {}  # type: Dict[AnyStr, ConnectionFailList]
        self.lock = threading.RLock()
        self.load_from_db()

    def load_from_db(self):
        if None is not db:
            with self.lock:
                my_db = db.DBConnection('cache.db')
                if my_db.hasTable('connection_fails'):
                    domains = my_db.select('SELECT DISTINCT domain_url from connection_fails')
                    for domain in domains:
                        self.domain_list[domain['domain_url']] = ConnectionFailList(domain['domain_url'])

    @staticmethod
    def get_domain(url):
        # type: (AnyStr) -> Optional[AnyStr]
        try:
            return urlsplit(url).hostname.lower()
        except (BaseException, Exception):
            pass

    def add_failure(self, url, fail_type):
        # type: (AnyStr, ConnectionFail) -> None
        host = self.get_domain(url)
        if None is not host:
            with self.lock:
                self.domain_list.setdefault(host, ConnectionFailList(host)).add_fail(fail_type)

    def inc_failure_count(self,
                          url,  # type: AnyStr
                          *args, **kwargs):
        host = self.get_domain(url)
        if None is not host:
            with self.lock:
                if host in self.domain_list:
                    domain = self.domain_list[host]
                    fail_type = ('fail_type' in kwargs and kwargs['fail_type'].fail_type) or \
                                (isinstance(args, tuple) and isinstance(args[0], ConnectionFail) and args[0].fail_type)
                    # noinspection PyProtectedMember
                    if not isinstance(domain.failure_time, datetime.datetime) or \
                            fail_type != domain._last_fail_type or \
                            domain.fail_newest_delta() > datetime.timedelta(seconds=3):
                        domain.failure_count += 1
                        domain.failure_time = datetime.datetime.now()
                        domain._last_fail_type = fail_type
                        domain.add_fail(*args, **kwargs)
                    else:
                        logger.debug('%s: Not logging same failure within 3 seconds' % url)

    def should_skip(self, url, log_warning=True, use_tmr_limit=True):
        # type: (AnyStr, bool, bool) -> bool
        host = self.get_domain(url)
        if None is not host:
            with self.lock:
                if host in self.domain_list:
                    return self.domain_list[host].should_skip(log_warning=log_warning, use_tmr_limit=use_tmr_limit)
        return False


DOMAIN_FAILURES = ConnectionFailDict()
sp = 8
trakt_fail_times = {(i * sp) + m: s for m in range(1, 1 + sp) for i, s in
                    enumerate([(0, 5), (0, 15), (0, 30), (1, 0), (2, 0)])}
trakt_fail_times.update({i: s for i, s in enumerate([(3, 0), (6, 0), (12, 0), (24, 0)], len(trakt_fail_times))})
domain_fail_times = {'api.trakt.tv': trakt_fail_times}
default_fail_times = {1: (0, 15), 2: (0, 30), 3: (1, 0), 4: (2, 0), 5: (3, 0), 6: (6, 0), 7: (12, 0), 8: (24, 0)}


class ConnectionFailList(object):
    def __init__(self, url):
        # type: (AnyStr) -> None
        self.url = url
        self._fails = []  # type: List[ConnectionFail]
        self.lock = threading.Lock()
        self.clear_old()
        self.load_list()
        self.last_save = datetime.datetime.now()  # type: datetime.datetime
        self._failure_count = 0  # type: int
        self._failure_time = None  # type: Optional[datetime.datetime]
        self._tmr_limit_count = 0  # type: int
        self._tmr_limit_time = None  # type: Optional[datetime.datetime]
        self._tmr_limit_wait = None  # type: Optional[datetime.timedelta]
        self._last_fail_type = None  # type: Optional[ConnectionFail]
        self.has_limit = False  # type: bool
        self.fail_times = domain_fail_times.get(url, default_fail_times)  # type: Dict[integer_types, Tuple[int, int]]
        self._load_fail_values()
        self.dirty = False  # type: bool

    @property
    def failure_time(self):
        # type: (...) -> Union[None, datetime.datetime]
        return self._failure_time

    @failure_time.setter
    def failure_time(self, value):
        if None is value or isinstance(value, datetime.datetime):
            changed_val = self._failure_time != value
            self._failure_time = value
            if changed_val:
                # noinspection PyCallByClass,PyTypeChecker
                self._save_fail_value('failure_time', (_totimestamp(value), value)[None is value])

    @property
    def tmr_limit_count(self):
        # type: (...) -> int
        return self._tmr_limit_count

    @tmr_limit_count.setter
    def tmr_limit_count(self, value):
        changed_val = self._tmr_limit_count != value
        self._tmr_limit_count = value
        if changed_val:
            self._save_fail_value('tmr_limit_count', value)

    def tmr_limit_update(self, period, unit, desc):
        # type: (Optional[AnyStr], Optional[AnyStr], AnyStr) -> None
        self.tmr_limit_time = datetime.datetime.now()
        self.tmr_limit_count += 1
        limit_set = False
        if None not in (period, unit):
            limit_set = True
            if unit in ('s', 'sec', 'secs', 'seconds', 'second'):
                self.tmr_limit_wait = datetime.timedelta(seconds=try_int(period))
            elif unit in ('m', 'min', 'mins', 'minutes', 'minute'):
                self.tmr_limit_wait = datetime.timedelta(minutes=try_int(period))
            elif unit in ('h', 'hr', 'hrs', 'hours', 'hour'):
                self.tmr_limit_wait = datetime.timedelta(hours=try_int(period))
            elif unit in ('d', 'days', 'day'):
                self.tmr_limit_wait = datetime.timedelta(days=try_int(period))
            else:
                limit_set = False
        if not limit_set:
            time_index = self.fail_time_index(base_limit=0)
            self.tmr_limit_wait = self.wait_time(time_index)
        logger.warning('Request limit reached. Waiting for %s until next retry. Message: %s' %
                       (self.tmr_limit_wait, desc or 'none found'))

    @property
    def tmr_limit_time(self):
        # type: (...) -> Union[None, datetime.datetime]
        return self._tmr_limit_time

    @tmr_limit_time.setter
    def tmr_limit_time(self, value):
        if None is value or isinstance(value, datetime.datetime):
            changed_val = self._tmr_limit_time != value
            self._tmr_limit_time = value
            if changed_val:
                # noinspection PyCallByClass,PyTypeChecker
                self._save_fail_value('tmr_limit_time', (_totimestamp(value), value)[None is value])

    @property
    def last_fail(self):
        # type: (...) -> Optional[int]
        try:
            return sorted(self.fails, key=lambda x: x.fail_time, reverse=True)[0].fail_type
        except (BaseException, Exception):
            pass

    @property
    def failure_count(self):
        # type: (...) -> int
        return self._failure_count

    @failure_count.setter
    def failure_count(self, value):
        changed_val = self._failure_count != value
        self._failure_count = value
        if changed_val:
            self._save_fail_value('failure_count', value)

    def is_waiting(self):
        # type: (...) -> bool
        return self.fail_newest_delta() < self.wait_time()

    @property
    def max_index(self):
        # type: (...) -> int
        return len(self.fail_times)

    @property
    def tmr_limit_wait(self):
        # type: (...) -> Optional[datetime.timedelta]
        return self._tmr_limit_wait

    @tmr_limit_wait.setter
    def tmr_limit_wait(self, value):
        if isinstance(getattr(self, 'fails', None), ConnectionFailList) and isinstance(value, datetime.timedelta):
            self.add_fail(ConnectionFail(fail_type=ConnectionFailTypes.limit))
        changed_val = self._tmr_limit_wait != value
        self._tmr_limit_wait = value
        if changed_val:
            if None is value:
                self._save_fail_value('tmr_limit_wait', value)
            elif isinstance(value, datetime.timedelta):
                self._save_fail_value('tmr_limit_wait', value.total_seconds())

    def fail_time_index(self, base_limit=2):
        # type: (int) -> int
        i = max(self.failure_count - base_limit, 1)
        if i not in self.fail_times:
            i = list(self.fail_times)[-1]
        return (i, self.max_index)[i >= self.max_index]

    def valid_tmr_time(self):
        # type: (...) -> bool
        return isinstance(self.tmr_limit_wait, datetime.timedelta) and \
            isinstance(self.tmr_limit_time, datetime.datetime)

    def wait_time(self, time_index=None):
        # type: (Optional[int]) -> datetime.timedelta
        """
        Return a suitable wait time, selected by parameter, or based on the current failure count

        :param time_index: A key value index into the fail_times dict, or selects using failure count if None
        :return: Time
        """
        if None is time_index:
            time_index = self.fail_time_index()
        return datetime.timedelta(hours=self.fail_times[time_index][0], minutes=self.fail_times[time_index][1])

    def fail_newest_delta(self):
        # type: (...) -> datetime.timedelta
        """
        Return how long since most recent failure
        :return: Period since most recent failure on record
        """
        try:
            return datetime.datetime.now() - self.failure_time
        except (BaseException, Exception):
            return datetime.timedelta(days=1000)

    @property
    def get_next_try_time(self):
        # type: (...) -> datetime.timedelta
        n = None
        h = datetime.timedelta(seconds=0)
        f = datetime.timedelta(seconds=0)
        if self.valid_tmr_time():
            h = self.tmr_limit_time + self.tmr_limit_wait - datetime.datetime.now()
        if 3 <= self.failure_count and isinstance(self.failure_time, datetime.datetime) and self.is_waiting():
            h = self.failure_time + self.wait_time() - datetime.datetime.now()
        if datetime.timedelta(seconds=0) < max((h, f)):
            n = max((h, f))
        return n

    def retry_next(self):
        if self.valid_tmr_time():
            self.tmr_limit_time = datetime.datetime.now() - self.tmr_limit_wait
        if 3 <= self.failure_count and isinstance(self.failure_time, datetime.datetime) and self.is_waiting():
            self.failure_time = datetime.datetime.now() - self.wait_time()

    @staticmethod
    def fmt_delta(delta):
        # type: (Union[datetime.datetime, datetime.timedelta]) -> AnyStr
        return str(delta).rsplit('.')[0]

    def should_skip(self, log_warning=True, use_tmr_limit=True):
        # type: (bool, bool) -> bool
        """
        Determine if a subsequent server request should be skipped.  The result of this logic is based on most recent
        server connection activity including, exhausted request limits, and counting connect failures to determine a
        "cool down" period before recommending reconnection attempts; by returning False.
        :param log_warning: Output to log if True (default) otherwise set False for no output.
        :param use_tmr_limit: Setting this to False will ignore a tmr limit being reached and will instead return False.
        :return: True for any known issue that would prevent a subsequent server connection, otherwise False.
        """
        if self.valid_tmr_time():
            time_left = self.tmr_limit_time + self.tmr_limit_wait - datetime.datetime.now()
            if time_left > datetime.timedelta(seconds=0):
                if log_warning:
                    logger.warning('%sToo many requests reached at %s, waiting for %s' % (
                        self.url, self.fmt_delta(self.tmr_limit_time), self.fmt_delta(time_left)))
                return use_tmr_limit
            else:
                self.tmr_limit_time = None
                self.tmr_limit_wait = None
        if 3 <= self.failure_count:
            if None is self.failure_time:
                self.failure_time = datetime.datetime.now()
            if self.is_waiting():
                if log_warning:
                    time_left = self.wait_time() - self.fail_newest_delta()
                    logger.warning('Failed %s times, skipping domain %s for %s, '
                                   'last failure at %s with fail type: %s' %
                                   (self.failure_count, self.url, self.fmt_delta(time_left),
                                    self.fmt_delta(self.failure_time), ConnectionFailTypes.names.get(
                                       self.last_fail, ConnectionFailTypes.names[ConnectionFailTypes.other])))
                return True
        return False

    @property
    def fails(self):
        # type: (...) -> List
        return self._fails

    @property
    def fails_sorted(self):
        # type: (...) -> List
        fail_dict = {}
        b_d = {'count': 0}
        for e in self._fails:
            fail_date = e.fail_time.date()
            fail_hour = e.fail_time.time().hour
            date_time = datetime.datetime.combine(fail_date, datetime.time(hour=fail_hour))
            if ConnectionFailTypes.names[e.fail_type] not in fail_dict.get(date_time, {}):
                default = {'date': str(fail_date), 'date_time': date_time,
                           'timestamp': try_int(_totimestamp(e.fail_time)), 'multirow': False}
                for et in itervalues(ConnectionFailTypes.names):
                    default[et] = b_d.copy()
                fail_dict.setdefault(date_time, default)[ConnectionFailTypes.names[e.fail_type]]['count'] = 1
            else:
                fail_dict[date_time][ConnectionFailTypes.names[e.fail_type]]['count'] += 1
            if ConnectionFailTypes.http == e.fail_type:
                if e.code in fail_dict[date_time].get(ConnectionFailTypes.names[e.fail_type],
                                                      {'code': {}}).get('code', {}):
                    fail_dict[date_time][ConnectionFailTypes.names[e.fail_type]]['code'][e.code] += 1
                else:
                    fail_dict[date_time][ConnectionFailTypes.names[e.fail_type]].setdefault('code', {})[e.code] = 1

        row_count = {}
        for (k, v) in iteritems(fail_dict):
            row_count.setdefault(v.get('date'), 0)
            if v.get('date') in row_count:
                row_count[v.get('date')] += 1
        for (k, v) in iteritems(fail_dict):
            if 1 < row_count.get(v.get('date')):
                fail_dict[k]['multirow'] = True

        fail_list = sorted([fail_dict[k] for k in iterkeys(fail_dict)], key=lambda y: y.get('date_time'), reverse=True)

        totals = {}
        for fail_date in set([fail.get('date') for fail in fail_list]):
            daytotals = {}
            for et in itervalues(ConnectionFailTypes.names):
                daytotals.update({et: sum([x.get(et).get('count') for x in fail_list if fail_date == x.get('date')])})
            totals.update({fail_date: daytotals})
        for (fail_date, total) in iteritems(totals):
            for i, item in enumerate(fail_list):
                if fail_date == item.get('date'):
                    if item.get('multirow'):
                        fail_list[i:i] = [item.copy()]
                        for et in itervalues(ConnectionFailTypes.names):
                            fail_list[i][et] = {'count': total[et]}
                            if et == ConnectionFailTypes.names[ConnectionFailTypes.http]:
                                fail_list[i][et]['code'] = {}
                    break

        return fail_list

    def add_fail(self,
                 fail  # type: ConnectionFail
                 ):
        if isinstance(fail, ConnectionFail):
            with self.lock:
                self.dirty = True
                self._fails.append(fail)
                logger.debug('Adding fail.%s for %s' % (ConnectionFailTypes.names.get(
                    fail.fail_type, ConnectionFailTypes.names[ConnectionFailTypes.other]), self.url))
            self.save_list()

    def _load_fail_values(self):
        if None is not DATA_DIR:
            my_db = db.DBConnection('cache.db')
            if my_db.hasTable('connection_fails_count'):
                r = my_db.select('SELECT * FROM connection_fails_count WHERE domain_url = ?', [self.url])
                if r:
                    self._failure_count = try_int(r[0]['failure_count'], 0)
                    if r[0]['failure_time']:
                        self._failure_time = datetime.datetime.fromtimestamp(r[0]['failure_time'])
                    else:
                        self._failure_time = None
                    self._tmr_limit_count = try_int(r[0]['tmr_limit_count'], 0)
                    if r[0]['tmr_limit_time']:
                        self._tmr_limit_time = datetime.datetime.fromtimestamp(r[0]['tmr_limit_time'])
                    else:
                        self._tmr_limit_time = None
                    if r[0]['tmr_limit_wait']:
                        self._tmr_limit_wait = datetime.timedelta(seconds=try_int(r[0]['tmr_limit_wait'], 0))
                    else:
                        self._tmr_limit_wait = None
                self._last_fail_type = self.last_fail

    def _save_fail_value(self, field, value):
        my_db = db.DBConnection('cache.db')
        if my_db.hasTable('connection_fails_count'):
            r = my_db.action('UPDATE connection_fails_count SET %s = ? WHERE domain_url = ?' % field,
                             [value, self.url])
            if 0 == r.rowcount:
                my_db.action('REPLACE INTO connection_fails_count (domain_url, %s) VALUES (?,?)' % field,
                             [self.url, value])

    def save_list(self):
        if self.dirty:
            self.clear_old()
            if None is not db:
                with self.lock:
                    try:
                        my_db = db.DBConnection('cache.db')
                        cl = []
                        for f in self._fails:
                            cl.append(['INSERT OR IGNORE INTO connection_fails (domain_url, fail_type, fail_code, '
                                       'fail_time) '
                                       'VALUES (?,?,?,?)', [self.url, f.fail_type, f.code,
                                                            _totimestamp(f.fail_time)]])
                        self.dirty = False
                        if cl:
                            my_db.mass_action(cl)
                    except (BaseException, Exception):
                        pass
            self.last_save = datetime.datetime.now()

    def load_list(self):
        if None is not db:
            with self.lock:
                try:
                    my_db = db.DBConnection('cache.db')
                    if my_db.hasTable('connection_fails'):
                        results = my_db.select('SELECT * FROM connection_fails WHERE domain_url = ?', [self.url])
                        self._fails = []
                        for r in results:
                            try:
                                self._fails.append(ConnectionFail(
                                    fail_type=try_int(r['fail_type']), code=try_int(r['fail_code']),
                                    fail_time=datetime.datetime.fromtimestamp(try_int(r['fail_time']))))
                            except (BaseException, Exception):
                                continue
                except (BaseException, Exception):
                    pass

    def clear_old(self):
        if None is not db:
            with self.lock:
                try:
                    my_db = db.DBConnection('cache.db')
                    if my_db.hasTable('connection_fails'):
                        # noinspection PyCallByClass,PyTypeChecker
                        time_limit = _totimestamp(datetime.datetime.now() - datetime.timedelta(days=28))
                        my_db.action('DELETE FROM connection_fails WHERE fail_time < ?', [time_limit])
                except (BaseException, Exception):
                    pass


def _totimestamp(dt=None):
    # type: (Optional[datetime.datetime]) -> integer_types
    """ This function should only be used in this module due to its 1970s+ limitation as that's all we need here and
    sgdatatime can't be used at this module level
    """
    try:
        if PY2:
            import time
            return int(time.mktime(dt.timetuple()))
        return int(datetime.datetime.timestamp(dt))
    except (BaseException, Exception):
        return 0


def _log_failure_url(url, post_data=None, post_json=None):
    # type: (AnyStr, Optional[AnyStr], Optional[AnyStr]) -> None
    if DOMAIN_FAILURES.should_skip(url, log_warning=False):
        post = []
        if post_data:
            post += [' .. Post params: [%s]' % '&'.join([post_data])]
        if post_json:
            post += [' .. Json params: [%s]' % '&'.join([post_json])]
        logger.warning('Failure URL: %s%s' % (url, ''.join(post)))


# try to convert to int, if the value is not already int
def try_ord(c):
    # type: (Union[int, chr]) -> int
    if isinstance(c, int):
        return c
    return ord(c)


# try to convert to int, if it fails the default will be returned
def try_int(s, s_default=0):
    try:
        return int(s)
    except (BaseException, Exception):
        return s_default


def _maybe_request_url(e, def_url=''):
    return hasattr(e, 'request') and hasattr(e.request, 'url') and ' ' + e.request.url or def_url


def clean_data(data):
    """Cleans up strings, lists, dicts returned

    Issues corrected:
    - Replaces &amp; with &
    - Trailing whitespace
    - Decode html entities
    :param data: data
    :type data: List or Dict or AnyStr
    :return:
    :rtype: List or Dict or AnyStr
    """

    if isinstance(data, list):
        return [clean_data(d) for d in data]
    if isinstance(data, dict):
        return {k: clean_data(v) for k, v in iteritems(data)}
    if isinstance(data, string_types):
        return html_unescape(data).strip().replace(u'&amp;', u'&')
    return data


def get_system_temp_dir():
    """
    :return: Returns the [system temp dir]/tvdb_api-u501 (or tvdb_api-myuser)
    :rtype: AnyStr
    """
    if hasattr(os, 'getuid'):
        uid = 'u%d' % (os.getuid())
    else:
        # For Windows
        try:
            uid = getpass.getuser()
        except ImportError:
            return ek.ek(os.path.join, tempfile.gettempdir(), 'SickGear')

    return ek.ek(os.path.join, tempfile.gettempdir(), 'SickGear-%s' % uid)


def proxy_setting(setting, request_url, force=False):
    """
    Returns a list of a) proxy_setting address value or a PAC is fetched and parsed if proxy_setting
    starts with "PAC:" (case-insensitive) and b) True/False if "PAC" is found in the proxy_setting.

    The PAC data parser is crude, javascript is not eval'd. The first "PROXY URL" found is extracted with a list
    of "url_a_part.url_remaining", "url_b_part.url_remaining", "url_n_part.url_remaining" and so on.
    Also, PAC data items are escaped for matching therefore regular expression items will not match a request_url.

    If force is True or request_url contains a PAC parsed data item then the PAC proxy address is returned else False.
    None is returned in the event of an error fetching PAC data.

    """

    # check for "PAC" usage
    match = re.search(r'^\s*PAC:\s*(.*)', setting, re.I)
    if not match:
        return setting, False
    pac_url = match.group(1)

    # prevent a recursive test with existing proxy setting when fetching PAC url
    global PROXY_SETTING
    proxy_setting_backup = PROXY_SETTING
    PROXY_SETTING = ''

    resp = ''
    try:
        resp = get_url(pac_url)
    except (BaseException, Exception):
        pass
    PROXY_SETTING = proxy_setting_backup

    if not resp:
        return None, False

    proxy_address = None
    request_url_match = False
    parsed_url = urlparse(request_url)
    netloc = parsed_url.netloc
    for pac_data in re.finditer(r"""(?:[^'"]*['"])([^.]+\.[^'"]*)(?:['"])""", resp, re.I):
        data = re.search(r"""PROXY\s+([^'"]+)""", pac_data.group(1), re.I)
        if data:
            if force:
                return data.group(1), True
            # noinspection PyUnresolvedReferences
            proxy_address = (proxy_address, data.group(1))[None is proxy_address]
        elif re.search(re.escape(pac_data.group(1)), netloc, re.I):
            request_url_match = True
            if None is not proxy_address:
                break

    if None is proxy_address:
        return None, True

    return (False, proxy_address)[request_url_match], True


def get_url(url,  # type: AnyStr
            post_data=None,  # type: Optional
            params=None,  # type: Optional
            headers=None,  # type: Optional[Dict]
            timeout=30,  # type: int
            session=None,  # type: Optional[requests.Session]
            parse_json=False,  # type: bool
            memcache_cookies=None,  # type: dict
            raise_status_code=False,  # type: bool
            raise_exceptions=False,  # type: bool
            as_binary=False,  # type: bool
            encoding=None,  # type: Optional[AnyStr]
            failure_monitor=True,  # type: bool
            use_tmr_limit=True,  # type: bool
            raise_skip_exception=False,  # type: bool
            exclude_client_http_codes=True,  # type: bool
            exclude_http_codes=(404, 429),  # type: Tuple[integer_types]
            exclude_no_data=True,  # type: bool
            use_method=None,  # type: Optional[AnyStr]
            return_response=False,  # type: bool
            **kwargs):
    # type: (...) -> Optional[Union[AnyStr, bool, bytes, Dict, Tuple[Union[Dict, List], requests.Session], requests.Response]]
    """
    Return data from a URI with a possible check for authentication prior to the data fetch.
    Raised errors and no data in responses are tracked for making future logic decisions.

    # param url_solver=sickbeard.FLARESOLVERR_HOST must be passed if url is behind CF for use in cf_scrape/__init__.py

    Returned data is either:
    1) a byte-string retrieved from the URL provider.
    2) a boolean if successfully used kwargs 'savefile' set to file pathname.
    3) JSON dict if parse_json is True, and `Requests::session` when kwargs 'resp_sess' True.
    4) `Requests::response`, and `Requests::session` when kwargs 'resp_sess' is True.

    :param url: address to request fetch data from
    :param post_data: if this or `post_json` is set, then request POST method is used to send this data
    :param params:
    :param headers: headers to add
    :param timeout: timeout
    :param session: optional session object
    :param parse_json: return JSON Dict
    :param memcache_cookies: memory persistent store for cookies
    :param raise_status_code: raise exception for status codes
    :param raise_exceptions: raise exceptions
    :param as_binary: return bytes instead of text
    :param encoding: overwrite encoding return header if as_binary is False
    :param failure_monitor: if True, will enable failure monitor for this request
    :param use_tmr_limit: an API limit can be +ve before a fetch, but unwanted, set False to short should_skip
    :param raise_skip_exception: if True, will raise ConnectionSkipException if this request should be skipped
    :param exclude_client_http_codes: if True, exclude client http codes 4XX from failure monitor
    :param exclude_http_codes: http codes to exclude from failure monitor, default: (404, 429)
    :param exclude_no_data: exclude no data as failure
    :param use_method: force any supported method by Session(): get, put, post, delete
    :param return_response: return response object
    :param kwargs: keyword params to passthru to Requests
    :return: None or data fetched from address
    """

    domain = None
    if failure_monitor:
        domain = DOMAIN_FAILURES.get_domain(url)
        if domain not in DOMAIN_FAILURES.domain_list:
            DOMAIN_FAILURES.domain_list[domain] = ConnectionFailList(domain)

        if DOMAIN_FAILURES.should_skip(url, use_tmr_limit=use_tmr_limit):
            if raise_skip_exception:
                raise ConnectionSkipException
            return

    response_attr = ('text', 'content')[as_binary]

    # selectively mute some errors
    mute = filter_list(lambda x: kwargs.pop(x, False), [
        'mute_connect_err', 'mute_read_timeout', 'mute_connect_timeout', 'mute_http_error'])

    # reuse or instantiate request session
    resp_sess = kwargs.pop('resp_sess', None)
    if None is session:
        session = CloudflareScraper.create_scraper()
        session.headers.update({'User-Agent': USER_AGENT})

    proxy_browser = kwargs.get('proxy_browser')
    if isinstance(memcache_cookies, dict):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain in memcache_cookies:
            session.cookies.update(memcache_cookies[domain])

    # download and save file or simply fetch url
    savename = kwargs.pop('savename', None)
    if savename:
        # session streaming
        session.stream = True

    if not kwargs.pop('nocache', False):
        cache_dir = CACHE_DIR or get_system_temp_dir()
        session = CacheControl(sess=session, cache=caches.FileCache(ek.ek(os.path.join, cache_dir, 'sessions')))

    provider = kwargs.pop('provider', None)

    # handle legacy uses of `json` param
    if kwargs.get('json'):
        parse_json = kwargs.pop('json')
    post_json = kwargs.pop('post_json', None)

    # session master headers
    req_headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Accept-Encoding': 'gzip,deflate'}
    if headers:
        req_headers.update(headers)
    if hasattr(session, 'reserved') and 'headers' in session.reserved:
        req_headers.update(session.reserved['headers'] or {})
    session.headers.update(req_headers)

    # session parameters
    session.params = params

    # session ssl verify
    session.verify = False

    # don't trust os environments (auth, proxies, ...)
    session.trust_env = False

    result = response = raised = connection_fail_params = log_failure_url = None
    try:
        # sanitise url
        parsed = list(urlparse(url))
        parsed[2] = re.sub('/{2,}', '/', parsed[2])  # replace two or more / with one
        url = urlunparse(parsed)

        # session proxies
        if PROXY_SETTING:
            (proxy_address, pac_found) = proxy_setting(PROXY_SETTING, url)
            msg = '%sproxy for url: %s' % (('', 'PAC parsed ')[pac_found], url)
            if None is proxy_address:
                logger.debug('Proxy error, aborted the request using %s' % msg)
                return
            elif proxy_address:
                logger.debug('Using %s' % msg)
                session.proxies = {'http': proxy_address, 'https': proxy_address}

        if None is not use_method:

            method = getattr(session, use_method.strip().lower())

        elif post_data or post_json:  # decide if to post data or send a get request to server

            if True is post_data:
                post_data = None

            if post_data:
                kwargs.setdefault('data', post_data)

            if post_json:
                kwargs.setdefault('json', post_json)

            method = session.post
        else:
            method = session.get

        for r in range(0, 5):
            response = method(url, timeout=timeout, **kwargs)
            if response.ok and not response.content:
                if 'url=' in response.headers.get('Refresh', '').lower():
                    url = response.headers.get('Refresh').lower().split('url=')[1].strip('/')
                    if not url.startswith('http'):
                        parsed[2] = '/%s' % url
                        url = urlunparse(parsed)
                    response = session.get(url, timeout=timeout, **kwargs)
                elif 'github' in url:
                    time.sleep(2)
                    continue
            break

        # if encoding is not in header try to use best guess
        # ignore downloads with savename
        if not savename and not as_binary:
            if encoding:
                response.encoding = encoding
            elif not response.encoding or 'charset' not in response.headers.get('Content-Type', ''):
                response.encoding = response.apparent_encoding

        # noinspection PyProtectedMember
        if provider and provider._has_signature(response.text):
            result = getattr(response, response_attr)
        else:
            if raise_status_code:
                response.raise_for_status()

            if not response.ok:
                http_err_text = 'CloudFlare Ray ID' in response.text and \
                                'CloudFlare reports, "Website is offline"; ' or ''
                if response.status_code in http_error_code:
                    http_err_text += http_error_code[response.status_code]
                elif response.status_code in range(520, 527):
                    http_err_text += 'Origin server connection failure'
                else:
                    http_err_text = 'Custom HTTP error code'
                    if 'mute_http_error' not in mute:
                        logger.debug(u'Response not ok. %s: %s from requested url %s'
                                     % (response.status_code, http_err_text, url))

    except requests.exceptions.HTTPError as e:
        raised = e
        is_client_error = 400 <= e.response.status_code < 500
        if failure_monitor and e.response.status_code not in exclude_http_codes and \
                not (exclude_client_http_codes and is_client_error):
            connection_fail_params = dict(fail_type=ConnectionFailTypes.http, code=e.response.status_code)
        if not raise_status_code:
            logger.warning(u'HTTP error %s while loading URL%s' % (e.errno, _maybe_request_url(e)))
    except requests.exceptions.ConnectionError as e:
        raised = e
        if 'mute_connect_err' not in mute:
            logger.warning(u'Connection error msg:%s while loading URL%s' % (ex(e), _maybe_request_url(e)))
        if failure_monitor:
            connection_fail_params = dict(fail_type=ConnectionFailTypes.connection)
    except requests.exceptions.ReadTimeout as e:
        raised = e
        if 'mute_read_timeout' not in mute:
            logger.warning(u'Read timed out msg:%s while loading URL%s' % (ex(e), _maybe_request_url(e)))
        if failure_monitor:
            connection_fail_params = dict(fail_type=ConnectionFailTypes.timeout)
    except (requests.exceptions.Timeout, socket.timeout) as e:
        raised = e
        if 'mute_connect_timeout' not in mute:
            logger.warning(u'Connection timed out msg:%s while loading URL %s' % (ex(e), _maybe_request_url(e, url)))
        if failure_monitor:
            connection_fail_params = dict(fail_type=ConnectionFailTypes.connection_timeout)
    except (BaseException, Exception) as e:
        raised = e
        logger.warning((u'Exception caught while loading URL {0}\r\nDetail... %s\r\n{1}' % ex(e),
                        u'Unknown exception while loading URL {0}\r\nDetail... {1}')[not ex(e)]
                       .format(url, traceback.format_exc()))
        if failure_monitor:
            connection_fail_params = dict(fail_type=ConnectionFailTypes.other)
            log_failure_url = True
    finally:
        if None is not connection_fail_params:
            DOMAIN_FAILURES.inc_failure_count(url, ConnectionFail(**connection_fail_params))
            save_failure(url, domain, log_failure_url, post_data, post_json)

        if isinstance(raised, Exception):
            if raise_exceptions or raise_status_code:
                try:
                    if not hasattr(raised, 'text') and hasattr(response, 'text'):
                        raised.text = response.text
                except (BaseException, Exception):
                    pass
                raise raised
            return

    if return_response:
        result = response
    elif None is result and None is not response and response.ok:
        if isinstance(memcache_cookies, dict):
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            memcache_cookies[domain] = session.cookies.copy()

        if parse_json or proxy_browser:
            try:
                data_json = response.json()
                if proxy_browser:
                    result = ({}, data_json.get('solution', {}).get('response', {}))[isinstance(data_json, dict)]
                else:
                    result = ({}, data_json)[isinstance(data_json, (dict, list))]
                if resp_sess:
                    result = result, session
            except (TypeError, Exception) as e:
                raised = e
                logger.warning(u'%s data issue from URL %s\r\nDetail... %s' % (
                    ('Proxy browser', 'JSON')[parse_json], url, ex(e)))

        elif savename:
            try:
                write_file(savename, response, raw=True, raise_exceptions=raise_exceptions)
                result = True
            except (BaseException, Exception) as e:
                raised = e

        else:
            result = getattr(response, response_attr)
            if resp_sess:
                result = result, session

        if raise_exceptions and isinstance(raised, Exception):
            raise raised

    if failure_monitor:
        if return_response or (result and not isinstance(result, tuple)
                               or isinstance(result, tuple) and result[0]):
            domain = DOMAIN_FAILURES.get_domain(url)
            if 0 != DOMAIN_FAILURES.domain_list[domain].failure_count:
                logger.info('Unblocking: %s' % domain)
            DOMAIN_FAILURES.domain_list[domain].failure_count = 0
            DOMAIN_FAILURES.domain_list[domain].failure_time = None
            save_failure(url, domain, False, post_data, post_json)
        elif not exclude_no_data:
            DOMAIN_FAILURES.inc_failure_count(url, ConnectionFail(fail_type=ConnectionFailTypes.nodata))
            save_failure(url, domain, True, post_data, post_json)

    return result


def save_failure(url, domain, log_failure_url, post_data, post_json):
    DOMAIN_FAILURES.domain_list[domain].save_list()
    if log_failure_url:
        _log_failure_url(url, post_data, post_json)


def file_bit_filter(mode):
    for bit in [stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH, stat.S_ISUID, stat.S_ISGID]:
        if mode & bit:
            mode -= bit

    return mode


def chmod_as_parent(child_path):
    """

    :param child_path: path
    :type child_path: AnyStr
    :return:
    :rtype: None
    """
    if os.name in ('nt', 'ce'):
        return

    parent_path = ek.ek(os.path.dirname, child_path)

    if not parent_path:
        logger.debug(u'No parent path provided in %s, unable to get permissions from it' % child_path)
        return

    parent_path_stat = ek.ek(os.stat, parent_path)
    parent_mode = stat.S_IMODE(parent_path_stat[stat.ST_MODE])

    child_path_stat = ek.ek(os.stat, child_path)
    child_path_mode = stat.S_IMODE(child_path_stat[stat.ST_MODE])

    if ek.ek(os.path.isfile, child_path):
        child_mode = file_bit_filter(parent_mode)
    else:
        child_mode = parent_mode

    if child_path_mode == child_mode:
        return

    child_path_owner = child_path_stat.st_uid
    user_id = os.geteuid()  # only available on UNIX

    if 0 != user_id and user_id != child_path_owner:
        logger.debug(u'Not running as root or owner of %s, not trying to set permissions' % child_path)
        return

    try:
        ek.ek(os.chmod, child_path, child_mode)
        logger.debug(u'Setting permissions for %s to %o as parent directory has %o'
                     % (child_path, child_mode, parent_mode))
    except OSError:
        logger.error(u'Failed to set permission for %s to %o' % (child_path, child_mode))


def make_dirs(path, syno=False):
    """
    Creates any folders that are missing and assigns them the permissions of their
    parents
    :param path: path
    :type path: AnyStr
    :param syno: whether to trigger a syno library update for path
    :type syno: bool
    :return: success
    :rtype: bool
    """
    if not ek.ek(os.path.isdir, path):
        # Windows, create all missing folders
        if os.name in ('nt', 'ce'):
            try:
                logger.debug(u'Path %s doesn\'t exist, creating it' % path)
                ek.ek(os.makedirs, path)
            except (OSError, IOError) as e:
                logger.error(u'Failed creating %s : %s' % (path, ex(e)))
                return False

        # not Windows, create all missing folders and set permissions
        else:
            sofar = ''
            folder_list = path.split(os.path.sep)

            # look through each sub folder and make sure they all exist
            for cur_folder in folder_list:
                sofar += cur_folder + os.path.sep

                # if it exists then just keep walking down the line
                if ek.ek(os.path.isdir, sofar):
                    continue

                try:
                    logger.debug(u'Path %s doesn\'t exist, creating it' % sofar)
                    ek.ek(os.mkdir, sofar)
                    # use normpath to remove end separator, otherwise checks permissions against itself
                    chmod_as_parent(ek.ek(os.path.normpath, sofar))
                    if syno:
                        # do the library update for synoindex
                        NOTIFIERS.NotifierFactory().get('SYNOINDEX').addFolder(sofar)
                except (OSError, IOError) as e:
                    logger.error(u'Failed creating %s : %s' % (sofar, ex(e)))
                    return False

    return True


def fix_set_group_id(child_path):
    """

    :param child_path: path
    :type child_path: AnyStr
    :return:
    :rtype: None
    """
    if os.name in ('nt', 'ce'):
        return

    parent_path = ek.ek(os.path.dirname, child_path)
    parent_stat = ek.ek(os.stat, parent_path)
    parent_mode = stat.S_IMODE(parent_stat[stat.ST_MODE])

    if parent_mode & stat.S_ISGID:
        parent_gid = parent_stat[stat.ST_GID]
        child_stat = ek.ek(os.stat, child_path)
        child_gid = child_stat[stat.ST_GID]

        if child_gid == parent_gid:
            return

        child_path_owner = child_stat.st_uid
        user_id = os.geteuid()  # only available on UNIX

        if 0 != user_id and user_id != child_path_owner:
            logger.debug(u'Not running as root or owner of %s, not trying to set the set-group-id' % child_path)
            return

        try:
            ek.ek(os.chown, child_path, -1, parent_gid)  # only available on UNIX
            logger.debug(u'Respecting the set-group-ID bit on the parent directory for %s' % child_path)
        except OSError:
            logger.error(u'Failed to respect the set-group-id bit on the parent directory for %s (setting group id %i)'
                         % (child_path, parent_gid))


def copy_file(src_file, dest_file):
    if os.name.startswith('posix'):
        ek.ek(subprocess.call, ['cp', src_file, dest_file])
    else:
        ek.ek(shutil.copyfile, src_file, dest_file)

    try:
        ek.ek(shutil.copymode, src_file, dest_file)
    except OSError:
        pass


def move_file(src_file, dest_file, raise_exceptions=False):
    try:
        ek.ek(shutil.move, src_file, dest_file)
        fix_set_group_id(dest_file)
    except OSError:
        copy_file(src_file, dest_file)
        if ek.ek(os.path.exists, dest_file):
            fix_set_group_id(dest_file)
            ek.ek(os.unlink, src_file)
        elif raise_exceptions:
            raise OSError('Destination file could not be created: %s' % dest_file)


def remove_file_perm(filepath, log_err=True):
    # type: (AnyStr, Optional[bool]) -> Optional[bool]
    """
    Remove file

    :param filepath: Path and file name
    :param log_err: False to suppress log msgs
    :return True if filepath does not exist else None if no removal
    """
    if not ek.ek(os.path.exists, filepath):
        return True
    for t in list_range(10):  # total seconds to wait 0 - 9 = 45s over 10 iterations
        try:
            ek.ek(os.remove, filepath)
        except OSError as e:
            if getattr(e, 'winerror', 0) not in (5, 32):  # 5=access denied (e.g. av), 32=another process has lock
                if log_err:
                    logger.warning('Unable to delete %s: %r / %s' % (filepath, e, ex(e)))
                return
        except (BaseException, Exception):
            pass
        time.sleep(t)
        if not ek.ek(os.path.exists, filepath):
            return True
    if log_err:
        logger.warning('Unable to delete %s' % filepath)


def remove_file(filepath, tree=False, prefix_failure='', log_level=logging.INFO):
    """
    Remove file based on setting for trash v permanent delete

    :param filepath: Path and file name
    :type filepath: String
    :param tree: Remove file tree
    :type tree: Bool
    :param prefix_failure: Text to prepend to error log, e.g. show id
    :type prefix_failure: String
    :param log_level: Log level to use for error
    :type log_level: Int
    :return: Type of removal ('Deleted' or 'Trashed') if filepath does not exist or None if no removal occurred
    :rtype: String or None
    """
    result = None
    if filepath:
        for t in list_range(10):  # total seconds to wait 0 - 9 = 45s over 10 iterations
            try:
                result = 'Deleted'
                if TRASH_REMOVE_SHOW:
                    result = 'Trashed'
                    ek.ek(send2trash, filepath)
                elif tree:
                    ek.ek(shutil.rmtree, filepath)
                else:
                    ek.ek(os.remove, filepath)
            except OSError as e:
                if getattr(e, 'winerror', 0) not in (5, 32):  # 5=access denied (e.g. av), 32=another process has lock
                    logger.log(level=log_level, msg=u'%sUnable to %s %s %s: %s' %
                                                    (prefix_failure, ('delete', 'trash')[TRASH_REMOVE_SHOW],
                                                     ('file', 'dir')[tree], filepath, ex(e)))
                    break
            time.sleep(t)
            if not ek.ek(os.path.exists, filepath):
                break

    return (None, result)[filepath and not ek.ek(os.path.exists, filepath)]


def replace_extension(filename, new_ext):
    """

    :param filename: filename
    :type filename: AnyStr
    :param new_ext: new extension
    :type new_ext: AnyStr
    :return: filename with new extension
    :rtype: AnyStr
    """
    sepFile = filename.rpartition('.')
    if sepFile[0] == '':
        return filename
    return sepFile[0] + '.' + new_ext


def write_file(filepath,  # type: AnyStr
               data,  # type: Union[AnyStr, etree.Element, requests.Response]
               raw=False,  # type: bool
               xmltree=False,  # type: bool
               utf8=False,  # type: bool
               raise_exceptions=False  # type: bool
               ):  # type: (...) -> bool
    """

    :param filepath: filepath
    :param data: data to write
    :param raw: write binary or text
    :param xmltree: use xmel tree
    :param utf8: use UTF8
    :param raise_exceptions: raise excepitons
    :return: succuess
    """
    result = False

    if make_dirs(ek.ek(os.path.dirname, filepath)):
        try:
            if raw:
                with ek.ek(io.FileIO, filepath, 'wb') as fh:
                    for chunk in data.iter_content(chunk_size=1024):
                        if chunk:
                            fh.write(chunk)
                            fh.flush()
                    ek.ek(os.fsync, fh.fileno())
            else:
                w_mode = 'w'
                if utf8:
                    w_mode = 'a'
                    with ek.ek(io.FileIO, filepath, 'wb') as fh:
                        fh.write(codecs.BOM_UTF8)

                if xmltree:
                    with ek.ek(io.FileIO, filepath, w_mode) as fh:
                        if utf8:
                            data.write(fh, encoding='utf-8')
                        else:
                            data.write(fh)
                else:
                    if isinstance(data, text_type):
                        with ek.ek(io.open, filepath, w_mode, encoding='utf-8') as fh:
                            fh.write(data)
                    else:
                        with ek.ek(io.FileIO, filepath, w_mode) as fh:
                            fh.write(data)

            chmod_as_parent(filepath)

            result = True
        except (EnvironmentError, IOError) as e:
            logger.error('Unable to write file %s : %s' % (filepath, ex(e)))
            if raise_exceptions:
                raise e

    return result


def long_path(path):
    # type: (AnyStr) -> AnyStr
    """add long path prefix for Windows"""
    if 'nt' == os.name and 260 < len(path) and not path.startswith('\\\\?\\') and ek.ek(os.path.isabs, path):
        return '\\\\?\\' + path
    return path


def md5_for_text(text):
    """

    :param text: test
    :type text: AnyStr
    :return:
    :rtype: AnyStr or None
    """
    result = None
    try:
        md5 = hashlib.md5()
        md5.update(decode_bytes(str(text)))
        raw_md5 = md5.hexdigest()
        result = raw_md5[17:] + raw_md5[9:17] + raw_md5[0:9]
    except (BaseException, Exception):
        pass
    return result


def maybe_plural(subject=1):
    """
    returns 's' or '' depending on numeric subject or length of subject

    :param subject: number or list or dict
    :type subject: int or list or dict
    :return: returns s or ''
    :rtype: AnyStr
    """
    number = subject if not isinstance(subject, (list, dict)) else len(subject)
    return ('s', '')[1 == number]


def time_to_int(dt):
    # type: (Union[datetime.time, None]) -> Optional[integer_types]
    """
    converts datetime.time to integer (hour + minute only)

    :param dt: datetime.time obj
    :return: integer of hour + min
    """
    if None is dt:
        return None
    try:
        return dt.hour * 100 + dt.minute
    except (BaseException, Exception):
        return 0


def int_to_time(d_int):
    # type: (Union[integer_types, None]) -> Optional[datetime.time]
    """
    convert integer from dt_to_int back to datetime.time

    :param d_int: integer
    :return: datetime.time
    """
    if None is d_int:
        return None
    if isinstance(d_int, integer_types):
        try:
            return datetime.time(*divmod(d_int, 100))
        except (BaseException, Exception):
            pass
    return datetime.time(hour=0, minute=0)


def indent_xml(elem, level=0):
    """
    Does our pretty printing, makes Matt very happy
    """
    i = '\n' + level * '  '
    if len(elem):
        if not elem.text or not ('%s' % elem.text).strip():
            elem.text = i + '  '
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent_xml(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        # Strip out the newlines from text
        if elem.text:
            elem.text = ('%s' % elem.text).replace('\n', ' ')
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def compress_file(target, filename, prefer_7z=True, remove_source=True):
    # type: (AnyStr, AnyStr, bool, bool) -> bool
    """
    compress given file to zip or 7z archive

    :param target: file to compress with full path
    :param filename: filename inside the archive
    :param prefer_7z: prefer 7z over zip compression if available
    :param remove_source: remove source file after successful creation of archive
    :return: success of compression
    """
    try:
        if prefer_7z and None is not py7zr:
            z_name = '%s.7z' % target.rpartition('.')[0]
            with py7zr.SevenZipFile(z_name, 'w') as z_file:
                z_file.write(target, filename)
        else:
            zip_name = '%s.zip' % target.rpartition('.')[0]
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zip_fh:
                zip_fh.write(target, filename)
    except (BaseException, Exception) as e:
        logger.error('error compressing %s' % target)
        logger.debug('traceback: %s' % ex(e))
        return False
    if remove_source:
        remove_file_perm(target)
    return True


def scantree(path,  # type: AnyStr
             exclude=None,  # type: Optional[AnyStr, List[AnyStr]]
             include=None,  # type: Optional[AnyStr, List[AnyStr]]
             follow_symlinks=False,  # type: bool
             filter_kind=None,  # type: Optional[bool]
             recurse=True  # type: bool
             ):
    # type: (...) -> Generator[DirEntry, None, None]
    """Yield DirEntry objects for given path. Returns without yield if path fails sanity check

    :param path: Path to scan, sanity check is_dir and exists
    :param exclude: Escaped regex string(s) to exclude
    :param include: Escaped regex string(s) to include
    :param follow_symlinks: Follow symlinks
    :param filter_kind: None to yield everything, True yields directories, False yields files
    :param recurse: Recursively scan the tree
    """
    if isinstance(path, string_types) and path and ek.ek(os.path.isdir, path):
        rc_exc, rc_inc = [re.compile(rx % '|'.join(
            [x for x in (param, ([param], [])[None is param])[not isinstance(param, list)]]))
                          for rx, param in ((r'(?i)^(?:(?!%s).)*$', exclude), (r'(?i)%s', include))]
        for entry in ek.ek(scandir, path):
            is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            is_file = entry.is_file(follow_symlinks=follow_symlinks)
            no_filter = any([None is filter_kind, filter_kind and is_dir, not filter_kind and is_file])
            if (rc_exc.search(entry.name), True)[not exclude] and (rc_inc.search(entry.name), True)[not include] \
                    and (no_filter or (not filter_kind and is_dir and recurse)):
                if recurse and is_dir:
                    for subentry in scantree(entry.path, exclude, include, follow_symlinks, filter_kind, recurse):
                        yield subentry
                if no_filter:
                    yield entry


def cmdline_runner(cmd, shell=False, suppress_stderr=False):
    # type: (Union[AnyStr, List[AnyStr]], bool, bool) -> Tuple[AnyStr, Optional[AnyStr], int]
    """ Execute a child program in a new process.

    Can raise an exception to be caught in callee

    :param cmd: A string, or a sequence of program arguments
    :param shell: If true, the command will be executed through the shell.
    :param suppress_stderr: Suppress stderr output if True
    """
    # noinspection PyUnresolvedReferences
    kw = dict(cwd=PROG_DIR, shell=shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
              stderr=(open(os.devnull, 'w') if PY2 else subprocess.DEVNULL, subprocess.STDOUT)[not suppress_stderr])

    if not PY2:
        kw.update(dict(encoding=ek.SYS_ENCODING, text=True, bufsize=0))

    if 'win32' == sys.platform:
        kw['creationflags'] = 0x08000000   # CREATE_NO_WINDOW (needed for py2exe)

    with Popen(cmd, **kw) as p:
        out, err = p.communicate()
        if out:
            out = out.strip()

        return out, err, p.returncode


def ast_eval(value, default=None):
    # type: (AnyStr, Any) -> Any
    """Convert string typed value into actual Python type and value

    :param value: string value to convert
    :param default: value to return if cannot convert
    :return: converted type and value or default
    """
    if not isinstance(value, string_types):
        return default

    if 'OrderedDict()' == value:
        value = ordered_dict()

    elif 'OrderedDict([(' == value[0:14]:
        try:
            list_of_tuples = ast.literal_eval(value[12:-1])
            value = ordered_dict()
            for cur_tuple in list_of_tuples:
                value[cur_tuple[0]] = cur_tuple[1]
        except (BaseException, Exception):
            value = default

    elif '{' == value[0:1] and '}' == value[-1]:  # this way avoids index out of range with (value = '' and [-1])
        try:
            value = ast.literal_eval(value)
        except (BaseException, Exception):
            value = default

    else:
        value = default

    return value


def sanitize_filename(name):
    """

    :param name: filename
    :type name: AnyStr
    :return: sanitized filename
    :rtype: AnyStr
    """
    # remove bad chars from the filename
    name = re.sub(r'[\\/*]', '-', name)
    name = re.sub(r'[:"<>|?]', '', name)

    # remove leading/trailing periods and spaces
    name = name.strip(' .')

    for char in REMOVE_FILENAME_CHARS or []:
        name = name.replace(char, '')

    return name


def download_file(url, filename, session=None, **kwargs):
    """
    download given url to given filename

    :param url: url to download
    :type url: AnyStr
    :param filename: filename to save the data to
    :type filename: AnyStr
    :param session: optional requests session object
    :type session: requests.Session or None
    :param kwargs:
    :return: success of download
    :rtype: bool
    """
    MEMCACHE.setdefault('cookies', {})
    if None is get_url(url, session=session, savename=filename,
                       url_solver=FLARESOLVERR_HOST, memcache_cookies=MEMCACHE['cookies'],
                       **kwargs):
        remove_file_perm(filename)
        return False
    return True


def calc_age(birthday, deathday=None, date=None):
    # type: (datetime.date, datetime.date, Optional[datetime.date]) -> Optional[int]
    """
    returns age based on current date or given date
    :param birthday: birth date
    :param deathday: death date
    :param date:
    """
    if isinstance(birthday, datetime.date):
        today = (datetime.date.today(), date)[isinstance(date, datetime.date)]
        today = (today, deathday)[isinstance(deathday, datetime.date) and today > deathday]
        try:
            b_d = birthday.replace(year=today.year)

        # raised when birth date is February 29
        # and the current year is not a leap year
        except ValueError:
            b_d = birthday.replace(year=today.year, month=birthday.month + 1, day=1)

        if b_d > today:
            return today.year - birthday.year - 1
        else:
            return today.year - birthday.year


def convert_to_inch_faction_html(height):
    # type: (float) -> AnyStr
    """
    returns html string in foot and inches including fractions
    :param height: height in cm
    """
    total_inches = round(height / float(2.54), 2)
    foot, inches = divmod(total_inches, 12)
    _, fraction = '{0:.2f}'.format(total_inches).split('.')
    fraction = int(fraction)
    # fix rounding errors
    fraction = next((html_convert_fractions.get(fraction + round_error)
                    or html_convert_fractions.get(fraction - round_error)
                    for round_error in moves.xrange(0, 25) if fraction + round_error in html_convert_fractions
                    or fraction - round_error in html_convert_fractions), '')
    if 1 == fraction:
        inches += 1
        fraction = ''
    if 12 <= inches:
        foot += 1
        inches = 0
    inches = str(inches).split('.')[0]
    return '%s\' %s%s%s' % (int(foot), (inches, '')['0' == inches], fraction,
                            ('', '"')['0' != inches or '' != fraction])


def spoken_height(height):
    # type: (float) -> AnyStr
    """
    return text for spoken words of height

    :param height: height in cm
    """
    return convert_to_inch_faction_html(height).replace('\'', ' foot').replace('"', '')


def touch_file(fname, atime=None, dir_name=None):
    """
    set access time of given file

    :param fname: filename
    :type fname: AnyStr
    :param atime: access time as epoch
    :type atime: int
    :param: dir_name: directory name
    :type dir_name: AnyStr
    :return: success
    :rtype: bool
    """
    if None is not dir_name:
        fname = ek.ek(os.path.join, dir_name, fname)
        if make_dirs(dir_name):
            if not ek.ek(os.path.exists, fname):
                with io.open(fname, 'w') as fh:
                    fh.flush()

    if None is not atime:
        try:
            with open(fname, 'a'):
                ek.ek(os.utime, fname, (atime, atime))
            return True
        except (BaseException, Exception):
            logger.debug('File air date stamping not available on your OS')

    return False
