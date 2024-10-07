# coding=utf-8
import threading
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')

import test_lib as test

from datetime import date as org_date, datetime as org_datetime
import datetime
import gc
import hashlib
import lzma
import pickle
import sys
import unittest
import os.path
import shutil
sys.path.insert(1, os.path.abspath('..'))

import sickgear
from sickgear.indexers.indexer_config import TVINFO_TVDB, TVINFO_TMDB, TVINFO_TVMAZE, TVINFO_TRAKT, TVINFO_IMDB, \
    TVINFO_TVDB_SLUG, TVINFO_TRAKT_SLUG
from lib.tvinfo_base import TVInfoPerson as TVInfoPerson_lib, TVInfoImage as TVInfoImage_lib, \
    TVInfoSocialIDs as TVInfoSocialIDs_lib, TVInfoCharacter as TVInfoCharacter_lib, TVInfoShow as TVInfoShow_lib, \
    TVInfoIDs as TVInfoIDs_lib, CastList as CastList_lib, CrewList as CrewList_lib, \
    TVInfoEpisode as TVInfoEpisode_lib, TVInfoSeason as TVInfoSeason_lib, \
    TVInfoNetwork as TVInfoNetwork_lib
from tvinfo_base import TVInfoPerson, TVInfoImage, TVInfoSocialIDs, TVInfoCharacter, TVInfoShow, TVInfoIDs, CastList, \
    CrewList, RoleTypes, TVInfoEpisode, TVInfoSeason, TVInfoNetwork
import requests

# noinspection PyUnreachableCode
if False:
    from typing import Any, List, Optional

NoneType = type(None)
threading_Lock = (type(threading.Lock()), type(threading.RLock()))
file_dir = os.path.dirname(__file__)
sickgear.CACHE_DIR = os.path.join(file_dir, 'cache')
os.makedirs(sickgear.CACHE_DIR, exist_ok=True)

test_base_name = os.path.splitext(os.path.basename(__file__))[0]
mock_data_dir = os.path.join(file_dir, 'mock_data', test_base_name)
os.makedirs(mock_data_dir, exist_ok=True)
cast_types = [t for t in RoleTypes.reverse.keys() if t < RoleTypes.crew_limit]
crew_types = [t for t in RoleTypes.reverse.keys() if t >= RoleTypes.crew_limit]

# settings for mock file creation
disable_content_creation = True
only_new_urls_data_creation = True
delete_unused_mock_files = False

# other settings
pickle_protocol = 5  # needed for python 3.8 compatibility
used_files = {'browse_start_date.data'}


def _make_filename(file_str, file_ext, extra_strs=None):
    # type: (str, str, Optional[List[str]]) -> str
    hash_256 = hashlib.sha256()
    hash_256.update(file_str.encode('utf-8'))
    if isinstance(extra_strs, list):
        for _e in extra_strs:
            hash_256.update(_e.encode('utf-8'))
    return '%s%s' % (hash_256.hexdigest(), file_ext)


def _mock_get(*args, **kwargs):
    url = (1 < len(args) and args[1]) or kwargs.get('url')
    resp = requests.Response()
    resp.url = url
    resp.status_code = 200
    resp._content = ''
    resp.encoding = 'UTF-8'
    resp.headers.update({'Content-Type': 'application/json; charset=UTF-8'})
    filename = _make_filename(
        url, '.data', extra_strs=['%s%s' % (_k, _v) for _k, _v in (args[0].params or {}).items()
                                  if _k not in ('api_key')])
    data_file = os.path.join(mock_data_dir, filename)
    used_files.add(filename)
    if (disable_content_creation or only_new_urls_data_creation) and os.path.isfile(data_file):
        with lzma.open(data_file, 'rb') as fd:
            resp._content = fd.read()
        return resp
    elif not disable_content_creation:
        kw = kwargs.copy()
        kw.update({'params': args[0].params, 'headers': args[0].headers})
        resp = requests.get(*args[1:], **kw)
        with lzma.open(data_file, 'wb') as fd:
            fd.write(resp.content)
    else:
        print('error getting: %s' % url)
    return resp


def _mock_post(*args, **kwargs):
    url = (1 < len(args) and args[1]) or kwargs.get('url')
    resp = requests.Response()
    resp.status_code = 200
    resp._content = ''
    return resp


browse_start_date_filename = os.path.join(mock_data_dir, 'browse_start_date.data')
if disable_content_creation:
    with open(browse_start_date_filename, 'rt', encoding='UTF-8') as f:
        browse_start_date = f.read()
else:
    with open(browse_start_date_filename, 'wt', encoding='UTF-8') as f:
        browse_start_date = org_datetime.now().strftime('%Y-%m-%d')
        f.write(browse_start_date)


