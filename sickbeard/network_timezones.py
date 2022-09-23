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

from itertools import chain
import datetime
import os
import re
import sys
import threading

import sickbeard
from . import db, helpers, logger
from sg_helpers import int_to_time

# noinspection PyPep8Naming
import encodingKludge as ek
from lib.dateutil import tz, zoneinfo
from lib.tzlocal import get_localzone

from sg_helpers import remove_file_perm, scantree
from six import integer_types, iteritems, string_types, PY2
from _23 import list_keys

# noinspection PyUnreachableCode
if False:
    from _23 import DirEntry
    from typing import AnyStr, Optional, Tuple, Union

# regex to parse time (12/24 hour format)
time_regex = re.compile(r'(\d{1,2})(([:.](\d{2}))? ?([PA][. ]? ?M)|[:.](\d{2}))\b', flags=re.I)
am_regex = re.compile(r'(A[. ]? ?M)', flags=re.I)
pm_regex = re.compile(r'(P[. ]? ?M)', flags=re.I)

network_dict = {}
network_dupes = {}
last_failure = {'datetime': datetime.datetime.fromordinal(1), 'count': 0}  # type: dict
max_retry_time = 900
max_retry_count = 3
is_win = 'win32' == sys.platform

country_timezones = {
    'AU': 'Australia/Sydney', 'AR': 'America/Buenos_Aires', 'AUSTRALIA': 'Australia/Sydney', 'BR': 'America/Sao_Paulo',
    'CA': 'Canada/Eastern', 'CZ': 'Europe/Prague', 'DE': 'Europe/Berlin', 'ES': 'Europe/Madrid',
    'FI': 'Europe/Helsinki', 'FR': 'Europe/Paris', 'HK': 'Asia/Hong_Kong', 'IE': 'Europe/Dublin',
    'IS': 'Atlantic/Reykjavik', 'IT': 'Europe/Rome', 'JP': 'Asia/Tokyo', 'MX': 'America/Mexico_City',
    'MY': 'Asia/Kuala_Lumpur', 'NL': 'Europe/Amsterdam', 'NZ': 'Pacific/Auckland', 'PH': 'Asia/Manila',
    'PT': 'Europe/Lisbon', 'RU': 'Europe/Kaliningrad', 'SE': 'Europe/Stockholm', 'SG': 'Asia/Singapore',
    'TW': 'Asia/Taipei', 'UK': 'Europe/London', 'US': 'US/Eastern', 'ZA': 'Africa/Johannesburg'}

EPOCH_START = None  # type: Optional[datetime.datetime]
EPOCH_START_WIN = None  # type: Optional[datetime.datetime]
SG_TIMEZONE = None  # type: Optional[datetime.tzinfo]

network_timezone_lock = threading.Lock()


def reset_last_retry():
    # type: (...) -> None
    global last_failure
    last_failure = {'datetime': datetime.datetime.fromordinal(1), 'count': 0}


def update_last_retry():
    # type: (...) -> None
    global last_failure
    last_failure = {'datetime': datetime.datetime.now(), 'count': last_failure.get('count', 0) + 1}


def should_try_loading():
    # type: (...) -> bool
    global last_failure
    if last_failure.get('count', 0) >= max_retry_count \
            and max_retry_time > (datetime.datetime.now() - last_failure.get(
                'datetime', datetime.datetime.fromordinal(1))).seconds:
        return False
    return True


def tz_fallback(t):
    # type: (...) -> datetime.tzinfo
    if isinstance(t, datetime.tzinfo):
        return t
    if is_win:
        return tz.tzwinlocal()
    return tz.tzlocal()


