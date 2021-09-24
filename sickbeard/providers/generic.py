# coding=utf-8
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

from __future__ import with_statement, division

from base64 import b64decode
import codecs
import datetime
import itertools
import math
import os
import re
import time
import threading
import socket
import zlib

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import SickBeardException, AuthException, ex

import sickbeard
from .. import classes, db, helpers, logger, tvcache
from ..classes import NZBSearchResult, TorrentSearchResult, SearchResult
from ..common import Quality, MULTI_EP_RESULT, SEASON_RESULT, USER_AGENT
from ..helpers import maybe_plural, remove_file_perm
from ..name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from ..scene_exceptions import has_season_exceptions
from ..show_name_helpers import get_show_names_all_possible
from ..sgdatetime import SGDatetime, timestamp_near
from ..tv import TVEpisode, TVShow

from cfscrape import CloudflareScraper
from hachoir.parser import guessParser
from hachoir.stream import FileInputStream
from lxml_etree import etree
import requests
import requests.cookies

from _23 import decode_bytes, filter_list, filter_iter, make_btih, map_list, quote, quote_plus, urlparse
from six import iteritems, iterkeys, itervalues, PY2, string_types
from sg_helpers import try_int

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Callable, Dict, List, Match, Optional, Tuple, Union


class HaltParseException(SickBeardException):
    """Something requires the current processing to abort"""


class ProviderFailTypes(object):
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


class ProviderFail(object):
    def __init__(self, fail_type=ProviderFailTypes.other, code=None, fail_time=None):
        self.code = code
        self.fail_type = fail_type
        self.fail_time = (datetime.datetime.now(), fail_time)[isinstance(fail_time, datetime.datetime)]


class ProviderFailList(object):
    def __init__(self, provider_name):
        # type: (Callable[[], AnyStr]) -> None
        self.provider_name = provider_name
        self._fails = []  # type: List[ProviderFail]
        self.lock = threading.Lock()
        self.clear_old()
        self.load_list()
        self.last_save = datetime.datetime.now()  # type: datetime.datetime
        self.dirty = False  # type: bool

    @property
    def fails(self):
        # type: (...) -> List
        return self._fails

    @property
    def fails_sorted(self):
        fail_dict = {}
        b_d = {'count': 0}
        for e in self._fails:
            fail_date = e.fail_time.date()
            fail_hour = e.fail_time.time().hour
            date_time = datetime.datetime.combine(fail_date, datetime.time(hour=fail_hour))
            if ProviderFailTypes.names[e.fail_type] not in fail_dict.get(date_time, {}):
                if isinstance(e.fail_time, datetime.datetime):
                    value = timestamp_near(e.fail_time)
                else:
                    value = SGDatetime.timestamp_far(e.fail_time)
                default = {'date': str(fail_date), 'date_time': date_time,
                           'timestamp': helpers.try_int(value), 'multirow': False}
                for et in itervalues(ProviderFailTypes.names):
                    default[et] = b_d.copy()
                fail_dict.setdefault(date_time, default)[ProviderFailTypes.names[e.fail_type]]['count'] = 1
            else:
                fail_dict[date_time][ProviderFailTypes.names[e.fail_type]]['count'] += 1
            if ProviderFailTypes.http == e.fail_type:
                if e.code in fail_dict[date_time].get(ProviderFailTypes.names[e.fail_type],
                                                      {'code': {}}).get('code', {}):
                    fail_dict[date_time][ProviderFailTypes.names[e.fail_type]]['code'][e.code] += 1
                else:
                    fail_dict[date_time][ProviderFailTypes.names[e.fail_type]].setdefault('code', {})[e.code] = 1

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
            for et in itervalues(ProviderFailTypes.names):
                daytotals.update({et: sum([x.get(et).get('count') for x in fail_list if fail_date == x.get('date')])})
            totals.update({fail_date: daytotals})
        for (fail_date, total) in iteritems(totals):
            for i, item in enumerate(fail_list):
                if fail_date == item.get('date'):
                    if item.get('multirow'):
                        fail_list[i:i] = [item.copy()]
                        for et in itervalues(ProviderFailTypes.names):
                            fail_list[i][et] = {'count': total[et]}
                            if et == ProviderFailTypes.names[ProviderFailTypes.http]:
                                fail_list[i][et]['code'] = {}
                    break

        return fail_list

    def add_fail(self,
                 fail  # type: ProviderFail
                 ):
        if isinstance(fail, ProviderFail):
            with self.lock:
                self.dirty = True
                self._fails.append(fail)
                logger.log('Adding fail.%s for %s' % (ProviderFailTypes.names.get(
                    fail.fail_type, ProviderFailTypes.names[ProviderFailTypes.other]), self.provider_name()),
                           logger.DEBUG)
            self.save_list()

    def save_list(self):
        if self.dirty:
            self.clear_old()
            with self.lock:
                my_db = db.DBConnection('cache.db')
                cl = []
                for f in self._fails:
                    if isinstance(f.fail_time, datetime.datetime):
                        value = int(timestamp_near(f.fail_time))
                    else:
                        value = SGDatetime.timestamp_far(f.fail_time)
                    cl.append(['INSERT OR IGNORE INTO provider_fails (prov_name, fail_type, fail_code, fail_time) '
                               'VALUES (?,?,?,?)', [self.provider_name(), f.fail_type, f.code, value]])
                self.dirty = False
                if cl:
                    my_db.mass_action(cl)
            self.last_save = datetime.datetime.now()

    def load_list(self):
        with self.lock:
            try:
                my_db = db.DBConnection('cache.db')
                if my_db.hasTable('provider_fails'):
                    results = my_db.select('SELECT * FROM provider_fails WHERE prov_name = ?', [self.provider_name()])
                    self._fails = []
                    for r in results:
                        try:
                            self._fails.append(ProviderFail(
                                fail_type=helpers.try_int(r['fail_type']), code=helpers.try_int(r['fail_code']),
                                fail_time=datetime.datetime.fromtimestamp(helpers.try_int(r['fail_time']))))
                        except (BaseException, Exception):
                            continue
            except (BaseException, Exception):
                pass

    def clear_old(self):
        with self.lock:
            try:
                my_db = db.DBConnection('cache.db')
                if my_db.hasTable('provider_fails'):
                    # noinspection PyCallByClass,PyTypeChecker
                    time_limit = int(timestamp_near(datetime.datetime.now() - datetime.timedelta(days=28)))
                    my_db.action('DELETE FROM provider_fails WHERE fail_time < ?', [time_limit])
            except (BaseException, Exception):
                pass