class _FakeDate(datetime.date):
    @classmethod
    def today(cls):
        d = org_date.fromisoformat(browse_start_date)
        return cls(d.year, d.month, d.day)


class _FakeDateTime(datetime.datetime):
    @classmethod
    def now(cls, *args, **kwargs):
        d = org_datetime.fromisoformat(browse_start_date)
        return cls(d.year, d.month, d.day, d.hour, d.minute, d.second)


datetime_date_backup = datetime.date
datetime_datetime_backup = datetime.datetime


def _save_pickle_file(f_name, save_obj):
    # type: (str, object) -> None
    used_files.add(f_name)
    full_filename = os.path.join(mock_data_dir, f_name)
    datetime.date = datetime_date_backup
    datetime.datetime = datetime_datetime_backup
    try:
        with lzma.open(full_filename, 'wb') as f:
            pickle.dump(save_obj, f, protocol=pickle_protocol)
    finally:
        datetime.date = _FakeDate
        datetime.datetime = _FakeDateTime


def _load_pickle_file(f_name):
    # type: (str) -> Any
    used_files.add(f_name)
    full_filename = os.path.join(mock_data_dir, f_name)
    datetime.date = datetime_date_backup
    datetime.datetime = datetime_datetime_backup
    try:
        with lzma.open(full_filename, 'rb') as f:
            return pickle.load(f)
    except (BaseException, Exception):
        return
    finally:
        datetime.date = _FakeDate
        datetime.datetime = _FakeDateTime


backup_session_get = requests.sessions.Session.get
backup_session_post = requests.sessions.Session.post


def _check_types(obj, check_list):
    # type: (object, List) -> None
    for _p, _pt, _st in check_list:
        if not isinstance(getattr(obj, _p), _pt):
            raise AssertionError('property: [%s] as unexpected type [%s), expected [%s]' %
                                 (_p, type(getattr(obj, _p)), _pt))
        if None is not _st:
            if isinstance(getattr(obj, _p), list):
                for _o in getattr(obj, _p):
                    if not isinstance(_o, _st):
                        raise AssertionError('property: [%s] as unexpected type [%s), expected [%s]' %
                                             (_p, type(_o), _st))
            elif isinstance(getattr(obj, _p), dict):
                for _k, _v in getattr(obj, _p).items():
                    if not isinstance(_k, _st[0]):
                        raise AssertionError('property key: [%s] as unexpected type [%s), expected [%s]' %
                                             (_p, type(_k), _st[0]))
                    if not isinstance(_v, _st[1]):
                        raise AssertionError('property key: [%s] as unexpected type [%s), expected [%s]' %
                                             (_p, type(_v), _st[0]))