def get_tz():
    # type: (...) -> datetime.tzinfo
    t = None
    try:
        t = get_localzone()
    except (BaseException, Exception):
        pass
    if isinstance(t, datetime.tzinfo) and hasattr(t, 'zone') and t.zone and hasattr(sickbeard, 'ZONEINFO_DIR'):
        try:
            # noinspection PyUnresolvedReferences
            t = tz_fallback(tz.gettz(t.zone, zoneinfo_priority=True))
        except (BaseException, Exception):
            t = tz_fallback(t)
    else:
        t = tz_fallback(t)
    return t


def get_utc():
    # type: (...) -> Optional[datetime.tzinfo]
    if hasattr(sickbeard, 'ZONEINFO_DIR'):
        utc = None
        try:
            utc = tz.gettz('GMT', zoneinfo_priority=True)
        except (BaseException, Exception):
            pass
        if isinstance(utc, datetime.tzinfo):
            return utc
    tz_utc_file = ek.ek(os.path.join, ek.ek(os.path.dirname, zoneinfo.__file__), 'Greenwich')
    if ek.ek(os.path.isfile, tz_utc_file):
        return tz.tzfile(tz_utc_file)


def set_vars():
    # type: (...) -> None
    global EPOCH_START, EPOCH_START_WIN, SG_TIMEZONE
    SG_TIMEZONE = get_tz()
    params = dict(year=1970, month=1, day=1)
    EPOCH_START_WIN = EPOCH_START = datetime.datetime(tzinfo=get_utc(), **params)
    if is_win:
        try:
            EPOCH_START_WIN = datetime.datetime(tzinfo=tz.win.tzwin('UTC'), **params)
        except (BaseException, Exception):
            pass


set_vars()


def _remove_old_zoneinfo():
    # type: (...) -> None
    """
    helper to remove old unneeded zoneinfo files
    """
    if None is not zoneinfo.ZONEFILENAME:
        current_file = helpers.real_path(
            ek.ek(os.path.join, sickbeard.ZONEINFO_DIR, ek.ek(os.path.basename, zoneinfo.ZONEFILENAME)))
        for entry in chain.from_iterable([scantree(helpers.real_path(_dir), include=r'\.tar\.gz$', filter_kind=False)
                                          for _dir in (sickbeard.ZONEINFO_DIR, )]):  # type: DirEntry
            if current_file != entry.path:
                if remove_file_perm(entry.path, log_err=False):
                    logger.log(u'Delete unneeded old zoneinfo File: %s' % entry.path)
                else:
                    logger.log(u'Unable to delete: %s' % entry.path, logger.ERROR)


