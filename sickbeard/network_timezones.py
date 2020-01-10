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
from os.path import basename, join, isfile
import datetime
import os
import re

import sickbeard
from . import db, helpers, logger

# noinspection PyPep8Naming
import encodingKludge as ek
from lib.dateutil import tz, zoneinfo
from lib.tzlocal import get_localzone

from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union

# regex to parse time (12/24 hour format)
time_regex = re.compile(r'(\d{1,2})(([:.](\d{2}))? ?([PA][. ]? ?M)|[:.](\d{2}))\b', flags=re.I)
am_regex = re.compile(r'(A[. ]? ?M)', flags=re.I)
pm_regex = re.compile(r'(P[. ]? ?M)', flags=re.I)

network_dict = None
network_dupes = None
last_failure = {'datetime': datetime.datetime.fromordinal(1), 'count': 0}
max_retry_time = 900
max_retry_count = 3

country_timezones = {
    'AU': 'Australia/Sydney', 'AR': 'America/Buenos_Aires', 'AUSTRALIA': 'Australia/Sydney', 'BR': 'America/Sao_Paulo',
    'CA': 'Canada/Eastern', 'CZ': 'Europe/Prague', 'DE': 'Europe/Berlin', 'ES': 'Europe/Madrid',
    'FI': 'Europe/Helsinki', 'FR': 'Europe/Paris', 'HK': 'Asia/Hong_Kong', 'IE': 'Europe/Dublin',
    'IS': 'Atlantic/Reykjavik', 'IT': 'Europe/Rome', 'JP': 'Asia/Tokyo', 'MX': 'America/Mexico_City',
    'MY': 'Asia/Kuala_Lumpur', 'NL': 'Europe/Amsterdam', 'NZ': 'Pacific/Auckland', 'PH': 'Asia/Manila',
    'PT': 'Europe/Lisbon', 'RU': 'Europe/Kaliningrad', 'SE': 'Europe/Stockholm', 'SG': 'Asia/Singapore',
    'TW': 'Asia/Taipei', 'UK': 'Europe/London', 'US': 'US/Eastern', 'ZA': 'Africa/Johannesburg'}


def reset_last_retry():
    global last_failure
    last_failure = {'datetime': datetime.datetime.fromordinal(1), 'count': 0}


def update_last_retry():
    global last_failure
    last_failure = {'datetime': datetime.datetime.now(), 'count': last_failure.get('count', 0) + 1}


def should_try_loading():
    global last_failure
    if last_failure.get('count', 0) >= max_retry_count and \
            (datetime.datetime.now() - last_failure.get('datetime',
                                                        datetime.datetime.fromordinal(1))).seconds < max_retry_time:
        return False
    return True


def tz_fallback(t):
    return t if isinstance(t, datetime.tzinfo) else tz.tzlocal()


def get_tz():
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


sb_timezone = get_tz()


def _remove_zoneinfo_failed(filename):
    # type: (AnyStr) -> None
    """
    helper to remove failed temp download
    """
    try:
        ek.ek(os.remove, filename)
    except (BaseException, Exception):
        pass


def _remove_old_zoneinfo():
    # type: (...) -> None
    """
    helper to remove old unneeded zoneinfo files
    """
    zonefilename = zoneinfo.ZONEFILENAME
    if None is zonefilename:
        return
    cur_zoneinfo = ek.ek(basename, zonefilename)

    cur_file = helpers.real_path(ek.ek(join, sickbeard.ZONEINFO_DIR, cur_zoneinfo))

    for (path, dirs, files) in chain.from_iterable(
            [ek.ek(os.walk, helpers.real_path(_dir))
             for _dir in (sickbeard.ZONEINFO_DIR, ek.ek(os.path.dirname, zoneinfo.__file__))]):
        for filename in files:
            if filename.endswith('.tar.gz'):
                file_w_path = ek.ek(join, path, filename)
                if file_w_path != cur_file and ek.ek(isfile, file_w_path):
                    try:
                        ek.ek(os.remove, file_w_path)
                        logger.log(u'Delete unneeded old zoneinfo File: %s' % file_w_path)
                    except (BaseException, Exception):
                        logger.log(u'Unable to delete: %s' % file_w_path, logger.ERROR)