def _property_type_checker(obj, checked_objs=None):
    # type: (object, bool) -> None

    # make aure each object is only checked once
    checked_objs = checked_objs or []
    obj_id = id(obj)
    if obj_id in checked_objs:
        return
    checked_objs.append(obj_id)

    # make sure type check uses original types
    datetime.date = datetime_date_backup
    datetime.datetime = datetime_datetime_backup

    try:
        # special checks for TVInfoPerson property types
        if isinstance(obj, (TVInfoPerson, TVInfoPerson_lib)):
            _check_types(obj, [
                ('images', list, (TVInfoImage, TVInfoImage_lib)),
                ('social_ids', (TVInfoSocialIDs, TVInfoSocialIDs_lib), None),
                ('characters', list, (TVInfoCharacter, TVInfoCharacter_lib)),
                ('name', str, None),
                ('id', int, None),
                ('image', (str, NoneType), None),
                ('thumb_url', (str, NoneType), None),
                ('gender', (int, NoneType), None),
                ('bio', (str, NoneType), None),
                ('birthdate', (datetime.date, NoneType), None),
                ('deathdate', (datetime.date, NoneType), None),
                ('country', (str, NoneType), None),
                ('country_code', (str, NoneType), None),
                ('country_timezone', (str, NoneType), None),
                ('ids', (TVInfoIDs, TVInfoIDs_lib), None),
                ('social_ids', (TVInfoSocialIDs, TVInfoSocialIDs_lib), None),
                ('birthplace', (str, NoneType), None),
                ('deathplace', (str, NoneType), None),
                ('url', (str, NoneType), None),
                ('height', (int, float, NoneType), None),
                ('nicknames', set, str),
                ('real_name', (str, NoneType), None),
                ('akas', set, str),
            ])
            for _o in obj.characters:
                _property_type_checker(_o, checked_objs=checked_objs)
        # special checks for TVInfoCharacter property types
        elif isinstance(obj, (TVInfoCharacter, TVInfoCharacter_lib)):
            _check_types(obj, [
                ('person', (list, NoneType), (TVInfoPerson, TVInfoPerson_lib)),
                ('ti_show', (TVInfoShow, TVInfoShow_lib, NoneType), None),
                ('voice', (bool, NoneType), None),
                ('plays_self', (bool, NoneType), None),
                ('regular', (bool, NoneType), None),
                ('start_year', (int, NoneType), None),
                ('end_year', (int, NoneType), None),
                ('name', (str, NoneType), None),
                ('episode_count', (int, NoneType), None),
                ('guest_episodes_numbers', dict, [int, list]),
                ('name', (str, NoneType), None),
                ('id', (int, NoneType), None),
                ('image', (str, NoneType), None),
                ('thumb_url', (str, NoneType), None),
                ('gender', (int, NoneType), None),
                ('bio', (str, NoneType), None),
                ('birthdate', (datetime.date, NoneType), None),
                ('deathdate', (datetime.date, NoneType), None),
                ('country', (str, NoneType), None),
                ('country_code', (str, NoneType), None),
                ('country_timezone', (str, NoneType), None),
                ('ids', (TVInfoIDs, TVInfoIDs_lib), None),
            ])
            if isinstance(obj.person, list):
                for _p in obj.person:
                    if not isinstance(_p, (TVInfoPerson, TVInfoPerson_lib)):
                        raise AssertionError('invalid person object in character object [%s]' % obj)
                    _property_type_checker(_p, checked_objs=checked_objs)

            # for some api the show can't directly be loaded for character credits
            if isinstance(obj.ti_show, (TVInfoShow, TVInfoShow_lib)) and obj.ti_show.show_loaded:
                _property_type_checker(obj.ti_show, checked_objs=checked_objs)
        # special checks for TVInfoShow property types
        elif isinstance(obj, (TVInfoShow, TVInfoShow_lib)):
            _check_types(obj, [
                ('id', int, None),
                ('seriesname', str, None),
                ('poster_loaded', bool, None),
                ('banner_loaded', bool, None),
                ('fanart_loaded', bool, None),
                ('season_images_loaded', bool, None),
                ('seasonwide_images_loaded', bool, None),
                ('actors_loaded', bool, None),
                ('show_not_found', bool, None),
                ('ids', (TVInfoIDs, TVInfoIDs_lib), None),
                ('social_ids', (TVInfoSocialIDs, TVInfoSocialIDs_lib), None),
                ('slug', (str, NoneType), None),
                ('seriesid', int, None),
                ('aliases', list, str),
                ('classification', (str, NoneType), None),
                ('genre', (str, NoneType), None),
                ('genre', (str, NoneType), None),
                ('genre_list', list, str),
                ('actors', list, dict),
                ('cast', (CastList, CastList_lib), None),
                ('crew', (CrewList, CrewList_lib), None),
                ('show_type', list, str),
                ('networks', list, (TVInfoNetwork, TVInfoNetwork_lib)),
                ('network', (str, NoneType), None),
                ('network_id', (int, NoneType), None),
                ('network_country', (str, NoneType), None),
                ('network_country_code', (str, NoneType), None),
                ('network_is_stream', (bool, NoneType), None),
                ('runtime', (int, NoneType), None),
                ('language', (str, NoneType), None),
                ('spoken_languages', list, str),
                ('official_site', (str, NoneType), None),
                ('imdb_id', (str, NoneType), None),
                ('zap2itid', (str, NoneType), None),
                ('airs_dayofweek', (str, NoneType), None),
                ('airs_time', (str, NoneType), None),
                ('time', (datetime.time, NoneType), None),
                ('added', (str, NoneType), None),
                ('addedby', (str, NoneType), None),
                ('siteratingcount', (int, NoneType), None),
                ('lastupdated', (int, str, NoneType), None),
                ('contentrating', (str, NoneType), None),
                ('rating', (int, float, NoneType), None),
                ('status', (str, NoneType), None),
                ('overview', str, None),
                ('poster', (str, NoneType), None),
                ('poster_thumb', (str, NoneType), None),
                ('banner', (str, NoneType), None),
                ('banner_thumb', (str, NoneType), None),
                ('fanart', (str, NoneType), None),
                ('banners', dict, None),
                ('images', dict, [int, list]),
                ('updated_timestamp', (int, NoneType), None),
                ('popularity', (int, float, NoneType), None),
                ('vote_count', (int, NoneType), None),
                ('vote_average', (int, float, NoneType), None),
                ('origin_countries', list, str),
                ('alt_ep_numbering', dict, [str, dict]),
                ('watcher_count', (int, NoneType), None),
                ('play_count', (int, NoneType), None),
                ('collected_count', (int, NoneType), None),
                ('collector_count', (int, NoneType), None),
                ('next_season_airdate', (str, NoneType), None),
                ('trailers', dict, [str, str]),
                ('requested_language', str, None),
            ])
            for _ct, _cl in obj.cast.items():
                if _ct not in cast_types:
                    raise AssertionError('invalid CastType in show object')
                for _c in _cl:
                    _property_type_checker(_c, checked_objs=checked_objs)

            for _ct, _cl in obj.crew.items():
                if _ct not in crew_types:
                    raise AssertionError('invalid CrewType in show object')
                for _c in _cl:
                    _property_type_checker(_c, checked_objs=checked_objs)

            # iter though episode objects and test them
            for _s, _sl in obj.items():
                if not isinstance(_s, int):
                    raise AssertionError('invalid season number in show object [%s]' % _s)
                if not isinstance(_sl, (TVInfoSeason, TVInfoSeason_lib)):
                    raise AssertionError('invalid season object in show object [%s]' % _s)
                _property_type_checker(_sl, checked_objs=checked_objs)
        # special checks for TVInfoSeason property types
        elif isinstance(obj, (TVInfoSeason, TVInfoSeason_lib)):
            _check_types(obj, [
                ('id', (int, NoneType), None),
                ('show', (TVInfoShow, TVInfoShow_lib), None),
                ('number', int, None),
                ('name', (str, NoneType), None),
                ('actors', list, None),
                ('cast', (CastList, CastList_lib), None),
                ('network', (str, NoneType), None),
                ('network_id', (int, NoneType), None),
                ('network_timezone', (str, NoneType), None),
                ('network_country', (str, NoneType), None),
                ('network_country_code', (str, NoneType), None),
                ('network_is_stream', (bool, NoneType), None),
                ('ordered', (int, NoneType), None),
                ('start_date', (str, NoneType), None),
                ('end_date', (str, NoneType), None),
                ('poster', (str, NoneType), None),
                ('summery', (str, NoneType), None),
                ('episode_order', (int, NoneType), None),
                ])

            for _ct, _cl in obj.cast.items():
                if _ct not in cast_types:
                    raise AssertionError('invalid CastType in season object')
                for _c in _cl:
                    _property_type_checker(_c, checked_objs=checked_objs)

            for _en, _eo in obj.items():
                if not isinstance(_en, int):
                    raise AssertionError('invalid episode number in show object [%s]' % _en)
                if not isinstance(_eo, (TVInfoEpisode, TVInfoEpisode_lib)):
                    raise AssertionError('invalid episdode object in season object [%s]' % _en)
                _property_type_checker(_eo, checked_objs=checked_objs)
        # special checks for TVInfoEpisode property types
        elif isinstance(obj, (TVInfoEpisode, TVInfoEpisode_lib)):
            _check_types(obj, [
                ('id', int, None),
                ('episodename', (str, NoneType), None),
                ('seriesid', (int, NoneType), None),
                ('season', (TVInfoSeason, TVInfoSeason_lib), None),
                ('seasonnumber', int, None),
                ('episodenumber', int, None),
                ('absolute_number', (int, NoneType), None),
                ('is_special', (bool, NoneType), None),
                ('actors', list, dict),
                ('gueststars', (str, NoneType), None),
                ('gueststars_list', list, str),
                ('cast', (CastList, CastList_lib), None),
                ('directors', list, str),
                ('writer', (str, NoneType), None),
                ('writers', list, str),
                ('crew', (CrewList, CrewList_lib), None),
                ('overview', str, None),
                ('productioncode', (str, NoneType), None),
                ('showurl', (str, NoneType), None),
                ('lastupdated', (int, str, NoneType), None),
                ('dvddiscid', (str, NoneType), None),
                ('dvd_season', (int, NoneType), None),
                ('dvd_episodenumber', (int, NoneType), None),
                ('dvdchapter', (int, NoneType), None),
                ('firstaired', (str, NoneType), None),
                ('airtime', (datetime.time, NoneType), None),
                ('runtime', (int, NoneType), None),
                ('timestamp', (int, float, NoneType), None),
                ('network', (str, NoneType), None),
                ('network_id', (int, NoneType), None),
                ('network_timezone', (str, NoneType), None),
                ('network_country', (str, NoneType), None),
                ('network_country_code', (str, NoneType), None),
                ('network_is_stream', (bool, NoneType), None),
                ('filename', (str, NoneType), None),
                ('lastupdatedby', (int, str, NoneType), None),
                ('airsafterseason', (int, NoneType), None),
                ('airsbeforeseason', (int, NoneType), None),
                ('airsbeforeepisode', (bool, NoneType), None),
                ('imdb_id', (str, NoneType), None),
                ('contentrating', (str, NoneType), None),
                ('thumbadded', (str, NoneType), None),
                ('rating', (int, float, NoneType), None),
                ('vote_count', (int, NoneType), None),
                ('siteratingcount', (int, NoneType), None),
                ('show', (TVInfoShow, TVInfoShow_lib, NoneType), None),
                ('alt_nums', dict, [str, dict]),
                ('finale_type', (int, NoneType), None),
            ])
            if isinstance(obj.show, (TVInfoShow, TVInfoShow_lib)):
                _property_type_checker(obj.show, checked_objs=checked_objs)

            _property_type_checker(obj.season, checked_objs=checked_objs)

            for _ct, _cl in obj.cast.items():
                if _ct not in cast_types:
                    raise AssertionError('invalid CastType in episode object')
                for _c in _cl:
                    _property_type_checker(_c, checked_objs=checked_objs)

            for _ct, _cl in obj.crew.items():
                if _ct not in crew_types:
                    raise AssertionError('invalid CrewType in episode object')
                for _c in _cl:
                    _property_type_checker(_c, checked_objs=checked_objs)
    finally:
        datetime.date = _FakeDate
        datetime.datetime = _FakeDateTime