def _update_zoneinfo():
    # type: (...) -> None
    """
    update the dateutil zoneinfo
    """
    set_vars()

    # check if the zoneinfo needs update
    url = 'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/zoneinfo.txt'

    url_data = helpers.get_url(url)
    if None is url_data:
        update_last_retry()
        # when None is urlData, trouble connecting to github
        logger.log(u'Fetching zoneinfo.txt failed, this can happen from time to time. Unable to get URL: %s' % url,
                   logger.WARNING)
        return

    reset_last_retry()

    try:
        (new_zoneinfo, zoneinfo_md5) = url_data.strip().rsplit(u' ')
    except (BaseException, Exception):
        logger.log('Fetching zoneinfo.txt failed, update contains unparsable data: %s' % url_data, logger.DEBUG)
        return

    current_file = zoneinfo.ZONEFILENAME
    if None is not current_file:
        current_file = ek.ek(os.path.basename, current_file)
    zonefile = helpers.real_path(ek.ek(os.path.join, sickbeard.ZONEINFO_DIR, current_file))
    zonemetadata = None if not ek.ek(os.path.isfile, zonefile) else \
        zoneinfo.ZoneInfoFile(zoneinfo.getzoneinfofile_stream()).metadata

    newtz_regex = re.search(r'(\d{4}[^.]+)', new_zoneinfo)
    if not newtz_regex or 1 != len(newtz_regex.groups()):
        return
    newtzversion = newtz_regex.group(1)

    if None is not current_file \
            and None is not zonemetadata \
            and 'tzversion' in zonemetadata \
            and zonemetadata['tzversion'] == newtzversion:
        return

    # load the new zoneinfo
    url_tar = u'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/%s' % new_zoneinfo

    zonefile_tmp = re.sub(r'\.tar\.gz$', '.tmp', zonefile)

    if not remove_file_perm(zonefile_tmp, log_err=False):
        logger.log(u'Unable to delete: %s' % zonefile_tmp, logger.ERROR)
        return

    if not helpers.download_file(url_tar, zonefile_tmp):
        return

    if not ek.ek(os.path.exists, zonefile_tmp):
        logger.log(u'Download of %s failed.' % zonefile_tmp, logger.ERROR)
        return

    new_hash = str(helpers.md5_for_file(zonefile_tmp))

    if zoneinfo_md5.upper() == new_hash.upper():
        logger.log(u'Updating timezone info with new one: %s' % new_zoneinfo, logger.MESSAGE)
        try:
            # remove the old zoneinfo file
            if None is not current_file:
                remove_file_perm(zonefile)
            # rename downloaded file
            ek.ek(os.rename, zonefile_tmp, zonefile)
            setattr(zoneinfo, '_CLASS_ZONE_INSTANCE', list())
            tz.gettz.cache_clear()
            from dateutil.zoneinfo import get_zonefile_instance
            try:
                delattr(get_zonefile_instance, '_cached_instance')
            except AttributeError:
                pass

            set_vars()
        except (BaseException, Exception):
            remove_file_perm(zonefile_tmp, log_err=False)
            return
    else:
        remove_file_perm(zonefile_tmp, log_err=False)
        logger.log(u'MD5 hash does not match: %s File: %s' % (zoneinfo_md5.upper(), new_hash.upper()), logger.ERROR)
        return


def update_network_dict():
    # type: (...) -> None
    """
    update the network timezone table
    """
    if not should_try_loading():
        return

    _remove_old_zoneinfo()
    _update_zoneinfo()
    _load_network_conversions()

    network_tz_data = {}

    # network timezones are stored on github pages
    url = 'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/network_timezones.txt'

    url_data = helpers.get_url(url)
    if url_data in (None, ''):
        update_last_retry()
        # When None is urlData, trouble connecting to github
        logger.debug(u'Updating network timezones failed, this can happen from time to time. URL: %s' % url)
        load_network_dict(load=False)
        return

    reset_last_retry()

    try:
        for line in url_data.splitlines():
            try:
                (name, tzone) = line.strip().rsplit(u':', 1)
            except (BaseException, Exception):
                continue
            if None is name or None is tzone:
                continue
            network_tz_data[name] = tzone
    except (IOError, OSError):
        pass

    with network_timezone_lock:
        my_db = db.DBConnection('cache.db')

        # load current network timezones
        sql_result = dict(my_db.select('SELECT * FROM network_timezones'))

        # list of sql commands to update the network_timezones table
        cl = []
        for cur_name, cur_tz in iteritems(network_tz_data):
            network_known = cur_name in sql_result
            if network_known and cur_tz != sql_result[cur_name]:
                # update old record
                cl.append(
                    ['UPDATE network_timezones SET network_name=?, timezone=? WHERE network_name=?',
                     [cur_name, cur_tz, cur_name]])
            elif not network_known:
                # add new record
                cl.append(['REPLACE INTO network_timezones (network_name, timezone) VALUES (?,?)', [cur_name, cur_tz]])
            if network_known:
                del sql_result[cur_name]

        # remove deleted records
        if 0 < len(sql_result):
            network_names = list([network_name for network_name in sql_result])
            cl.append(['DELETE FROM network_timezones WHERE network_name IN (%s)'
                       % ','.join(['?'] * len(network_names)), network_names])

        # change all network timezone infos at once (much faster)
        if 0 < len(cl):
            my_db.mass_action(cl)
            load_network_dict(load=False)