def _update_zoneinfo():
    # type: (...) -> None
    """
    update the dateutil zoneinfo
    """
    if not should_try_loading():
        return

    global sb_timezone
    sb_timezone = get_tz()

    # now check if the zoneinfo needs update
    url_zv = 'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/zoneinfo.txt'

    url_data = helpers.get_url(url_zv)
    if None is url_data:
        update_last_retry()
        # When None is urlData, trouble connecting to github
        logger.log(u'Loading zoneinfo.txt failed, this can happen from time to time. Unable to get URL: %s' % url_zv,
                   logger.WARNING)
        return
    else:
        reset_last_retry()

    zonefilename = zoneinfo.ZONEFILENAME
    cur_zoneinfo = zonefilename
    if None is not cur_zoneinfo:
        cur_zoneinfo = ek.ek(basename, zonefilename)
    zonefile = helpers.real_path(ek.ek(join, sickbeard.ZONEINFO_DIR, cur_zoneinfo))
    zonemetadata = None if not ek.ek(os.path.isfile, zonefile) else \
        zoneinfo.ZoneInfoFile(zoneinfo.getzoneinfofile_stream()).metadata
    (new_zoneinfo, zoneinfo_md5) = url_data.strip().rsplit(u' ')
    newtz_regex = re.search(r'(\d{4}[^.]+)', new_zoneinfo)
    if not newtz_regex or 1 != len(newtz_regex.groups()):
        return
    newtzversion = newtz_regex.group(1)

    if None is not cur_zoneinfo \
            and None is not zonemetadata \
            and 'tzversion' in zonemetadata \
            and zonemetadata['tzversion'] == newtzversion:
        return

    # now load the new zoneinfo
    url_tar = u'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/%s' % new_zoneinfo

    zonefile_tmp = re.sub(r'\.tar\.gz$', '.tmp', zonefile)

    if ek.ek(os.path.exists, zonefile_tmp):
        try:
            ek.ek(os.remove, zonefile_tmp)
        except (BaseException, Exception):
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
            if None is not cur_zoneinfo:
                old_file = helpers.real_path(
                    ek.ek(os.path.join, sickbeard.ZONEINFO_DIR, cur_zoneinfo))
                if ek.ek(os.path.exists, old_file):
                    ek.ek(os.remove, old_file)
            # rename downloaded file
            ek.ek(os.rename, zonefile_tmp, zonefile)
            setattr(zoneinfo, '_CLASS_ZONE_INSTANCE', list())
            tz.gettz.cache_clear()
            from dateutil.zoneinfo import get_zonefile_instance
            try:
                delattr(get_zonefile_instance, '_cached_instance')
            except AttributeError:
                pass

            sb_timezone = get_tz()
        except (BaseException, Exception):
            _remove_zoneinfo_failed(zonefile_tmp)
            return
    else:
        _remove_zoneinfo_failed(zonefile_tmp)
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
    load_network_conversions()

    d = {}

    # network timezones are stored on github pages
    url = 'https://raw.githubusercontent.com/Prinz23/sb_network_timezones/master/network_timezones.txt'

    url_data = helpers.get_url(url)
    if None is url_data:
        update_last_retry()
        # When None is urlData, trouble connecting to github
        logger.log(u'Updating network timezones failed, this can happen from time to time. URL: %s' % url,
                   logger.WARNING)
        load_network_dict(load=False)
        return
    else:
        reset_last_retry()

    try:
        for line in url_data.splitlines():
            try:
                (key, val) = line.strip().rsplit(u':', 1)
            except (BaseException, Exception):
                continue
            if None is key or None is val:
                continue
            d[key] = val
    except (IOError, OSError):
        pass

    my_db = db.DBConnection('cache.db')

    # load current network timezones
    old_d = dict(my_db.select('SELECT * FROM network_timezones'))

    # list of sql commands to update the network_timezones table
    cl = []
    for cur_d, cur_t in iteritems(d):
        h_k = cur_d in old_d
        if h_k and cur_t != old_d[cur_d]:
            # update old record
            cl.append(
                ['UPDATE network_timezones SET network_name=?, timezone=? WHERE network_name=?', [cur_d, cur_t, cur_d]])
        elif not h_k:
            # add new record
            cl.append(['INSERT INTO network_timezones (network_name, timezone) VALUES (?,?)', [cur_d, cur_t]])
        if h_k:
            del old_d[cur_d]

    # remove deleted records
    if 0 < len(old_d):
        old_items = list([va for va in old_d])
        cl.append(['DELETE FROM network_timezones WHERE network_name IN (%s)'
                   % ','.join(['?'] * len(old_items)), old_items])

    # change all network timezone infos at once (much faster)
    if 0 < len(cl):
        my_db.mass_action(cl)
        load_network_dict()


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
        return sb_timezone

    timezone = None
    timezone_name = None

    try:
        if None is not zoneinfo.ZONEFILENAME:
            if not network_dict:
                load_network_dict()
            try:
                timezone_name = network_dupes.get(network) or network_dict.get(network.replace(' ', '').lower())
                timezone = tz.gettz(timezone_name, zoneinfo_priority=True)
            except (BaseException, Exception):
                pass

            if None is timezone:
                cc = re.search(r'\(([a-z]+)\)$', network, flags=re.I)
                try:
                    timezone_name = country_timezones.get(cc.group(1).upper())
                    timezone = tz.gettz(timezone_name, zoneinfo_priority=True)
                except (BaseException, Exception):
                    pass
    except (BaseException, Exception):
        pass

    if return_name:
        return timezone if isinstance(timezone, datetime.tzinfo) else sb_timezone, timezone_name
    return timezone if isinstance(timezone, datetime.tzinfo) else sb_timezone