def _compare_helper(obj_a, obj_b):
    _property_type_checker(obj_a)

    for prop, value in vars(obj_a).items():
        if isinstance(value, threading_Lock):
            continue
        try:
            assert value == getattr(obj_b, prop)
        except AssertionError as e:
            print('property [%s] different: obj_a [%s], obj_b [%s)' % (prop, value, getattr(obj_b, prop)))
            raise e
        except (BaseException, Exception) as e:
            print(e)
            raise e


person_tests = [
    {'p_id': 346941, 'tvid': TVINFO_TVDB},  # Katherine McNamara
    {'p_id': 968006, 'tvid': TVINFO_TMDB},  # Katherine McNamara
    {'p_id': 15776, 'tvid': TVINFO_TVMAZE},  # Katherine McNamara
    {'p_id': 260345, 'tvid': TVINFO_TRAKT},  # Katherine McNamara
    {'p_id': 3031063, 'tvid': TVINFO_IMDB},  # Katherine McNamara
]

show_tests = [
    {'prodid': 295837, 'tvid': TVINFO_TVDB},  # Shadowhunters
    {'prodid': 63210, 'tvid': TVINFO_TMDB},  # Shadowhunters
    {'prodid': 2158, 'tvid': TVINFO_TVMAZE},  # Shadowhunters
]