def load_network_dict(load=True):
    # type: (bool) -> None
    """
    load network timezones from db into dict

    :param load: load networks
    """
    global network_dict, network_dupes

    my_db = db.DBConnection('cache.db')
    sql_name = 'REPLACE(LOWER(network_name), " ", "")'
    try:
        sql = 'SELECT %s AS network_name, timezone FROM [network_timezones] ' % sql_name + \
              'GROUP BY %s HAVING COUNT(*) = 1 ORDER BY %s;' % (sql_name, sql_name)
        cur_network_list = my_db.select(sql)
        if load and (None is cur_network_list or 1 > len(cur_network_list)):
            update_network_dict()
            cur_network_list = my_db.select(sql)
        network_dict = dict(cur_network_list)
    except (BaseException, Exception):
        network_dict = {}

    try:

        case_dupes = my_db.select('SELECT * FROM [network_timezones] WHERE %s IN ' % sql_name +
                                  '(SELECT %s FROM [network_timezones]' % sql_name +
                                  ' GROUP BY %s HAVING COUNT(*) > 1)' % sql_name +
                                  ' ORDER BY %s;' % sql_name)
        network_dupes = dict(case_dupes)
    except (BaseException, Exception):
        network_dupes = {}


def get_network_timezone(network, return_name=False):
    # type: (AnyStr, bool) -> Optional[datetime.tzinfo, Tuple[datetime.tzinfo, AnyStr]]
    """
    get timezone of a network or return default timezone

    :param network: network name
    :param return_name: return name
    :return: timezone info or tuple of timezone info, timezone name
    """
    if None is network:
        return SG_TIMEZONE

    timezone = None
    timezone_name = None

    try:
        if None is not zoneinfo.ZONEFILENAME:
            if not network_dict:
                load_network_dict()
            try:
                timezone_name = network_dupes.get(network) or network_dict.get(network.replace(' ', '').lower())
                if isinstance(timezone_name, string_types):
                    timezone = tz.gettz(timezone_name, zoneinfo_priority=True)
            except (BaseException, Exception):
                pass

            if None is timezone:
                cc = re.search(r'\(([a-z]+)\)$', network, flags=re.I)
                try:
                    timezone_name = country_timezones.get(cc.group(1).upper())
                    if isinstance(timezone_name, string_types):
                        timezone = tz.gettz(timezone_name, zoneinfo_priority=True)
                except (BaseException, Exception):
                    pass
    except (BaseException, Exception):
        pass

    if not isinstance(timezone, datetime.tzinfo):
        timezone = SG_TIMEZONE
    if return_name:
        return timezone, timezone_name
    return timezone


def parse_time(time_of_day):
    # type: (AnyStr) -> Tuple[int, int]
    """

    :param time_of_day: time string
    :return: tuple of hour, minute
    """
    time_parsed = time_regex.search(time_of_day)
    hour = mins = 0
    if None is not time_parsed and 5 <= len(time_parsed.groups()):
        if None is not time_parsed.group(5):
            try:
                hour = helpers.try_int(time_parsed.group(1))
                mins = helpers.try_int(time_parsed.group(4))
                ampm = time_parsed.group(5)
                # convert am/pm to 24 hour clock
                if None is not ampm:
                    if None is not pm_regex.search(ampm) and 12 != hour:
                        hour += 12
                    elif None is not am_regex.search(ampm) and 12 == hour:
                        hour -= 12
            except (BaseException, Exception):
                hour = mins = 0
        else:
            try:
                hour = helpers.try_int(time_parsed.group(1))
                mins = helpers.try_int(time_parsed.group(6))
            except (BaseException, Exception):
                hour = mins = 0
    if 0 > hour or 23 < hour or 0 > mins or 59 < mins:
        hour = mins = 0

    return hour, mins