def parse_time(t):
    # type: (AnyStr) -> Tuple[int, int]
    """

    :param t: time string
    :return: tuple of hour, minute
    """
    mo = time_regex.search(t)
    if None is not mo and 5 <= len(mo.groups()):
        if None is not mo.group(5):
            try:
                hr = helpers.try_int(mo.group(1))
                m = helpers.try_int(mo.group(4))
                ap = mo.group(5)
                # convert am/pm to 24 hour clock
                if None is not ap:
                    if None is not pm_regex.search(ap) and 12 != hr:
                        hr += 12
                    elif None is not am_regex.search(ap) and 12 == hr:
                        hr -= 12
            except (BaseException, Exception):
                hr = 0
                m = 0
        else:
            try:
                hr = helpers.try_int(mo.group(1))
                m = helpers.try_int(mo.group(6))
            except (BaseException, Exception):
                hr = 0
                m = 0
    else:
        hr = 0
        m = 0
    if hr < 0 or hr > 23 or m < 0 or m > 59:
        hr = 0
        m = 0

    return hr, m


def parse_date_time(d, t, network):
    # type: (int, Union[AnyStr or Tuple[int, int]], AnyStr) -> datetime.datetime
    """
    parse date and time string into local time

    :param d: ordinal datetime
    :param t: time as a string or as a tuple(hr, m)
    :param network: network names
    """
    if isinstance(t, tuple) and 2 == len(t) and isinstance(t[0], int) and isinstance(t[1], int):
        (hr, m) = t
    else:
        (hr, m) = parse_time(t)

    te = datetime.datetime.fromordinal(helpers.try_int(d))
    try:
        if isinstance(network, datetime.tzinfo):
            foreign_timezone = network
        else:
            foreign_timezone = get_network_timezone(network)
        foreign_naive = datetime.datetime(te.year, te.month, te.day, hr, m, tzinfo=foreign_timezone)
        return foreign_naive
    except (BaseException, Exception):
        return datetime.datetime(te.year, te.month, te.day, hr, m, tzinfo=sb_timezone)


def test_timeformat(t):
    # type: (AnyStr) -> bool
    """

    :param t: time to check
    :return: is valid timeformat
    """
    mo = time_regex.search(t)
    if None is mo or 2 > len(mo.groups()):
        return False
    return True


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


def load_network_conversions():
    # type: (...) -> None
    
    if not should_try_loading():
        return

    conversions = []

    # network conversions are stored on github pages
    url = 'https://raw.githubusercontent.com/prinz23/sg_network_conversions/master/conversions.txt'

    url_data = helpers.get_url(url)
    if None is url_data:
        update_last_retry()
        # When None is urlData, trouble connecting to github
        logger.log(u'Updating network conversions failed, this can happen from time to time. URL: %s' % url,
                   logger.WARNING)
        return
    else:
        reset_last_retry()

    try:
        for line in url_data.splitlines():
            (tvdb_network, tvrage_network, tvrage_country) = line.strip().rsplit(u'::', 2)
            if not (tvdb_network and tvrage_network and tvrage_country):
                continue
            conversions.append({'tvdb_network': tvdb_network,
                                'tvrage_network': tvrage_network,
                                'tvrage_country': tvrage_country})
    except (IOError, OSError):
        pass

    my_db = db.DBConnection('cache.db')

    old_d = my_db.select('SELECT * FROM network_conversions')
    old_d = helpers.build_dict(old_d, 'tvdb_network')

    # list of sql commands to update the network_conversions table
    cl = []

    for n_w in conversions:
        cl.append(['INSERT OR REPLACE INTO network_conversions (tvdb_network, tvrage_network, tvrage_country)'
                   'VALUES (?,?,?)', [n_w['tvdb_network'], n_w['tvrage_network'], n_w['tvrage_country']]])
        try:
            del old_d[n_w['tvdb_network']]
        except (BaseException, Exception):
            pass

    # remove deleted records
    if 0 < len(old_d):
        old_items = list([va for va in old_d])
        cl.append(['DELETE FROM network_conversions WHERE tvdb_network'
                   ' IN (%s)' % ','.join(['?'] * len(old_items)), old_items])

    # change all network conversion info at once (much faster)
    if 0 < len(cl):
        my_db.mass_action(cl)