search_tests = [
    # tvdb tests
    {'kwargs': {'name': 'Shadowhunters'}, 'search_tvid': TVINFO_TVDB},  # Shadowhunters
    {'kwargs': {'name': 'Wednesday'}, 'search_tvid': TVINFO_TVDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVDB: 295837}}, 'search_tvid': TVINFO_TVDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_IMDB: 4145054}}, 'search_tvid': TVINFO_TVDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TMDB: 119051}}, 'search_tvid': TVINFO_TVDB},  # Wednesday
    {'kwargs': {'ids': {TVINFO_TVMAZE: 53647}}, 'search_tvid': TVINFO_TVDB},  # Wednesday
    {'kwargs': {'ids': {TVINFO_TVDB_SLUG: 'walker-independence'}}, 'search_tvid': TVINFO_TVDB},  # Walker: Independence
    # trakt tests
    {'kwargs': {'name': 'Shadowhunters'}, 'search_tvid': TVINFO_TRAKT},  # Shadowhunters
    {'kwargs': {'name': 'Wednesday'}, 'search_tvid': TVINFO_TRAKT},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVDB: 295837}}, 'search_tvid': TVINFO_TRAKT},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_IMDB: 4145054}}, 'search_tvid': TVINFO_TRAKT},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TMDB: 119051}}, 'search_tvid': TVINFO_TRAKT},  # Wednesday
    {'kwargs': {'ids': {TVINFO_TRAKT_SLUG: 'walker-independence'}}, 'search_tvid': TVINFO_TRAKT},  # Walker: Independence
    # tmdb tests
    {'kwargs': {'name': 'Shadowhunters'}, 'search_tvid': TVINFO_TMDB},  # Shadowhunters
    {'kwargs': {'name': 'Wednesday'}, 'search_tvid': TVINFO_TMDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVDB: 295837}}, 'search_tvid': TVINFO_TMDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_IMDB: 4145054}}, 'search_tvid': TVINFO_TMDB},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TMDB: 119051}}, 'search_tvid': TVINFO_TMDB},  # Wednesday
    # tvmaze tests
    {'kwargs': {'name': 'Shadowhunters'}, 'search_tvid': TVINFO_TVMAZE},  # Shadowhunters
    {'kwargs': {'name': 'Wednesday'}, 'search_tvid': TVINFO_TVMAZE},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVDB: 295837}}, 'search_tvid': TVINFO_TVMAZE},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_IMDB: 4145054}}, 'search_tvid': TVINFO_TVMAZE},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVMAZE: 2158}}, 'search_tvid': TVINFO_TVMAZE},  # Shadowhunters
    {'kwargs': {'ids': {TVINFO_TVMAZE: 53647}}, 'search_tvid': TVINFO_TVMAZE},  # Wednesday
]