def parse_date_time(date_stamp, time_of_day, network):
    # type: (int, Union[AnyStr or Tuple[int, int]], Union[AnyStr, datetime.tzinfo]) -> datetime.datetime
    """
    parse date and time string into local time

    :param date_stamp: ordinal datetime
    :param time_of_day: time as a string or as a tuple(hr, m)
    :param network: network names
    """
    dt_t = None
    hour = mins = 0
    if isinstance(time_of_day, integer_types):
        dt_t = int_to_time(time_of_day)
    elif isinstance(time_of_day, tuple) and 2 == len(time_of_day) and isinstance(time_of_day[0], int) \
            and isinstance(time_of_day[1], int):
        (hour, mins) = time_of_day
    else:
        (hour, mins) = parse_time(time_of_day)

    dt = datetime.datetime.fromordinal(helpers.try_int(date_stamp))
    try:
        if isinstance(network, datetime.tzinfo):
            foreign_timezone = network
        else:
            foreign_timezone = get_network_timezone(network)
        if None is not dt_t:
            foreign_naive = datetime.datetime.combine(datetime.date(dt.year, dt.month, dt.day),
                                                      dt_t).replace(tzinfo=foreign_timezone)
        else:
            foreign_naive = datetime.datetime(dt.year, dt.month, dt.day, hour, mins, tzinfo=foreign_timezone)
        return foreign_naive
    except (BaseException, Exception):
        if None is dt_t:
            return datetime.datetime(dt.year, dt.month, dt.day, hour, mins, tzinfo=SG_TIMEZONE)
        else:
            return datetime.datetime.combine(datetime.datetime(dt.year, dt.month, dt.day),
                                             dt_t).replace(tzinfo=SG_TIMEZONE)


def test_timeformat(t):
    # type: (AnyStr) -> bool
    """

    :param t: time to check
    :return: is valid timeformat
    """
    time_parsed = time_regex.search(t)
    return not (None is time_parsed or 2 > len(time_parsed.groups()))


def standardize_network(network, country):
    # type: (AnyStr, AnyStr) -> AnyStr
    """

    :param network: network name
    :param country: country name
    :return: network name
    """
    my_db = db.DBConnection('cache.db')
    sql_result = my_db.select('SELECT * FROM network_conversions'
                              ' WHERE tvrage_network = ? AND tvrage_country = ?',
                              [network, country])
    if 1 == len(sql_result):
        return sql_result[0]['tvdb_network']
    return network


def _load_network_conversions():
    # type: (...) -> None

    conversions_in = []

    # network conversions are stored on github pages
    url = 'https://raw.githubusercontent.com/prinz23/sg_network_conversions/master/conversions.txt'

    url_data = helpers.get_url(url)
    if url_data in (None, ''):
        update_last_retry()
        # when no url_data, trouble connecting to github
        logger.debug(u'Updating network conversions failed, this can happen from time to time. URL: %s' % url)
        return

    reset_last_retry()

    try:
        for line in url_data.splitlines():
            (tvdb_network, tvrage_network, tvrage_country) = line.strip().rsplit(u'::', 2)
            if not (tvdb_network and tvrage_network and tvrage_country):
                continue
            conversions_in.append(
                dict(tvdb_network=tvdb_network, tvrage_network=tvrage_network, tvrage_country=tvrage_country))
    except (IOError, OSError):
        pass

    my_db = db.DBConnection('cache.db')

    sql_result = my_db.select('SELECT * FROM network_conversions')
    conversions_db = helpers.build_dict(sql_result, 'tvdb_network')

    # list of sql commands to update the network_conversions table
    cl = []

    for cur_network in conversions_in:
        cl.append([
            'INSERT OR REPLACE INTO network_conversions (tvdb_network, tvrage_network, tvrage_country) VALUES (?,?,?)',
            [cur_network['tvdb_network'], cur_network['tvrage_network'], cur_network['tvrage_country']]])
        try:
            del conversions_db[cur_network['tvdb_network']]
        except (BaseException, Exception):
            pass

    # remove deleted records
    if 0 < len(conversions_db):
        network_name = list_keys(conversions_db)
        cl.append(['DELETE FROM network_conversions WHERE tvdb_network'
                   ' IN (%s)' % ','.join(['?'] * len(network_name)), network_name])

    # change all network conversion info at once (much faster)
    if 0 < len(cl):
        my_db.mass_action(cl)