class GenericProvider(object):
    NZB = 'nzb'
    TORRENT = 'torrent'

    def __init__(self, name, supports_backlog=False, anime_only=False):
        # type: (AnyStr, bool, bool) -> None
        """

        :param name: provider name
        :param supports_backlog: supports backlog
        :param anime_only: is anime only
        """
        # these need to be set in the subclass
        self.providerType = None   # type: Optional[GenericProvider.TORRENT, GenericProvider.NZB]
        self.name = name
        self.supports_backlog = supports_backlog
        self.anime_only = anime_only
        if anime_only:
            self.proper_search_terms = 'v1|v2|v3|v4|v5'
        self.url = ''

        self.show_obj = None  # type: Optional[TVShow]

        self.search_mode = None  # type: Optional[AnyStr]
        self.search_fallback = False  # type: bool
        self.enabled = False  # type: bool
        self.enable_recentsearch = False  # type: bool
        self.enable_backlog = False  # type: bool
        self.enable_scheduled_backlog = True  # type: bool
        self.categories = None

        self.cache = tvcache.TVCache(self)

        self.session = CloudflareScraper.create_scraper()

        self.headers = {
            # Using USER_AGENT instead of Mozilla to keep same user agent along authentication and download phases,
            # otherwise session might be broken and download fail, asking again for authentication
            # 'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) ' +
            #              'Chrome/32.0.1700.107 Safari/537.36'}
            'User-Agent': USER_AGENT}

        self._failure_count = 0  # type: int
        self._failure_time = None  # type: Optional[datetime.datetime]
        self.fails = ProviderFailList(self.get_id)
        self._tmr_limit_count = 0  # type: int
        self._tmr_limit_time = None  # type: Optional[datetime.datetime]
        self._tmr_limit_wait = None  # type: Optional[datetime.timedelta]
        self._last_fail_type = None  # type: Optional[ProviderFailTypes]
        self.has_limit = False  # type: bool
        self.fail_times = {1: (0, 15), 2: (0, 30), 3: (1, 0), 4: (2, 0), 5: (3, 0), 6: (6, 0), 7: (12, 0), 8: (24, 0)}
        self._load_fail_values()

        self.scene_only = False  # type: bool
        self.scene_or_contain = ''  # type: AnyStr
        self.scene_loose = False  # type: bool
        self.scene_loose_active = False  # type: bool
        self.scene_rej_nuked = False  # type: bool
        self.scene_nuked_active = False  # type: bool

    def _load_fail_values(self):
        if hasattr(sickbeard, 'DATA_DIR'):
            my_db = db.DBConnection('cache.db')
            if my_db.hasTable('provider_fails_count'):
                r = my_db.select('SELECT * FROM provider_fails_count WHERE prov_name = ?', [self.get_id()])
                if r:
                    self._failure_count = helpers.try_int(r[0]['failure_count'], 0)
                    if r[0]['failure_time']:
                        self._failure_time = datetime.datetime.fromtimestamp(r[0]['failure_time'])
                    else:
                        self._failure_time = None
                    self._tmr_limit_count = helpers.try_int(r[0]['tmr_limit_count'], 0)
                    if r[0]['tmr_limit_time']:
                        self._tmr_limit_time = datetime.datetime.fromtimestamp(r[0]['tmr_limit_time'])
                    else:
                        self._tmr_limit_time = None
                    if r[0]['tmr_limit_wait']:
                        self._tmr_limit_wait = datetime.timedelta(seconds=helpers.try_int(r[0]['tmr_limit_wait'], 0))
                    else:
                        self._tmr_limit_wait = None
                self._last_fail_type = self.last_fail

    def _save_fail_value(self, field, value):
        my_db = db.DBConnection('cache.db')
        if my_db.hasTable('provider_fails_count'):
            r = my_db.action('UPDATE provider_fails_count SET %s = ? WHERE prov_name = ?' % field,
                             [value, self.get_id()])
            if 0 == r.rowcount:
                my_db.action('REPLACE INTO provider_fails_count (prov_name, %s) VALUES (?,?)' % field,
                             [self.get_id(), value])

    @property
    def last_fail(self):
        # type: (...) -> Optional[int]
        try:
            return sorted(self.fails.fails, key=lambda x: x.fail_time, reverse=True)[0].fail_type
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
                if isinstance(value, datetime.datetime):
                    value = int(timestamp_near(value))
                elif value:
                    # noinspection PyCallByClass
                    value = SGDatetime.timestamp_far(value)
                self._save_fail_value('failure_time', value)

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
                if isinstance(value, datetime.datetime):
                    value = int(timestamp_near(value))
                elif value:
                    # noinspection PyCallByClass
                    value = SGDatetime.timestamp_far(value)
                self._save_fail_value('tmr_limit_time', value)

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
        if isinstance(getattr(self, 'fails', None), ProviderFailList) and isinstance(value, datetime.timedelta):
            self.fails.add_fail(ProviderFail(fail_type=ProviderFailTypes.limit))
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

    def tmr_limit_update(self, period, unit, desc):
        # type: (Optional[AnyStr], Optional[AnyStr], AnyStr) -> None
        self.tmr_limit_time = datetime.datetime.now()
        self.tmr_limit_count += 1
        limit_set = False
        if None not in (period, unit):
            limit_set = True
            if unit in ('s', 'sec', 'secs', 'seconds', 'second'):
                self.tmr_limit_wait = datetime.timedelta(seconds=helpers.try_int(period))
            elif unit in ('m', 'min', 'mins', 'minutes', 'minute'):
                self.tmr_limit_wait = datetime.timedelta(minutes=helpers.try_int(period))
            elif unit in ('h', 'hr', 'hrs', 'hours', 'hour'):
                self.tmr_limit_wait = datetime.timedelta(hours=helpers.try_int(period))
            elif unit in ('d', 'days', 'day'):
                self.tmr_limit_wait = datetime.timedelta(days=helpers.try_int(period))
            else:
                limit_set = False
        if not limit_set:
            time_index = self.fail_time_index(base_limit=0)
            self.tmr_limit_wait = self.wait_time(time_index)
        logger.log('Request limit reached. Waiting for %s until next retry. Message: %s' %
                   (self.tmr_limit_wait, desc or 'none found'), logger.WARNING)

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

    def is_waiting(self):
        # type: (...) -> bool
        return self.fail_newest_delta() < self.wait_time()

    def valid_tmr_time(self):
        # type: (...) -> bool
        return isinstance(self.tmr_limit_wait, datetime.timedelta) and \
            isinstance(self.tmr_limit_time, datetime.datetime)

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
                    # Ensure provider name output (e.g. when displaying config/provs) instead of e.g. thread "Tornado"
                    prepend = ('[%s] :: ' % self.name, '')[any([x.name in threading.current_thread().name
                                                                for x in sickbeard.providers.sortedProviderList()])]
                    logger.log('%sToo many requests reached at %s, waiting for %s' % (
                        prepend, self.fmt_delta(self.tmr_limit_time), self.fmt_delta(time_left)), logger.WARNING)
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
                    logger.log('Failed %s times, skipping provider for %s, last failure at %s with fail type: %s' % (
                        self.failure_count, self.fmt_delta(time_left), self.fmt_delta(self.failure_time),
                        ProviderFailTypes.names.get(
                            self.last_fail, ProviderFailTypes.names[ProviderFailTypes.other])), logger.WARNING)
                return True
        return False

    def inc_failure_count(self, *args, **kwargs):
        fail_type = ('fail_type' in kwargs and kwargs['fail_type'].fail_type) or \
                     (isinstance(args, tuple) and isinstance(args[0], ProviderFail) and args[0].fail_type)
        if not isinstance(self.failure_time, datetime.datetime) or \
                fail_type != self._last_fail_type or \
                self.fail_newest_delta() > datetime.timedelta(seconds=3):
            self.failure_count += 1
            self.failure_time = datetime.datetime.now()
            self._last_fail_type = fail_type
            self.fails.add_fail(*args, **kwargs)
        else:
            logger.log('%s: Not logging same failure within 3 seconds' % self.name, logger.DEBUG)

    def get_url(self, url, skip_auth=False, use_tmr_limit=True, *args, **kwargs):
        # type: (AnyStr, bool, bool, Any, Any) -> Optional[AnyStr, Dict]
        """
        Return data from a URI with a possible check for authentication prior to the data fetch.
        Raised errors and no data in responses are tracked for making future logic decisions.

        :param url: Address where to fetch data from
        :param skip_auth: Skip authentication check of provider if True
        :param use_tmr_limit: An API limit can be +ve before a fetch, but unwanted, set False to short should_skip
        :param args: params to pass-through to get_url
        :param kwargs: keyword params to pass-through to get_url
        :return: None or data fetched from URL
        """
        data = None

        # check for auth
        if (not skip_auth and not (self.is_public_access()
                                   and type(self).__name__ not in ['TorrentRssProvider']) and not self._authorised()) \
                or self.should_skip(use_tmr_limit=use_tmr_limit):
            return

        kwargs['raise_exceptions'] = True
        kwargs['raise_status_code'] = True
        kwargs['failure_monitor'] = False
        kwargs['exclude_no_data'] = False
        sickbeard.MEMCACHE.setdefault('cookies', {})
        for k, v in iteritems(dict(
                headers=self.headers, hooks=dict(response=self.cb_response),
                url_solver=sickbeard.FLARESOLVERR_HOST, memcache_cookies=sickbeard.MEMCACHE['cookies'])):
            kwargs.setdefault(k, v)
        if 'nzbs.in' not in url:  # this provider returns 503's 3 out of 4 requests with the persistent session system
            kwargs.setdefault('session', self.session)
        if self.providerType == self.NZB:
            kwargs['timeout'] = 60

        post_data = kwargs.get('post_data')
        post_json = kwargs.get('post_json')

        # noinspection PyUnusedLocal
        log_failure_url = False
        try:
            data = helpers.get_url(url, *args, **kwargs)
            if data and not isinstance(data, tuple) \
                    or isinstance(data, tuple) and data[0]:
                if 0 != self.failure_count:
                    logger.log('Unblocking provider: %s' % self.get_id(), logger.DEBUG)
                self.failure_count = 0
                self.failure_time = None
            else:
                self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.nodata))
                log_failure_url = True
        except requests.exceptions.HTTPError as e:
            if 429 == e.response.status_code:
                r_headers = getattr(e.response, 'headers', {})
                retry_time = None
                unit = None
                if None is not r_headers and 'Retry-After' in r_headers:
                    retry_time = try_int(r_headers.get('Retry-After', 60), 60)
                    unit = 'seconds'
                    retry_time = (retry_time, 60)[0 > retry_time]

                description = r_headers.get('X-nZEDb', '')
                if not retry_time:
                    try:
                        retry_time, unit = re.findall(r'Retry in (\d+)\W+([a-z]+)', description, flags=re.I)[0]
                    except IndexError:
                        retry_time, unit = None, None
                self.tmr_limit_update(retry_time, unit, description)
            else:
                self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.http, code=e.response.status_code))
        except requests.exceptions.ConnectionError:
            self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.connection))
        except requests.exceptions.ReadTimeout:
            self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.timeout))
        except (requests.exceptions.Timeout, socket.timeout):
            self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.connection_timeout))
        except (BaseException, Exception):
            log_failure_url = True
            self.inc_failure_count(ProviderFail(fail_type=ProviderFailTypes.other))

        self.fails.save_list()
        if log_failure_url:
            self.log_failure_url(url, post_data, post_json)
        return data

    def log_failure_url(self, url, post_data=None, post_json=None):
        # type: (AnyStr, Optional[AnyStr], Optional[AnyStr]) -> None
        if self.should_skip(log_warning=False):
            post = []
            if post_data:
                post += [' .. Post params: [%s]' % '&'.join([post_data])]
            if post_json:
                post += [' .. Json params: [%s]' % '&'.join([post_json])]
            logger.log('Failure URL: %s%s' % (url, ''.join(post)), logger.WARNING)

    def get_id(self):
        # type: (...) -> AnyStr
        return GenericProvider.make_id(self.name)

    @staticmethod
    def make_id(name):
        # type: (AnyStr) -> AnyStr
        """
        :param name: name
        :return:
        """
        return re.sub(r'[^\w\d_]', '_', name.strip().lower())

    def image_name(self, *default_name):
        # type: (...) -> AnyStr
        """

        :param default_name:
        :return:
        """
        for name in ['%s.%s' % (self.get_id(), image_ext) for image_ext in ['png', 'gif', 'jpg']]:
            if ek.ek(os.path.isfile,
                     ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', sickbeard.GUI_NAME, 'images', 'providers', name)):
                return name

        return '%s.png' % ('newznab', default_name[0])[any(default_name)]

    def _authorised(self):
        # type: (...) -> bool
        return True

    def _check_auth(self, is_required=None):
        # type: (Optional[bool]) -> bool
        return True

    def is_public_access(self):
        # type: (...) -> bool
        try:
            return bool(re.search('(?i)rarbg|sick|anizb', self.name)) \
                   or False is bool(('_authorised' in self.__class__.__dict__ or hasattr(self, 'digest')
                                     or self._check_auth(is_required=True)))
        except AuthException:
            return False

    def is_active(self):
        # type: (...) -> bool
        if GenericProvider.NZB == self.providerType and sickbeard.USE_NZBS:
            return self.is_enabled()
        elif GenericProvider.TORRENT == self.providerType and sickbeard.USE_TORRENTS:
            return self.is_enabled()
        return False

    def is_enabled(self):
        # type: (...) -> bool
        """
        This should be overridden and should return the config setting eg. sickbeard.MYPROVIDER
        """
        return self.enabled

    def get_result(self, ep_obj_list, url):
        # type: (List[TVEpisode], AnyStr) -> Union[NZBSearchResult, TorrentSearchResult]
        """
        Returns a result of the correct type for this provider

        :param ep_obj_list: TVEpisode object
        :param url:
        :return: SearchResult object
        """

        if GenericProvider.NZB == self.providerType:
            search_result = NZBSearchResult(ep_obj_list)
        elif GenericProvider.TORRENT == self.providerType:
            search_result = TorrentSearchResult(ep_obj_list)
        else:
            search_result = SearchResult(ep_obj_list)

        search_result.provider = self
        search_result.url = url

        return search_result

    # noinspection PyUnusedLocal
    def cb_response(self, r, *args, **kwargs):
        self.session.response = dict(url=r.url, status_code=r.status_code, elapsed=r.elapsed, from_cache=r.from_cache)
        return r

    def download_result(self, result):
        # type: (Union[NZBSearchResult, TorrentSearchResult]) -> Optional[bool]
        """
        Save the result to disk.
        :param result:
        :return:
        """

        # check for auth
        if not self._authorised():
            return False

        if GenericProvider.TORRENT == self.providerType:
            final_dir = sickbeard.TORRENT_DIR
            link_type = 'magnet'
            try:
                btih = None
                try:
                    btih = re.findall(r'urn:btih:([\w]{32,40})', result.url)[0]
                    if 32 == len(btih):
                        btih = make_btih(btih)
                except (BaseException, Exception):
                    pass

                if not btih or not re.search('(?i)[0-9a-f]{32,40}', btih):
                    assert not result.url.startswith('http')
                    logger.log('Unable to extract torrent hash from link: ' + ex(result.url), logger.ERROR)
                    return False

                urls = ['http%s://%s/torrent/%s.torrent' % (u + (btih.upper(),))
                        for u in (('s', 'itorrents.org'), ('s', 'torrage.info'))]
            except (BaseException, Exception):
                link_type = 'torrent'
                urls = [result.url]

        elif GenericProvider.NZB == self.providerType:
            final_dir = sickbeard.NZB_DIR
            link_type = 'nzb'
            urls = [result.url]

        else:
            return

        ref_state = 'Referer' in self.session.headers and self.session.headers['Referer']
        saved = False
        for url in urls:
            cache_dir = sickbeard.CACHE_DIR or helpers.get_system_temp_dir()
            base_name = '%s.%s' % (re.sub('.%s$' % self.providerType, '', helpers.sanitize_filename(result.name)),
                                   self.providerType)
            final_file = ek.ek(os.path.join, final_dir, base_name)
            cached = result.cache_filepath
            if cached and ek.ek(os.path.isfile, cached):
                base_name = ek.ek(os.path.basename, cached)
            cache_file = ek.ek(os.path.join, cache_dir, base_name)

            self.session.headers['Referer'] = url
            if cached or helpers.download_file(url, cache_file, session=self.session, allow_redirects='/it' not in url,
                                               failure_monitor=False):

                if self._verify_download(cache_file):
                    logger.log(u'Downloaded %s result from %s' % (self.name, url))
                    try:
                        helpers.move_file(cache_file, final_file)
                        msg = 'moved'
                    except (OSError, Exception):
                        msg = 'copied cached file'
                    logger.log(u'Saved .%s data and %s to %s' % (
                        (link_type, 'torrent cache')['magnet' == link_type], msg, final_file))
                    saved = True
                    break

                remove_file_perm(cache_file)

        if 'Referer' in self.session.headers:
            if ref_state:
                self.session.headers['Referer'] = ref_state
            else:
                del(self.session.headers['Referer'])

        if not saved and 'magnet' == link_type:
            logger.log(u'All torrent cache servers failed to return a downloadable result', logger.DEBUG)
            final_file = ek.ek(os.path.join, final_dir, '%s.%s' % (helpers.sanitize_filename(result.name), link_type))
            try:
                with open(final_file, 'wb') as fp:
                    fp.write(decode_bytes(result.url))
                    fp.flush()
                    os.fsync(fp.fileno())
                saved = True
                logger.log(u'Saved magnet link to file as some clients (or plugins) support this, %s' % final_file)
                if 'blackhole' == sickbeard.TORRENT_METHOD:
                    logger.log('Tip: If your client fails to load magnet in files, ' +
                               'change blackhole to a client connection method in search settings')
            except (BaseException, Exception):
                logger.log(u'Failed to save magnet link to file, %s' % final_file)
        elif not saved:
            if 'torrent' == link_type and result.provider.get_id() in sickbeard.PROVIDER_HOMES:
                t_result = result  # type: TorrentSearchResult
                # home var url can differ to current url if a url has changed, so exclude both on error
                urls = list(set([sickbeard.PROVIDER_HOMES[result.provider.get_id()][0]]
                                + re.findall('^(https?://[^/]+/)', result.url)
                                + getattr(sickbeard, 'PROVIDER_EXCLUDE', [])))
                # noinspection PyProtectedMember
                chk_url = t_result.provider._valid_home()
                if chk_url not in urls:
                    sickbeard.PROVIDER_HOMES[t_result.provider.get_id()] = ('', None)
                    # noinspection PyProtectedMember
                    t_result.provider._valid_home(url_exclude=urls)
                    setattr(sickbeard, 'PROVIDER_EXCLUDE', ([], urls)[any([t_result.provider.url])])

            logger.log(u'Server failed to return anything useful', logger.ERROR)

        return saved

    def _verify_download(self, file_name=None):
        # type: (Optional[AnyStr]) -> bool
        """
        Checks the saved file to see if it was actually valid, if not then consider the download a failure.
        :param file_name:
        :return:
        """
        result = True
        # primitive verification of torrents, just make sure we didn't get a text file or something
        if GenericProvider.TORRENT == self.providerType:
            parser = stream = None
            try:
                stream = FileInputStream(file_name)
                parser = guessParser(stream)
            except (BaseException, Exception):
                pass
            result = parser and 'application/x-bittorrent' == parser.mime_type

            try:
                # noinspection PyProtectedMember
                stream._input.close()
            except (BaseException, Exception):
                pass

        return result

    def search_rss(self, ep_obj_list):
        # type: (List[TVEpisode]) -> Dict[TVEpisode, SearchResult]
        return self.cache.findNeededEpisodes(ep_obj_list)

    def get_quality(self, item, anime=False):
        # type: (etree.Element, bool) -> int
        """
        Figures out the quality of the given RSS item node

        :param item: An elementtree.ElementTree element representing the <item> tag of the RSS feed
        :param anime:
        :return: a Quality value obtained from the node's data
        """
        (title, url) = self._title_and_url(item)
        quality = Quality.sceneQuality(title, anime)
        return quality

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, age=0, **kwargs):
        return []

    def _season_strings(self, episode):
        return []

    def _episode_strings(self, *args, **kwargs):
        return []

    def _title_and_url(self, item):
        # type: (Union[etree.Element, Dict]) -> Union[Tuple[AnyStr, AnyStr], Tuple[None, None]]
        """
        Retrieves the title and URL data from the item

        :param item: An elementtree.ElementTree element representing the <item> tag of the RSS feed, or a two part tup
        :type item:
        :return: A tuple containing two strings representing title and URL respectively
        :rtype: Tuple[AnyStr, AnyStr] or Tuple[None, None]
        """

        title, url = None, None
        try:
            title, url = isinstance(item, tuple) and (item[0], item[1]) or \
                (item.get('title', None), item.get('link', None))
        except (BaseException, Exception):
            pass

        title = title and re.sub(r'\s+', '.', u'%s' % title)
        if url and not re.match('(?i)magnet:', url):
            url = str(url).replace('&amp;', '&')

        return title, url

    def _link(self, url, url_tmpl=None, url_quote=None):
        url = '%s' % url  # ensure string type
        if url and not re.match('(?i)magnet:', url):
            if PY2:
                try:
                    url = url.encode('utf-8')
                except (BaseException, Exception):
                    pass
            url = url.strip().replace('&amp;', '&')
        if not url:
            url = ''
        # noinspection PyUnresolvedReferences
        return url if re.match('(?i)(https?://|magnet:)', url) \
            else (url_tmpl or self.urls.get('get', (getattr(self, 'url', '') or
                                                    getattr(self, 'url_base')) + '%s')) % (
                not url_quote and url or quote(url)).lstrip('/')

    @staticmethod
    def _header_row(table_row, custom_match=None, custom_tags=None, header_strip=''):
        """
        :param table_row: Soup resultset of table header row
        :param custom_match: Dict key/values to override one or more default regexes
        :param custom_tags: List of tuples with tag and attribute
        :param header_strip: String regex of ambiguities to remove from headers
        :return: dict column indices or None for leech, seeds, and size
        """
        results = {}
        rc = dict([(k, re.compile('(?i)' + r)) for (k, r) in itertools.chain(iteritems(
            {'seed': r'(?:seed|s/l)', 'leech': r'(?:leech|peers)', 'size': r'(?:size)'}),
            iteritems(({}, custom_match)[any([custom_match])]))])
        table = table_row.find_parent('table')
        header_row = table.tr or table.thead.tr or table.tbody.tr
        for y in [x for x in header_row(True) if x.attrs.get('class')]:
            y['class'] = '..'.join(y['class'])
        all_cells = header_row.find_all('th')
        all_cells = all_cells if any(all_cells) else header_row.find_all('td')

        headers = [re.sub(
            r'[\s]+', '',
            ((any([cell.get_text()]) and any([rc[x].search(cell.get_text()) for x in iterkeys(rc)]) and cell.get_text())
             or (cell.attrs.get('id') and any([rc[x].search(cell['id']) for x in iterkeys(rc)]) and cell['id'])
             or (cell.attrs.get('title') and any([rc[x].search(cell['title']) for x in iterkeys(rc)]) and cell['title'])
             or next(iter(set(filter_iter(lambda rz: any([rz]), [
                next(iter(set(filter_iter(lambda ry: any([ry]), [
                    cell.find(tag, **p) for p in [{attr: rc[x]} for x in iterkeys(rc)]]))), {}).get(attr)
                for (tag, attr) in [
                    ('img', 'title'), ('img', 'src'), ('i', 'title'), ('i', 'class'),
                    ('abbr', 'title'), ('a', 'title'), ('a', 'href')] + (custom_tags or [])]))), '')
             or cell.get_text()
             )).strip() for cell in all_cells]
        headers = [re.sub(header_strip, '', x) for x in headers]
        all_headers = headers
        colspans = [int(cell.attrs.get('colspan', 0)) for cell in all_cells]
        if any(colspans):
            all_headers = []
            for i, width in enumerate(colspans):
                all_headers += [headers[i]] + ([''] * (width - 1))

        for k, r in iteritems(rc):
            if k not in results:
                for name in filter_iter(lambda v: any([v]) and r.search(v), all_headers[::-1]):
                    results[k] = all_headers.index(name) - len(all_headers)
                    break

        for missing in set(iterkeys(rc)) - set(iterkeys(results)):
            results[missing] = None

        return results

    @staticmethod
    def _dhtless_magnet(btih, name=None):
        """
        :param btih: torrent hash
        :param name: torrent name
        :return: a magnet loaded with default trackers for clients without enabled DHT or None if bad hash
        """
        try:
            btih = btih.lstrip('/').upper()
            if 32 == len(btih):
                btih = make_btih(btih).lower()
            btih = re.search('(?i)[0-9a-f]{32,40}', btih) and btih or None
        except (BaseException, Exception):
            btih = None
        return (btih and 'magnet:?xt=urn:btih:%s&dn=%s&tr=%s' % (btih, quote_plus(name or btih), '&tr='.join(
            [quote_plus(tr) for tr in (
             'http://atrack.pow7.com/announce', 'http://mgtracker.org:2710/announce',
             'http://pow7.com/announce', 'http://t1.pow7.com/announce',
             'http://tracker.tfile.me/announce', 'udp://9.rarbg.com:2710/announce',
             'udp://9.rarbg.me:2710/announce', 'udp://9.rarbg.to:2710/announce',
             'udp://eddie4.nl:6969/announce', 'udp://explodie.org:6969/announce',
             'udp://inferno.demonoid.pw:3395/announce', 'udp://inferno.subdemon.com:3395/announce',
             'udp://ipv4.tracker.harry.lu:80/announce', 'udp://p4p.arenabg.ch:1337/announce',
             'udp://shadowshq.yi.org:6969/announce', 'udp://tracker.aletorrenty.pl:2710/announce',
             'udp://tracker.coppersurfer.tk:6969', 'udp://tracker.coppersurfer.tk:6969/announce',
             'udp://tracker.internetwarriors.net:1337', 'udp://tracker.internetwarriors.net:1337/announce',
             'udp://tracker.leechers-paradise.org:6969', 'udp://tracker.leechers-paradise.org:6969/announce',
             'udp://tracker.opentrackr.org:1337/announce', 'udp://tracker.torrent.eu.org:451/announce',
             'udp://tracker.trackerfix.com:80/announce', 'udp://tracker.zer0day.to:1337/announce')])) or None)

    def get_show(self, item, **kwargs):
        return None

    def get_size_uid(self, item, **kwargs):
        return -1, None

    def find_search_results(self,
                            show_obj,  # type: TVShow
                            ep_obj_list,  # type: List[TVEpisode]
                            search_mode,  # type: AnyStr
                            manual_search=False,  # type: bool
                            **kwargs
                            ):  # type: (...) -> Union[Dict[TVEpisode, Dict[TVEpisode, SearchResult]], Dict]
        """

        :param show_obj: show object
        :param ep_obj_list: episode list
        :param search_mode: search mode
        :param manual_search: maunal search
        :param kwargs:
        :return:
        """
        self._check_auth()
        self.show_obj = show_obj

        results = {}
        item_list = []
        if self.should_skip():
            return results

        searched_scene_season = None
        search_list = []
        for cur_ep_obj in ep_obj_list:
            # search cache for episode result
            cache_result = self.cache.searchCache(cur_ep_obj, manual_search)  # type: List[SearchResult]
            if cache_result:
                if cur_ep_obj.episode not in results:
                    results[cur_ep_obj.episode] = cache_result
                else:
                    results[cur_ep_obj.episode].extend(cache_result)

                # found result, search next episode
                continue

            if 'sponly' == search_mode:
                # skip if season already searched
                if 1 < len(ep_obj_list) and searched_scene_season == cur_ep_obj.scene_season:
                    continue

                searched_scene_season = cur_ep_obj.scene_season

                # get season search params
                search_params = self._season_strings(cur_ep_obj)
            else:
                # get single episode search params
                search_params = self._episode_strings(cur_ep_obj)

            search_list += [search_params]

        search_done = []
        for search_params in search_list:
            if self.should_skip(log_warning=False):
                break
            for cur_param in search_params:
                if cur_param in search_done:
                    continue
                search_done += [cur_param]
                item_list += self._search_provider(cur_param, search_mode=search_mode, epcount=len(ep_obj_list))
                if self.should_skip():
                    break

        return self.finish_find_search_results(show_obj, ep_obj_list, search_mode, manual_search, results, item_list)

    def finish_find_search_results(self,
                                   show_obj,  # type: TVShow
                                   ep_obj_list,  # type: List[TVEpisode]
                                   search_mode,  # type: AnyStr
                                   manual_search,  # type: bool
                                   results,  # type: Dict[int, Dict[TVEpisode, SearchResult]]
                                   item_list,  # type: List[etree.Element]
                                   **kwargs
                                   ):  # type: (...) -> Union[Dict[TVEpisode, Dict[TVEpisode, SearchResult]], Dict]
        """

        :param show_obj: show object
        :param ep_obj_list: list of episode objects
        :param search_mode: search mode
        :param manual_search: manual search
        :param results: Dict where key episode number, value search result
        :param item_list:
        :param kwargs:
        :return:
        """
        # if we found what we needed already from cache then return results and exit
        if len(results) == len(ep_obj_list):
            return results

        # sort list by quality
        if len(item_list):
            items = {}
            items_unknown = []
            for item in item_list:
                quality = self.get_quality(item, anime=show_obj.is_anime)
                if Quality.UNKNOWN == quality:
                    items_unknown += [item]
                else:
                    if quality not in items:
                        items[quality] = [item]
                    else:
                        items[quality].append(item)

            item_list = list(itertools.chain(*[v for (k, v) in sorted(iteritems(items), reverse=True)]))
            item_list += items_unknown if items_unknown else []

        # filter results
        cl = []
        for item in item_list:
            (title, url) = self._title_and_url(item)

            parser = NameParser(False, show_obj=self.get_show(item, **kwargs), convert=True, indexer_lookup=False)
            # parse the file name
            try:
                parse_result = parser.parse(title, release_group=self.get_id())
            except InvalidNameException:
                logger.log(u'Unable to parse the filename %s into a valid episode' % title, logger.DEBUG)
                continue
            except InvalidShowException:
                logger.log(u'No match for search criteria in the parsed filename ' + title, logger.DEBUG)
                continue

            if parse_result.show_obj.is_anime:
                t_show_obj = helpers.get_show(parse_result.show_obj.name, True)
                post_parser = NameParser(False, show_obj=t_show_obj, convert=True, indexer_lookup=False)
                try:
                    parse_result = post_parser.parse(title, release_group=self.get_id())
                except(BaseException, Exception):
                    continue

            if not (parse_result.show_obj.tvid == show_obj.tvid and parse_result.show_obj.prodid == show_obj.prodid):
                logger.debug(u'Parsed show [%s] is not show [%s] we are searching for' % (
                    parse_result.show_obj.unique_name, show_obj.unique_name))
                continue

            parsed_show_obj = parse_result.show_obj
            quality = parse_result.quality
            release_group = parse_result.release_group
            version = parse_result.version

            add_cache_entry = False
            season_number = -1
            episode_numbers = []
            if not (parsed_show_obj.air_by_date or parsed_show_obj.is_sports):
                if 'sponly' == search_mode:
                    if len(parse_result.episode_numbers):
                        logger.log(u'This is supposed to be a season pack search but the result ' + title +
                                   u' is not a valid season pack, skipping it', logger.DEBUG)
                        add_cache_entry = True
                    if len(parse_result.episode_numbers) \
                            and (parse_result.season_number not in set([ep_obj.season for ep_obj in ep_obj_list])
                                 or not [ep_obj for ep_obj in ep_obj_list
                                         if ep_obj.scene_episode in parse_result.episode_numbers]):
                        logger.log(u'The result ' + title + u' doesn\'t seem to be a valid episode that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True
                else:
                    if not len(parse_result.episode_numbers)\
                            and parse_result.season_number\
                            and not [ep_obj for ep_obj in ep_obj_list
                                     if ep_obj.season == parse_result.season_number and
                                     ep_obj.episode in parse_result.episode_numbers]:
                        logger.log(u'The result ' + title + u' doesn\'t seem to be a valid season that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True
                    elif len(parse_result.episode_numbers) and not [
                        ep_obj for ep_obj in ep_obj_list if ep_obj.season == parse_result.season_number
                            and ep_obj.episode in parse_result.episode_numbers]:
                        logger.log(u'The result ' + title + ' doesn\'t seem to be a valid episode that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True

                if not add_cache_entry:
                    # we just use the existing info for normal searches
                    season_number = parse_result.season_number
                    episode_numbers = parse_result.episode_numbers
            else:
                if not parse_result.is_air_by_date:
                    logger.log(u'This is supposed to be a date search but the result ' + title +
                               u' didn\'t parse as one, skipping it', logger.DEBUG)
                    add_cache_entry = True
                else:
                    season_number = parse_result.season_number
                    episode_numbers = parse_result.episode_numbers

                    if not episode_numbers or \
                            not [ep_obj for ep_obj in ep_obj_list
                                 if ep_obj.season == season_number and ep_obj.episode in episode_numbers]:
                        logger.log(u'The result ' + title + ' doesn\'t seem to be a valid episode that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True

            # add parsed result to cache for usage later on
            if add_cache_entry:
                logger.log(u'Adding item from search to cache: ' + title, logger.DEBUG)
                ci = self.cache.add_cache_entry(title, url, parse_result=parse_result)
                if None is not ci:
                    cl.append(ci)
                continue

            # make sure we want the episode
            want_ep = True
            multi_ep = False
            for epNo in episode_numbers:
                want_ep = parsed_show_obj.want_episode(season_number, epNo, quality, manual_search, multi_ep)
                if not want_ep:
                    break
                # after initial single ep perspective, prepare multi ep for subsequent iterations
                multi_ep = 1 < len(episode_numbers)

            if not want_ep:
                logger.log(u'Ignoring result %s because we don\'t want an episode that is %s'
                           % (title, Quality.qualityStrings[quality]), logger.DEBUG)
                continue

            logger.log(u'Found result %s at %s' % (title, url), logger.DEBUG)

            # make a result object
            ep_obj_results = []  # type: List[TVEpisode]
            for cur_ep_num in episode_numbers:
                ep_obj_results.append(parsed_show_obj.get_episode(season_number, cur_ep_num))

            result = self.get_result(ep_obj_results, url)
            if None is result:
                continue
            result.show_obj = parsed_show_obj
            result.name = title
            result.quality = quality
            result.release_group = release_group
            result.content = None
            result.version = version
            result.size, result.puid = self.get_size_uid(item, **kwargs)
            result.is_repack, result.properlevel = Quality.get_proper_level(parse_result.extra_info_no_name(),
                                                                            parse_result.version,
                                                                            parsed_show_obj.is_anime,
                                                                            check_is_repack=True)

            ep_num = None
            if 1 == len(ep_obj_results):
                ep_num = ep_obj_results[0].episode
                logger.log(u'Single episode result.', logger.DEBUG)
            elif 1 < len(ep_obj_results):
                ep_num = MULTI_EP_RESULT
                logger.log(u'Separating multi-episode result to check for later - result contains episodes: ' +
                           str(parse_result.episode_numbers), logger.DEBUG)
            elif 0 == len(ep_obj_results):
                ep_num = SEASON_RESULT
                logger.log(u'Separating full season result to check for later', logger.DEBUG)

            if ep_num not in results:
                # noinspection PyTypeChecker
                results[ep_num] = [result]
            else:
                # noinspection PyUnresolvedReferences
                results[ep_num].append(result)

        # check if we have items to add to cache
        if 0 < len(cl):
            my_db = self.cache.get_db()
            my_db.mass_action(cl)

        return results

    def find_propers(self, search_date=None, **kwargs):
        # type: (datetime.date, Any) -> List[classes.Proper]
        """

        :param search_date:
        :param kwargs:
        :return:
        """
        results = self.cache.listPropers(search_date)

        return [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show_obj) for x in
                results]

    def seed_ratio(self):
        """
        Provider should override this value if custom seed ratio enabled
        It should return the value of the provider seed ratio
        """
        return ''

    def _log_search(self, mode='Cache', count=0, url='url missing', log_setting_hint=False):
        """
        Simple function to log the result of a search types except propers
        :param count: count of successfully processed items
        :param url: source url of item(s)
        """
        if 'Propers' != mode:
            self.log_result(mode, count, url)

        if log_setting_hint:
            logger.log('Perfomance tip: change "Torrents per Page" to 100 at the site/Settings page')

    def log_result(self, mode='Cache', count=0, url='url missing'):
        """
        Simple function to log the result of any search
        :param mode: string that this log relates to
        :param count: count of successfully processed items
        :param url: source url of item(s)
        """
        stats = map_list(lambda arg: ('_reject_%s' % arg[0], arg[1]),
                         filter_iter(lambda _arg: all([getattr(self, '_reject_%s' % _arg[0], None)]),
                                     (('seed', '%s <min seeders'), ('leech', '%s <min leechers'),
                                      ('notfree', '%s not freeleech'), ('unverified', '%s unverified'),
                                      ('container', '%s unwanted containers'))))
        rejects = ', '.join([(text % getattr(self, attr, '')).strip() for attr, text in stats])
        for (attr, _) in stats:
            setattr(self, attr, None)

        if not self.should_skip():
            str1, thing, str3 = (('', '%s item' % mode.lower(), ''), (' usable', 'proper', ' found'))['Propers' == mode]
            logger.log((u'%s %s in response%s from %s' % (('No' + str1, count)[0 < count], (
                '%s%s%s%s' % (('', 'freeleech ')[getattr(self, 'freeleech', False)], thing, maybe_plural(count), str3)),
                ('', ' (rejects: %s)' % rejects)[bool(rejects)], re.sub(r'(\s)\s+', r'\1', url))).replace('%%', '%'))

    def check_auth_cookie(self):

        if hasattr(self, 'cookies'):
            cookies = self.cookies

            if not (cookies and re.match(r'^(?:\w+=[^;\s]+[;\s]*)+$', cookies)):
                return False, None

            if self.enabled:
                ui_string_method = getattr(self, 'ui_string', None)
                if callable(ui_string_method):
                    pid = self.get_id()
                    # `cookie_str_only` prevents circular call via _valid_home() in ui_string_method
                    key = ('%s_digest' % pid, 'cookie_str_only')[
                        pid in ('ptfiles', 'scenetime', 'torrentday', 'torrentleech')]
                    reqd = 'cf_clearance'
                    if reqd in ui_string_method(key) and reqd not in cookies:
                        return False, \
                               u'%(p)s Cookies setting require %(r)s. If %(r)s not found in browser, log out,' \
                               u' delete site cookies, refresh browser, %(r)s should be created' % \
                               dict(p=self.name, r='\'%s\'' % reqd)

            cj = requests.utils.add_dict_to_cookiejar(self.session.cookies,
                                                      dict([x.strip().split('=', 1) for x in cookies.split(';')
                                                            if '' != x])),
            for item in cj:
                if not isinstance(item, requests.cookies.RequestsCookieJar):
                    return False, None

        return True, None

    def _check_cookie(self):

        success, err_msg = self.check_auth_cookie()
        if success or (not success and err_msg):
            return success, err_msg

        return False, 'Cookies not correctly formatted key=value pairs e.g. uid=xx;pass=yy)'

    def has_all_cookies(self, cookies=None, pre=''):

        cookies = cookies and ([cookies], cookies)[isinstance(cookies, list)] or ['uid', 'pass']
        return all(['%s%s' % (pre, item) in self.session.cookies for item in cookies])

    def _categories_string(self, mode='Cache', template='c%s=1', delimiter='&'):

        return delimiter.join([('%s', template)[any(template)] % c for c in sorted(
            'shows' in self.categories and (isinstance(self.categories['shows'], type([])) and
                                            self.categories['shows'] or [self.categories['shows']]) or
            self.categories[(mode, 'Episode')['Propers' == mode]] +
            ([], self.categories.get('anime') or [])[
                (mode in ['Cache', 'Propers'] and helpers.has_anime()) or
                ((mode in ['Season', 'Episode']) and self.show_obj and self.show_obj.is_anime)])])

    @staticmethod
    def _bytesizer(size_dim=''):

        try:
            value = float('.'.join(re.findall(r'(?i)(\d+)(?:[.,](\d+))?', size_dim)[0]))
        except TypeError:
            return size_dim
        except IndexError:
            return None
        try:
            value *= 1024 ** ['b', 'k', 'm', 'g', 't'].index(re.findall('([tgmk])[i]?b', size_dim.lower())[0])
        except IndexError:
            pass
        return int(math.ceil(value))

    @staticmethod
    def _should_stop():
        # type: (...) -> bool
        if getattr(threading.current_thread(), 'stop', False):
            return True
        return False

    def _sleep_with_stop(self, t):
        t_l = t
        while 0 < t_l:
            time.sleep(3)
            t_l -= 3
            if self._should_stop():
                return


class NZBProvider(GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False):
        # type: (AnyStr, bool, bool) -> None
        """

        :param name: provider name
        :param supports_backlog: supports backlog
        :param anime_only: is anime only
        """
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.NZB
        self.has_limit = True  # type: bool

    def image_name(self):
        # type: (...) -> AnyStr

        return GenericProvider.image_name(self, 'newznab')

    def maybe_apikey(self):
        # type: (...) -> Optional[AnyStr, bool]

        if getattr(self, 'needs_auth', None):
            return (getattr(self, 'key', '') and self.key) or (getattr(self, 'api_key', '') and self.api_key) or None
        return False

    def _check_auth(self, is_required=None):
        # type: (Optional[bool]) -> Union[AnyStr, bool]
        has_key = self.maybe_apikey()
        if has_key:
            return has_key
        if None is has_key:
            raise AuthException('%s for %s is empty in Media Providers/Options'
                                % ('API key' + ('', ' and/or Username')[hasattr(self, 'username')], self.name))

        return GenericProvider._check_auth(self)

    def find_propers(self,
                     search_date=None,  # type: datetime.date
                     shows=None,  # type: Optional[List[Tuple[int, int]]]
                     anime=None,  # type: Optional[List[Tuple[int, int]]]
                     **kwargs
                     ):  # type: (...) -> List[classes.Proper]
        """

        :param search_date:
        :param shows:
        :param anime:
        :param kwargs:
        :return:
        """
        cache_results = self.cache.listPropers(search_date)
        results = [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show_obj)
                   for x in cache_results]

        if self.should_skip():
            return results

        index = 0
        # alt_search = ('nzbs_org' == self.get_id())
        # do_search_alt = False

        search_terms = []
        regex = []
        if shows:
            search_terms += ['.proper.', '.repack.', '.real.']
            regex += ['proper|repack', Quality.real_check]
            proper_check = re.compile(r'(?i)(\b%s\b)' % '|'.join(regex))
        if anime:
            terms = 'v2|v3|v4|v5|v6|v7|v8|v9'
            search_terms += [terms]
            regex += [terms]
            proper_check = re.compile(r'(?i)(%s)' % '|'.join(regex))

        urls = []
        while index < len(search_terms):
            if self.should_skip(log_warning=False):
                break

            search_params = {'q': search_terms[index], 'maxage': sickbeard.BACKLOG_LIMITED_PERIOD + 2}
            # if alt_search:
            #
            #     if do_search_alt:
            #         search_params['t'] = 'search'
            #         index += 1
            #
            #     do_search_alt = not do_search_alt
            #
            # else:
            #     index += 1
            index += 1

            for item in self._search_provider({'Propers': [search_params]}):

                (title, url) = self._title_and_url(item)

                # noinspection PyUnboundLocalVariable
                if not proper_check.search(title) or url in urls:
                    continue
                urls.append(url)

                if 'published_parsed' in item and item['published_parsed']:
                    result_date = item.published_parsed
                    if result_date:
                        result_date = datetime.datetime(*result_date[0:6])
                else:
                    logger.log(u'Unable to figure out the date for entry %s, skipping it' % title)
                    continue

                if not search_date or search_date < result_date:
                    search_result = classes.Proper(title, url, result_date, self.show_obj)
                    results.append(search_result)

            time.sleep(0.5)

        return results

    def cache_data(self, *args, **kwargs):

        search_params = {'Cache': [{}]}
        return self._search_provider(search_params=search_params, **kwargs)


class TorrentProvider(GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False, cache_update_iv=7, update_iv=None):
        # type: (AnyStr, bool, bool, int, Optional[int]) -> None
        """

        :param name: provider name
        :param supports_backlog: supports backlog
        :param anime_only: is anime only
        :param cache_update_iv:
        :param update_iv:
        """
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.TORRENT

        self._seed_ratio = None
        self.seed_time = None
        self._url = None
        self.urls = {}  # type: Dict[AnyStr]
        self.cache._cache_data = self._cache_data
        if cache_update_iv:
            self.cache.update_iv = cache_update_iv
        self.ping_iv = update_iv
        self.ping_skip = None
        self._reject_seed = None
        self._reject_leech = None
        self._reject_unverified = None
        self._reject_notfree = None
        self._reject_container = None
        self._last_recent_search = None
        self.may_filter = dict()

    @property
    def url(self):
        # type: (...) -> AnyStr
        if None is self._url or (hasattr(self, 'url_tmpl') and not self.urls):
            self._url = self._valid_home(False)
            self._valid_url()
        return self._url

    @url.setter
    def url(self, value=None):
        self._url = value

    def _valid_url(self):
        # type: (...) -> bool
        return True

    def image_name(self):
        # type: (...) -> AnyStr
        return GenericProvider.image_name(self, 'torrent')

    def seed_ratio(self):

        return self._seed_ratio

    @staticmethod
    def _sort_seeders(mode, items):
        """ legacy function used by a custom provider, do not remove """
        mode in ['Season', 'Episode'] and items[mode].sort(key=lambda tup: tup[2], reverse=True)

    @staticmethod
    def _sort_seeding(mode, items):

        if mode in ['Season', 'Episode']:
            return sorted(set(items), key=lambda tup: tup[2], reverse=True)
        return items

    def _peers_fail(self, mode, seeders=0, leechers=0):
        """ legacy function used by a custom provider, do not remove """

        return 'Cache' != mode and (seeders < getattr(self, 'minseed', 0) or leechers < getattr(self, 'minleech', 0))

    def _reject_item(self, seeders=0, leechers=0, freeleech=None, verified=None, container=None):
        reject = False
        for condition, attr in filter_iter(lambda arg: all([arg[0]]), (
                (seeders < getattr(self, 'minseed', 0), 'seed'),
                (leechers < getattr(self, 'minleech', 0), 'leech'),
                (all([freeleech]), 'notfree'),
                (all([verified]), 'unverified'),
                (all([container]), 'container'),
        )):
            reject = True
            attr = '_reject_%s' % attr
            rejected = getattr(self, attr, None)
            setattr(self, attr, 1 if not rejected else 1 + rejected)

        return reject

    def get_quality(self, item, anime=False):
        # type: (Union[Tuple, Dict, Any], bool) -> int
        """

        :param item:
        :param anime: is anime
        :return:
        """
        if isinstance(item, tuple):
            name = item[0]
        elif isinstance(item, dict):
            name, url = self._title_and_url(item)
        else:
            # noinspection PyUnresolvedReferences
            name = item.title
        return Quality.sceneQuality(name, anime)

    @staticmethod
    def _reverse_quality(quality):
        # type: (int) -> AnyStr
        """

        :param quality: quality
        :return:
        """
        return {
            Quality.SDTV: 'HDTV x264',
            Quality.SDDVD: 'DVDRIP',
            Quality.HDTV: '720p HDTV x264',
            Quality.FULLHDTV: '1080p HDTV x264',
            Quality.RAWHDTV: '1080i HDTV mpeg2',
            Quality.HDWEBDL: '720p WEB-DL h264',
            Quality.FULLHDWEBDL: '1080p WEB-DL h264',
            Quality.HDBLURAY: '720p Bluray x264',
            Quality.FULLHDBLURAY: '1080p Bluray x264'
        }.get(quality, '')

    def _season_strings(self, ep_obj, detail_only=False, scene=True, prefix='', **kwargs):
        # type: (TVEpisode, bool, bool, AnyStr, Any) -> Union[List[Dict[AnyStr, List[AnyStr]]], List]
        """

        :param ep_obj: episode object
        :param detail_only:
        :param scene:
        :param prefix:
        :param kwargs:
        :return:
        """
        if not ep_obj:
            return []

        show_obj = ep_obj.show_obj
        season = (-1, ep_obj.season)[has_season_exceptions(ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season)]
        ep_dict = self._ep_dict(ep_obj)
        sp_detail = (show_obj.air_by_date or show_obj.is_sports) and str(ep_obj.airdate).split('-')[0] or \
                    (show_obj.is_anime and ep_obj.scene_absolute_number or
                     ('sp_detail' in kwargs and kwargs['sp_detail'](ep_dict)) or 'S%(seasonnumber)02d' % ep_dict)
        sp_detail = ([sp_detail], sp_detail)[isinstance(sp_detail, list)]
        detail = ({}, {'Season_only': sp_detail})[detail_only
                                                  and not self.show_obj.is_sports and not self.show_obj.is_anime]
        return [dict(itertools.chain(iteritems({'Season': self._build_search_strings(sp_detail, scene, prefix,
                                                                                     season=season)}),
                                     iteritems(detail)))]

    def _episode_strings(self,
                         ep_obj,  # type: TVEpisode
                         detail_only=False,  # type: bool
                         scene=True,  # type: bool
                         prefix='',  # type: AnyStr
                         sep_date=' ',  # type: AnyStr
                         date_or=False,  # type: bool
                         **kwargs
                         ):  # type: (...) -> Union[List[Dict[AnyStr, List[Union[AnyStr, Dict]]]], List]
        """

        :param ep_obj: episode object
        :param detail_only:
        :param scene:
        :param prefix:
        :param sep_date:
        :param date_or:
        :param kwargs:
        :return:
        """
        if not ep_obj:
            return []

        show_obj = ep_obj.show_obj
        season = (-1, ep_obj.season)[has_season_exceptions(ep_obj.show_obj.tvid, ep_obj.show_obj.prodid, ep_obj.season)]
        if show_obj.air_by_date or show_obj.is_sports:
            ep_detail = [str(ep_obj.airdate).replace('-', sep_date)]\
                if 'date_detail' not in kwargs else kwargs['date_detail'](ep_obj.airdate)
            if show_obj.is_sports:
                month = ep_obj.airdate.strftime('%b')
                ep_detail = (ep_detail + [month], ['%s|%s' % (x, month) for x in ep_detail])[date_or]
        elif show_obj.is_anime:
            ep_detail = ep_obj.scene_absolute_number \
                if 'ep_detail_anime' not in kwargs else kwargs['ep_detail_anime'](ep_obj.scene_absolute_number)
        else:
            ep_dict = self._ep_dict(ep_obj)
            ep_detail = sickbeard.config.naming_ep_type[2] % ep_dict \
                if 'ep_detail' not in kwargs else kwargs['ep_detail'](ep_dict)
            if sickbeard.scene_exceptions.has_abs_episodes(ep_obj):
                ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)] + ['%d' % ep_dict['episodenumber']]
        ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)]
        detail = ({}, {'Episode_only': ep_detail})[detail_only and not show_obj.is_sports and not show_obj.is_anime]
        return [dict(itertools.chain(iteritems({'Episode': self._build_search_strings(ep_detail, scene, prefix,
                                                                                      season=season)}),
                                     iteritems(detail)))]

    @staticmethod
    def _ep_dict(ep_obj):
        # type: (TVEpisode) -> Dict[AnyStr, int]
        """

        :param ep_obj: episode object
        :return:
        """
        season, episode = ((ep_obj.season, ep_obj.episode),
                           (ep_obj.scene_season, ep_obj.scene_episode))[bool(ep_obj.show_obj.is_scene)]
        return {'seasonnumber': season, 'episodenumber': episode}

    def _build_search_strings(self, ep_detail, process_name=True, prefix='', season=-1):
        # type: (Union[List[AnyStr], AnyStr], bool, AnyStr, int) -> List[AnyStr]
        """
        Build a list of search strings for querying a provider
        :param ep_detail: String of episode detail or List of episode details
        :param process_name: Bool Whether to call sanitize_scene_name() on show name
        :param prefix: String to insert to search strings
        :return: List of search string parameters
        :rtype: List[AnyStr]
        """
        ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)]
        prefix = ([prefix], prefix)[isinstance(prefix, list)]

        search_params = []
        crop = re.compile(r'([.\s])(?:\1)+')
        for name in get_show_names_all_possible(self.show_obj, scenify=process_name and getattr(self, 'scene', True),
                                                season=season):
            for detail in ep_detail:
                search_params += [crop.sub(r'\1', '%s %s%s' % (name, x, detail)) for x in prefix]
        return search_params

    @staticmethod
    def _has_signature(data=None):
        # type: (AnyStr) -> Optional[bool]
        """

        :param data:
        :return:
        """
        return data and re.search(r'(?sim)<input[^<]+?name=["\'\s]*?password', data) and \
            re.search(r'(?sim)<input[^<]+?name=["\'\s]*?username', data)

    def _decode_urls(self, url_exclude=None):
        # type: (Optional[List[AnyStr]]) -> List[AnyStr]
        """

        :param url_exclude:
        :return:
        """
        data_attr = 'PROVIDER_DATA'
        data_refresh = 'PROVIDER_DATA_REFRESH'
        obf = getattr(sickbeard, data_attr, None)
        now = int(time.time())
        data_window = getattr(sickbeard, data_refresh, now - 1)
        if data_window < now:
            setattr(sickbeard, data_refresh, (10*60) + now)
            url = 'https://raw.githubusercontent.com/SickGear/sickgear.extdata/master/SickGear/data.txt'
            obf_new = helpers.get_url(url, parse_json=True) or {}
            if obf_new:
                setattr(sickbeard, data_attr, obf_new)
                obf = obf_new

        urls = []

        seen_attr = 'PROVIDER_SEEN'
        if obf and self.__module__ not in getattr(sickbeard, seen_attr, []):
            file_path = '%s.py' % os.path.join(sickbeard.PROG_DIR, *self.__module__.split('.'))
            if ek.ek(os.path.isfile, file_path):
                with open(file_path, 'rb') as file_hd:
                    c = bytearray(codecs.encode(decode_bytes(str(zlib.crc32(file_hd.read()))), 'hex_codec'))

                for x in obf:
                    if self.__module__.endswith(self._decode(bytearray(b64decode(x)), c)):
                        for ux in obf[x]:
                            urls += [self._decode(bytearray(
                                b64decode(''.join([re.sub(r'[\s%s]+' % ux[0], '', x[::-1]) for x in ux[1:]]))), c)]
                        url_exclude = url_exclude or []
                        if url_exclude:
                            urls = urls[1:]
                        urls = filter_list(lambda u: u not in url_exclude, urls)
                        break
                if not urls:
                    setattr(sickbeard, seen_attr, list(set(getattr(sickbeard, seen_attr, []) + [self.__module__])))

        if not urls:
            urls = filter_list(lambda uh: 'http' in uh, getattr(self, 'url_home', []))

        return urls

    # noinspection DuplicatedCode
    @staticmethod
    def _decode(data, c):
        try:
            fx = (lambda x: x, lambda x: str(x))[PY2]
            result = ''.join(chr(int(fx(bytearray([(8 * c)[i] ^ x for i, x in enumerate(data)])[i:i + 2]), 16))
                             for i in range(0, len(data), 2))
        except (BaseException, Exception):
            result = '|'
        return result

    def _valid_home(self, attempt_fetch=True, url_exclude=None):
        # type: (bool, Union[List[AnyStr], None]) -> Optional[AnyStr]
        """
        :param attempt_fetch:
        :param url_exclude:
        :return: signature verified home url else None if validation fail
        """

        if getattr(self, 'digest', None):
            # noinspection PyUnresolvedReferences
            self.cookies = re.sub(r'(?i)([\s\']+|cookie\s*:)', '', self.digest)
            success, msg = self._check_cookie()
            if not success:
                self.cookies = None
                logger.log(u'%s' % msg, logger.WARNING)
                return

        url_base = getattr(self, 'url_base', None)
        if url_base:
            return url_base

        url_list = self._decode_urls(url_exclude)
        if not url_list and getattr(self, 'url_edit', None) or not any(filter_iter(lambda u: 10 < len(u), url_list)):
            return None

        url_list = map_list(lambda u: '%s/' % u.rstrip('/'), url_list)
        last_url, expire = sickbeard.PROVIDER_HOMES.get(self.get_id(), ('', None))
        url_drop = (url_exclude or []) + getattr(self, 'url_drop', [])
        if url_drop and any([url in last_url for url in url_drop]):  # deprecate url
            last_url = ''

        if 'site down' == last_url:
            if expire and (expire > int(time.time())) or not self.enabled:
                return None
        elif last_url:
            last_url = last_url.replace('getrss.php', '/')  # correct develop typo after a network outage (0.11>0.12)
            last_url in url_list and url_list.remove(last_url)
            url_list.insert(0, last_url)

        if not self.enabled:
            return last_url

        self.failure_count = failure_count = 0
        for cur_url in url_list:
            if not self.is_valid_mod(cur_url):
                return None
            failure_count += self.failure_count
            self.failure_count = 0
            cur_url = cur_url.replace('{ts}', '%s.' % str(time.time())[2:6])
            if 10 < len(cur_url) and ((expire and (expire > int(time.time()))) or
                                      self._has_signature(self.get_url(cur_url, skip_auth=True))):
                for k, v in iteritems(getattr(self, 'url_tmpl', {})):
                    self.urls[k] = v % {'home': cur_url, 'vars': getattr(self, 'url_vars', {}).get(k, '')}

                if last_url != cur_url or (expire and not (expire > int(time.time()))):
                    sickbeard.PROVIDER_HOMES[self.get_id()] = (cur_url, int(time.time()) + (60*60))
                    sickbeard.save_config()
                return cur_url

        seen_attr = 'PROVIDER_SEEN'
        setattr(sickbeard, seen_attr, filter_list(lambda u: self.__module__ not in u,
                                                  getattr(sickbeard, seen_attr, [])))

        self.failure_count = 3 * bool(failure_count)
        if self.should_skip():
            return None

        logger.log('Failed to identify a "%s" page with %s %s (local network issue, site down, or ISP blocked) ' %
                   (self.name, len(url_list), ('URL', 'different URLs')[1 < len(url_list)]) +
                   (attempt_fetch and ('Suggest; 1) Disable "%s" 2) Use a proxy/VPN' % self.get_id()) or ''),
                   (logger.WARNING, logger.ERROR)[self.enabled])
        if not hasattr(self, 'url_api'):
            self.urls = {}
        sickbeard.PROVIDER_HOMES[self.get_id()] = ('site down', int(time.time()) + (5 * 60))
        sickbeard.save_config()
        return None

    def is_valid_mod(self, url):
        # type: (AnyStr) -> bool
        parsed, s, is_valid = urlparse(url), 70000700, True
        if 2012691328 == s + zlib.crc32(decode_bytes(('.%s' % parsed.netloc).split('.')[-2])):
            is_valid = False
            file_name = '%s.py' % os.path.join(sickbeard.PROG_DIR, *self.__module__.split('.'))
            if ek.ek(os.path.isfile, file_name):
                with open(file_name, 'rb') as file_hd:
                    is_valid = s + zlib.crc32(file_hd.read()) in (1661931498, 472149389)
        return is_valid

    def _authorised(self, logged_in=None, post_params=None, failed_msg=None, url=None, timeout=30, **kwargs):

        maxed_out = (lambda y: isinstance(y, string_types) and re.search(
            r'(?i)([1-3]((<[^>]+>)|\W)*(attempts|tries|remain)[\W\w]{,40}?(remain|left|attempt)|last[^<]+?attempt)', y))
        logged_in, failed_msg = [None is not a and a or b for (a, b) in (
            (logged_in, (lambda y=None: self.has_all_cookies())),
            (failed_msg, (lambda y='': maxed_out(y) and u'Urgent abort, running low on login attempts. ' +
                                                        u'Password flushed to prevent service disruption to %s.' or
                          (re.search(r'(?i)(username|password)((<[^>]+>)|\W)*' +
                                     r'(or|and|/|\s)((<[^>]+>)|\W)*(password|incorrect)', y) and
                           u'Invalid username or password for %s. Check settings' or
                           u'Failed to authenticate or parse a response from %s, abort provider')))
        )]

        if logged_in() and (not hasattr(self, 'urls') or bool(len(getattr(self, 'urls')))):
            return True

        if not self._valid_home():
            return False

        if not getattr(self, 'digest', None):
            try:
                if not self._check_auth():
                    return False
            except AuthException as e:
                logger.log('%s' % ex(e), logger.ERROR)
                return False

        if isinstance(url, type([])):
            for i in range(0, len(url)):
                self.get_url(url.pop(), skip_auth=True, **kwargs)
                if self.should_skip():
                    return False

        passfield, userfield = None, None
        post_params = isinstance(post_params, type({})) and post_params or {}
        if not url:
            if hasattr(self, 'urls'):
                url = self.urls.get('login_action')
                if url:
                    response = self.get_url(url, skip_auth=True, **kwargs)
                    if isinstance(response, tuple):
                        response = response[0]
                    if self.should_skip() or None is response:
                        return False
                    try:
                        form = 'form_tmpl' in post_params and post_params.pop('form_tmpl')
                        if form:
                            form = re.findall(
                                '(?is)(<form[^>]+%s.*?</form>)' % (True is form and 'login' or form), response)
                            response = form and form[0] or response

                        action = re.findall('<form[^>]+action=[\'"]([^\'"]*)', response)[0]
                        url = action if action.startswith('http') else \
                            url if not action else \
                            (url + action) if action.startswith('?') else \
                            (self.urls.get('login_base') or self.urls['config_provider_home_uri']) + action.lstrip('/')

                        tags = re.findall(r'(?is)(<input[^>]*?name=[\'"][^\'"]+[^>]*)', response)
                        attrs = [[(re.findall(r'(?is)%s=[\'"]([^\'"]+)' % attr, x) or [''])[0]
                                  for attr in ['type', 'name', 'value']] for x in tags]
                        for itype, name, value in attrs:
                            if 'password' in [itype, name]:
                                passfield = name
                            if name not in ('username', 'password') and 'password' != itype:
                                post_params.setdefault(name, value)
                    except IndexError:
                        return False
                    except KeyError:
                        return super(TorrentProvider, self)._authorised()
                else:
                    url = self.urls.get('login')
            if not url:
                return super(TorrentProvider, self)._authorised()

        if getattr(self, 'username', None) and getattr(self, 'password', None) and post_params.pop('login', True):
            if not post_params:
                # noinspection PyUnresolvedReferences
                post_params = dict(username=self.username, password=self.password)
            elif isinstance(post_params, type({})):
                # noinspection PyUnresolvedReferences
                if self.username not in itervalues(post_params):
                    # noinspection PyUnresolvedReferences
                    post_params['username'] = self.username
                if self.password not in itervalues(post_params):
                    post_params[(passfield, 'password')[not passfield]] = self.password

        # noinspection PyTypeChecker
        response = self.get_url(url, skip_auth=True, post_data=post_params, timeout=timeout, **kwargs)
        session = True
        if isinstance(response, tuple):
            session = response[1]
            response = response[0]
        if not self.should_skip() and response:
            if logged_in(response):
                return session

            if maxed_out(response) and hasattr(self, 'password'):
                self.password = None
                sickbeard.save_config()
            msg = failed_msg(response)
            if msg:
                logger.log(msg % self.name, logger.ERROR)

        return False

    def _check_auth(self, is_required=False):

        if hasattr(self, 'username') and hasattr(self, 'password'):
            if self.username and self.password:
                return True
            setting = 'Password or Username'
        elif hasattr(self, 'username') and hasattr(self, 'api_key'):
            if self.username and self.api_key:
                return True
            setting = 'Api key or Username'
        elif hasattr(self, 'username') and hasattr(self, 'passkey'):
            if self.username and self.passkey:
                return True
            setting = 'Passkey or Username'
        elif hasattr(self, 'uid') and hasattr(self, 'passkey'):
            if self.uid and self.passkey:
                return True
            setting = 'Passkey or uid'
        elif hasattr(self, 'api_key'):
            if self.api_key:
                return True
            setting = 'Api key'
        elif hasattr(self, 'passkey'):
            if self.passkey:
                return True
            setting = 'Passkey'
        else:
            return not is_required and GenericProvider._check_auth(self)

        raise AuthException('%s for %s is empty in Media Providers/Options' % (setting, self.name))

    def find_propers(self, anime=False, **kwargs):
        # type: (bool, Any) -> List[classes.Proper]
        """
        Search for releases of type PROPER

        :param anime:
        :param kwargs:
        :return: list of Proper objects
        """
        results = []
        if self.should_skip():
            return results

        # chance of a v6-v9 is so rare that to do every bl search with each in turn is too aggressive
        search_terms = getattr(self, 'proper_search_terms', ['proper', 'repack', 'real'] +
                               ([], ['v2', 'v3', 'v4', 'v5'])[True is anime])
        if not isinstance(search_terms, list):
            if None is search_terms:
                search_terms = ['proper|repack|real']
                if anime:
                    search_terms += ['v2|v3|v4|v5']
            else:
                search_terms = [search_terms]

        items = self._search_provider({'Propers': search_terms})

        clean_term = re.compile(r'(?i)[^a-z1-9|.]+')
        for proper_term in search_terms:
            if self.should_skip(log_warning=False):
                break

            proper_check = re.compile(r'(?i)(?:%s)' % clean_term.sub('', proper_term))
            for item in items:
                if self.should_skip(log_warning=False):
                    break

                title, url = self._title_and_url(item)
                if proper_check.search(title):
                    results.append(classes.Proper(title, url, datetime.datetime.now(), None))
        return results

    @staticmethod
    def _has_no_results(html):
        # type: (AnyStr) -> Optional[Match[AnyStr]]
        return re.search(r'(?i)<(?:b|div|font|h\d|p|span|strong|td)[^>]*>\s*(?:' +
                         r'your\ssearch.*?did\snot\smatch|' +
                         r'(?:nothing|0</b>\s+torrents)\sfound|' +
                         r'(?:sorry,\s)?no\s(?:results|torrents)\s(found|here|match)|' +
                         r'no\s(?:match|results|torrents)!*|'
                         r'[^<]*?there\sare\sno\sresults|' +
                         r'[^<]*?no\shits\.\sTry\sadding' +
                         ')', html)

    def _cache_data(self, **kwargs):

        return self._search_provider({'Cache': ['']})

    def _ping(self):
        while not self._should_stop():
            if self.ping_skip:
                self.ping_skip -= 1
            else:
                self.ping_skip = ((60*60) // self.ping_iv, None)[self._authorised()]

            self._sleep_with_stop(self.ping_iv)

    def get_result(self, ep_obj_list, url):
        # type: (List[TVEpisode], AnyStr) -> Optional[NZBSearchResult, TorrentSearchResult]
        """
        Returns a result of the correct type for this provider

        :param ep_obj_list: TVEpisode object
        :param url:
        :return: SearchResult object
        """
        search_result = None

        if url:
            search_result = super(TorrentProvider, self).get_result(ep_obj_list, url)
            if hasattr(self, 'get_data'):
                search_result.get_data_func = self.get_data
            if hasattr(self, 'after_get_data'):
                search_result.after_get_data_func = self.after_get_data

        return search_result

    @property
    def last_recent_search(self):
        if not self._last_recent_search:
            try:
                my_db = db.DBConnection('cache.db')
                res = my_db.select('SELECT' + ' "datetime" FROM "lastrecentsearch" WHERE "name"=?', [self.get_id()])
                if res:
                    self._last_recent_search = res[0]['datetime']
            except (BaseException, Exception):
                pass
        return self._last_recent_search

    @last_recent_search.setter
    def last_recent_search(self, value):
        value = 0 if not value else re.sub('^(id-)+', r'\1', 'id-%s' % value)
        try:
            my_db = db.DBConnection('cache.db')
            my_db.action('INSERT OR REPLACE INTO "lastrecentsearch" (name, datetime) VALUES (?,?)',
                         [self.get_id(), value])
        except (BaseException, Exception):
            pass
        self._last_recent_search = value

    def is_search_finished(self, mode, items, cnt_search, rc_dlid, last_recent_search, lrs_rst, lrs_found):
        result = True
        if cnt_search:
            if 'Cache' == mode:
                if last_recent_search and lrs_rst:
                    self.last_recent_search = None

                if not self.last_recent_search:
                    try:
                        self.last_recent_search = helpers.try_int(rc_dlid.findall(items[mode][0][1])[0]) \
                                                  or rc_dlid.findall(items[mode][0][1])[0]
                    except IndexError:
                        self.last_recent_search = last_recent_search

                if last_recent_search and lrs_found:
                    return result
            if cnt_search in (25, 50, 100):
                result = False
        return result