person_search_tests = [
    # tvdb tests
    {'kwargs': {'name': 'Katherine McNamara'}, 'search_tvid': TVINFO_TVDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TVDB: 346941}}, 'search_tvid': TVINFO_TVDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_IMDB: 3031063}}, 'search_tvid': TVINFO_TVDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TMDB: 968006}}, 'search_tvid': TVINFO_TVDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TVMAZE: 15776}}, 'search_tvid': TVINFO_TVDB},  # Katherine McNamara
    # trakt tests
    {'kwargs': {'name': 'Katherine McNamara'}, 'search_tvid': TVINFO_TRAKT},  # Katherine McNamara
    # {'kwargs': {'ids': {TVINFO_TVDB: 346941}}, 'search_tvid': TVINFO_TRAKT},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_IMDB: 3031063}}, 'search_tvid': TVINFO_TRAKT},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TMDB: 968006}}, 'search_tvid': TVINFO_TRAKT},  # Katherine McNamara
    # tmdb tests
    {'kwargs': {'name': 'Katherine McNamara'}, 'search_tvid': TVINFO_TMDB},  # Katherine McNamara
    # {'kwargs': {'ids': {TVINFO_TVDB: 346941}}, 'search_tvid': TVINFO_TMDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_IMDB: 3031063}}, 'search_tvid': TVINFO_TMDB},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TMDB: 968006}}, 'search_tvid': TVINFO_TMDB},  # Katherine McNamara
    # tvmaze tests
    {'kwargs': {'name': 'Katherine McNamara'}, 'search_tvid': TVINFO_TVMAZE},  # Katherine McNamara
    # {'kwargs': {'ids': {TVINFO_TVDB: 346941}}, 'search_tvid': TVINFO_TVMAZE},  # Katherine McNamara
    # {'kwargs': {'ids': {TVINFO_IMDB: 3031063}}, 'search_tvid': TVINFO_TVMAZE},  # Katherine McNamara
    {'kwargs': {'ids': {TVINFO_TVMAZE: 15776}}, 'search_tvid': TVINFO_TVMAZE},  # Katherine McNamara
]


browser_extra_args = {
    TVINFO_TVDB: {
        'get_top_rated': [{'year': 2022}, {'year': 2020}, {'year': 2010}, {'in_last_year': True}]
    },
    TVINFO_TVMAZE: {},
    TVINFO_TMDB: {
        'get_trending': [{'time_window': 'days'}, {'time_window': 'week'}],
        'get_similar': [{'tvid': 4145054}],
        'get_recommended_for_show': [{'tvid': 4145054}],
    },
    TVINFO_TRAKT: {
        'get_similar': [{'tvid': 99113}],
        'get_recommended': [{'period': 'weekly'}, {'period': 'daily'}, {'period': 'monthly'}, {'period': 'yearly'},
                            {'period': 'all'}],
        'get_most_collected': [{'period': 'weekly'}, {'period': 'daily'}, {'period': 'monthly'}, {'period': 'yearly'},
                               {'period': 'all'}],
        'get_most_watched': [{'period': 'weekly'}, {'period': 'daily'}, {'period': 'monthly'}, {'period': 'yearly'},
                             {'period': 'all'}],
        'get_most_played': [{'period': 'weekly'}, {'period': 'daily'}, {'period': 'monthly'}, {'period': 'yearly'},
                            {'period': 'all'}],
    },
}