def get_episode_time(d,  # type: int
                     t,  # type: Union[AnyStr or Tuple[int, int]]
                     show_network,  # type: Optional[AnyStr]
                     show_airtime=None,  # type: Optional[integer_types, datetime.time]
                     show_timezone=None,  # type: Union[AnyStr, datetime.tzinfo]
                     ep_timestamp=None,  # type: Union[integer_types, float]
                     ep_network=None,  # type: Optional[AnyStr]
                     ep_airtime=None,  # type: Optional[integer_types, datetime.time]
                     ep_timezone=None  # type: Union[AnyStr, datetime.tzinfo]
                     ):
    # type: (...) -> datetime.datetime
    """
    parse data and time data into datetime

    :param d: ordinal datetime
    :param t: time as a string or as a tuple(hr, m)
    :param show_network: network names of show
    :param show_airtime: airtime of show as integer or time
    :param show_timezone: timezone of show as string or tzinfo
    :param ep_timestamp: timestamp of episode
    :param ep_network: network name of episode as string
    :param ep_airtime: airtime as integer or time
    :param ep_timezone: timezone of episode as string or tzinfo
    """
    tzinfo = None
    if ep_timezone:
        if isinstance(ep_timezone, datetime.tzinfo):
            tzinfo = ep_timezone
        elif isinstance(ep_timezone, string_types):
            tzinfo = tz.gettz(ep_timezone, zoneinfo_priority=True)
    if not tzinfo:
        if ep_network and isinstance(ep_network, string_types):
            tzinfo = get_network_timezone(ep_network)

        if not tzinfo:
            if show_timezone:
                if isinstance(show_timezone, datetime.tzinfo):
                    tzinfo = show_timezone
                elif isinstance(show_timezone, string_types):
                    tzinfo = tz.gettz(show_timezone, zoneinfo_priority=True)

            if not tzinfo:
                if show_network and isinstance(show_network, string_types):
                    tzinfo = get_network_timezone(show_network)

                if not isinstance(tzinfo, datetime.tzinfo):
                    tzinfo = SG_TIMEZONE

    if isinstance(ep_timestamp, (integer_types, float)):
        from .sgdatetime import SGDatetime
        try:
            return SGDatetime.from_timestamp(ep_timestamp, tzinfo=tzinfo, tz_aware=True, local_time=False)
        except OverflowError:
            logger.debug('Invalid timestamp: %s, using fallback' % ep_timestamp)
            ep_timestamp = None

    ep_time = None
    if isinstance(ep_airtime, integer_types):
        ep_time = int_to_time(ep_airtime)
    elif isinstance(ep_airtime, datetime.time):
        ep_time = ep_airtime

    if None is ep_time and show_airtime:
        if isinstance(show_airtime, integer_types):
            ep_time = int_to_time(show_airtime)
        elif isinstance(show_airtime, datetime.time):
            ep_time = show_airtime

    if None is ep_time:
        if isinstance(t, string_types):
            ep_hr, ep_min = parse_time(t)
            ep_time = datetime.time(ep_hr, ep_min)
        else:
            ep_time = datetime.time(0, 0)

    if d and None is not ep_time and None is not tzinfo:
        ep_date = datetime.date.fromordinal(helpers.try_int(d))
        if PY2:
            return datetime.datetime.combine(ep_date, ep_time).replace(tzinfo=tzinfo)
        return datetime.datetime.combine(ep_date, ep_time, tzinfo)

    return parse_date_time(d, t, tzinfo)