class TVInfoTests(test.SickbeardTestDBCase):

    @classmethod
    def setUpClass(cls) -> None:
        test.teardown_test_db()
        super(TVInfoTests, cls).setUpClass()
        datetime.date = _FakeDate
        datetime.datetime = _FakeDateTime
        requests.sessions.Session.get = _mock_get
        if disable_content_creation:
            requests.sessions.Session.post = _mock_post

    @classmethod
    def tearDownClass(cls):
        super(TVInfoTests, cls).tearDownClass()
        with os.scandir(mock_data_dir) as s_d:
            files = {_f.name for _f in os.scandir(mock_data_dir) if _f.is_file()}
            unused_files = files - used_files
            if delete_unused_mock_files:
                for _u_f in unused_files:
                    full_filename = os.path.join(mock_data_dir, _u_f)
                    try:
                        os.remove(full_filename)
                    except (BaseException, Exception) as e:
                        print('errror deleting: [%s], error: %s' % (full_filename, e))
        if unused_files:
            print('unused files: %s' % unused_files)
        print('reset mock methods')
        datetime.date = datetime_date_backup
        datetime.datetime = datetime_datetime_backup
        requests.sessions.Session.get = backup_session_get
        requests.sessions.Session.post = backup_session_post

    def tearDown(self):
        super(TVInfoTests, self).tearDown()
        try:
            gc.collect(2)
            shutil.rmtree(sickgear.CACHE_DIR)
        except (BaseException, Exception):
            pass

    def test_person_data(self):
        for t_c in person_tests:
            tvid = t_c['tvid']
            p_id = t_c['p_id']
            print('testing person: %s: %s' % (sickgear.TVInfoAPI(tvid).name, p_id))

            tvinfo_config = sickgear.TVInfoAPI(tvid).api_params.copy()
            tvinfo_config['cache'] = False

            t = sickgear.TVInfoAPI(tvid).setup(**tvinfo_config)
            t.clear_cache()
            person_obj = t.get_person(p_id, get_show_credits=True, get_images=True)
            filename = _make_filename('%s_%s_person' % (tvid, p_id), '.obj_data')
            for _c in person_obj.characters:
                _c.ti_show.load_data()
            if os.path.isfile(os.path.join(mock_data_dir, filename)):
                _p_o = _load_pickle_file(filename)  # type: TVInfoPerson
            elif not disable_content_creation:
                _save_pickle_file(filename, person_obj)
                _p_o = person_obj
            try:
                assert None is not person_obj and None is not _p_o
                _compare_helper(person_obj, _p_o)
            except (BaseException, Exception) as e:
                if not disable_content_creation and os.path.isfile(os.path.join(mock_data_dir, filename)):
                    _save_pickle_file(filename, person_obj)
                    _p_o = person_obj
                    assert None is not person_obj and None is not _p_o
                    _compare_helper(person_obj, _p_o)
                else:
                    raise e

    def test_show_data(self):
        for t_c in show_tests:
            tvid = t_c['tvid']
            prodid = t_c['prodid']
            print('testing show: %s: %s' % (sickgear.TVInfoAPI(tvid).name, prodid))

            tvinfo_config = sickgear.TVInfoAPI(tvid).api_params.copy()
            tvinfo_config['cache'] = False

            t = sickgear.TVInfoAPI(tvid).setup(**tvinfo_config)
            t.clear_cache()
            show_obj = t.get_show(prodid, load_episodes=True, banners=True, posters=True, seasons=True,
                                  seasonwides=True, fanart=True, actors=True)
            filename = _make_filename('%s_%s_show' % (tvid, prodid), '.obj_data')
            if os.path.isfile(os.path.join(mock_data_dir, filename)):
                _s_o = _load_pickle_file(filename)  # type: TVInfoShow
            elif not disable_content_creation:
                _save_pickle_file(filename, show_obj)
                _s_o = show_obj
            try:
                assert None is not show_obj and None is not _s_o
                _compare_helper(show_obj, _s_o)
            except (BaseException, Exception) as e:
                if not disable_content_creation and os.path.isfile(os.path.join(mock_data_dir, filename)):
                    _save_pickle_file(filename, show_obj)
                    _s_o = show_obj
                    assert None is not show_obj and None is not _s_o
                    _compare_helper(show_obj, _s_o)
                else:
                    raise e

    def test_person_search(self):
        for t_c in person_search_tests:
            search_tvid = t_c['search_tvid']
            print('testing [%s] person search for: %s' % (sickgear.TVInfoAPI(search_tvid).name, t_c['kwargs']))

            tvinfo_config = sickgear.TVInfoAPI(search_tvid).api_params.copy()
            tvinfo_config['cache'] = False

            t = sickgear.TVInfoAPI(search_tvid).setup(**tvinfo_config)
            t.clear_cache()
            search_results = t.search_person(**t_c['kwargs'])
            filename = _make_filename('%s_%s_person_search' % (search_tvid, ','.join(
                ['%s%s' % (_k, _v) for _k, _v in t_c['kwargs'].items()])), '.obj_data')
            if os.path.isfile(os.path.join(mock_data_dir, filename)):
                _s_o = _load_pickle_file(filename)  # type: List[TVInfoPerson]
            elif not disable_content_creation:
                _save_pickle_file(filename, search_results)
                _s_o = search_results
            try:
                assert None is not search_results and None is not _s_o
                for _i, _r in enumerate(search_results):
                    _compare_helper(_r, _s_o[_i])
            except (BaseException, Exception) as e:
                if not disable_content_creation and os.path.isfile(os.path.join(mock_data_dir, filename)):
                    _save_pickle_file(filename, search_results)
                    _s_o = search_results
                    assert None is not search_results and None is not _s_o
                    for _i, _r in enumerate(search_results):
                        _compare_helper(_r, _s_o[_i])
                else:
                    raise e

    def test_show_search(self):
        for t_c in search_tests:
            search_tvid = t_c['search_tvid']
            print('testing [%s] search for: %s' % (sickgear.TVInfoAPI(search_tvid).name, t_c['kwargs']))

            tvinfo_config = sickgear.TVInfoAPI(search_tvid).api_params.copy()
            tvinfo_config['cache'] = False

            t = sickgear.TVInfoAPI(search_tvid).setup(**tvinfo_config)
            t.clear_cache()
            search_results = t.search_show(**t_c['kwargs'])
            filename = _make_filename('%s_%s_search' % (search_tvid, ','.join(
                ['%s%s' % (_k, _v) for _k, _v in t_c['kwargs'].items()])), '.obj_data')
            if os.path.isfile(os.path.join(mock_data_dir, filename)):
                _s_o = _load_pickle_file(filename)  # type: List[TVInfoShow]
            elif not disable_content_creation:
                _save_pickle_file(filename, search_results)
                _s_o = search_results
            try:
                assert None is not search_results and None is not _s_o
                for _i, _r in enumerate(search_results):
                    _compare_helper(_r, _s_o[_i])
            except (BaseException, Exception) as e:
                if not disable_content_creation and os.path.isfile(os.path.join(mock_data_dir, filename)):
                    _save_pickle_file(filename, search_results)
                    _s_o = search_results
                    assert None is not search_results and None is not _s_o
                    for _i, _r in enumerate(search_results):
                        _compare_helper(_r, _s_o[_i])
                else:
                    raise e

    def test_browse_endpoints(self):
        for _tvid in sickgear.TVInfoAPI().all_sources:
            tvinfo_config = sickgear.TVInfoAPI(_tvid).api_params.copy()
            tvinfo_config['cache'] = False

            t = sickgear.TVInfoAPI(_tvid).setup(**tvinfo_config)
            t.clear_cache()
            for _m in (('get_premieres', {}), ('get_anticipated', {}),
                       ('get_recommended', {}), ('get_most_collected', {}), ('get_most_watched', {}),
                       ('get_most_played', {}), ('get_returning', {}), ('discover', {}), ('get_new_seasons', {}),
                       ('get_new_shows', {}), ('get_top_rated', {}), ('get_popular', {}), ('get_trending', {}),
                       ('get_recommended_for_show', {}), ('get_similar', {})):
                _method = getattr(t, _m[0], None)
                # check if method is implemented in tvid source
                if not _method or 'TVInfoBase' in _method.__qualname__:
                    continue
                for _e_kw in browser_extra_args.get(_tvid, {}).get(_m[0], [{}]) or [{}]:
                    kw = _m[1].copy()
                    kw.update(_e_kw)
                    print('testing %s: %s%s' % (sickgear.TVInfoAPI(_tvid).name, _m[0],
                                                ('', ' with parameter: %s' % kw)[0 != len(kw)]))
                    results = _method(**kw)
                    filename = _make_filename('%s_%s_%s' % (
                        _tvid, ''.join('%s%s' % (_k, _v) for _k, _v in kw.items()), _m[0]), '.obj_data')
                    if os.path.isfile(os.path.join(mock_data_dir, filename)):
                        _s_o = _load_pickle_file(filename)  # type: List[TVInfoShow]
                    elif not disable_content_creation:
                        _save_pickle_file(filename, results)
                        _s_o = results

                    try:
                        assert None is not results and None is not _s_o
                        for _i, _r in enumerate(results):
                            _compare_helper(_r, _s_o[_i])
                    except (BaseException, Exception) as e:
                        if not disable_content_creation and os.path.isfile(os.path.join(mock_data_dir, filename)):
                            _save_pickle_file(filename, results)
                            _s_o = results
                            assert None is not results and None is not _s_o
                            for _i, _r in enumerate(results):
                                _compare_helper(_r, _s_o[_i])
                        else:
                            raise e


if '__main__' == __name__:

    print('===============================')
    print('STARTING - TV Info TESTS')
    print('===============================')

    try:
        suite = unittest.TestLoader().loadTestsFromTestCase(TVInfoTests)
        unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        requests.sessions.Session.get = backup_session_get
        requests.sessions.Session.post = backup_session_post
        datetime.date = datetime_date_backup
        datetime.datetime = datetime_datetime_backup
