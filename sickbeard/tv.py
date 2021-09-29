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

from collections import Counter, OrderedDict
from functools import reduce
from itertools import chain

import datetime
import glob
import inspect
import os.path
import re
import requests
import stat
import threading
import traceback

from imdbpie import ImdbAPIError
from lxml_etree import etree

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex

import sickbeard
from . import db, helpers, history, image_cache, indexermapper, logger, \
    name_cache, network_timezones, notifiers, postProcessor, subtitles
from .anime import AniGroupList
from .common import Quality, statusStrings, \
    ARCHIVED, DOWNLOADED, FAILED, IGNORED, SKIPPED, SNATCHED, SNATCHED_ANY, SNATCHED_PROPER, UNAIRED, UNKNOWN, WANTED, \
    NAMING_DUPLICATE, NAMING_EXTEND, NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED, NAMING_SEPARATED_REPEAT
from .generic_queue import QueuePriorities
from .helpers import try_float, try_int
from .indexermapper import del_mapping, MapStatus, save_mapping
from .indexers.indexer_config import TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT, TVINFO_TVDB, TVINFO_TVMAZE, TVINFO_TVRAGE
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from .sgdatetime import SGDatetime, timestamp_near
from .tv_base import TVEpisodeBase, TVShowBase

from lib import imdbpie, subliminal
from lib.dateutil import tz
from lib.dateutil.parser import parser as du_parser
from lib.fuzzywuzzy import fuzz
from lib.tvinfo_base import TVINFO_FACEBOOK, TVINFO_INSTAGRAM, TVINFO_SLUG, TVINFO_TWITTER, TVINFO_WIKIPEDIA
from lib.tvinfo_base.exceptions import *
from sg_helpers import calc_age, int_to_time, remove_file_perm, time_to_int

from _23 import filter_iter, filter_list, list_keys
from six import integer_types, iteritems, itervalues, moves, PY2, string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Set, Text, Union
    from sqlite3 import Row
    from lib.tvinfo_base import CastList, Character as TVINFO_Character, Person as TVINFO_Person, \
        TVInfoEpisode, TVInfoShow

coreid_warnings = False
if coreid_warnings:
    import warnings
    warnings.simplefilter('always', DeprecationWarning)

tz_p = du_parser()

# status codes for switching tv show source
TVSWITCH_DUPLICATE_SHOW = 0
TVSWITCH_ID_CONFLICT = 1
TVSWITCH_NO_NEW_ID = 2
TVSWITCH_NORMAL = 3
TVSWITCH_NOT_FOUND_ERROR = 4
TVSWITCH_SAME_ID = 5
TVSWITCH_SOURCE_NOT_FOUND_ERROR = 6
TVSWITCH_VERIFY_ERROR = 7

tvswitch_names = {
    TVSWITCH_DUPLICATE_SHOW: 'Duplicate Show',
    TVSWITCH_ID_CONFLICT: 'new id conflicts with existing show',
    TVSWITCH_NO_NEW_ID: 'no new id found',
    TVSWITCH_NORMAL: 'Normal',
    TVSWITCH_NOT_FOUND_ERROR: 'Not found on new tv source',
    TVSWITCH_SAME_ID: 'unchanged ids given',
    TVSWITCH_SOURCE_NOT_FOUND_ERROR: 'source show not found',
    TVSWITCH_VERIFY_ERROR: 'Verification error',
}

TVSWITCH_EP_DELETED = 1
TVSWITCH_EP_RENAMED = 2

tvswitch_ep_names = {
    TVSWITCH_EP_DELETED: 'deleted',
    TVSWITCH_EP_RENAMED: 'renamed'
}

concurrent_show_not_found_days = 7
show_not_found_retry_days = 7

prodid_bitshift = 4
tvid_bitmask = (1 << prodid_bitshift) - 1


class TVidProdid(object):
    """
    Helper class to standardise the use of a TV info source id with its associated TV show id

    Examples of setting and using on the one action, tvid and prodid are numbers of type int or string;
    TVidProdid({tvid: prodid})
    TVidProdid({tvid: prodid})([])
    TVidProdid({tvid: prodid})(list)
    TVidProdid({tvid: prodid})('list')
    TVidProdid({tvid: prodid}).list

    Whitespace may exist between the number value and <self.glue> in these strings
    TVidProdid('tvid <self.glue> prodid')({})
    TVidProdid('tvid <self.glue> prodid')(dict)
    TVidProdid('tvid <self.glue> prodid')('dict')
    TVidProdid('tvid <self.glue> prodid').dict
    """
    glue = ':'

    def __init__(self, tvid_prodid=None):
        """
        :param tvid_prodid: TV info data source ID, and TV show ID
        :type tvid_prodid: Dict or String
        """
        self.tvid = None
        self.prodid = None
        self.sid_int = None

        if isinstance(tvid_prodid, dict) and 1 == len(tvid_prodid):
            try:
                for (tvid, prodid) in iteritems(tvid_prodid):
                    self.tvid, self.prodid = int(tvid), int(prodid)
            except ValueError:
                pass
        elif isinstance(tvid_prodid, string_types):
            if self.glue in tvid_prodid:
                try:
                    for (tvid, prodid) in [re.findall(r'(\d+)\s*%s\s*(\d+)' % self.glue, tvid_prodid)[0]]:
                        self.tvid, self.prodid = int(tvid), int(prodid)
                except IndexError:
                    pass
            else:
                try:
                    legacy_showid = int(re.findall(r'(?i)\d+', tvid_prodid)[0])
                    show_obj = (helpers.find_show_by_id({TVINFO_TVDB: legacy_showid})
                                or helpers.find_show_by_id({TVINFO_TVRAGE: legacy_showid}))
                    pre_msg = 'Todo: Deprecate show_id used without a tvid'
                    if None is show_obj:
                        pre_msg += ' and show_obj not found'
                    else:
                        self.tvid, self.prodid = show_obj.tvid, legacy_showid

                    if coreid_warnings:
                        logger.log('%s\n' % pre_msg +
                                   '|>%s^-- Note: Bootstrap & Tornado startup functions stripped from traceback log.' %
                                   '|>'.join(filter_iter(lambda text: not re.search(r'(?i)bootstrap|traceback\.'
                                                                                    r'format_stack|pydevd|tornado'
                                                                                    r'|webserveinit', text),
                                                         traceback.format_stack(inspect.currentframe()))))
                except IndexError:
                    pass
        elif isinstance(tvid_prodid, integer_types):
            self.tvid = tvid_prodid & tvid_bitmask
            self.prodid = tvid_prodid >> prodid_bitshift
            self.sid_int = tvid_prodid
            return

        if None not in (self.prodid, self.tvid):
            self.sid_int = self.prodid << prodid_bitshift | self.tvid

    def __call__(self, *args, **kwargs):
        return self._get(*args, **kwargs)

    def __repr__(self):
        return self._get()

    def __str__(self):
        return self._get()

    def __tuple__(self):
        return self._get(tuple)

    def __int__(self):
        return self._get(int)

    @property
    def list(self):
        return self._get(list)

    @property
    def dict(self):
        return self._get(dict)

    @property
    def tuple(self):
        return self._get(tuple)

    @property
    def int(self):
        return self._get(int)

    @staticmethod
    def _checktype(value, t):
        if isinstance(value, string_types) and not isinstance(value, type) and value:
            if value == getattr(t, '__name__', None):
                return True
        elif (isinstance(value, type) and value == t) or isinstance(value, t):
            return True
        return False

    def _get(self, kind=None):
        if None is not kind:
            if self._checktype(kind, int):
                return self.sid_int
            elif self._checktype(kind, dict):
                return {self.tvid: self.prodid}
            elif self._checktype(kind, tuple):
                return self.tvid, self.prodid
        if None is kind or self._checktype(kind, string_types):
            return '%s%s%s' % (self.tvid, self.glue, self.prodid)
        return [self.tvid, self.prodid]

    @property
    def _tvid(self):
        return self.tvid

    @property
    def _prodid(self):
        return self.prodid


class PersonGenders(object):
    UNKNOWN = 0
    male = 1
    female = 2

    possible_values = [0, 1, 2]
    names = {UNKNOWN: 'Unknown', male: 'Male', female: 'Female'}
    tmdb_map = {0: UNKNOWN, 1: female, 2: male}


def _make_date(dt):
    # type: (datetime.date) -> integer_types
    if not dt:
        return None
    return dt.toordinal()


def usable_id(value):
    # type: (Union[AnyStr, int]) -> Optional[AnyStr, int]
    """
    return value as int if value is numerical,
    or value as string if value is valid id:format
    otherwise None
    """
    value_id = try_int(value, None)
    if None is not value_id:
        return value_id
    return usable_rid(value)


def usable_rid(value):
    # type: (Union[AnyStr]) -> Optional[AnyStr]
    """
    return value if is a id:format is valid
    otherwise None if value fails basic id format validation
    """
    if isinstance(value, string_types) and ':' in value:
        temp = value.split(':')
        if 2 == len(temp) and None not in [try_int(_x, None) for _x in temp]:
            return value


class Referential(object):
    """
    This class superimposes handling for a string based ID named `ref_id`.

    __init__ will pass back control untouched to the object deriving
    from this one if an integer is passed so that integer ID can peform
    """

    def __init__(self, sid=None):
        self.id = None  # type: integer_types
        self.ids = {}  # type: Dict[int, integer_types]
        self._rid = usable_rid(sid)

    def has_ref_id(self, item):
        if isinstance(item, integer_types):
            return self.id == item

        tvid, src_id = self.ref_id(rid=item, string=False)
        return self.ids.get(tvid) == src_id

    def ref_id(self,
               rid=None,  # type: Optional[AnyStr, int]
               string=True  # type: Optional[bool]
               ):  # type: (...) -> Union[tuple[Optional[AnyStr, int], Optional[AnyStr, int]], AnyStr]
        """
        return either,
         1) a prefered external unique id for a consistent reliable `reference`, or the internal row id as fallback
         2) convert a consistent `reference` to src and src_id to use for matching to an internal row id
            uses param rid or self._rid as reference id to convert if either is not Nonetype

        for example,
         1) if string is False, prefered static tuple[tvid, id], or tuple[None, id] if ids not set
         2)          otherwise, prefered static 'tvid:id', or 'id' if ids not set
         3) if string is False and self._rid contains ':', list[src, src_id]
         4)           otherwise if self._rid contains ':', list['src', 'src_id']

        reason, a row id is highly volatile, but a prefered ID is more reliable.
        use cases,
         show removed and readded, or src switched, then refreshing any character/person views will be consistent.
         can share/save a character/person link/bookmark as it will be consistent across instances.
         cast glide startAt is unreliable using glide index or row id.
         """
        # if self._rid is a temporary type string containing ':' (use case during init)
        # return it as a tuple[int, int] -> src, src_id
        rid = rid or self._rid
        if usable_rid(rid):
            self._rid = None  # consume once
            parts = [try_int(_x, None) for _x in rid.split(':')]

            # if string: no usage for this case
            #     ? return rid
            #     ? return '%s' % parts[0], '%s' % parts[1]
            return parts[0], parts[1]

        # get an available id from an order of preferred ids for use
        if self.ids:
            for cur_tvid in [TVINFO_IMDB, TVINFO_TVMAZE, TVINFO_TMDB, TVINFO_TRAKT]:
                if self.ids.get(cur_tvid):
                    if string:
                        return '%s:%s' % (cur_tvid, self.ids.get(cur_tvid))
                    return cur_tvid, self.ids.get(cur_tvid)
        if string:
            return '%s' % self.id
        return None, self.id  # default internal id has no slug


class Person(Referential):
    def __init__(
            self,
            name=None,  # type: AnyStr
            gender=PersonGenders.UNKNOWN,  # type: int
            birthday=None,  # type: datetime.date
            deathday=None,  # type: datetime.date
            bio=None,  # type: AnyStr
            ids=None,  # type: Dict[int, integer_types]
            sid=None,  # type: integer_types
            birthplace=None,  # type: AnyStr
            homepage=None,  # type: AnyStr
            image_url=None,  # type: AnyStr
            thumb_url=None,  # type: AnyStr
            show_obj=None,  # type: TVShow
            updated=1,  # type: integer_types
            deathplace=None,  # type: AnyStr
            height=None,  # type: Union[integer_types, float]
            real_name=None,  # type: AnyStr
            nicknames=None,  # type: Set[AnyStr]
            akas=None,  # type: Set[AnyStr]
            character_obj=None,  # type: Character
            tmp_character_obj=None  # type: Character
    ):  # type: (...) -> Person

        super(Person, self).__init__(sid)

        self.updated = updated  # type: integer_types
        self._data_failure = False  # type: bool
        self._data_fetched = False  # type: bool
        self.name = name  # type: AnyStr
        self.character_obj = character_obj  # type: Optional[Character]
        self._tmp_character_obj = tmp_character_obj  # type: Optional[Character]
        self.gender = (PersonGenders.UNKNOWN, gender)[gender in PersonGenders.possible_values]  # type: int
        self.birthday = birthday  # type: Optional[datetime.date]
        self.deathday = deathday  # type: Optional[datetime.date]
        self.biography = bio  # type: Optional[AnyStr]
        self.birthplace = birthplace  # type: Optional[AnyStr]
        self.homepage = homepage  # type: Optional[AnyStr]
        self.image_url = image_url  # type: Optional[AnyStr]
        self.thumb_url = thumb_url  # type: Optional[AnyStr]
        self.deathplace = deathplace  # type: Optional[AnyStr]
        self.height = height  # type: Optional[Union[integer_types, float]]
        self.real_name = real_name  # type: Optional[AnyStr]
        self.nicknames = nicknames or set()  # type: Set[AnyStr]
        self.akas = akas or set()  # type: Set[AnyStr]
        self.ids = ids or {}  # type: Dict[int, integer_types]
        if not self._rid:
            self.id = sid or self._get_sid(show_obj=show_obj)  # type: integer_types
        new_dirty = not sid
        self.dirty_main = new_dirty  # type: bool
        self.dirty_ids = new_dirty  # type: bool
        if not sid and self.id:
            fetched = self._data_fetched
            cur_data = self._remember_properties()
            self.load_from_db()
            cur_data['ids'] = dict(chain.from_iterable(iteritems(d) for d in (self.ids, ids or {})))
            self.update_properties(**cur_data)
            self._data_fetched = fetched
        elif not self.name:
            self.load_from_db()

    @staticmethod
    def _order_names(name_set):
        # type: (Set[AnyStr]) -> List[AnyStr]
        rc_aka = re.compile(r'[\x00-\x7f]+')

        aka_all_ascii = []
        aka_non_ascii = []

        for cur_aka in name_set or []:
            if rc_aka.match(cur_aka):
                aka_all_ascii += [cur_aka]
            else:
                aka_non_ascii += [cur_aka]

        return aka_all_ascii + aka_non_ascii

    @property
    def lang_ordered_akas(self):
        # type: (...) -> List[AnyStr]
        return self._order_names(self.akas)

    @property
    def lang_ordered_nicknames(self):
        # type: (...) -> List[AnyStr]
        return self._order_names(self.nicknames)

    def _remember_properties(self):
        # type: (...) -> Dict
        return {k: self.__dict__[k] for k in
                ['akas', 'biography', 'birthday', 'birthplace', 'deathday', 'deathplace', 'gender', 'height',
                 'homepage', 'ids', 'image_url', 'name', 'nicknames', 'real_name', 'thumb_url']}

    def reset(self, person_obj=None):
        # type: (TVINFO_Person) -> None
        """
        reset all properties with the exception of: name, id, ids

        :param person_obj: TVInfo Person object to reset to
        """
        self._data_failure = False
        self._data_fetched = False
        self.akas = person_obj.akas or set()
        self.biography = person_obj.bio or None
        self.birthday = person_obj.birthdate or None
        self.birthplace = person_obj.birthplace or None
        self.deathday = person_obj.deathdate or None
        self.deathplace = person_obj.deathplace or None
        self.dirty_main = True
        self.gender = person_obj.gender or PersonGenders.UNKNOWN
        self.height = person_obj.height or None
        self.homepage = person_obj.homepage or None
        self.image_url = person_obj.image or None
        self.nicknames = person_obj.nicknames or set()
        self.real_name = person_obj.real_name or None
        self.thumb_url = person_obj.thumb_url or None
        self.updated = 1

    def _get_sid(self, mass_action_result=None, show_obj=None):
        # type: (List, TVShow) -> Optional[integer_types]
        if getattr(self, 'id', None):
            return self.id

        def _get_from_ids():
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT person_id
                FROM person_ids
                WHERE %s
                """ % ' OR '.join(['( src = ? AND src_id = ? )'] * len(self.ids)),
                list(reduce(lambda a, b: a + b, iteritems(self.ids))))
            for cur_id in sql_result or []:
                return cur_id['person_id']

        if mass_action_result:
            try:
                return mass_action_result[-1:][0][0]['last_rowid']
            except (BaseException, Exception):
                return
        elif self.ids:
            i = _get_from_ids()
            if i:
                return i
        self.get_missing_data(show_obj=show_obj)
        if self.ids:
            return _get_from_ids()

    def _set_updated(self):
        # type: (...) -> integer_types
        """
        set and return new update date
        """
        self.updated = datetime.date.today().toordinal() - (0, 120)[self._data_failure]
        return self.updated

    def remove_img(self):
        """
        removes image of person
        """
        try:
            remove_file_perm(image_cache.ImageCache().person_path(self))
        except (BaseException, Exception):
            pass

    def remove_thumb(self):
        """
        removes thumb image of person
        """
        try:
            remove_file_perm(image_cache.ImageCache().person_thumb_path(self))
        except (BaseException, Exception):
            pass

    def remove_all_img(self):
        """
        remove all images of person
        """
        try:
            for r in image_cache.ImageCache().person_both_paths(self):
                try:
                    remove_file_perm(r)
                except (BaseException, Exception):
                    pass
        except (BaseException, Exception):
            pass

    def update_properties(self, **kwargs):
        """
        updates properties of class, if changed sets dirty
        :param kwargs: properties of class
        """
        if (not self.image_url and not self.thumb_url) or (not self.image_url and kwargs.get('image_url')):
            if kwargs.get('image_url'):
                self.dirty_main = True
                self.remove_img()
                self.image_url = kwargs.get('image_url')
                # thumb changed, remove old image
                if kwargs.get('thumb_url'):
                    self.remove_thumb()
                    self.thumb_url = kwargs.get('thumb_url')
                else:
                    self.remove_thumb()
                    self.thumb_url = None
            elif kwargs.get('thumb_url'):
                self.dirty_main = True
                self.thumb_url = kwargs.get('thumb_url')
                # image changed remove old image
                self.remove_img()
                if kwargs.get('image_url'):
                    self.remove_img()
                    self.image_url = kwargs.get('image_url')
                else:
                    self.remove_img()
                    self.image_url = None

        for k, v in iteritems(kwargs):
            if k in ('image_url', 'thumb_url'):
                continue
            if k not in self.__dict__:
                raise Exception('Person has no property [%s]' % k)
            if None is not v:
                if 'akas' == k:
                    v.update(self.akas)
                elif 'nicknames' == k:
                    v.update(self.nicknames)
                if v != self.__dict__[k]:
                    if 'biography' == k:
                        if len(v) > len(self.biography or ''):
                            self.biography = v
                            self.dirty_main = True
                    elif 'gender' == k and v not in (PersonGenders.male, PersonGenders.female):
                        continue
                    else:
                        self.__dict__[k] = v
                    if 'ids' == k:
                        self.dirty_ids = True
                    else:
                        self.dirty_main = True

    def load_from_db(self):
        if self.id or usable_rid(self._rid):
            my_db = db.DBConnection()
            src, src_id = self.ref_id(string=False)
            sql_result = my_db.select(
                """
                SELECT persons.*,
                (SELECT group_concat(person_ids.src || ':' || person_ids.src_id, ';;;')
                 FROM person_ids 
                 WHERE person_ids.person_id = persons.id) AS p_ids
                FROM persons
                LEFT JOIN person_ids pi ON persons.id = pi.person_id
                WHERE %s
                """ % ('pi.src = ? and pi.src_id = ?', 'persons.id = ?')[not src],
                ([src, src_id], [self.id])[not src])

            for cur_person in sql_result or []:
                birthdate = try_int(cur_person['birthdate'], None)
                birthdate = birthdate and datetime.date.fromordinal(cur_person['birthdate'])
                deathdate = try_int(cur_person['deathdate'], None)
                deathdate = deathdate and datetime.date.fromordinal(cur_person['deathdate'])

                p_ids = {}
                for cur_ids in (cur_person['p_ids'] and cur_person['p_ids'].split(';;;')) or []:
                    k, v = cur_ids.split(':')
                    k = try_int(k, None)
                    if v and None is not k:
                        p_ids[k] = v if k in (TVINFO_FACEBOOK, TVINFO_INSTAGRAM, TVINFO_TWITTER, TVINFO_WIKIPEDIA) \
                            else try_int(v, None)

                (self._data_failure, self._data_fetched,
                 self.akas, self.biography,
                 self.birthday, self.birthplace, self.deathday, self.deathplace,
                 self.gender, self.height, self.homepage,
                 self.id, self.ids, self.image_url, self.name,
                 self.nicknames,
                 self.real_name, self.thumb_url, self.updated) = \
                    (False, False,
                     set((cur_person['akas'] and cur_person['akas'].split(';;;')) or []), cur_person['bio'],
                     birthdate, cur_person['birthplace'], deathdate, cur_person['deathplace'],
                     cur_person['gender'], cur_person['height'], cur_person['homepage'],
                     cur_person['id'], p_ids, cur_person['image_url'], cur_person['name'],
                     set((cur_person['nicknames'] and cur_person['nicknames'].split(';;;')) or []),
                     cur_person['realname'], cur_person['thumb_url'], cur_person['updated'])
                break

    def update_prop_from_tvinfo_person(self, person_obj):
        # type: (TVINFO_Person) -> None
        """
        update person with tvinfo person object info
        Note: doesn't change: name, id, image_url, thumb_url

        :param person_obj: TVInfo Person object
        """
        if person_obj:
            char_obj = self.character_obj or self._tmp_character_obj
            if person_obj.characters and char_obj and char_obj.show_obj \
                    and char_obj.show_obj.ids.get(TVINFO_IMDB, {}).get('id'):
                p_char = [pc for pc in person_obj.characters
                          if pc.show.ids.imdb == char_obj.show_obj.ids.get(TVINFO_IMDB, {}).get('id')]
                p_count = len(p_char)
                if 1 == p_count:
                    if (p_char[0].start_year or p_char[0].end_year) and getattr(self, 'id', None):
                        char_obj.combine_start_end_years(
                            {self.id: {'start': p_char[0].start_year, 'end': p_char[0].end_year}})
                elif 1 < p_count:
                    start, end, found, p_p = None, None, False, None
                    for c_p in p_char:
                        if not start or start > (c_p.start_year or 3000):
                            start = c_p.start_year
                        if not end or end < (c_p.end_year or 0):
                            end = c_p.end_year
                        if c_p.name == char_obj.name:
                            start = c_p.start_year
                            end = c_p.end_year
                            found = True
                            break
                    if not found:
                        try:
                            p_p = sorted([
                                (fuzz.UWRatio(char_obj.name, p.name),
                                 p.end_year and p.start_year and p.end_year - p.start_year, p) for p in p_char],
                                key=lambda a: (a[0], a[1]), reverse=True)[0][2]
                        except (BaseException, Exception):
                            p_p = None
                    if None is not p_p and (p_p.start_year or p_p.end_year):
                        start = p_p.start_year
                        end = p_p.end_year
                    if (start or end) and getattr(self, 'id', None):
                        char_obj.combine_start_end_years({self.id: {'start': start, 'end': end}})
            self.update_properties(
                gender=person_obj.gender, homepage=person_obj.homepage,
                ids=dict(chain.from_iterable(
                    iteritems(d) for d in (self.ids, {k: v for k, v in iteritems(person_obj.ids)
                                                      if v and TVINFO_SLUG != k} or {}))),
                birthday=person_obj.birthdate, deathday=person_obj.deathdate, biography=person_obj.bio,
                birthplace=person_obj.birthplace, deathplace=person_obj.deathplace, height=person_obj.height,
                real_name=person_obj.real_name, nicknames=person_obj.nicknames, akas=person_obj.akas
            )

    def get_missing_data(self, show_obj=None, character_obj=None, stop_event=None, force_id=False):
        # type: (TVShow, Character, threading.Event, bool) -> None
        """
        load missing data for person from trakt + tmdb

        :param show_obj:
        :param character_obj:
        :param stop_event:
        :param force_id: refetch all external ids, normally only source ids and missing are fetched
        """
        if character_obj and not self.character_obj:
            self.character_obj = character_obj
        if self._data_failure:
            self.dirty_main = True
        self._data_failure = False
        self._data_fetched = True
        tvsrc_result, found_persons, found_on_src, search_sources, found_ids, ids_to_check, tv_loop, imdb_confirmed, \
            source_confirmed = \
            None, {}, set(), [TVINFO_TRAKT, TVINFO_TMDB, TVINFO_IMDB], \
            set([k for k, v in iteritems(self.ids) if v] + ['text']), {}, 0, False, {}
        # confirmed_character =  False
        max_search_src = len(search_sources)
        logger.debug('Getting extra data for: %s' % self.name)
        for tv_loop in moves.xrange(0, max_search_src):
            search_sources = [s for s in search_sources if s not in found_on_src]
            for cur_tv_info_src in search_sources:
                if stop_event and stop_event.is_set():
                    return
                rp, confirmed_on_src = None, False
                tvinfo_config = sickbeard.TVInfoAPI(cur_tv_info_src).api_params.copy()
                t = sickbeard.TVInfoAPI(cur_tv_info_src).setup(**tvinfo_config)
                if 0 == tv_loop or cur_tv_info_src not in ids_to_check:
                    ids_to_check[cur_tv_info_src] = t.supported_person_id_searches + ['text']
                    found_persons[cur_tv_info_src] = set()
                for tv_src in ids_to_check[cur_tv_info_src]:
                    if 'text' != tv_src and not self.ids.get(tv_src):
                        continue
                    try:
                        if 'text' != tv_src:
                            kw = {'ids': {tv_src: self.ids[tv_src]}}
                        else:
                            kw = {'name': self.name}
                        tvsrc_result = t.search_person(**kw)
                    except (BaseException, Exception):
                        self._data_failure = True
                        continue
                    if tvsrc_result:
                        # verify we have the correct person
                        for cur_person in tvsrc_result:  # type: TVINFO_Person
                            if None is not rp:
                                break
                            if not (imdb_confirmed and TVINFO_IMDB == tv_src) \
                                    and cur_person.id in found_persons[cur_tv_info_src]:
                                continue
                            found_persons[cur_tv_info_src].add(cur_person.id)
                            try:
                                pd = t.get_person(cur_person.ids.get(cur_tv_info_src),
                                                  get_show_credits=True, get_images=True)
                            except (BaseException, Exception) as e:
                                self._data_failure = True
                                logger.warning('Error searching extra info for person: %s - %s' % (self.name, ex(e)))
                                continue
                            if None is not pd and imdb_confirmed and TVINFO_IMDB == tv_src:
                                rp = pd
                                break
                            # noinspection PyUnresolvedReferences
                            if show_obj and None is not pd and pd.characters:
                                clean_show_name = indexermapper.clean_show_name(show_obj.name.lower())
                                for ch in pd.characters or []:  # type: TVINFO_Character
                                    if clean_show_name == indexermapper.clean_show_name(ch.show.seriesname.lower()):
                                        rp = pd
                                        confirmed_on_src = True
                                        # confirmed_character = True
                                        break
                                    elif any(t_src == s_src and bool(t_id) and t_id == s_id['id']
                                             for t_src, t_id in iteritems(ch.show.ids)
                                             for s_src, s_id in iteritems(show_obj.ids)):
                                        rp = pd
                                        confirmed_on_src = True
                                        # confirmed_character = True
                                        break
                        if rp:
                            if TVINFO_IMDB == cur_tv_info_src and confirmed_on_src:
                                imdb_confirmed = True
                            found_on_src.add(cur_tv_info_src)
                            break

                ids_to_check[cur_tv_info_src] = [i for i in ids_to_check[cur_tv_info_src] if i not in found_ids]

                if None is not rp:
                    if confirmed_on_src:
                        for i in (TVINFO_TRAKT, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVMAZE, TVINFO_TVDB):
                            # in case it's the current source use it's id and lock if from being changed
                            if cur_tv_info_src == i and rp.ids.get(i):
                                source_confirmed[i] = True
                                if rp.ids.get(i) != self.ids.get(i):
                                    self.ids[i] = rp.ids[i]
                                    self.dirty_ids = True
                            if not source_confirmed.get(i) and \
                                    (rp.ids.get(i) and not self.ids.get(i) or
                                     (force_id and rp.ids.get(i) and rp.ids.get(i) != self.ids.get(i))):
                                self.ids[i] = rp.ids[i]
                                found_ids.add(i)
                                self.dirty_ids = True

                        for i in (TVINFO_INSTAGRAM, TVINFO_TWITTER, TVINFO_FACEBOOK, TVINFO_WIKIPEDIA):
                            if rp.social_ids.get(i) and not self.ids.get(i) or \
                                    (rp.social_ids.get(i) and rp.social_ids.get(i) != self.ids.get(i)):
                                self.ids[i] = rp.social_ids[i]
                                found_ids.add(i)
                                self.dirty_ids = True

                    self.update_prop_from_tvinfo_person(rp)
                    if not self.image_url and rp.image:
                        self.image_url = rp.image
                        if rp.thumb_url:
                            self.thumb_url = rp.thumb_url
                        else:
                            self.remove_thumb()
                            self.thumb_url = None
                        self.dirty_main = True
                    elif not self.thumb_url and rp.thumb_url:
                        self.thumb_url = rp.thumb_url
                        if not rp.image:
                            self.remove_img()
                            self.image_url = None
                        self.dirty_main = True

    def save_to_db(self, show_obj=None, character_obj=None, force=False, stop_event=None):
        # type: (TVShow, Character, bool, threading.Event) -> None
        if not self._data_fetched:
            self.get_missing_data(show_obj=show_obj, character_obj=character_obj, stop_event=stop_event)
        self._data_fetched = False
        if not any(d for d in (self.dirty_main, self.dirty_ids)):
            return
        my_db = db.DBConnection()
        if not self.id:
            cl = [[
                """
                INSERT INTO persons (akas, bio, birthdate, birthplace,
                deathdate, deathplace, gender, height, homepage,
                image_url, name, nicknames, realname, thumb_url,
                updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, [';;;'.join(self.akas or []), self.biography, _make_date(self.birthday), self.birthplace,
                      _make_date(self.deathday), self.deathplace, self.gender, self.height, self.homepage,
                      self.image_url, self.name, ';;;'.join(self.nicknames or []), self.real_name, self.thumb_url,
                      self._set_updated()]
            ]]
            c_ids = len(self.ids)
            if c_ids:
                f_d = next(iter(self.ids))
                cl.extend([[
                    """
                    INSERT INTO person_ids (src, src_id, person_id)
                    VALUES (?,?,last_insert_rowid())
                    """, [f_d, self.ids[f_d]]]
                ])
                if 1 < c_ids:
                    cl.extend([[
                        """
                        INSERT INTO person_ids (src, src_id, person_id)
                        VALUES (?,?, 
                         (SELECT person_ids.person_id FROM person_ids
                          WHERE person_ids.id = last_insert_rowid())
                        );
                        """, [s, self.ids[s]]] for s in list(self.ids)[1:]
                    ])
                cl.extend([[
                    """
                    SELECT person_ids.person_id AS last_rowid
                    FROM person_ids
                    WHERE person_ids.id = last_insert_rowid()
                    """]
                ])
            else:
                cl.extend([['SELECT last_insert_rowid() as last_rowid;']])
        else:
            cl = []
            if force or self.dirty_main:
                cl = [[
                    """
                    UPDATE persons
                     SET name = ?, gender = ?, birthdate = ?, deathdate = ?, bio = ?,
                     birthplace = ?, homepage = ?, image_url = ?, thumb_url = ?, updated = ?,
                     deathplace = ?, height = ?, realname = ?, nicknames = ?, akas = ?
                    WHERE id = ?
                    """,
                    [self.name, self.gender, _make_date(self.birthday), _make_date(self.deathday), self.biography,
                     self.birthplace, self.homepage, self.image_url, self.thumb_url,
                     self._set_updated(), self.deathplace, self.height, self.real_name,
                     ';;;'.join(self.nicknames or []), ';;;'.join(self.akas or []), self.id]],
                ]
            if force or self.dirty_ids:
                for s, v in iteritems(self.ids):
                    cl.extend([
                        ['UPDATE person_ids SET src_id = ? WHERE person_id = ? AND src = ?', [v, self.id, s]],
                        ["INSERT INTO person_ids (src, src_id, person_id) SELECT %s, '%s', %s WHERE changes() == 0"
                         % (s, v, self.id)]
                    ])
        if cl:
            r_id = my_db.mass_action(cl)
            if r_id and r_id[-1:][0]:
                self.id = self._get_sid(r_id)
            self.dirty_main, self.dirty_ids = False, False

    def calc_age(self, date=None):
        # type: (Optional[datetime.date]) -> Optional[int]
        """
        returns age based on current date or given date
        :param date:
        """
        return calc_age(self.birthday, self.deathday, date)

    @property
    def age(self):
        # type: (...) -> Optional[int]
        """
        :return: age of person if birthdate is known, in case of deathdate is known return age of death
        """
        return self.calc_age()

    def __bool__(self):
        return bool(self.name)

    def __eq__(self, other):
        return (self.id not in [None, 0] and other.id == self.id) \
               and any(self.ids[o] == v for o, v in iteritems(other.ids))

    def __str__(self):
        lived, id_str, id_list = '', '', []
        if self.birthday:
            lived += ' %s' % self.birthday
        if self.deathday:
            lived += ' - %s' % self.deathday
        for i, d in iteritems(self.ids):
            id_list.append('%s: %s' % (sickbeard.TVInfoAPI(i).name, d))
        if id_list:
            id_str = ' (%s)' % ', '.join(id_list)
        return '<Person %s%s%s>' % (self.name, lived, id_str)

    def __repr__(self):
        return self.__str__()

    __nonzero__ = __bool__


class Character(Referential):
    def __init__(
            self,
            name=None,  # type: AnyStr
            person=None,  # type: List[Person]
            ids=None,  # type: Dict[int, integer_types]
            bio=None,  # type: AnyStr
            sid=None,  # type: integer_types
            image_url=None,  # type: AnyStr
            thumb_url=None,  # type: AnyStr
            show_obj=None,  # type: TVShow
            updated=1,  # type: integer_types
            persons_years=None,  # type: Dict[integer_types, Dict[AnyStr, int]]
            tmp=False  # type:bool
    ):  # type: (...) -> Character

        super(Character, self).__init__(sid)

        self.updated = updated  # type: integer_types
        self.name = name  # type: AnyStr
        self.persons_years = persons_years or {}  # type: Dict[integer_types, Dict[AnyStr, int]]
        self.person = person or []  # type: List[Person]
        self.biography = bio  # type: Optional[AnyStr]
        self.ids = ids or {}  # type: Dict[int, integer_types]
        self.image_url = image_url  # type: Optional[AnyStr]
        self.thumb_url = thumb_url  # type: Optional[AnyStr]
        self.show_obj = show_obj  # type: TVShow
        if not tmp:
            if not self._rid:
                self.id = sid or self._get_sid()  # type: integer_types
            new_dirty = not sid
            self.dirty_main = new_dirty  # type: bool
            self.dirty_ids = new_dirty  # type: bool
            self.dirty_person = new_dirty  # type: bool
            self.dirty_years = new_dirty  # type: bool
            if not sid and self.id:
                self.load_from_db()
                self.update_properties(name=name, person=person, biography=bio,
                                       ids=dict(chain.from_iterable(iteritems(d) for d in (self.ids, ids or {}))),
                                       image_url=image_url, thumb_url=thumb_url)
            elif not self.name:
                self.load_from_db()

    def _get_sid(self, mass_action_result=None):
        # type: (List) -> Optional[integer_types]
        if getattr(self, 'id', None):
            return self.id

        if mass_action_result:
            try:
                return mass_action_result[-1:][0][0]['last_rowid']
            except (BaseException, Exception):
                return
        elif self.ids:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT character_id 
                FROM character_ids 
                WHERE %s
                """ % ' OR '.join(['( src = ? AND src_id = ? )'] * len(self.ids)),
                list(reduce(lambda a, b: a+b, iteritems(self.ids))))
            if sql_result:
                return sql_result[0]['character_id']
        elif self.person:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT characters.id AS c_id 
                FROM characters
                LEFT JOIN character_person_map cpm ON characters.id = cpm.character_id
                WHERE name = ? AND cpm.person_id IN (%s)
                """ % ','.join(['?' * len(self.person)]),
                [self.name] + [p.id for p in self.person])
            if sql_result:
                return sql_result[0]['c_id']

    def _set_updated(self):
        # type: (...) -> integer_types
        """
        set and return new update date
        """
        self.updated = datetime.date.today().toordinal()
        return self.updated

    def remove_img(self):
        """
        removes image of person
        """
        try:
            remove_file_perm(image_cache.ImageCache().character_path(self, self.show_obj))
        except (BaseException, Exception):
            pass

    def remove_thumb(self):
        """
        removes thumb image of person
        """
        try:
            remove_file_perm(image_cache.ImageCache().character_thumb_path(self, self.show_obj))
        except (BaseException, Exception):
            pass

    def remove_all_img(self, include_person=False, tvid=None, proid=None):
        # type: (bool, integer_types, integer_types) -> None
        """
        remove all images of person
        """
        try:
            for r in image_cache.ImageCache().character_both_path(self, show_obj=self.show_obj, tvid=tvid, proid=proid):
                try:
                    remove_file_perm(r)
                except (BaseException, Exception):
                    pass
        except (BaseException, Exception):
            pass
        if include_person:
            for p in self.person or []:
                try:
                    p.remove_all_img()
                except (BaseException, Exception):
                    pass

    def update_properties(self, **kwargs):
        for k, v in iteritems(kwargs):
            if k not in self.__dict__:
                raise Exception('Character has no property [%s]' % k)
            if None is not v and v != self.__dict__[k]:
                if 'image_url' == k:
                    self.dirty_main = True
                    self.remove_img()
                    if not kwargs.get('thumb_url'):
                        self.remove_thumb()
                        self.thumb_url = None
                elif 'thumb_url' == k:
                    self.dirty_main = True
                    self.remove_thumb()
                    if not kwargs.get('image_url'):
                        self.remove_img()
                        self.image_url = None
                self.__dict__[k] = v
                if 'ids' == k:
                    self.dirty_ids = True
                elif 'person' == k:
                    self.dirty_person = True
                else:
                    self.dirty_main = True

    def combine_start_end_years(self, new_years):
        # type: (Dict[integer_types, Dict[AnyStr, int]]) -> None
        new_dict = dict(chain.from_iterable(
                    iteritems(d) for d in (self.persons_years, {k: v for k, v in iteritems(new_years) if v} or {})))
        if new_dict != self.persons_years:
            self.persons_years = new_dict
            self.dirty_years = True

    def load_from_db(self):
        if self.id or usable_rid(self._rid):
            my_db = db.DBConnection()
            src, src_id = self.ref_id(string=False)
            sql_result = my_db.select(
                """
                SELECT characters.name AS name, characters.bio AS bio,
                characters.thumb_url AS thumb_url, characters.image_url AS image_url,
                characters.updated AS c_updated, characters.id AS c_id,
                (SELECT group_concat(character_ids.src || ':' || character_ids.src_id, ';;;')
                FROM character_ids WHERE character_ids.character_id = characters.id) AS c_ids,
                (SELECT group_concat(character_person_map.person_id, ';;;')
                FROM character_person_map
                WHERE character_person_map.character_id = characters.id) AS person_ids,
                (SELECT group_concat(character_person_years.person_id || ':' ||
                character_person_years.start_year || '-' || character_person_years.end_year, ';;;')
                FROM character_person_years WHERE character_person_years.character_id = characters.id)
                AS p_years
                FROM characters
                LEFT JOIN character_ids ci ON characters.id = ci.character_id
                WHERE %s
                """ % ('ci.src = ? and ci.src_id = ?', 'characters.id = ?')[not src],
                ([src, src_id], [self.id])[not src])

            for cur_row in (sql_result or []):
                c_ids = {}
                for cur_ids in (cur_row['c_ids'] and cur_row['c_ids'].split(';;;')) or []:
                    k, v = cur_ids.split(':')
                    v = try_int(v, None)
                    if v:
                        c_ids[int(k)] = try_int(v, None)

                p_years = {}
                for cur_years in (cur_row['p_years'] and cur_row['p_years'].split(';;;')) or []:
                    p_id, py = cur_years.split(':')
                    start, end = py.split('-')
                    p_years[int(p_id)] = {'start': try_int(start, None), 'end': try_int(end, None)}

                (self.biography, self.id, self.ids, self.image_url, self.name,
                 self.person,
                 self.persons_years, self.thumb_url, self.updated) = \
                    (cur_row['bio'], cur_row['c_id'], c_ids, cur_row['image_url'], cur_row['name'],
                     [Person(sid=int(p), character_obj=self)
                      for p in (cur_row['person_ids'] and cur_row['person_ids'].split(';;;')) or []],
                     p_years, cur_row['thumb_url'], cur_row['c_updated'])

                self.dirty_main, self.dirty_ids, self.dirty_person = False, False, False
                break

    def _get_start_end_year(self):
        if self.person:
            tvinfo_config = sickbeard.TVInfoAPI(TVINFO_IMDB).api_params.copy()
            t = sickbeard.TVInfoAPI(TVINFO_IMDB).setup(**tvinfo_config)
            for cur_per in self.person:
                if not cur_per.id:
                    continue
                if cur_per.ids.get(TVINFO_IMDB):
                    try:
                        res = t.get_person(cur_per.ids.get(TVINFO_IMDB), get_show_credits=True)
                    except (BaseException, Exception):
                        continue
                    if res and res.characters:
                        cur_per.character_obj = self
                        cur_per.update_prop_from_tvinfo_person(res)

    def save_to_db(self, show_obj=None, force=False, stop_event=None):
        # type: (TVShow, bool, threading.Event) -> None
        if self.person:
            for cur_per in self.person:
                if stop_event and stop_event.is_set():
                    return
                if force or self.dirty_person or not cur_per.id or cur_per.dirty_main or cur_per.dirty_ids or \
                        14 < (datetime.date.today().toordinal() - cur_per.updated):
                    cur_per.save_to_db(show_obj=show_obj, character_obj=self, force=force, stop_event=stop_event)
                    self.dirty_person = True

        if ((None is self.id and not self.persons_years)
                or self.dirty_main or 14 < datetime.date.today().toordinal() - self.updated) and self.person:
            self._get_start_end_year()

        my_db = db.DBConnection()
        if not self.id:
            cl = [[
                """
                INSERT INTO characters (bio, image_url, name, thumb_url, updated)
                VALUES (?,?,?,?,?)
                """, [self.biography, self.image_url, self.name, self.thumb_url, self._set_updated()]],
                 ]
            c_ids = len(self.ids)
            if c_ids:
                f_d = next(iter(self.ids))
                cl.extend([[
                    """
                    INSERT INTO character_ids (src, src_id, character_id)
                    VALUES (?,?,last_insert_rowid())
                    """, [f_d, self.ids[f_d]]]
                ])
                if 1 < c_ids:
                    cl.extend([[
                        """
                        INSERT INTO character_ids (src, src_id, character_id)
                        VALUES (?,?,
                         (SELECT character_ids.character_id FROM character_ids
                          WHERE character_ids.id = last_insert_rowid())
                         );
                        """, [s, self.ids[s]]] for s in list(self.ids)[1:]
                    ])
                cl.extend([[
                    """
                    SELECT character_ids.character_id AS last_rowid
                    FROM character_ids
                    WHERE character_ids.id = last_insert_rowid()
                    """]
                ])
            else:
                cl.extend([['SELECT last_insert_rowid() AS last_rowid;']])
        else:
            cl = []
            if force or self.dirty_main:
                cl = [[
                    """
                    UPDATE characters SET bio = ?, image_url = ?, name = ?, thumb_url = ?, updated = ?
                    WHERE id = ?
                    """, [self.biography, self.image_url, self.name, self.thumb_url, self._set_updated(), self.id]],
                ]
            if force or self.dirty_ids:
                for cur_tvid, cur_src_id in iteritems(self.ids):
                    cl.extend([[
                        """
                        UPDATE character_ids SET src_id = ?
                        WHERE src = ? AND character_id = ? 
                        """, [cur_src_id, cur_tvid, self.id]
                    ], [
                        """
                        INSERT INTO character_ids (src, src_id, character_id)
                        SELECT %s, %s, %s WHERE changes() == 0
                        """ % (cur_tvid, cur_src_id, self.id)]
                    ])

        # in case we don't have a character id yet, we need to fetch it for the next step
        if not self.id and cl:
            r_id = my_db.mass_action(cl)
            cl = []
            if r_id and r_id[-1:][0]:
                # r_id = list(itertools.chain.from_iterable(r_id))
                if r_id:
                    self.id = self._get_sid(r_id)

        if (force or self.dirty_person) and self.person:
            cl.append([
                """
                DELETE FROM character_person_map
                WHERE character_id = ? AND person_id NOT IN (%s)
                """ % ','.join(['?'] * len(self.person)),
                [self.id] + [p.id for p in self.person]])
            for cur_per in self.person:
                cl.extend([[
                    """
                    INSERT OR IGNORE INTO character_person_map (character_id, person_id)
                    VALUES (?,?)
                    """, [self.id, cur_per.id]]
                ])

        if (force or self.dirty_years) and self.person:
            cl.append([
                """
                DELETE FROM character_person_years
                WHERE character_id = ? AND person_id NOT IN (%s)
                """ % ','.join(['?'] * len(self.person)),
                [self.id] + [p.id for p in self.person]])
            for cur_per in self.person:
                if cur_per.id and any(1 for v in itervalues(self.persons_years.get(cur_per.id, {})) if v):
                    p_years = self.persons_years.get(cur_per.id, {})
                    cl.append([
                        """
                        REPLACE INTO character_person_years (character_id, person_id, start_year, end_year)
                        VALUES (?,?,?,?)
                        """, [self.id, cur_per.id, p_years.get('start'), p_years.get('end')]]
                    )

        if cl:
            my_db.mass_action(cl)
            self.dirty_ids, self.dirty_main, self.dirty_person, self.dirty_years = False, False, False, False

    def __bool__(self):
        return bool(self.name) or bool(self.person) or bool(self.ids)

    def __eq__(self, other):
        return other.person == self.person and ((self.id not in [None, 0] and other.id == self.id)
                                                or any(self.ids[o] == v for o, v in iteritems(other.ids))
                                                or (not other.ids and other.name == self.name))

    def __str__(self):
        id_str, id_list = '', []
        for i, d in iteritems(self.ids):
            id_list.append('%s: %s' % (sickbeard.TVInfoAPI(i).name, d))
        if id_list:
            id_str = ' (%s)' % ', '.join(id_list)
        return '<Character %s (%s)%s>' % (self.name, ', '.join(p.name for p in self.person), id_str)

    def __repr__(self):
        return self.__str__()

    __nonzero__ = __bool__


class TVShow(TVShowBase):
    __slots__ = (
        'path',
        'unique_name',
    )

    def __init__(self, tvid, prodid, lang='', show_result=None, imdb_info_result=None):
        # type: (int, int, Text, Optional[Row], Optional[Union[Row, Dict]]) -> None
        super(TVShow, self).__init__(tvid, prodid, lang)

        self.unique_name = ''
        self.tvid = int(tvid)
        self.prodid = int(prodid)
        self.sid_int = self.create_sid(self.tvid, self.prodid)
        if None is not helpers.find_show_by_id(self.sid_int, check_multishow=True):
            raise exceptions_helper.MultipleShowObjectsException('Can\'t create a show if it already exists')

        self._airtime = None  # type: Optional[datetime.time]
        self._cast_list = None  # type: Optional[List[Character]]
        self._last_found_on_indexer = -1  # type: int
        self._location = self.path = ''  # type: AnyStr
        # self._is_location_good = None
        self._network_country = None  # type: Optional[AnyStr]
        self._network_country_code = None  # type: Optional[AnyStr]
        self._network_id = None  # type: Optional[int]
        self._network_is_stream = None  # type: Optional[bool]
        self._not_found_count = None  # type: None or int
        self._paused = 0
        self._src_update_time = None  # type: Optional[integer_types]

        self.internal_ids = {}  # type: Dict
        self.internal_timezone = None  # type: Optional[AnyStr]
        self.lock = threading.RLock()
        self.nextaired = ''  # type: AnyStr
        # noinspection added so that None _can_ be excluded from type annotation
        # so that this property evaluates directly to the class on ctrl+hover instead of "multiple implementations"
        # noinspection PyTypeChecker
        self.release_groups = None  # type: AniGroupList
        self.sxe_ep_obj = {}  # type: Dict

        self.load_from_db(show_result=show_result, imdb_info_result=imdb_info_result)

    def _get_end_episode(self, last=False, exclude_specials=False):
        # type: (bool, bool) -> Optional[TVEpisode]
        eps = self.get_all_episodes()
        if eps:
            ed = datetime.date(1900, 1, 1)
            return next(iter(sorted((ep for ep in eps if ep.airdate > ed and (not exclude_specials or ep.season != 0)),
                                    key=lambda a: a.airdate, reverse=last)), None)

    @property
    def first_aired_episode(self):
        # type: (...) -> Optional[TVEpisode]
        """
        returns first aired episode
        """
        return self._get_end_episode()

    @property
    def first_aired_regular_episode(self):
        # type: (...) -> Optional[TVEpisode]
        """
        returns first aired regular episode
        """
        return self._get_end_episode(exclude_specials=True)

    @property
    def latest_aired_episode(self):
        # type: (...) -> Optional[TVEpisode]
        """
        returns latest aired episode
        """
        return self._get_end_episode(last=True)

    @property
    def latest_aired_regular_episode(self):
        # type: (...) -> Optional[TVEpisode]
        """
        returns latest aired regular episode
        """
        return self._get_end_episode(last=True, exclude_specials=True)

    @property
    def cast_list(self):
        # type: (...) -> List[Character]
        if None is self._cast_list:
            self._load_cast_from_db()
        return self._cast_list

    @property
    def network_id(self):
        return self._network_id

    @network_id.setter
    def network_id(self, *args):
        self.dirty_setter('_network_id')(self, *args)

    @property
    def network_country(self):
        return self._network_country

    @network_country.setter
    def network_country(self, *args):
        self.dirty_setter('_network_country')(self, *args)

    @property
    def network_country_code(self):
        return self._network_country_code

    @network_country_code.setter
    def network_country_code(self, *args):
        self.dirty_setter('_network_country_code')(self, *args)

    @property
    def network_is_stream(self):
        return self._network_is_stream

    @network_is_stream.setter
    def network_is_stream(self, *args):
        self.dirty_setter('_network_is_stream')(self, *args)

    @property
    def airtime(self):
        return self._airtime

    @airtime.setter
    def airtime(self, *args):
        self.dirty_setter('_airtime')(self, *args)

    @property
    def timezone(self):
        return self.internal_timezone

    @timezone.setter
    def timezone(self, *args):
        self.dirty_setter('internal_timezone')(self, *args)

    @staticmethod
    def create_sid(tvid, prodid):
        # type: (int, int) -> int
        return int(prodid) << prodid_bitshift | int(tvid)

    @property
    def _tvid(self):
        return self.tvid

    @_tvid.setter
    def _tvid(self, val):
        self.dirty_setter('tvid')(self, int(val))
        self.tvid_prodid = self.create_sid(val, self.prodid)
        # TODO: remove the following when indexer is gone
        # in deprecation transition, tvid also sets indexer so that existing uses continue to work normally
        self.dirty_setter('_indexer')(self, int(val))

    @property
    def _prodid(self):
        return self.prodid

    @_prodid.setter
    def _prodid(self, val):
        # type: (int) -> None
        self.dirty_setter('prodid')(self, int(val))
        self.tvid_prodid = self.create_sid(self.tvid, val)
        # TODO: remove the following when indexerid is gone
        # in deprecation transition, prodid also sets indexerid so that existing usages continue as normal
        self.dirty_setter('_indexerid')(self, int(val))

    @property
    def tvid_prodid(self):
        # type: (...) -> AnyStr
        return TVidProdid({self.tvid: self.prodid})()

    @tvid_prodid.setter
    def tvid_prodid(self, val):
        tvid_prodid_obj = TVidProdid(val)
        if getattr(self, 'tvid_prodid', None) != tvid_prodid_obj():
            self.tvid, self.prodid = tvid_prodid_obj.list
            self.dirty = True
        tvid_prodid_int = int(tvid_prodid_obj)
        if getattr(self, 'sid_int', None) != tvid_prodid_int:
            self.sid_int = tvid_prodid_int

    def helper_load_failed_db(self, sql_result=None):
        # type: (Optional[Row, Dict]) -> None
        if None is self._not_found_count or -1 == self._last_found_on_indexer:
            if sql_result and self.prodid == sql_result['indexer_id'] and self.tvid == sql_result['indexer']:
                sql_result = [sql_result]
            else:
                my_db = db.DBConnection()
                sql_result = my_db.select(
                    """
                    SELECT fail_count, last_success
                    FROM tv_shows_not_found
                    WHERE indexer = ? AND indexer_id = ?
                    """, [self.tvid, self.prodid])
            if sql_result:
                self._not_found_count = helpers.try_int(sql_result[0]['fail_count'])
                self._last_found_on_indexer = helpers.try_int(sql_result[0]['last_success'])
            else:
                self._not_found_count = 0
                self._last_found_on_indexer = 0

    @property
    def not_found_count(self):
        self.helper_load_failed_db()
        return self._not_found_count

    @not_found_count.setter
    def not_found_count(self, v):
        if isinstance(v, integer_types) and v != self._not_found_count:
            self._last_found_on_indexer = self.last_found_on_indexer
            my_db = db.DBConnection()
            # noinspection PyUnresolvedReferences
            last_check = int(timestamp_near(datetime.datetime.now()))
            # in case of flag change (+/-) don't change last_check date
            if abs(v) == abs(self._not_found_count):
                sql_result = my_db.select(
                    """
                    SELECT last_check
                    FROM tv_shows_not_found
                    WHERE indexer = ? AND indexer_id = ?
                    """, [self.tvid, self.prodid])
                if sql_result:
                    last_check = helpers.try_int(sql_result[0]['last_check'])
            my_db.upsert('tv_shows_not_found',
                         dict(fail_count=v, last_check=last_check, last_success=self._last_found_on_indexer),
                         dict(indexer=self.tvid, indexer_id=self.prodid))
            self._not_found_count = v

    @property
    def last_found_on_indexer(self):
        self.helper_load_failed_db()
        return (self._last_found_on_indexer, self.last_update_indexer)[0 >= self._last_found_on_indexer]

    def inc_not_found_count(self):
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT last_check
            FROM tv_shows_not_found
            WHERE indexer = ? AND indexer_id = ?
            """, [self.tvid, self.prodid])
        days = (show_not_found_retry_days - 1, 0)[abs(self.not_found_count) <= concurrent_show_not_found_days]
        if not sql_result or datetime.datetime.fromtimestamp(helpers.try_int(sql_result[0]['last_check'])) + \
                datetime.timedelta(days=days, hours=18) < datetime.datetime.now():
            self.not_found_count += (-1, 1)[0 <= self.not_found_count]

    def reset_not_found_count(self):
        if 0 != self.not_found_count:
            self._not_found_count = 0
            self._last_found_on_indexer = 0
            my_db = db.DBConnection()
            my_db.action(
                """
                DELETE FROM tv_shows_not_found
                WHERE indexer = ? AND indexer_id = ?
                """, [self.tvid, self.prodid])

    @property
    def paused(self):
        """
        :rtype: bool
        """
        return self._paused

    @paused.setter
    def paused(self, value):
        if value != self._paused:
            if isinstance(value, bool) or (isinstance(value, integer_types) and value in [0, 1]):
                self._paused = int(value)
                self.dirty = True
            else:
                logger.log('tried to set paused property to invalid value: %s of type: %s' % (value, type(value)),
                           logger.ERROR)

    @property
    def ids(self):
        if not self.internal_ids:
            acquired_lock = self.lock.acquire(False)
            if acquired_lock:
                try:
                    indexermapper.map_indexers_to_show(self)
                finally:
                    self.lock.release()
        return self.internal_ids

    @ids.setter
    def ids(self, value):
        if isinstance(value, dict):
            for k, v in iteritems(value):
                if k not in indexermapper.indexer_list or \
                        not isinstance(v, dict) or \
                        not isinstance(v.get('id'), integer_types) or \
                        not isinstance(v.get('status'), integer_types) or \
                        v.get('status') not in indexermapper.MapStatus.allstatus or \
                        not isinstance(v.get('date'), datetime.date):
                    return
            self.internal_ids = value

    @property
    def is_anime(self):
        # type: (...) -> bool
        return 0 < int(self.anime)

    @property
    def is_sports(self):
        # type: (...) -> bool
        return 0 < int(self.sports)

    @property
    def is_scene(self):
        # type: (...) -> bool
        return 0 < int(self.scene)

    def _get_location(self):
        # type: (...) -> AnyStr
        # no dir check needed if missing show dirs are created during post-processing
        if sickbeard.CREATE_MISSING_SHOW_DIRS:
            return self._location

        if ek.ek(os.path.isdir, self._location):
            return self._location

        raise exceptions_helper.ShowDirNotFoundException('Show folder does not exist: \'%s\'' % self._location)

    def _set_location(self, new_location):
        # type: (AnyStr) -> None
        logger.log('Setter sets location to %s' % new_location, logger.DEBUG)
        # Don't validate dir if user wants to add shows without creating a dir
        if sickbeard.ADD_SHOWS_WO_DIR or ek.ek(os.path.isdir, new_location):
            self.dirty_setter('_location')(self, new_location)
            self.path = new_location
            # self._is_location_good = True
        else:
            raise exceptions_helper.NoNFOException('Invalid folder for the show!')

    location = property(_get_location, _set_location)

    # delete references to anything that's not in the internal lists
    def flush_episodes(self):

        for cur_season_number in self.sxe_ep_obj:
            for cur_ep_number in self.sxe_ep_obj[cur_season_number]:
                # noinspection PyUnusedLocal
                ep_obj = self.sxe_ep_obj[cur_season_number][cur_ep_number]
                self.sxe_ep_obj[cur_season_number][cur_ep_number] = None
                del ep_obj

    def get_all_episodes(self, season=None, has_location=False, check_related_eps=True):
        # type: (Optional[integer_types], bool, bool) -> List[TVEpisode]
        """

        :param season: None or season number
        :param has_location:  return only with location
        :param check_related_eps: get related episodes
        :return: List of TVEpisode objects
        """
        sql_selection = 'SELECT *'

        if check_related_eps:
            # subselection to detect multi-episodes early, share_location > 0
            sql_selection += """
            , (SELECT COUNT (*)
               FROM tv_episodes
               WHERE showid = tve.showid AND indexer = tve.indexer AND season = tve.season AND location != ''
               AND location = tve.location AND episode != tve.episode
            ) AS share_location
            """

        sql_selection += ' FROM tv_episodes tve WHERE indexer = ? AND showid = ?'
        sql_parameter = [self.tvid, self.prodid]

        if None is not season:
            sql_selection += ' AND season = ?'
            sql_parameter += [season]

        if has_location:
            sql_selection += ' AND location != "" '

        # need ORDER episode ASC to rename multi-episodes in order S01E01-02
        sql_selection += ' ORDER BY season ASC, episode ASC'

        my_db = db.DBConnection()
        sql_result = my_db.select(sql_selection, sql_parameter)

        ep_obj_list = []
        for cur_row in sql_result:
            ep_obj = self.get_episode(int(cur_row['season']), int(cur_row['episode']), ep_result=[cur_row])
            if ep_obj:
                ep_obj.related_ep_obj = []
                if check_related_eps and ep_obj.location:
                    # if there is a location, check if it's a multi-episode (share_location > 0)
                    # and put into related_ep_obj
                    if 0 < cur_row['share_location']:
                        # noinspection SqlRedundantOrderingDirection
                        related_ep_sql_result = my_db.select(
                            """
                            SELECT * 
                            FROM tv_episodes
                            WHERE indexer = ? AND showid = ? AND season = ? AND location = ? AND episode != ? 
                            ORDER BY episode ASC
                            """, [self.tvid, self.prodid, ep_obj.season, ep_obj.location, ep_obj.episode])
                        for cur_ep_row in related_ep_sql_result:
                            related_ep_obj = self.get_episode(int(cur_ep_row['season']),
                                                              int(cur_ep_row['episode']),
                                                              ep_result=[cur_ep_row])
                            if related_ep_obj not in ep_obj.related_ep_obj:
                                ep_obj.related_ep_obj.append(related_ep_obj)
                ep_obj_list.append(ep_obj)

        return ep_obj_list

    def get_episode(self,
                    season=None,  # type: Optional[int]
                    episode=None,  # type: Optional[int]
                    path=None,  # type: Optional[AnyStr]
                    no_create=False,  # type: bool
                    absolute_number=None,  # type: Optional[int]
                    ep_result=None,  # type: Optional[List[Row]]
                    existing_only=False  # type: bool
                    ):  # type: (...) -> Optional[TVEpisode]
        """
        Initialise sxe_ep_obj with db fetched season keys, and then fill the TVShow episode property
        and return an TVEpisode object if no_create is False

        :param season: Season number
        :param episode: Episode number
        :param path: path to file episode
        :param no_create: return None instead of an instantiated TVEpisode object
        :param absolute_number: absolute number
        :param ep_result:
        :param existing_only: only return existing episodes
        :return: TVEpisode object
        """
        # if we get an anime get the real season and episode
        if self.is_anime and absolute_number and not season and not episode:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT season, episode
                FROM tv_episodes
                WHERE indexer = ? AND showid = ? AND absolute_number = ? AND season != 0
                LIMIT 2
                """, [self.tvid, self.prodid, absolute_number])

            if 1 != len(sql_result):
                msg = 'found for absolute number: %s in show: %s' % (absolute_number, self._name)
                if not len(sql_result):
                    logger.debug('No entries %s' % msg)
                else:
                    logger.error('Multiple entries %s' % msg)
                return

            season = int(sql_result[0]['season'])
            episode = int(sql_result[0]['episode'])
            logger.debug('Found episode by absolute_number: %s which is %sx%s' % (absolute_number, season, episode))

        if season not in self.sxe_ep_obj:
            self.sxe_ep_obj[season] = {}

        if episode not in self.sxe_ep_obj[season] or None is self.sxe_ep_obj[season][episode]:
            if no_create:
                return

            # logger.log('%s: An object for episode %sx%s did not exist in the cache, trying to create it' %
            #            (self.tvid_prodid, season, episode), logger.DEBUG)

            if path and not existing_only:
                ep_obj = TVEpisode(self, season, episode, path, show_result=ep_result)
            else:
                ep_obj = TVEpisode(self, season, episode, show_result=ep_result, existing_only=existing_only)

            if None is not ep_obj:
                self.sxe_ep_obj[season][episode] = ep_obj

        return self.sxe_ep_obj[season][episode]

    def _load_cast_from_db(self):
        # cast_list = []
        old_list = {c.id for c in self._cast_list or []}
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT castlist.sort_order AS sort_order, characters.name AS name,
            characters.bio AS c_bio, characters.id AS c_id,
            characters.image_url AS image_url, characters.thumb_url AS thumb_url,
            characters.updated AS c_updated,
            persons.name AS p_name, persons.gender AS gender, persons.bio AS p_bio,
            persons.birthdate AS birthdate, persons.thumb_url AS p_thumb,
            persons.image_url AS p_image, persons.deathdate AS deathdate, persons.id AS p_id,
            persons.birthplace AS birthplace, persons.updated AS p_updated,
            persons.deathplace AS deathplace, persons.height AS height,
            persons.realname AS realname, persons.nicknames AS nicknames,
            persons.akas AS akas,            
            (SELECT group_concat(person_ids.src || ':' || person_ids.src_id, ';;;')
            FROM person_ids WHERE person_ids.person_id = persons.id) AS p_ids,
            (SELECT group_concat(character_ids.src || ':' || character_ids.src_id, ';;;')
            FROM character_ids WHERE character_ids.character_id = characters.id) AS c_ids,
            (SELECT group_concat(character_person_years.person_id || ':' ||
            character_person_years.start_year || '-' || character_person_years.end_year, ';;;')
            FROM character_person_years WHERE
            character_person_years.character_id = characters.id) AS p_years
            FROM castlist
            LEFT JOIN character_person_map
            ON castlist.character_id = character_person_map.character_id
            LEFT JOIN characters ON character_person_map.character_id = characters.id
            LEFT JOIN persons ON character_person_map.person_id = persons.id
            WHERE castlist.indexer = ? AND castlist.indexer_id = ?
            ORDER BY castlist.sort_order       
            """, [self.tvid, self.prodid])
        self._cast_list = self._cast_list or []
        for cur_row in sql_result:
            existing_character = next(
                (c for c in self._cast_list or [] if None is not c.id and c.id == cur_row['c_id']),
                None)  # type: Optional[Character]
            birthdate = try_int(cur_row['birthdate'], None)
            birthdate = birthdate and datetime.date.fromordinal(cur_row['birthdate'])
            deathdate = try_int(cur_row['deathdate'], None)
            deathdate = deathdate and datetime.date.fromordinal(cur_row['deathdate'])
            p_years = {}
            for p in (cur_row['p_years'] and cur_row['p_years'].split(';;;')) or []:
                p_id, py = p.split(':')
                start, end = py.split('-')
                p_years[int(p_id)] = {'start': try_int(start, None), 'end': try_int(end, None)}

            p_ids, c_ids = {}, {}
            for i in (cur_row['p_ids'] and cur_row['p_ids'].split(';;;')) or []:
                k, v = i.split(':')
                k = try_int(k, None)
                if v:
                    if k in (TVINFO_INSTAGRAM, TVINFO_TWITTER, TVINFO_FACEBOOK, TVINFO_WIKIPEDIA):
                        p_ids[k] = v
                    else:
                        p_ids[k] = try_int(v, None)
            for i in (cur_row['c_ids'] and cur_row['c_ids'].split(';;;')) or []:
                k, v = i.split(':')
                v = try_int(v, None)
                if v:
                    c_ids[int(k)] = try_int(v, None)
            person = Person(cur_row['p_name'], cur_row['gender'],
                            akas=set((cur_row['akas'] and cur_row['akas'].split(';;;')) or []),
                            bio=cur_row['p_bio'],
                            birthday=birthdate, birthplace=cur_row['birthplace'],
                            deathday=deathdate, deathplace=cur_row['deathplace'],
                            height=cur_row['height'],
                            ids=p_ids,
                            image_url=cur_row['p_image'],
                            nicknames=set((cur_row['nicknames'] and cur_row['nicknames'].split(';;;')) or []),
                            real_name=cur_row['realname'], show_obj=self, sid=cur_row['p_id'],
                            thumb_url=cur_row['p_thumb'], updated=cur_row['p_updated'])
            if existing_character:
                try:
                    old_list.remove(existing_character.id)
                except (BaseException, Exception):
                    pass
                existing_person = next((p for p in existing_character.person if (None is not p.id
                                        and p.ids.get(self.tvid) == person.ids.get(self.tvid))
                                        or p.name == person.name),
                                       None)  # type: Optional[Person]
                existing_character.combine_start_end_years(p_years)
                if existing_person:
                    existing_person.update_properties(
                        akas=set((cur_row['akas'] and cur_row['akas'].split(';;;')) or []),
                        biography=person.biography,
                        birthday=person.birthday, birthplace=person.birthplace,
                        deathday=person.deathday, deathplace=cur_row['deathplace'],
                        gender=person.gender, height=cur_row['height'],
                        ids=dict(chain.from_iterable(iteritems(d) for d in (existing_person.ids, person.ids or {}))),
                        image_url=person.image_url, name=person.name,
                        nicknames=set((cur_row['nicknames'] and cur_row['nicknames'].split(';;;')) or []),
                        real_name=cur_row['realname'], thumb_url=person.thumb_url
                    )
                else:
                    existing_character.person.append(person)
            else:
                self._cast_list.append(Character(
                    cur_row['name'],
                    bio=cur_row['c_bio'], ids=c_ids, image_url=cur_row['image_url'], person=[person],
                    persons_years=p_years, show_obj=self, sid=cur_row['c_id'],
                    thumb_url=cur_row['thumb_url'], updated=cur_row['c_updated']))
        self._cast_list = [c for c in self._cast_list or [] if c.id not in old_list]

    def cast_list_id(self):
        # type: (...) -> Set
        """
        return an identifier that represents the current state of the show cast list

        used to tell if a change has occured in a cast list after time/process
        """
        return set((c.name, c.image_url or '', c.thumb_url or '',
                    hash(*([', '.join(p.name for p in c.person or [] if p.name)])))
                   for c in self.cast_list or [] if c.name)

    @staticmethod
    def orphaned_cast_sql():
        # type: (...) -> List
        """
        returns list of sql that removes all character and person entries that are not linked to any show
        """
        return [
            ['DELETE FROM characters WHERE characters.id IN (SELECT c.id FROM characters c'
             ' LEFT JOIN castlist on castlist.character_id = c.id WHERE castlist.id is NULL);'],
            ['DELETE FROM character_ids WHERE character_ids.character_id IN'
             ' (SELECT c.character_id FROM character_ids c'
             ' LEFT JOIN characters ON c.character_id = characters.id WHERE characters.id is NULL);'],
            ['DELETE FROM character_person_map WHERE character_id IN (SELECT c.character_id FROM character_person_map c'
             ' LEFT JOIN characters ON c.character_id = characters.id WHERE characters.id is NULL)'],
            ['DELETE FROM persons WHERE persons.id IN (SELECT p.id FROM persons p'
             ' LEFT JOIN character_person_map c on p.id = c.person_id WHERE c.id is NULL);'],
            ['DELETE FROM person_ids WHERE person_ids.person_id IN (SELECT p.person_id FROM person_ids p'
             ' LEFT JOIN persons ON p.person_id = persons.id WHERE persons.id is NULL);'],
            ['DELETE FROM castlist WHERE castlist.id IN (SELECT c.id FROM castlist c'
             ' LEFT JOIN character_person_map cpm on c.character_id = cpm.character_id WHERE cpm.id IS NULL);'],
            ['DELETE FROM character_person_years WHERE character_person_years.ROWID IN (SELECT c.ROWID FROM'
             ' character_person_years c'
             ' LEFT JOIN characters ch on c.character_id = ch.id WHERE ch.id IS NULL);'],
            ['DELETE FROM character_person_years WHERE character_person_years.ROWID IN (SELECT c.ROWID FROM'
             ' character_person_years c'
             ' LEFT JOIN persons p on c.person_id = p.id WHERE p.id IS NULL);'],
        ]

    def _save_cast_list(self, removed_char_ids=None, force=False, stop_event=None):
        # type: (Union[List[integer_types], Set[integer_types]], bool, threading.Event) -> None
        if self._cast_list:
            my_db = db.DBConnection()
            cl = []
            for cur_id in removed_char_ids or []:
                cl.extend([[
                    """
                    DELETE FROM castlist
                    WHERE indexer = ? AND indexer_id = ? AND character_id = ?;
                    """, [self.tvid, self.prodid, cur_id]]
                ])
            update_date = datetime.date.today().toordinal()
            for cur_enum, cur_cast in enumerate(self._cast_list, 1):
                if stop_event and stop_event.is_set():
                    return
                cur_cast.save_to_db(show_obj=self, force=force, stop_event=stop_event)
                cl.extend([[
                    """
                    UPDATE castlist SET sort_order = ?, updated = ?
                    WHERE indexer = ? AND indexer_id = ?
                    AND character_id = ?;
                    """, [cur_enum, update_date, self.tvid, self.prodid, cur_cast.id]
                ], [
                    """
                    INSERT INTO castlist (indexer, indexer_id, character_id, sort_order, updated)
                    SELECT %s, %s, %s, %s, %s WHERE changes() == 0;
                    """ % (self.tvid, self.prodid, cur_cast.id, cur_enum, update_date)]
                ])
            if removed_char_ids:
                # remove orphaned entries
                cl.extend(self.orphaned_cast_sql())
            if cl:
                my_db.mass_action(cl)

    def should_update(self, update_date=datetime.date.today(), last_indexer_change=None):
        # type: (datetime.date, integer_types) -> bool
        if last_indexer_change and self._src_update_time:
            # update if show was updated or not updated within the last 30 days
            if self._src_update_time < last_indexer_change or \
                    (self._last_update_indexer and datetime.date.today().toordinal() - self._last_update_indexer > 30):
                return True
            return False

        # In some situations self.status = None.. need to figure out where that is!
        if not self._status:
            self.status = ''
            logger.log('Status missing for show: [%s] with status: [%s]' %
                       (self.tvid_prodid, self._status), logger.DEBUG)

        last_update_indexer = datetime.date.fromordinal(self._last_update_indexer)

        # if show was not found for 1 week, only retry to update once a week
        if (concurrent_show_not_found_days < abs(self.not_found_count)) \
                and (update_date - last_update_indexer) < datetime.timedelta(days=show_not_found_retry_days):
            return False

        my_db = db.DBConnection()
        sql_result = my_db.mass_action([[
            """
            SELECT airdate
            FROM [tv_episodes]
            WHERE indexer = ? AND showid = ? AND season > 0
            ORDER BY season DESC, episode DESC
            LIMIT 1
            """, [self.tvid, self.prodid]
        ], [
            """
            SELECT airdate
            FROM [tv_episodes]
            WHERE indexer = ? AND showid = ? AND season > 0 AND airdate > 1
            ORDER BY airdate DESC
            LIMIT 1
            """, [self.tvid, self.prodid]]])

        last_airdate_unknown = 1 >= int(sql_result[0][0]['airdate']) if sql_result and sql_result[0] else True

        last_airdate = datetime.date.fromordinal(sql_result[1][0]['airdate']) \
            if sql_result and sql_result[1] else datetime.date.fromordinal(1)

        # if show is not 'Ended' and last episode aired less then 460 days ago
        # or don't have an airdate for the last episode always update (status 'Continuing' or '')
        update_days_limit = 2013
        ended_limit = datetime.timedelta(days=update_days_limit)
        if 'Ended' not in self._status and (last_airdate == datetime.date.fromordinal(1)
                                            or last_airdate_unknown
                                            or (update_date - last_airdate) <= ended_limit
                                            or (update_date - last_update_indexer) > ended_limit):
            return True

        # in the first 460 days (last airdate), update regularly
        airdate_diff = update_date - last_airdate
        last_update_diff = update_date - last_update_indexer

        update_step_list = [[60, 1], [120, 3], [180, 7], [1281, 15], [update_days_limit, 30]]
        for date_diff, interval in update_step_list:
            if airdate_diff <= datetime.timedelta(days=date_diff) \
                    and last_update_diff >= datetime.timedelta(days=interval):
                return True

        # update shows without an airdate for the last episode for update_days_limit days every 7 days
        return last_airdate_unknown and airdate_diff <= ended_limit and last_update_diff >= datetime.timedelta(days=7)

    def write_show_nfo(self, force=False):
        # type: (bool) -> bool

        result = False

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return False

        logger.log('%s: Writing NFOs for show' % self.tvid_prodid)
        for cur_provider in itervalues(sickbeard.metadata_provider_dict):
            result = cur_provider.create_show_metadata(self, force) or result

        return result

    def write_metadata(self, show_only=False, force=False):
        # type:(bool, bool) -> None
        """
        :param show_only: only for show
        :param force:
        """
        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return

        self.get_images()

        force_nfo = force or not db.DBConnection().has_flag('kodi_nfo_uid')

        self.write_show_nfo(force_nfo)

        if not show_only:
            self.write_episode_nfo(force_nfo)

    def write_episode_nfo(self, force=False):
        # type: (bool) -> None

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return

        logger.log('%s: Writing NFOs for all episodes' % self.tvid_prodid)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            """
            SELECT *
            FROM tv_episodes
            WHERE indexer = ? AND showid = ? AND location != ''
            """, [self.tvid, self.prodid])

        processed = []
        for cur_row in sql_result:
            if (cur_row['season'], cur_row['episode']) in processed:
                continue
            logger.log('%s: Retrieving/creating episode %sx%s'
                       % (self.tvid_prodid, cur_row['season'], cur_row['episode']), logger.DEBUG)
            ep_obj = self.get_episode(cur_row['season'], cur_row['episode'], ep_result=[cur_row])
            if not ep_obj.related_ep_obj:
                processed += [(cur_row['season'], cur_row['episode'])]
            else:
                logger.log('%s: Found related to %sx%s episode(s)... %s'
                           % (self.tvid_prodid, cur_row['season'], cur_row['episode'],
                              ', '.join(['%sx%s' % (x.season, x.episode) for x in ep_obj.related_ep_obj])),
                           logger.DEBUG)
                processed += list(set([(cur_row['season'], cur_row['episode'])] +
                                      [(x.season, x.episode) for x in ep_obj.related_ep_obj]))
            ep_obj.create_meta_files(force)

    def update_metadata(self):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return

        self.update_show_nfo()

    def update_show_nfo(self):

        result = False

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return False

        logger.log('%s: Updating NFOs for show with new TV info' % self.tvid_prodid)
        for cur_provider in itervalues(sickbeard.metadata_provider_dict):
            result = cur_provider.update_show_indexer_metadata(self) or result

        return result

    # find all media files in the show folder and create episodes for as many as possible
    def load_episodes_from_dir(self):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, not loading episodes from disk' % self.tvid_prodid)
            return

        logger.log('%s: Loading all episodes from the show directory %s' % (self.tvid_prodid, self._location))

        # get file list
        file_list = helpers.list_media_files(self._location)

        # create TVEpisodes from each media file (if possible)
        sql_l = []
        for cur_media_file in file_list:
            parse_result = None
            ep_obj = None

            logger.log('%s: Creating episode from %s' % (self.tvid_prodid, cur_media_file), logger.DEBUG)
            try:
                ep_obj = self.ep_obj_from_file(ek.ek(os.path.join, self._location, cur_media_file))
            except (exceptions_helper.ShowNotFoundException, exceptions_helper.EpisodeNotFoundException) as e:
                logger.log('Episode %s returned an exception: %s' % (cur_media_file, ex(e)), logger.ERROR)
                continue
            except exceptions_helper.EpisodeDeletedException:
                logger.log('The episode deleted itself when I tried making an object for it', logger.DEBUG)

            if None is ep_obj:
                continue

            # see if we should save the release name in the db
            ep_file_name = ek.ek(os.path.basename, ep_obj.location)
            ep_file_name = ek.ek(os.path.splitext, ep_file_name)[0]

            try:
                parse_result = None
                np = NameParser(False, show_obj=self)
                parse_result = np.parse(ep_file_name)
            except (InvalidNameException, InvalidShowException):
                pass

            if ep_file_name and parse_result and None is not parse_result.release_group and not ep_obj.release_name:
                logger.log(
                    'Name %s gave release group of %s, seems valid' % (ep_file_name, parse_result.release_group),
                    logger.DEBUG)
                ep_obj.release_name = ep_file_name

            # store the reference in the show
            if None is not ep_obj:
                if sickbeard.USE_SUBTITLES and self.subtitles:
                    try:
                        ep_obj.refresh_subtitles()
                    except (BaseException, Exception):
                        logger.log('%s: Could not refresh subtitles' % self.tvid_prodid, logger.ERROR)
                        logger.log(traceback.format_exc(), logger.ERROR)

                result = ep_obj.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

    def load_episodes_from_db(self, update=False):
        # type: (bool) -> Dict[int, Dict[int, TVEpisode]]
        """

        :param update:
        :return:
        """
        logger.log('Loading all episodes for [%s] from the DB' % self._name)

        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT *
            FROM tv_episodes
            WHERE indexer = ? AND showid = ?
            """, [self.tvid, self.prodid])

        scanned_eps = {}

        tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

        if self._lang:
            tvinfo_config['language'] = self._lang

        if 0 != self._dvdorder:
            tvinfo_config['dvdorder'] = True

        t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)

        cached_show = None
        try:
            cached_show = t.get_show(self.prodid)
        except BaseTVinfoError as e:
            logger.log('Unable to find cached seasons from %s: %s' % (
                sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.WARNING)

        if None is cached_show:
            return scanned_eps

        scene_sql_result = my_db.select(
            """
            SELECT * 
            FROM scene_numbering 
            WHERE indexer == ? AND indexer_id = ?
            """, [self.tvid, self.prodid])

        cached_seasons = {}
        cl = []
        for cur_row in sql_result:

            delete_ep = False

            season = int(cur_row['season'])
            episode = int(cur_row['episode'])

            if season not in cached_seasons:
                try:
                    cached_seasons[season] = cached_show[season]
                except BaseTVinfoSeasonnotfound as e:
                    logger.log('Error when trying to load the episode for [%s] from %s: %s' %
                               (self._name, sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.WARNING)
                    delete_ep = True

            if season not in scanned_eps:
                scanned_eps[season] = {}

            logger.log('Loading episode %sx%s for [%s] from the DB' % (season, episode, self.name), logger.DEBUG)

            try:
                ep_obj = self.get_episode(season, episode, ep_result=[cur_row])  # type: TVEpisode

                # if we found out that the ep is no longer on TVDB then delete it from our database too
                if delete_ep and helpers.should_delete_episode(ep_obj.status):
                    cl.extend(ep_obj.delete_episode(return_sql=True))
                else:

                    ep_obj.load_from_db(season, episode, show_result=[cur_row], scene_result=scene_sql_result)
                    ep_obj.load_from_tvinfo(tvapi=t, update=update, cached_show=cached_show)
                scanned_eps[season][episode] = True
            except exceptions_helper.EpisodeDeletedException:
                logger.log('Tried loading an episode that should have been deleted from the DB [%s], skipping it'
                           % self._name, logger.DEBUG)
                continue

        if cl:
            my_db.mass_action(cl)

        return scanned_eps

    def switch_ep_change_sql(self, old_tvid, old_prodid, season, episode, reason):
        # type: (int, integer_types, int, int, int) -> List[AnyStr]
        return [
            """
            REPLACE INTO switch_ep_result
            (old_indexer, old_indexer_id, new_indexer, new_indexer_id, season, episode, reason)
            VALUES (?,?,?,?,?,?,?)
            """, [old_tvid, old_prodid, self.tvid, self.prodid, season, episode, reason]]

    def load_episodes_from_tvinfo(self, cache=True, update=False, tvinfo_data=None, switch=False, old_tvid=None,
                                  old_prodid=None):
        # type: (bool, bool, TVInfoShow, bool, int, integer_types) -> Optional[Dict[int, Dict[int, TVEpisode]]]
        """

        :param cache:
        :param update:
        :param tvinfo_data:
        :param switch:
        :param old_tvid:
        :param old_prodid:
        :return:
        """
        tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

        if not cache:
            tvinfo_config['cache'] = False

        if self._lang:
            tvinfo_config['language'] = self._lang

        if 0 != self._dvdorder:
            tvinfo_config['dvdorder'] = True

        logger.log('%s: Loading all episodes for [%s] from %s..'
                   % (self.tvid_prodid, self._name, sickbeard.TVInfoAPI(self.tvid).name))

        if getattr(tvinfo_data, 'id', None) == self.prodid:
            show_obj = tvinfo_data
            t = None
        else:
            try:
                t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
                show_obj = t.get_show(self.prodid)
            except BaseTVinfoError:
                logger.log('%s timed out, unable to update episodes for [%s] from %s' %
                           (sickbeard.TVInfoAPI(self.tvid).name, self._name, sickbeard.TVInfoAPI(self.tvid).name),
                           logger.ERROR)
                return None

        scanned_eps = {}

        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT * 
            FROM tv_episodes 
            WHERE indexer = ? AND showid = ?
            """, [self.tvid, self.prodid])
        sql_l = []
        for season in show_obj:
            scanned_eps[season] = {}
            for episode in show_obj[season]:
                # need some examples of wtf episode 0 means to decide if we want it or not
                if 0 == episode:
                    continue
                try:
                    ep_obj = self.get_episode(season, episode, ep_result=sql_result)  # type: TVEpisode
                except exceptions_helper.EpisodeNotFoundException:
                    logger.log('%s: %s object for %sx%s from [%s] is incomplete, skipping this episode' %
                               (self.tvid_prodid, sickbeard.TVInfoAPI(self.tvid).name, season, episode, self._name))
                    continue
                else:
                    try:
                        ep_obj.load_from_tvinfo(tvapi=t, update=update, cached_show=show_obj, switch=switch,
                                                old_tvid=old_tvid, old_prodid=old_prodid, switch_list=sql_l)
                    except exceptions_helper.EpisodeDeletedException:
                        logger.log('The episode from [%s] was deleted, skipping the rest of the load' % self._name)
                        continue

                with ep_obj.lock:
                    logger.log('%s: Loading info from %s for episode %sx%s from [%s]' %
                               (self.tvid_prodid, sickbeard.TVInfoAPI(self.tvid).name, season, episode, self._name),
                               logger.DEBUG)
                    ep_obj.load_from_tvinfo(season, episode, tvapi=t, update=update, cached_show=show_obj,
                                            switch=switch, old_tvid=old_tvid, old_prodid=old_prodid,
                                            switch_list=sql_l)

                    result = ep_obj.get_sql()
                    if None is not result:
                        sql_l.append(result)

                scanned_eps[season][episode] = True

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # Done updating save last update date
        self.last_update_indexer = datetime.date.today().toordinal()
        self.save_to_db()

        return scanned_eps

    def get_images(self):
        fanart_result = poster_result = banner_result = False
        season_posters_result = season_banners_result = season_all_poster_result = season_all_banner_result = False

        for cur_provider in itervalues(sickbeard.metadata_provider_dict):
            # FIXME: Needs to not show this message if the option is not enabled?
            logger.log('Running metadata routines for %s' % cur_provider.name, logger.DEBUG)

            fanart_result = cur_provider.create_fanart(self) or fanart_result
            poster_result = cur_provider.create_poster(self) or poster_result
            banner_result = cur_provider.create_banner(self) or banner_result

            season_posters_result = cur_provider.create_season_posters(self) or season_posters_result
            season_banners_result = cur_provider.create_season_banners(self) or season_banners_result
            season_all_poster_result = cur_provider.create_season_all_poster(self) or season_all_poster_result
            season_all_banner_result = cur_provider.create_season_all_banner(self) or season_all_banner_result

        return fanart_result or poster_result or banner_result or season_posters_result or season_banners_result \
            or season_all_poster_result or season_all_banner_result

    # make a TVEpisode object from a media file
    def ep_obj_from_file(self, path):
        # type: (AnyStr) -> Optional[TVEpisode]
        """

        :param path:
        :return:
        """
        if not ek.ek(os.path.isfile, path):
            logger.log('%s: Not a real file... %s' % (self.tvid_prodid, path))
            return None

        logger.log('%s: Creating episode object from %s' % (self.tvid_prodid, path), logger.DEBUG)

        try:
            my_parser = NameParser(show_obj=self)
            parse_result = my_parser.parse(path)
        except InvalidNameException:
            logger.log('Unable to parse the filename %s into a valid episode' % path, logger.DEBUG)
            return None
        except InvalidShowException:
            logger.log('Unable to parse the filename %s into a valid show' % path, logger.DEBUG)
            return None

        if not len(parse_result.episode_numbers):
            logger.log('parse_result: %s' % parse_result)
            logger.log('No episode number found in %s, ignoring it' % path, logger.ERROR)
            return None

        # for now lets assume that any episode in the show dir belongs to that show
        season_number = parse_result.season_number if None is not parse_result.season_number else 1
        episode_numbers = parse_result.episode_numbers
        root_ep_obj = None

        sql_l = []
        for cur_ep_num in episode_numbers:
            cur_ep_num = int(cur_ep_num)

            logger.log('%s: %s parsed to %s %sx%s' % (self.tvid_prodid, path, self._name, season_number, cur_ep_num),
                       logger.DEBUG)

            check_quality_again = False
            same_file = False
            ep_obj = self.get_episode(season_number, cur_ep_num)

            if None is ep_obj:
                try:
                    ep_obj = self.get_episode(season_number, cur_ep_num, path)
                except exceptions_helper.EpisodeNotFoundException:
                    logger.log('%s: Unable to figure out what this file is, skipping' % self.tvid_prodid, logger.ERROR)
                    continue

            else:
                # if there is a new file associated with this ep then re-check the quality
                status, quality = sickbeard.common.Quality.splitCompositeStatus(ep_obj.status)

                if IGNORED == status:
                    continue

                if (ep_obj.location and ek.ek(os.path.normpath, ep_obj.location) != ek.ek(os.path.normpath, path)) or \
                        (not ep_obj.location and path) or \
                        (SKIPPED == status):
                    logger.log('The old episode had a different file associated with it, re-checking the quality ' +
                               'based on the new filename %s' % path, logger.DEBUG)
                    check_quality_again = True

                with ep_obj.lock:
                    old_size = ep_obj.file_size if ep_obj.location and status != SKIPPED else 0
                    ep_obj.location = path
                    # if the sizes are the same then it's probably the same file
                    if old_size and ep_obj.file_size == old_size:
                        same_file = True
                    else:
                        same_file = False

                    ep_obj.check_for_meta_files()

            if None is root_ep_obj:
                root_ep_obj = ep_obj
            else:
                if ep_obj not in root_ep_obj.related_ep_obj:
                    root_ep_obj.related_ep_obj.append(ep_obj)

            # if it's a new file then
            if not same_file:
                ep_obj.release_name = ''

            # if user replaces a file, attempt to recheck the quality unless it's know to be the same file
            if check_quality_again and not same_file:
                new_quality = Quality.nameQuality(path, self.is_anime)
                if Quality.UNKNOWN == new_quality:
                    new_quality = Quality.fileQuality(path)
                logger.log('Since this file was renamed, file %s was checked and quality "%s" found'
                           % (path, Quality.qualityStrings[new_quality]), logger.DEBUG)
                status, quality = sickbeard.common.Quality.splitCompositeStatus(ep_obj.status)
                if Quality.UNKNOWN != new_quality or status in (SKIPPED, UNAIRED):
                    ep_obj.status = Quality.compositeStatus(DOWNLOADED, new_quality)

            # check for status/quality changes as long as it's a new file
            elif not same_file and sickbeard.helpers.has_media_ext(path)\
                    and ep_obj.status not in Quality.DOWNLOADED + Quality.ARCHIVED + [IGNORED]:

                old_status, old_quality = Quality.splitCompositeStatus(ep_obj.status)
                new_quality = Quality.nameQuality(path, self.is_anime)
                if Quality.UNKNOWN == new_quality:
                    new_quality = Quality.fileQuality(path)
                    if Quality.UNKNOWN == new_quality:
                        new_quality = Quality.assumeQuality(path)

                new_status = None

                # if it was snatched and now exists then set the status correctly
                if SNATCHED == old_status and old_quality <= new_quality:
                    logger.log('STATUS: this episode used to be snatched with quality %s but'
                               ' a file exists with quality %s so setting the status to DOWNLOADED'
                               % (Quality.qualityStrings[old_quality], Quality.qualityStrings[new_quality]),
                               logger.DEBUG)
                    new_status = DOWNLOADED

                # if it was snatched proper and we found a higher quality one then allow the status change
                elif SNATCHED_PROPER == old_status and old_quality < new_quality:
                    logger.log('STATUS: this episode used to be snatched proper with quality %s but'
                               ' a file exists with quality %s so setting the status to DOWNLOADED'
                               % (Quality.qualityStrings[old_quality], Quality.qualityStrings[new_quality]),
                               logger.DEBUG)
                    new_status = DOWNLOADED

                elif old_status not in SNATCHED_ANY:
                    new_status = DOWNLOADED

                if None is not new_status:
                    with ep_obj.lock:
                        logger.log('STATUS: we have an associated file, so setting the status from %s to DOWNLOADED/%s'
                                   % (ep_obj.status, Quality.compositeStatus(new_status, new_quality)), logger.DEBUG)
                        ep_obj.status = Quality.compositeStatus(new_status, new_quality)

            elif same_file:
                status, quality = Quality.splitCompositeStatus(ep_obj.status)
                if status in (SKIPPED, UNAIRED):
                    new_quality = Quality.nameQuality(path, self.is_anime)
                    if Quality.UNKNOWN == new_quality:
                        new_quality = Quality.fileQuality(path)
                    logger.log('Since this file has status: "%s", file %s was checked and quality "%s" found'
                               % (statusStrings[status], path, Quality.qualityStrings[new_quality]), logger.DEBUG)
                    ep_obj.status = Quality.compositeStatus(DOWNLOADED, new_quality)

            with ep_obj.lock:
                result = ep_obj.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # creating metafiles on the root should be good enough
        if sickbeard.USE_FAILED_DOWNLOADS and None is not root_ep_obj:
            with root_ep_obj.lock:
                root_ep_obj.create_meta_files()

        return root_ep_obj

    def load_from_db(self, show_result=None, imdb_info_result=None):
        # type: (Optional[Row], Optional[Union[Row, Dict]]) -> Optional[bool]
        """

        :return:
        """
        if not show_result or self.tvid != show_result['indexer'] or self.prodid != show_result['indexer_id']:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT * 
                FROM tv_shows
                WHERE indexer = ? AND indexer_id = ?
                """, [self.tvid, self.prodid])

            if 1 != len(sql_result):
                if len(sql_result):
                    tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
                    if self._lang:
                        tvinfo_config['language'] = self._lang
                    t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
                    cached_show = t.get_show(self.prodid, load_episodes=False)
                    vals = (self.prodid, '' if not cached_show else ' [%s]' % cached_show['seriesname'].strip())
                    if len(sql_result):
                        logger.log('%s: Loading show info%s from database' % vals)
                        raise exceptions_helper.MultipleDBShowsException()
                logger.log('%s-%s: Unable to find the show%s in the database' % (self.tvid, self.prodid, self.name))
                return

            show_result = next(iter(sql_result))

        if not self.tvid:
            self.tvid, self.prodid = int(show_result['indexer']), int(show_result['indexer_id'])

        self._air_by_date = show_result['air_by_date'] or 0
        self._airs = show_result['airs'] or ''
        self._airtime = self._make_airtime(show_result['airtime'])
        self._anime = show_result['anime'] or 0
        self._classification = None is self._classification and show_result['classification'] or ''
        self._dvdorder = show_result['dvdorder'] or 0
        self._flatten_folders = int(show_result['flatten_folders'])
        self._genre = self._genre or show_result['genre'] or ''
        self._lang = self._lang or show_result['lang'] or ''
        self._last_update_indexer = show_result['last_update_indexer']
        self._name = self._name or show_result['show_name'] or ''
        self._network_country = show_result['network_country']
        self._network_country_code = show_result['network_country_code']
        self._network_id = show_result['network_id']
        self._network_is_stream = bool(show_result['network_is_stream'])
        self._overview = self._overview or show_result['overview'] or ''
        self._paused = int(show_result['paused'])
        self._prune = show_result['prune'] or 0
        self._quality = int(show_result['quality'])
        self._runtime = show_result['runtime']
        self._scene = show_result['scene'] or 0
        self._sports = show_result['sports'] or 0
        self._src_update_time = try_int(show_result['src_update_timestamp'], None)
        self._startyear = show_result['startyear'] or 0
        self._status = show_result['status'] or ''
        self._subtitles = show_result['subtitles'] and 1 or 0
        self._tag = show_result['tag'] or 'Show List'
        self._upgrade_once = show_result['archive_firstmatch'] or 0

        if not self._imdbid:
            imdbid = show_result['imdb_id'] or ''
            self._imdbid = ('', imdbid)[2 < len(imdbid)]

        self._rls_global_exclude_ignore = helpers.split_word_str(
            show_result['rls_global_exclude_ignore'])[0]

        self._rls_global_exclude_require = helpers.split_word_str(
            show_result['rls_global_exclude_require'])[0]

        self._rls_ignore_words, self._rls_ignore_words_regex = helpers.split_word_str(
            show_result['rls_ignore_words'])

        self._rls_require_words, self._rls_require_words_regex = helpers.split_word_str(
            show_result['rls_require_words'])

        self.internal_network = self.internal_network or show_result['network'] or ''

        self.internal_timezone = show_result['timezone']
        if not self.internal_timezone and self.internal_network:
            _, self.internal_timezone = network_timezones.get_network_timezone(self.internal_network,
                                                                               return_name=True)
        try:
            self.location = show_result['location']
        except (BaseException, Exception):
            self.dirty_setter('_location')(self, show_result['location'])
            # self._is_location_good = False

        self.release_groups = self._anime and AniGroupList(self.tvid, self.prodid, self.tvid_prodid) or None

        logger.log(u'Loaded.. {: <9} {: <8} {}'.format(
            sickbeard.TVInfoAPI(self.tvid).config.get('name') + ',', '%s,' % self.prodid, self.name))

        # Get IMDb_info from database
        if not imdb_info_result or \
                self.tvid != imdb_info_result['indexer'] or self.prodid != imdb_info_result['indexer_id']:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT *
                FROM imdb_info
                WHERE indexer = ? AND indexer_id = ?
                """, [self.tvid, self.prodid])
        else:
            sql_result = [imdb_info_result]

        if 0 < len(sql_result):
            # this keys() is not a dict
            if isinstance(sql_result[0], dict):
                self._imdb_info = sql_result[0]
            else:
                self._imdb_info = dict(zip(sql_result[0].keys(), [(r, '')[None is r] for r in sql_result[0]]))
            if 'is_mini_series' in self._imdb_info:
                self._imdb_info['is_mini_series'] = bool(self._imdb_info['is_mini_series'])
        elif sickbeard.USE_IMDB_INFO:
            logger.log('%s: The next show update will attempt to find IMDb info for [%s]' %
                       (self.tvid_prodid, self.name), logger.DEBUG)
            return

        self.dirty = False
        return True

    def _get_tz_info(self):
        if self.internal_timezone:
            return tz.gettz(self.internal_timezone, zoneinfo_priority=True)
        elif self.internal_network:
            return network_timezones.get_network_timezone(self.internal_network)

    def _make_airtime(self, airtime=None):
        # type: (Optional[integer_types]) -> Optional[datetime.time]
        if isinstance(airtime, integer_types):
            return int_to_time(airtime)
        if self._airs:
            hour, minute = network_timezones.parse_time(self._airs)
            return datetime.time(hour=hour, minute=minute)
        return None

    def load_from_tvinfo(self, cache=True, tvapi=None, tvinfo_data=None, scheduled_update=False, switch=False):
        # type: (bool, bool, TVInfoShow, bool, bool) -> Optional[Union[bool, TVInfoShow]]
        """

        :param cache:
        :param tvapi:
        :param tvinfo_data:
        :param scheduled_update:
        :param switch:
        """
        # There's gotta be a better way of doing this but we don't wanna
        # change the cache value elsewhere
        if None is tvapi:
            tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

            if not cache:
                tvinfo_config['cache'] = False

            if self._lang:
                tvinfo_config['language'] = self._lang

            if 0 != self._dvdorder:
                tvinfo_config['dvdorder'] = True

            t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)

        else:
            t = tvapi

        if getattr(tvinfo_data, 'id', None) == self.prodid:
            show_info = tvinfo_data
        else:
            show_info = t.get_show(self.prodid, actors=True)  # type: Optional[TVInfoShow]
        if None is show_info or getattr(t, 'show_not_found', False):
            if getattr(t, 'show_not_found', False):
                self.inc_not_found_count()
                logger.log('Show [%s] not found (maybe even removed?)' % self._name, logger.WARNING)
            else:
                logger.log('Show data [%s] not found' % self._name, logger.WARNING)
            return False
        self.reset_not_found_count()

        try:
            self.name = show_info['seriesname'].strip()
        except AttributeError:
            raise BaseTVinfoAttributenotfound(
                "Found %s, but attribute 'seriesname' was empty." % self.tvid_prodid)

        if show_info:
            logger.log('%s: Loading show info [%s] from %s' % (
                self.tvid_prodid, self._name, sickbeard.TVInfoAPI(self.tvid).name))

        self.classification = self.dict_prevent_nonetype(show_info, 'classification', 'Scripted')
        self.genre = self.dict_prevent_nonetype(show_info, 'genre')
        self.network = self.dict_prevent_nonetype(show_info, 'network')
        self.runtime = self.dict_prevent_nonetype(show_info, 'runtime')
        self.dirty_setter('_src_update_time')(self, show_info.updated_timestamp)

        old_imdb = self.imdbid
        if show_info.ids.imdb:
            self.imdbid = 'tt%07d' % show_info.ids.imdb
        else:
            self.imdbid = self.dict_prevent_nonetype(show_info, 'imdb_id')
        if old_imdb != self.imdbid:
            try:
                imdb_id = try_int(self.imdbid.replace('tt', ''), None)
                mapped_imdb = self.ids.get(TVINFO_IMDB, {'id': 0})['id']
                if imdb_id != mapped_imdb:
                    indexermapper.map_indexers_to_show(self, recheck=True)
            except (BaseException, Exception):
                pass

        if None is not getattr(show_info, 'airs_dayofweek', None) and None is not getattr(show_info, 'airs_time', None):
            self.airs = ('%s %s' % (show_info['airs_dayofweek'], show_info['airs_time'])).strip()

        if None is not getattr(show_info, 'firstaired', None):
            self.startyear = int(str(show_info["firstaired"]).split('-')[0])

        self.status = self.dict_prevent_nonetype(show_info, 'status')
        self.overview = self.dict_prevent_nonetype(show_info, 'overview')
        self.network_id = show_info.network_id
        self.network_country = show_info.network_country
        self.network_country_code = show_info.network_country_code
        self.network_is_stream = show_info.network_is_stream
        self.timezone = show_info.network_timezone
        if not self.internal_timezone and self.internal_network:
            _, self.timezone = network_timezones.get_network_timezone(self.internal_network, return_name=True)
        self.airtime = self._make_airtime(show_info.time)

        if show_info.cast:
            sickbeard.people_queue_scheduler.action.add_cast_update(show_obj=self, show_info_cast=show_info.cast,
                                                                    scheduled_update=scheduled_update, switch=switch)
        return show_info

    @staticmethod
    def _update_person_properties_helper(person_obj, src_person, p_ids):
        # type: (Person, TVINFO_Person, Dict) -> None
        person_obj.update_properties(
            name=src_person.name, gender=src_person.gender,
            birthday=src_person.birthdate, deathday=src_person.deathdate,
            biography=src_person.bio,
            ids=dict(chain.from_iterable(iteritems(d) for d in
                                         (person_obj.ids, p_ids))),
            deathplace=src_person.deathplace, akas=src_person.akas,
            nicknames=src_person.nicknames, real_name=src_person.real_name,
            height=src_person.height)

    def load_cast_from_tvinfo(self, show_info_cast, force=False, stop_event=None):
        # type: (CastList, bool, threading.Event) -> None
        """
        add and fetch cast list info for show
        Note: currently not multithread safe

        :param show_info_cast: tvinfo castlist
        :param force: force reload of cast info
        :param stop_event:
        """
        if stop_event and stop_event.is_set():
            return

        if not show_info_cast:
            tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
            t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
            show_info = t.get_show(self.prodid, load_episodes=False, actors=True)  # type: Optional[TVInfoShow]
            if None is show_info:
                return
            show_info_cast = show_info.cast

        self._load_cast_from_db()
        remove_char_ids = {c.id for c in self._cast_list or []}
        cast_ordered = []
        for ct, c_l in iteritems(show_info_cast):  # type: (integer_types, List[TVINFO_Character])
            for c in c_l:
                if stop_event and stop_event.is_set():
                    return

                unique_name = 1 == len([cu for cu in c_l if (None is not c.id and cu.id == c.id)
                                        or cu.name == c.name])
                mc = next((cl for cl in self._cast_list or []
                           if (None is not c.id and cl.ids.get(self.tvid) == c.id)
                           or (unique_name and c.name and cl.name == c.name)
                           or any(cl.ids.get(src) == c.ids.get(src) for src in c.ids or {})),
                          None)  # type: Optional[Character]
                if not mc:
                    unique_person = not any(1 for _cp in
                                            Counter([_p.name for _cha in c_l for _p in _cha.person
                                                     if any(_p.name == _pp.name for _pp in c.person)]).values()
                                            if 1 != _cp)
                    if unique_person:
                        pc = [cl for cl in self._cast_list or [] if cl.person
                              and any(1 for p in cl.person if c.person
                                      and ((None is not p.ids.get(self.tvid) and any(p.ids.get(self.tvid) == cp.id
                                                                                     for cp in c.person))
                                           or any(p.name == cp.name for cp in c.person)))]
                        if 1 == len(pc):
                            mc = pc[0]
                if mc:
                    try:
                        remove_char_ids.remove(mc.id)
                    except KeyError:
                        logger.log('%s - error character: %s (%s)' % (self.name, mc.id, mc.name), logger.ERROR)
                        pass

                    old_person_ids = {op.id for op in mc.person if None is not op.id}
                    for src_person in c.person:
                        if src_person.id:
                            person_ids = {self.tvid: src_person.id}
                        else:
                            person_ids = {}
                        existing_person = next(
                            (cur_person for cur_person in mc.person
                             if (None is not src_person.id and cur_person.ids.get(self.tvid) == src_person.id)
                             or (cur_person.name and cur_person.name == src_person.name)),
                            None)  # type: Optional[Person]
                        new_person = None
                        if not existing_person:
                            new_person = Person(src_person.name, src_person.gender, src_person.birthdate,
                                                src_person.deathdate, src_person.bio, akas=src_person.akas,
                                                character_obj=mc, deathplace=src_person.deathplace,
                                                height=src_person.height, ids=person_ids, image_url=src_person.image,
                                                nicknames=src_person.nicknames, real_name=src_person.real_name,
                                                show_obj=self, thumb_url=src_person.thumb_url)
                            if new_person and new_person.id and any(1 for pi in mc.person if pi.id == new_person.id):
                                existing_person = next((pi for pi in mc.person if pi.id == new_person.id), None)

                        if existing_person:
                            try:
                                old_person_ids.remove(existing_person.id)
                            except KeyError:
                                logger.log('%s - Person error: %s (%s)' %
                                           (self.name, existing_person.name, existing_person.id), logger.ERROR)
                                pass
                            if force:
                                existing_person.reset(src_person)
                            self._update_person_properties_helper(existing_person, src_person, person_ids)
                        elif None is not new_person:
                            mc.person.append(new_person)

                    if old_person_ids:
                        mc.person = [cp for cp in mc.person if cp.id not in old_person_ids]

                    mc.update_properties(
                        name=c.name, image_url=c.image, thumb_url=c.thumb_url,
                        ids=dict(chain.from_iterable(
                            iteritems(d) for d in (mc.ids, ({}, {self.tvid: c.id})[None is not c.id]))))
                else:
                    persons = []
                    for s_pers in c.person:
                        existing_person = next((_p for _c in self._cast_list for _p in _c.person
                                                if (s_pers.id and _p.ids.get(self.tvid) == s_pers.id)
                                                or (not s_pers.id and s_pers.name == _p.name)),
                                               None)  # type: Optional[Person]
                        if s_pers.id:
                            person_ids = {self.tvid: s_pers.id}
                        else:
                            person_ids = {}
                        if existing_person:
                            if force:
                                existing_person.reset(s_pers)
                            self._update_person_properties_helper(existing_person, s_pers, person_ids)
                            persons.append(existing_person)
                        else:
                            tmp_char = Character(c.name, ids=({}, {self.tvid: c.id})[None is not c.id],
                                                 image_url=c.image, show_obj=self, thumb_url=c.thumb_url, tmp=True)
                            new_person = Person(
                                s_pers.name, s_pers.gender, s_pers.birthdate, s_pers.deathdate, s_pers.bio,
                                akas=s_pers.akas, deathplace=s_pers.deathplace, height=s_pers.height,
                                ids=({}, {self.tvid: s_pers.id})[None is not s_pers.id],
                                image_url=s_pers.image, nicknames=s_pers.nicknames, real_name=s_pers.real_name,
                                show_obj=self, thumb_url=s_pers.thumb_url, tmp_character_obj=tmp_char
                            )
                            if force:
                                new_person.reset(s_pers)
                            self._update_person_properties_helper(new_person, s_pers, person_ids)
                            persons.append(new_person)
                    mc = Character(c.name, ids=({}, {self.tvid: c.id})[None is not c.id], image_url=c.image,
                                   person=persons, show_obj=self, thumb_url=c.thumb_url)
                    self._cast_list.append(mc)
                cast_ordered.append(mc)

        if stop_event and stop_event.is_set():
            return
        if remove_char_ids:
            [c.remove_all_img(include_person=True) for c in self._cast_list or [] if c.id in remove_char_ids]
        self._cast_list = cast_ordered
        self._save_cast_list(force=force, removed_char_ids=remove_char_ids, stop_event=stop_event)

    def load_imdb_info(self):

        if not sickbeard.USE_IMDB_INFO:
            return

        logger.log('Retrieving show info [%s] from IMDb' % self._name, logger.DEBUG)
        try:
            self._get_imdb_info()
        except (BaseException, Exception) as e:
            logger.log('Error loading IMDb info: %s' % ex(e), logger.ERROR)
            logger.log('%s' % traceback.format_exc(), logger.ERROR)

    @staticmethod
    def check_imdb_redirect(imdb_id):
        # type: (Union[AnyStr, integer_types]) -> Optional[AnyStr]
        """

        :param imdb_id: imdb id
        """
        page_url = 'https://www.imdb.com/title/{0}/'.format(imdb_id)
        try:
            response = requests.head(page_url, allow_redirects=True)
            if response.history and any([h for h in response.history if 301 == h.status_code]):
                return helpers.parse_imdb_id(response.url)
        except (BaseException, Exception):
            pass

    def _get_imdb_info(self, retry=False):
        # type: (bool) -> None

        if not self._imdbid and 0 >= self.ids.get(indexermapper.TVINFO_IMDB, {'id': 0}).get('id', 0):
            return

        imdb_info = {'imdb_id': self._imdbid or 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id'],
                     'title': '',
                     'year': '',
                     'akas': '',
                     'runtimes': try_int(self._runtime, None),
                     'is_mini_series': False,
                     'episode_count': None,
                     'genres': '',
                     'countries': '',
                     'country_codes': '',
                     'certificates': '',
                     'rating': '',
                     'votes': '',
                     'last_update': ''}

        imdb_id = None
        imdb_certificates = None
        try:
            imdb_id = str(self._imdbid or 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id'])
            redirect_check = self.check_imdb_redirect(imdb_id)
            if redirect_check:
                self._imdbid = redirect_check
                imdb_id = redirect_check
                imdb_info['imdb_id'] = self.imdbid
            i = imdbpie.Imdb(exclude_episodes=True, cachedir=ek.ek(os.path.join, sickbeard.CACHE_DIR, 'imdb-pie'))
            if not helpers.parse_imdb_id(imdb_id):
                logger.log('Not a valid imdbid: %s for show: %s' % (imdb_id, self._name), logger.WARNING)
                return
            imdb_ratings = i.get_title_ratings(imdb_id=imdb_id)
            imdb_akas = i.get_title_versions(imdb_id=imdb_id)
            imdb_tv = i.get_title_auxiliary(imdb_id=imdb_id)
            ipie = getattr(imdbpie.__dict__.get('imdbpie'), '_SIMPLE_GET_ENDPOINTS', None)
            if ipie:
                ipie.update({
                    u'get_title_certificates': u'/title/{imdb_id}/certificates',
                    u'get_title_parentalguide': u'/title/{imdb_id}/parentalguide',
                })
                imdb_certificates = i.get_title_certificates(imdb_id=imdb_id)
        except LookupError as e:
            if 'Title was an episode' in ex(e) and imdb_id == 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id']:
                self.ids[indexermapper.TVINFO_IMDB]['id'] = 0
                self.ids[indexermapper.TVINFO_IMDB]['status'] = MapStatus.NOT_FOUND
                if datetime.date.today() != self.ids[indexermapper.TVINFO_IMDB]['date']:
                    indexermapper.map_indexers_to_show(self, force=True)
                    if not retry and imdb_id != 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id']:
                        # add retry arg to prevent endless loops
                        logger.log('imdbid: %s not found. retrying with newly found id: %s' %
                                   (imdb_id, 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id']), logger.DEBUG)
                        self._get_imdb_info(retry=True)
                        return
            logger.log('imdbid: %s not found. Error: %s' % (imdb_id, ex(e)), logger.WARNING)
            return
        except ImdbAPIError as e:
            logger.log('Imdb API Error: %s' % ex(e), logger.WARNING)
            return
        except (BaseException, Exception) as e:
            logger.log('Error: %s retrieving imdb id: %s' % (ex(e), imdb_id), logger.WARNING)
            return

        # ratings
        if isinstance(imdb_ratings.get('rating'), (int, float)):
            imdb_info['rating'] = try_float(imdb_ratings.get('rating'), '')
        if isinstance(imdb_ratings.get('ratingCount'), int):
            imdb_info['votes'] = try_int(imdb_ratings.get('ratingCount'), '')

        en_cc = ['GB', 'US', 'CA', 'AU']
        # akas
        if isinstance(imdb_akas.get('alternateTitles'), (list, tuple)):
            akas_head = OrderedDict([(k, None) for k in en_cc])
            akas_tail = []
            for t in imdb_akas.get('alternateTitles'):
                if isinstance(t, dict) and t.get('title') and t.get('region'):
                    cc = t.get('region').upper()
                    cc_aka = '%s::%s' % (cc, t.get('title'))
                    if cc in akas_head:
                        akas_head[cc] = cc_aka
                    else:
                        akas_tail += [cc_aka]
            imdb_info['akas'] = '|'.join([aka for aka in itervalues(akas_head) if aka] + sorted(akas_tail))

        # tv
        if isinstance(imdb_tv.get('title'), string_types):
            imdb_info['title'] = imdb_tv.get('title')
        if isinstance(imdb_tv.get('year'), (int, string_types)):
            imdb_info['year'] = try_int(imdb_tv.get('year'), '')
        if isinstance(imdb_tv.get('runningTimes'), list):
            try:
                for _t in imdb_tv.get('runningTimes'):
                    try:
                        if isinstance(_t.get('attributes'), list) and \
                                any(1 for _a in _t.get('attributes') if 'entire' in _a):
                            continue
                    except (BaseException, Exception):
                        continue
                    imdb_info['runtimes'] = try_int(_t.get('timeMinutes'), '')
                    break
            except (BaseException, Exception):
                pass
        if isinstance(imdb_tv.get('titleType'), string_types):
            imdb_info['is_mini_series'] = 'mini' in imdb_tv.get('titleType').lower()
        if isinstance(imdb_tv.get('numberOfEpisodes'), (int, string_types)):
            imdb_info['episode_count'] = try_int(imdb_tv.get('numberOfEpisodes'), 1)
        if isinstance(imdb_tv.get('genres'), (list, tuple)):
            imdb_info['genres'] = '|'.join(filter_iter(lambda _v: _v, imdb_tv.get('genres')))
        if isinstance(imdb_tv.get('origins'), list):
            imdb_info['country_codes'] = '|'.join(filter_iter(lambda _v: _v, imdb_tv.get('origins')))

        # certificate
        if isinstance(imdb_certificates.get('certificates'), dict):
            certs_head = OrderedDict([(k, None) for k in en_cc])
            certs_tail = []
            for cc, values in iteritems(imdb_certificates.get('certificates')):
                if cc and isinstance(values, (list, tuple)):
                    for cert in values:
                        if isinstance(cert, dict) and cert.get('certificate'):
                            extra_info = ''
                            if isinstance(cert.get('attributes'), list):
                                extra_info = ' (%s)' % ', '.join(cert.get('attributes'))
                            cc = cc.upper()
                            cc_cert = '%s:%s%s' % (cc, cert.get('certificate'), extra_info)
                            if cc in certs_head:
                                certs_head[cc] = cc_cert
                            else:
                                certs_tail += [cc_cert]
            imdb_info['certificates'] = '|'.join([cert for cert in itervalues(certs_head) if cert] + sorted(certs_tail))
        if (not imdb_info['certificates'] and isinstance(imdb_tv.get('certificate'), dict)
                and isinstance(imdb_tv.get('certificate').get('certificate'), string_types)):
            imdb_info['certificates'] = '%s:%s' % (u'US', imdb_tv.get('certificate').get('certificate'))

        imdb_info['last_update'] = datetime.date.today().toordinal()

        # Rename dict keys without spaces for DB upsert
        self.imdb_info = dict(
            [(k.replace(' ', '_'), k(v) if hasattr(v, 'keys') else v) for k, v in iteritems(imdb_info)])
        logger.log('%s: Obtained info from IMDb -> %s' % (self.tvid_prodid, self._imdb_info), logger.DEBUG)

        logger.log('%s: Parsed latest IMDb show info for [%s]' % (self.tvid_prodid, self._name))

    def next_episode(self):
        logger.log('%s: Finding the episode which airs next for: %s' % (self.tvid_prodid, self._name), logger.DEBUG)

        cur_date = datetime.date.today().toordinal()
        if not self.nextaired or self.nextaired and cur_date > self.nextaired:
            my_db = db.DBConnection()
            # noinspection SqlRedundantOrderingDirection
            sql_result = my_db.select(
                """
                SELECT airdate, season, episode 
                FROM tv_episodes
                WHERE indexer = ? AND showid = ? AND airdate >= ? AND status in (?,?,?)
                ORDER BY airdate ASC
                LIMIT 1
                """, [self.tvid, self.prodid, datetime.date.today().toordinal(), UNAIRED, WANTED, FAILED])

            if None is sql_result or 0 == len(sql_result):
                logger.log('%s: No episode found... need to implement a show status' % self.tvid_prodid, logger.DEBUG)
                self.nextaired = ''
            else:
                logger.log('%s: Found episode %sx%s' % (
                    self.tvid_prodid, sql_result[0]['season'], sql_result[0]['episode']), logger.DEBUG)
                self.nextaired = sql_result[0]['airdate']

        return self.nextaired

    def delete_show(self, full=False):
        # type: (bool) -> None
        """

        :param full:
        """
        try:
            sickbeard.people_queue_scheduler.action.abort_cast_update(show_obj=self)
        except (BaseException, Exception):
            pass
        try:
            sickbeard.show_queue_scheduler.action.abort_show(show_obj=self)
        except (BaseException, Exception):
            pass
        try:
            sickbeard.search_queue_scheduler.action.abort_show(show_obj=self)
        except (BaseException, Exception):
            pass
        sql_l = [['DELETE FROM tv_episodes WHERE indexer = ? AND showid = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM tv_shows WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM imdb_info WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM xem_refresh WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM scene_numbering WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM allowlist WHERE indexer = ? AND show_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM blocklist WHERE indexer = ? AND show_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM indexer_mapping WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]],
                 ['DELETE FROM castlist WHERE indexer = ? AND indexer_id = ?', [self.tvid, self.prodid]]
                 ] + self.orphaned_cast_sql()

        my_db = db.DBConnection()
        my_db.mass_action(sql_l)
        self.remove_character_images()

        name_cache.remove_from_namecache(self.tvid, self.prodid)
        try:
            sickbeard.name_parser.parser.name_parser_cache.flush(self)
        except (BaseException, Exception):
            pass

        action = ('delete', 'trash')[sickbeard.TRASH_REMOVE_SHOW]

        # remove self from show list
        sickbeard.showList = filter_list(lambda so: so.tvid_prodid != self.tvid_prodid, sickbeard.showList)
        try:
            del sickbeard.showDict[self.sid_int]
        except (BaseException, Exception):
            pass
        sickbeard.webserve.Home.make_showlist_unique_names()
        sickbeard.MEMCACHE['history_tab'] = sickbeard.webserve.History.menu_tab(sickbeard.MEMCACHE['history_tab_limit'])

        try:
            tvid_prodid = self.tvid_prodid
            if tvid_prodid in sickbeard.switched_shows:
                sickbeard.switched_shows.pop(tvid_prodid)
            elif tvid_prodid in itervalues(sickbeard.switched_shows):
                sickbeard.switched_shows = {k: v for k, v in iteritems(sickbeard.switched_shows) if tvid_prodid != v}
        except (BaseException, Exception):
            pass

        # clear the cache
        ic = image_cache.ImageCache()
        for cache_obj in ek.ek(glob.glob, ic.fanart_path(self.tvid, self.prodid).replace('fanart.jpg', '*')) \
                + ek.ek(glob.glob, ic.poster_thumb_path(self.tvid, self.prodid).replace('poster.jpg', '*')) \
                + ek.ek(glob.glob, ic.poster_path(self.tvid, self.prodid).replace('poster.jpg', '*')):
            cache_dir = ek.ek(os.path.isdir, cache_obj)
            result = helpers.remove_file(cache_obj, tree=cache_dir, log_level=logger.WARNING)
            if result:
                logger.log('%s cache %s %s' % (result, cache_dir and 'dir' or 'file', cache_obj))

        if self.tvid_prodid in sickbeard.FANART_RATINGS:
            del sickbeard.FANART_RATINGS[self.tvid_prodid]

        # remove entire show folder
        if full:
            try:
                logger.log('Attempt to %s show folder %s' % (action, self._location))
                # check first the read-only attribute
                file_attribute = ek.ek(os.stat, self.location)[0]
                if not file_attribute & stat.S_IWRITE:
                    # File is read-only, so make it writeable
                    logger.log('Attempting to make writeable the read only folder %s' % self._location, logger.DEBUG)
                    try:
                        ek.ek(os.chmod, self.location, stat.S_IWRITE)
                    except (BaseException, Exception):
                        logger.log('Unable to change permissions of %s' % self._location, logger.WARNING)

                result = helpers.remove_file(self.location, tree=True)
                if result:
                    logger.log('%s show folder %s' % (result, self._location))

            except exceptions_helper.ShowDirNotFoundException:
                logger.log('Show folder does not exist, no need to %s %s' % (action, self._location), logger.WARNING)
            except OSError as e:
                logger.log('Unable to %s %s: %s / %s' % (action, self._location, repr(e), ex(e)), logger.WARNING)

    def populate_cache(self, force=False):
        # type: (bool) -> None
        """

        :param force:
        """
        cache_inst = image_cache.ImageCache()

        logger.log('Checking & filling cache for show %s' % self._name)
        cache_inst.fill_cache(self, force)

    def refresh_dir(self):

        # make sure the show dir is where we think it is unless dirs are created on the fly
        if not ek.ek(os.path.isdir, self._location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
            return False

        # load from dir
        self.load_episodes_from_dir()

        # run through all locations from DB, check that they exist
        logger.log('%s: Loading all episodes for [%s] with a location from the database'
                   % (self.tvid_prodid, self._name))

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            """
            SELECT *
            FROM tv_episodes
            WHERE indexer = ? AND showid = ? AND location != ''
            ORDER BY season DESC, episode DESC
            """, [self.tvid, self.prodid])

        kept = 0
        deleted = 0
        attempted = []
        sql_l = []
        for cur_row in sql_result:
            season = int(cur_row['season'])
            episode = int(cur_row['episode'])
            location = ek.ek(os.path.normpath, cur_row['location'])

            try:
                ep_obj = self.get_episode(season, episode, ep_result=[cur_row])
            except exceptions_helper.EpisodeDeletedException:
                logger.log('The episode from [%s] was deleted while we were refreshing it, moving on to the next one'
                           % self._name, logger.DEBUG)
                continue

            # if the path exist and if it's in our show dir
            if (self.prune and season and ep_obj.location not in attempted and 0 < helpers.get_size(ep_obj.location) and
                    ek.ek(os.path.normpath, location).startswith(ek.ek(os.path.normpath, self.location))):
                with ep_obj.lock:
                    if ep_obj.status in Quality.DOWNLOADED:
                        # locations repeat but attempt to delete once
                        attempted += ep_obj.location
                        if kept >= self.prune:
                            result = helpers.remove_file(ep_obj.location, prefix_failure=u'%s: ' % self.tvid_prodid)
                            if result:
                                logger.log(u'%s: %s file %s' % (self.tvid_prodid, result, ep_obj.location),
                                           logger.DEBUG)
                                deleted += 1
                        else:
                            kept += 1

            # if the path doesn't exist or if it's not in our show dir
            if not ek.ek(os.path.isfile, location) or not ek.ek(os.path.normpath, location).startswith(
                    ek.ek(os.path.normpath, self.location)):

                # check if downloaded files still exist, update our data if this has changed
                if 1 != sickbeard.SKIP_REMOVED_FILES:
                    with ep_obj.lock:
                        # if it used to have a file associated with it and it doesn't anymore then set it to IGNORED
                        if ep_obj.location and ep_obj.status in Quality.DOWNLOADED:
                            if ARCHIVED == sickbeard.SKIP_REMOVED_FILES:
                                ep_obj.status = Quality.compositeStatus(
                                    ARCHIVED, Quality.qualityDownloaded(ep_obj.status))
                            else:
                                ep_obj.status = (sickbeard.SKIP_REMOVED_FILES, IGNORED)[
                                    not sickbeard.SKIP_REMOVED_FILES]
                            logger.log(
                                '%s: File no longer at location for s%02de%02d,' % (self.tvid_prodid, season, episode)
                                + ' episode removed and status changed to %s' % statusStrings[ep_obj.status],
                                logger.DEBUG)
                            ep_obj.subtitles = list()
                            ep_obj.subtitles_searchcount = 0
                            ep_obj.subtitles_lastsearch = str(datetime.datetime.min)
                        ep_obj.location = ''
                        ep_obj.hasnfo = False
                        ep_obj.hastbn = False
                        ep_obj.release_name = ''

                        result = ep_obj.get_sql()
                        if None is not result:
                            sql_l.append(result)
            else:
                # the file exists, set its modify file stamp
                if sickbeard.AIRDATE_EPISODES:
                    ep_obj.airdate_modify_stamp()

        if deleted:
            logger.log('%s: %s %s media file%s and kept %s most recent downloads' % (
                self.tvid_prodid, ('Permanently deleted', 'Trashed')[sickbeard.TRASH_REMOVE_SHOW],
                deleted, helpers.maybe_plural(deleted), kept))

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

    def download_subtitles(self, force=False):
        # type: (bool) -> None
        """

        :param force:
        """
        # TODO: Add support for force option
        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, can\'t download subtitles' % self.tvid_prodid, logger.DEBUG)
            return
        logger.log('%s: Downloading subtitles' % self.tvid_prodid, logger.DEBUG)

        try:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT location 
                FROM tv_episodes 
                WHERE indexer = ? AND showid = ? AND LENGTH(location) != 0 
                ORDER BY season DESC, episode DESC
                """, [self.tvid, self.prodid])

            for cur_row in sql_result:
                ep_obj = self.ep_obj_from_file(cur_row['location'])
                _ = ep_obj.download_subtitles(force=force)
        except (BaseException, Exception):
            logger.log('Error occurred when downloading subtitles: %s' % traceback.format_exc(), logger.ERROR)
            return

    def remove_character_images(self):
        try:
            img_obj = image_cache.ImageCache()
            delete_list = []
            for character in self._cast_list:
                for p in character.person:
                    person_img = img_obj.person_both_paths(p)
                    for i in person_img:
                        delete_list.append(i)
                character_img = img_obj.character_both_path(character, self)
                for i in character_img:
                    delete_list.append(i)

            for d in delete_list:
                try:
                    remove_file_perm(d)
                except (BaseException, Exception):
                    pass
        except (BaseException, Exception):
            pass

    def switch_infosrc(self, old_tvid, old_prodid, pausestatus_after=None, update_show=True):
        # type: (integer_types, integer_types, Optional[bool], bool) -> None
        """

        :param old_tvid: old tvid
        :param old_prodid: old prodid
        :param pausestatus_after: pause after switch
        :param update_show:
        """
        with self.lock:
            my_db = db.DBConnection()
            my_db.mass_action([
                ['UPDATE tv_shows SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE tv_episodes SET indexer = ?, showid = ?, indexerid = 0 WHERE indexer = ? AND showid = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE blocklist SET indexer = ?, show_id = ? WHERE indexer = ? AND show_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE history SET indexer = ?, showid = ? WHERE indexer = ? AND showid = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE imdb_info SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE scene_exceptions SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE scene_numbering SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE allowlist SET indexer = ?, show_id = ? WHERE indexer = ? AND show_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['UPDATE xem_refresh SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]],
                ['DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
                 [old_tvid, old_prodid]],
                ['UPDATE castlist SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                 [self.tvid, self.prodid, old_tvid, old_prodid]]
            ])

            my_failed_db = db.DBConnection('failed.db')
            my_failed_db.action('UPDATE history SET indexer = ?, showid = ? WHERE indexer = ? AND showid = ?',
                                [self.tvid, self.prodid, old_tvid, old_prodid])
            del_mapping(old_tvid, old_prodid)
            try:
                for c in self._cast_list:  # type: Character
                    c.remove_all_img(tvid=old_tvid, proid=old_prodid)
            except (BaseException, Exception):
                pass
            self._cast_list = None
            self.sxe_ep_obj = {}
            self.ids[old_tvid]['status'] = MapStatus.NONE
            self.ids[self.tvid]['status'] = MapStatus.SOURCE
            self.ids[self.tvid]['id'] = self.prodid
            if isinstance(self.imdb_info, dict):
                self.imdb_info['indexer'] = self.tvid
                self.imdb_info['indexer_id'] = self.prodid
            save_mapping(self)
            name_cache.remove_from_namecache(old_tvid, old_prodid)

            image_cache_dir = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', 'shows')
            old_dir = ek.ek(os.path.join, image_cache_dir, '%s-%s' % (old_tvid, old_prodid))
            new_dir = ek.ek(os.path.join, image_cache_dir, '%s-%s' % (self.tvid, self.prodid))
            try:
                ek.ek(os.rename, old_dir, new_dir)
            except (BaseException, Exception) as e:
                logger.log('Unable to rename %s to %s: %s / %s' % (old_dir, new_dir, repr(e), ex(e)),
                           logger.WARNING)

            old_id = TVidProdid({old_tvid: old_prodid})()
            rating = sickbeard.FANART_RATINGS.get(old_id)
            if rating:
                del sickbeard.FANART_RATINGS[old_id]
                sickbeard.FANART_RATINGS[self.tvid_prodid] = rating
                sickbeard.save_config()

            name_cache.buildNameCache(self)
            self.reset_not_found_count()
            old_sid_int = self.create_sid(old_tvid, old_prodid)
            if old_sid_int != self.sid_int:
                try:
                    del sickbeard.showDict[old_sid_int]
                except (BaseException, Exception):
                    pass
                sickbeard.showDict[self.sid_int] = self

            self.save_to_db()
            if update_show:
                # force the update
                try:
                    sickbeard.show_queue_scheduler.action.updateShow(
                        self, force=True, web=True, priority=QueuePriorities.VERYHIGH,
                        pausestatus_after=pausestatus_after, switch_src=True)
                except exceptions_helper.CantUpdateException as e:
                    logger.log('Unable to update this show. %s' % ex(e), logger.ERROR)

    def save_to_db(self, force_save=False):
        # type: (bool) -> None
        """

        :param force_save:
        """
        if not self.dirty and not force_save:
            logger.log('%s: Not saving show to db - record is not dirty' % self.tvid_prodid, logger.DEBUG)
            return

        logger.log('%s: Saving show info to database' % self.tvid_prodid, logger.DEBUG)

        new_value_dict = dict(
            air_by_date=self._air_by_date,
            airs=self._airs,
            airtime=time_to_int(self._airtime),
            anime=self._anime,
            archive_firstmatch=self._upgrade_once,
            classification=self._classification,
            dvdorder=self._dvdorder,
            flatten_folders=self._flatten_folders,
            genre=self._genre,
            indexer=self.tvid,
            lang=self._lang, imdb_id=self._imdbid,
            last_update_indexer=self._last_update_indexer,
            location=self._location,
            network=self.internal_network,
            network_country=self._network_country,
            network_country_code=self._network_country_code,
            network_id=self._network_id,
            network_is_stream=self._network_is_stream,
            overview=self._overview,
            paused=self._paused,
            prune=self._prune,
            quality=self._quality,
            rls_global_exclude_ignore=','.join(self._rls_global_exclude_ignore),
            rls_global_exclude_require=','.join(self._rls_global_exclude_require),
            rls_ignore_words=helpers.generate_word_str(self._rls_ignore_words, self._rls_ignore_words_regex),
            rls_require_words=helpers.generate_word_str(self._rls_require_words, self._rls_require_words_regex),
            runtime=self._runtime,
            scene=self._scene,
            show_name=self._name,
            sports=self._sports,
            startyear=self.startyear,
            status=self._status,
            subtitles=self._subtitles,
            tag=self._tag,
            timezone=self.internal_timezone,
        )

        control_value_dict = dict(indexer=self.tvid, indexer_id=self.prodid)

        my_db = db.DBConnection()
        my_db.upsert('tv_shows', new_value_dict, control_value_dict)
        self.dirty = False

        if sickbeard.USE_IMDB_INFO and len(self._imdb_info):
            new_value_dict = self._imdb_info

            my_db = db.DBConnection()
            my_db.upsert('imdb_info', new_value_dict, control_value_dict)

    def __ne__(self, o):
        # type: (TVShow) -> bool
        return not self.__eq__(o)

    def __eq__(self, o):
        # type: (TVShow) -> bool
        if not isinstance(o, TVShow):
            return False
        return o.tvid == self.tvid and o.prodid == self.prodid

    def __hash__(self):
        return hash((self.tvid, self.prodid))

    def __repr__(self):
        return 'TVShow(%s)' % self.__str__()

    def __str__(self):
        return 'prodid: %s\n' % self.prodid \
               + 'tvid: %s\n' % self.tvid \
               + 'name: %s\n' % self.name \
               + 'location: %s\n' % self._location \
               + ('', 'network: %s\n' % self.network)[self.network not in (None, '')] \
               + ('', 'airs: %s\n' % self.airs)[self.airs not in (None, '')] \
               + ('', 'status: %s\n' % self.status)[self.status not in (None, '')] \
               + 'startyear: %s\n' % self.startyear \
               + ('', 'genre: %s\n' % self.genre)[self.genre not in (None, '')] \
               + 'classification: %s\n' % self.classification \
               + 'runtime: %s\n' % self.runtime \
               + 'quality: %s\n' % self.quality \
               + 'scene: %s\n' % self.is_scene \
               + 'sports: %s\n' % self.is_sports \
               + 'anime: %s\n' % self.is_anime \
               + 'prune: %s\n' % self.prune

    def want_episode(self, season, episode, quality, manual_search=False, multi_ep=False):
        # type: (integer_types, integer_types, integer_types, bool, bool) -> bool
        """

        :param season: season number
        :param episode: episode number
        :param quality: quality
        :param manual_search: manual search
        :param multi_ep: multiple episodes
        :return:
        """
        logger.log('Checking if found %sepisode %sx%s is wanted at quality %s' %
                   (('', 'multi-part ')[multi_ep], season, episode, Quality.qualityStrings[quality]), logger.DEBUG)

        if not multi_ep:
            try:
                wq = getattr(self.sxe_ep_obj.get(season, {}).get(episode, {}), 'wanted_quality', None)
                if None is not wq:
                    if quality in wq:
                        cur_status, cur_quality = Quality.splitCompositeStatus(self.sxe_ep_obj[season][episode].status)
                        if cur_status in (WANTED, UNAIRED, SKIPPED, FAILED):
                            logger.log('Existing episode status is wanted/unaired/skipped/failed,'
                                       ' getting found episode', logger.DEBUG)
                            return True
                        elif manual_search:
                            logger.log('Usually ignoring found episode, but forced search allows the quality,'
                                       ' getting found episode', logger.DEBUG)
                            return True
                        elif quality > cur_quality:
                            logger.log(
                                'Episode already exists but the found episode has better quality,'
                                ' getting found episode', logger.DEBUG)
                            return True
                    logger.log('None of the conditions were met, ignoring found episode', logger.DEBUG)
                    return False
            except (BaseException, Exception):
                pass

        # if the quality isn't one we want under any circumstances then just say no
        initial_qualities, archive_qualities = Quality.splitQuality(self._quality)
        all_qualities = list(set(initial_qualities + archive_qualities))

        initial = '= (%s)' % ','.join([Quality.qualityStrings[qual] for qual in initial_qualities])
        if 0 < len(archive_qualities):
            initial = '+ upgrade to %s + (%s)'\
                      % (initial, ','.join([Quality.qualityStrings[qual] for qual in archive_qualities]))
        logger.log('Want initial %s and found %s' % (initial, Quality.qualityStrings[quality]), logger.DEBUG)

        if quality not in all_qualities:
            logger.log('Don\'t want this quality, ignoring found episode', logger.DEBUG)
            return False

        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT status
            FROM tv_episodes
            WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
            """, [self.tvid, self.prodid, season, episode])

        if not sql_result or not len(sql_result):
            logger.log('Unable to find a matching episode in database, ignoring found episode', logger.DEBUG)
            return False

        cur_status, cur_quality = Quality.splitCompositeStatus(int(sql_result[0]['status']))
        ep_status_text = statusStrings[cur_status]

        logger.log('Existing episode status: %s (%s)' % (statusStrings[cur_status], ep_status_text), logger.DEBUG)

        # if we know we don't want it then just say no
        if cur_status in [IGNORED, ARCHIVED] + ([SKIPPED], [])[multi_ep] and not manual_search:
            logger.log('Existing episode status is %signored/archived, ignoring found episode' %
                       ('skipped/', '')[multi_ep], logger.DEBUG)
            return False

        # if it's one of these then we want it as long as it's in our allowed initial qualities
        if quality in all_qualities:
            if cur_status in [WANTED, UNAIRED, SKIPPED, FAILED] + ([], SNATCHED_ANY)[multi_ep]:
                logger.log('Existing episode status is wanted/unaired/skipped/failed, getting found episode',
                           logger.DEBUG)
                return True
            elif manual_search:
                logger.log(
                    'Usually ignoring found episode, but forced search allows the quality, getting found episode',
                    logger.DEBUG)
                return True
            else:
                logger.log('Quality is on wanted list, need to check if it\'s better than existing quality',
                           logger.DEBUG)

        downloaded_status_list = SNATCHED_ANY + [DOWNLOADED]
        # special case: already downloaded quality is not in any of the wanted Qualities
        if cur_status in downloaded_status_list and cur_quality not in all_qualities:
            wanted_qualities = all_qualities
        else:
            wanted_qualities = archive_qualities

        # if re-downloading then only keep items in the archiveQualities list and better than what we have
        if cur_status in downloaded_status_list and quality in wanted_qualities and quality > cur_quality:
            logger.log('Episode already exists but the found episode has better quality, getting found episode',
                       logger.DEBUG)
            return True
        else:
            logger.log('Episode already exists and the found episode has same/lower quality, ignoring found episode',
                       logger.DEBUG)

        logger.log('None of the conditions were met, ignoring found episode', logger.DEBUG)
        return False

    def get_overview(self, ep_status, split_snatch=False):
        # type: (integer_types, bool) -> integer_types
        """
        :param ep_status: episode status
        :param split_snatch:
        :return:
        :rtype: int
        """
        return helpers.get_overview(ep_status, self.quality, self.upgrade_once, split_snatch=split_snatch)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.RLock()
        self.__dict__.update(d)

    def __bool__(self):
        return bool(self.tvid) and bool(self.prodid)

    __nonzero__ = __bool__


class TVEpisode(TVEpisodeBase):

    def __init__(self, show_obj, season, episode, path='', existing_only=False, show_result=None):
        # type: (TVShow, integer_types, integer_types, AnyStr, bool, List) -> None
        super(TVEpisode, self).__init__(season, episode, int(show_obj.tvid))

        self._airtime = None  # type: Optional[datetime.time]
        self._epid = 0  # type: int
        self._location = path  # type: AnyStr
        self._network = None  # type: Optional[AnyStr]
        self._network_country = None  # type: Optional[AnyStr]
        self._network_country_code = None  # type: Optional[AnyStr]
        self._network_id = None  # type: Optional[int]
        self._network_is_stream = None  # type: Optional[bool]
        self._runtime = 0  # type: integer_types
        self._show_obj = show_obj  # type: TVShow
        self._timestamp = None  # type: Optional[int]
        self._timezone = None  # type: Optional[AnyStr]
        self._tvid = int(show_obj.tvid)  # type: int

        self.check_for_meta_files()
        self.lock = threading.RLock()
        self.related_ep_obj = []  # type: List
        self.scene_absolute_number = 0  # type: int
        self.scene_episode = 0  # type: int
        self.scene_season = 0  # type: int
        self.specify_episode(self._season, self._episode, existing_only=existing_only, show_result=show_result)
        self.wanted_quality = []  # type: List

    @property
    def network(self):
        return self._network

    @network.setter
    def network(self, *args):
        self.dirty_setter('_network')(self, *args)

    @property
    def network_id(self):
        return self._network_id

    @network_id.setter
    def network_id(self, *args):
        self.dirty_setter('_network_id')(self, *args)

    @property
    def network_country(self):
        return self._network_country

    @network_country.setter
    def network_country(self, *args):
        self.dirty_setter('_network_country')(self, *args)

    @property
    def network_country_code(self):
        return self._network_country_code

    @network_country_code.setter
    def network_country_code(self, *args):
        self.dirty_setter('_network_country_code')(self, *args)

    @property
    def network_is_stream(self):
        return self._network_is_stream

    @network_is_stream.setter
    def network_is_stream(self, *args):
        self.dirty_setter('_network_is_stream')(self, *args)

    @property
    def airtime(self):
        # type: (...) -> Optional[datetime.time]
        return self._airtime

    @airtime.setter
    def airtime(self, *args):
        # type: (Optional[datetime.time, AnyStr]) -> None
        self.dirty_setter('_airtime')(self, *args)

    @property
    def runtime(self):
        return self._runtime

    @runtime.setter
    def runtime(self, *args):
        self.dirty_setter('_runtime')(self, *args)

    @property
    def timezone(self):
        return self._timezone

    @timezone.setter
    def timezone(self, *args):
        self.dirty_setter('_timezone')(self, *args)

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, *args):
        self.dirty_setter('_timestamp')(self, *args)

    @property
    def show_obj(self):
        """

        :return: TVShow object
        :rtype: TVShow
        """
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        self._show_obj = val

    @property
    def tvid(self):
        """
        :rtype: int
        """
        return self._tvid

    @tvid.setter
    def tvid(self, val):
        self.dirty_setter('_tvid')(self, int(val))
        # TODO: remove the following when indexerid is gone
        # in deprecation transition, tvid will also set indexer so that existing uses continue to work normally
        self.dirty_setter('_indexer')(self, int(val))

    @property
    def epid(self):
        """
        :rtype: int or long
        """
        return self._epid

    @epid.setter
    def epid(self, val):
        self.dirty_setter('_epid')(self, int(val))
        # TODO: remove the following when indexerid is gone
        # in deprecation transition, epid will also set indexerid so that existing uses continue as normal
        self.dirty_setter('_indexerid')(self, int(val))

    def _set_location(self, val):
        log_vals = (('clears', ''), ('sets', ' to ' + val))[any(val)]
        # noinspection PyStringFormat
        logger.log(u'Setter %s location%s' % log_vals, logger.DEBUG)

        # self._location = newLocation
        self.dirty_setter('_location')(self, val)

        if val and ek.ek(os.path.isfile, val):
            self.file_size = ek.ek(os.path.getsize, val)
        else:
            self.file_size = 0

    location = property(lambda self: self._location, _set_location)

    def refresh_subtitles(self):
        """Look for subtitles files and refresh the subtitles property"""
        if sickbeard.USE_SUBTITLES:
            self.subtitles = subtitles.subtitles_languages(self.location)

    def download_subtitles(self, force=False):
        """

        :param force:
        :type force: bool
        :return:
        :rtype:
        """
        if not sickbeard.USE_SUBTITLES:
            return

        # TODO: Add support for force option
        if not ek.ek(os.path.isfile, self.location):
            logger.log('%s: Episode file doesn\'t exist, can\'t download subtitles for episode %sx%s' %
                       (self.show_obj.tvid_prodid, self.season, self.episode), logger.DEBUG)
            return
        logger.log('%s: Downloading subtitles for episode %sx%s'
                   % (self.show_obj.tvid_prodid, self.season, self.episode), logger.DEBUG)

        previous_subtitles = self.subtitles

        try:
            need_languages = list(set(sickbeard.SUBTITLES_LANGUAGES) - set(self.subtitles))
            subs = subliminal.download_subtitles([self.location], languages=need_languages,
                                                 services=sickbeard.subtitles.get_enabled_service_list(),
                                                 force=force, multi=True, cache_dir=sickbeard.CACHE_DIR,
                                                 os_auth=sickbeard.SUBTITLES_SERVICES_AUTH[0],
                                                 os_hash=sickbeard.SUBTITLES_OS_HASH)

            if sickbeard.SUBTITLES_DIR:
                for video in subs:
                    subs_new_path = ek.ek(os.path.join, ek.ek(os.path.dirname, video.path), sickbeard.SUBTITLES_DIR)
                    dir_exists = helpers.make_dir(subs_new_path)
                    if not dir_exists:
                        logger.log('Unable to create subtitles folder %s' % subs_new_path, logger.ERROR)
                    else:
                        helpers.chmod_as_parent(subs_new_path)

                    for subtitle in subs.get(video):
                        new_file_path = ek.ek(os.path.join, subs_new_path, ek.ek(os.path.basename, subtitle.path))
                        helpers.move_file(subtitle.path, new_file_path)
                        helpers.chmod_as_parent(new_file_path)
            else:
                for video in subs:
                    for subtitle in subs.get(video):
                        helpers.chmod_as_parent(subtitle.path)

        except (BaseException, Exception):
            logger.log('Error occurred when downloading subtitles: %s' % traceback.format_exc(), logger.ERROR)
            return

        self.refresh_subtitles()
        # added the if because sometime it raises an error
        self.subtitles_searchcount = self.subtitles_searchcount + 1 if self.subtitles_searchcount else 1
        self.subtitles_lastsearch = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_to_db()

        newsubtitles = set(self.subtitles).difference(set(previous_subtitles))

        if newsubtitles:
            try:
                subtitle_list = ", ".join([subliminal.language.Language(x).name for x in newsubtitles])
            except (BaseException, Exception):
                logger.log('Could not parse a language to use to fetch subtitles for episode %sx%s' %
                           (self.season, self.episode), logger.DEBUG)
                return
            logger.log('%s: Downloaded %s subtitles for episode %sx%s' %
                       (self.show_obj.tvid_prodid, subtitle_list, self.season, self.episode), logger.DEBUG)

            notifiers.notify_subtitle_download(self, subtitle_list)

        else:
            logger.log('%s: No subtitles downloaded for episode %sx%s'
                       % (self.show_obj.tvid_prodid, self.season, self.episode), logger.DEBUG)

        if sickbeard.SUBTITLES_HISTORY:
            for video in subs:
                for subtitle in subs.get(video):
                    history.log_subtitle(self.show_obj.tvid, self.show_obj.prodid,
                                         self.season, self.episode, self.status, subtitle)

        return subs

    def check_for_meta_files(self):
        """

        :return:
        :rtype: bool
        """
        oldhasnfo = self._hasnfo
        oldhastbn = self._hastbn

        hasnfo = False
        hastbn = False

        # check for nfo and tbn
        if ek.ek(os.path.isfile, self.location):
            for cur_provider in itervalues(sickbeard.metadata_provider_dict):
                if cur_provider.episode_metadata:
                    new_result = cur_provider.has_episode_metadata(self)
                else:
                    new_result = False
                hasnfo = new_result or hasnfo

                if cur_provider.episode_thumbnails:
                    new_result = cur_provider.has_episode_thumb(self)
                else:
                    new_result = False
                hastbn = new_result or hastbn

        self.hasnfo = hasnfo
        self.hastbn = hastbn

        # if either setting has changed return true, if not return false
        return oldhasnfo != self._hasnfo or oldhastbn != self._hastbn

    def specify_episode(self, season, episode, existing_only=False, **kwargs):
        """
        kwargs['show_result']: type: Optional[List[Row]] passed thru

        :param season: season number
        :type season: int
        :param episode: episode number
        :type episode: int
        :param existing_only:
        :type existing_only: bool
        """
        if not self.load_from_db(season, episode, **kwargs):
            # only load from NFO if we didn't load from DB
            if ek.ek(os.path.isfile, self.location):
                try:
                    self.load_from_nfo(self.location)
                except exceptions_helper.NoNFOException:
                    logger.log('%s: There was an error loading the NFO for episode %sx%s' %
                               (self.show_obj.tvid_prodid, season, episode), logger.ERROR)
                    pass

                # if we tried loading it from NFO and didn't find the NFO, try the Indexers
                if not self._hasnfo:
                    try:
                        self.load_from_tvinfo(season, episode)
                    except exceptions_helper.EpisodeDeletedException:
                        # if we failed SQL *and* NFO, Indexers then fail
                        raise exceptions_helper.EpisodeNotFoundException(
                            'Couldn\'t find episode %sx%s' % (season, episode))
            elif existing_only:
                raise exceptions_helper.EpisodeNotFoundException(
                    'Couldn\'t find episode %sx%s' % (season, episode))

    def load_from_db(self, season, episode, show_result=None, **kwargs):
        # type: (int, int, Optional[List[Row]], Any) -> bool
        """

        kwargs['scene_result']: type: Optional[List[Row]] passed thru

        :param season: season number
        :param episode: episode number
        :param show_result:
        """
        logger.log('%s: Loading episode details from DB for episode %sx%s'
                   % (self._show_obj.tvid_prodid, season, episode), logger.DEBUG)

        show_result = show_result and next(iter(show_result), None)
        if not show_result or episode != show_result['episode'] or season != show_result['season']:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                """
                SELECT *
                FROM tv_episodes
                WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?
                LIMIT 2
                """, [self._show_obj.tvid, self._show_obj.prodid, season, episode])

            if 1 != len(sql_result):
                if len(sql_result):
                    raise exceptions_helper.MultipleDBEpisodesException('DB has multiple records for the same show')

                logger.log('%s: Episode %sx%s not found in the database'
                           % (self._show_obj.tvid_prodid, self._season, self._episode), logger.DEBUG)
                return False

            show_result = next(iter(sql_result))

        # todo: change to _tvid , _epid after removing indexer, indexerid
        self._tvid = int(show_result['indexer'])
        self._epid = int(show_result['indexerid'])

        self._absolute_number = show_result['absolute_number']
        self._airdate = datetime.date.fromordinal(int(show_result['airdate']))
        self._airtime = int_to_time(try_int(show_result['airtime'], None))
        self._description = self._description if not show_result['description'] else show_result['description']
        self._episode = episode
        self._file_size = try_int(show_result['file_size'])
        self._is_proper = self._is_proper if not show_result['is_proper'] else try_int(show_result['is_proper'])
        self._name = self._name if not show_result['name'] else show_result['name']
        self._network = show_result['network'] or self._show_obj.internal_network
        self._network_country = show_result['network_country']
        self._network_country_code = show_result['network_country_code']
        self._network_id = show_result['network_id']
        self._network_is_stream = bool(show_result['network_is_stream'])
        self._runtime = show_result['runtime']
        self._season = season
        self._status = self._status if None is show_result['status'] else int(show_result['status'])
        self._subtitles = show_result['subtitles'] and show_result['subtitles'] or show_result['subtitles'].split(',')
        self._subtitles_lastsearch = show_result['subtitles_lastsearch']
        self._subtitles_searchcount = show_result['subtitles_searchcount']
        self._timestamp = show_result['timestamp'] or self._make_timestamp()
        self._version = self._version if not show_result['version'] else int(show_result['version'])
        self.location = show_result['location'] and ek.ek(os.path.normpath, show_result['location']) or self.location

        if None is not show_result['release_group']:
            self._release_group = show_result['release_group']

        if None is not show_result['release_name']:
            self._release_name = show_result['release_name']

        sickbeard.scene_numbering.xem_refresh(self._show_obj.tvid, self._show_obj.prodid)

        self.scene_absolute_number = try_int(show_result['scene_absolute_number'])
        if 0 == self.scene_absolute_number:
            self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                self._show_obj.tvid, self._show_obj.prodid,
                absolute_number=self._absolute_number, season=self._season, episode=episode,
                show_result=show_result, show_obj=self._show_obj, **kwargs)

        self.scene_season = try_int(show_result['scene_season'])
        self.scene_episode = try_int(show_result['scene_episode'])
        if 0 == self.scene_season or 0 == self.scene_episode:
            self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode, show_obj=self._show_obj,
                show_result=show_result, **kwargs)

        self._timezone = show_result['timezone']
        if not self._timezone and (self._network or self._show_obj.internal_timezone):
            if self._show_obj.internal_timezone:
                self._timezone = self._show_obj.internal_timezone
            else:
                _, self.timezone = network_timezones.get_network_timezone(self._network, return_name=True)

        self.dirty = False
        return True

    # noinspection PyProtectedMember
    def _make_timestamp(self):
        # type: (...) -> Optional[integer_types]
        if self.airdate:
            if isinstance(self._airtime, datetime.time):
                ep_time = self._airtime
            elif isinstance(self._show_obj._airtime, datetime.time):
                ep_time = self._show_obj._airtime
            else:
                ep_time = datetime.time(hour=0, minute=0)
            tzinfo = None
            if isinstance(self._timezone, string_types) and self._timezone:
                tzinfo = tz.gettz(self._timezone, zoneinfo_priority=True)
            elif isinstance(self._network, string_types) and self._network:
                tzinfo = tz.gettz(self._network, zoneinfo_priority=True)
            elif isinstance(self._show_obj.timezone, string_types) and self._show_obj.timezone:
                tzinfo = self._show_obj.timezone
            elif isinstance(self._show_obj.network, string_types) and self._show_obj.network:
                tzinfo = network_timezones.get_network_timezone(self._show_obj.network)
            if PY2:
                return SGDatetime.combine(self.airdate, ep_time).replace(tzinfo=tzinfo).timestamp_far()
            return SGDatetime.combine(self.airdate, ep_time, tzinfo=tzinfo).timestamp_far()
        return None

    def load_from_tvinfo(
            self,
            season=None,  # type: integer_types
            episode=None,  # type: integer_types
            cache=True,  # type: bool
            tvapi=None,  # type: Any
            cached_season=None,  # type: Dict
            update=False,  # type: bool
            cached_show=None,  # type: Dict
            switch=False,  # type: bool
            old_tvid=None,  # type: int
            old_prodid=None,  # type: integer_types
            switch_list=None  # type: List
    ):  # type: (...) -> Optional[bool]
        """
        :param season: season number
        :param episode: episode number
        :param cache:
        :param tvapi:
        :param cached_season:
        :param update:
        :param cached_show:
        :param switch:
        :param old_tvid:
        :param old_prodid:
        :param switch_list:
        """
        if None is season:
            season = self._season
        if None is episode:
            episode = self._episode

        logger.log('%s: Loading episode details from %s for episode %sx%s' %
                   (self._show_obj.tvid_prodid, sickbeard.TVInfoAPI(self._show_obj.tvid).name, season, episode),
                   logger.DEBUG)

        try:
            if cached_show:
                ep_info = cached_show[season][episode]
            elif None is cached_season:
                if None is tvapi:
                    tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

                    if not cache:
                        tvinfo_config['cache'] = False

                    show_lang = self._show_obj.lang

                    if show_lang:
                        tvinfo_config['language'] = show_lang

                    if 0 != self._show_obj.dvdorder:
                        tvinfo_config['dvdorder'] = True

                    t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
                else:
                    t = tvapi
                ep_info = t.get_show(self._show_obj.prodid)[season][episode]  # type: TVInfoEpisode
            else:
                ep_info = cached_season[episode]  # type: TVInfoEpisode

        except (BaseTVinfoEpisodenotfound, BaseTVinfoSeasonnotfound):
            logger.log('Unable to find the episode on %s... has it been removed? Should I delete from db?' %
                       sickbeard.TVInfoAPI(self.tvid).name, logger.DEBUG)
            # if I'm no longer on the Indexers but I once was then delete myself from the DB
            if -1 != self._epid and helpers.should_delete_episode(self._status):
                self.delete_episode()
            elif UNKNOWN == self._status:
                self.status = SKIPPED
            return
        except (BaseTVinfoError, IOError) as e:
            logger.log('%s threw up an error: %s' % (sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.DEBUG)
            # if the episode is already valid just log it, if not throw it up
            if UNKNOWN == self._status:
                self.status = SKIPPED

            if self._name:
                logger.log('%s timed out but there is enough info from other sources, allowing the error' %
                           sickbeard.TVInfoAPI(self.tvid).name, logger.DEBUG)
                return

            logger.log('%s timed out, unable to create the episode' % sickbeard.TVInfoAPI(self.tvid).name,
                       logger.ERROR)
            return False

        if getattr(ep_info, 'absolute_number', None) in (None, ''):
            logger.debug('This episode (%s - %sx%s) has no absolute number on %s' %
                         (self.show_obj.unique_name, season, episode, sickbeard.TVInfoAPI(self.tvid).name))
        else:
            logger.log('%s: The absolute_number for %sx%s is : %s' %
                       (self._show_obj.tvid_prodid, season, episode, ep_info['absolute_number']), logger.DEBUG)
            self.absolute_number = int(ep_info['absolute_number'])

        if switch and None is not switch_list:
            if self._name != self.dict_prevent_nonetype(ep_info, 'episodename'):
                switch_list.append(self.show_obj.switch_ep_change_sql(old_tvid, old_prodid, episode, season,
                                                                      TVSWITCH_EP_RENAMED))
        self.name = self.dict_prevent_nonetype(ep_info, 'episodename')
        self.season = season
        self.episode = episode

        sickbeard.scene_numbering.xem_refresh(self._show_obj.tvid, self._show_obj.prodid)

        self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
            self._show_obj.tvid, self._show_obj.prodid,
            absolute_number=self._absolute_number,
            season=self._season, episode=self._episode, show_obj=self._show_obj)

        self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
            self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode, show_obj=self._show_obj)

        self.description = self.dict_prevent_nonetype(ep_info, 'overview')

        firstaired = getattr(ep_info, 'firstaired', None)
        if None is firstaired or firstaired in '0000-00-00':
            firstaired = str(datetime.date.fromordinal(1))
        raw_airdate = [int(x) for x in firstaired.split('-')]

        old_airdate_future = self._airdate == datetime.date.fromordinal(1) or self._airdate >= datetime.date.today()
        try:
            self.airdate = datetime.date(raw_airdate[0], raw_airdate[1], raw_airdate[2])
        except (ValueError, IndexError):
            logger.error('Malformed air date retrieved from %s (%s - %sx%s)' %
                         (sickbeard.TVInfoAPI(self.tvid).name, self.show_obj.unique_name, season, episode))
            # if I'm incomplete on TVDB but I once was complete then just delete myself from the DB for now
            if -1 != self._epid and helpers.should_delete_episode(self._status):
                self.delete_episode()
            elif UNKNOWN == self._status:
                self.status = SKIPPED
            return False

        self.network = ep_info.network
        if not self._network:
            self.network = self._show_obj.internal_network
        self.network_id = ep_info.network_id
        self.network_country = ep_info.network_country
        self.network_country_code = ep_info.network_country_code
        self.timezone = ep_info.network_timezone
        if not self._timezone and (self._network or self._show_obj.internal_timezone):
            if self._show_obj.internal_timezone:
                self._timezone = self._show_obj.internal_timezone
            else:
                _, self.timezone = network_timezones.get_network_timezone(self._network, return_name=True)
        self.network_is_stream = ep_info.network_is_stream
        self.airtime = ep_info.airtime
        self.runtime = ep_info.runtime
        self.timestamp = ep_info.timestamp or self._make_timestamp()

        today = datetime.date.today()
        delta = datetime.timedelta(days=1)
        if self._timestamp and self._timezone:
            show_time = SGDatetime.from_timestamp(self._timestamp, tz_aware=True, local_time=False,
                                                  tzinfo=tz.gettz(self._timezone))
        else:
            show_time = network_timezones.parse_date_time(self._airdate.toordinal(),
                                                          self._airtime or self._show_obj.airs,
                                                          self._network or self._show_obj.network)
        tz_now = datetime.datetime.now(network_timezones.SG_TIMEZONE)
        show_length = datetime.timedelta(minutes=helpers.try_int(self._runtime or self._show_obj.runtime, 60))
        future_airtime = (self._airdate > (today + delta) or
                          (not self._airdate < (today - delta) and ((show_time + show_length) > tz_now)))

        # early conversion to int so that episode doesn't get marked dirty
        self.epid = getattr(ep_info, 'id', None)
        if None is self._epid:
            logger.log('Failed to retrieve ID from %s' % sickbeard.TVInfoAPI(self.tvid).name, logger.ERROR)
            if helpers.should_delete_episode(self._status):
                self.delete_episode()
            elif UNKNOWN == self._status:
                self.status = (SKIPPED, UNAIRED)[future_airtime]
            return False

        # don't update show status if show dir is missing, unless it's missing on purpose
        # noinspection PyProtectedMember
        if not ek.ek(os.path.isdir, self._show_obj._location) \
                and not sickbeard.CREATE_MISSING_SHOW_DIRS and not sickbeard.ADD_SHOWS_WO_DIR:
            if UNKNOWN == self._status:
                self.status = (SKIPPED, UNAIRED)[future_airtime]
                logger.log('The show directory is missing but an episode status found at Unknown is set Skipped')
            else:
                logger.log('The show directory is missing,'
                           ' not bothering to change the episode statuses since it\'d probably be invalid')
            return

        if self._location:
            logger.log('%s: Setting status for %sx%s based on status %s and existence of %s' %
                       (self._show_obj.tvid_prodid, season, episode, statusStrings[self._status], self._location),
                       logger.DEBUG)

        # if we don't have the file
        if not ek.ek(os.path.isfile, self._location):

            if self._status in [SKIPPED, UNAIRED, UNKNOWN, WANTED]:
                very_old_delta = datetime.timedelta(days=90)
                very_old_airdate = datetime.date.fromordinal(1) < self._airdate < (today - very_old_delta)

                # if this episode hasn't aired yet set the status to UNAIRED
                if future_airtime:
                    msg = 'Episode airs in the future, marking it %s'
                    self.status = UNAIRED

                # if there's no airdate then set it to unaired (and respect ignored)
                elif self._airdate == datetime.date.fromordinal(1):
                    if IGNORED == self._status:
                        msg = 'Episode has no air date and marked %s, no change'
                    else:
                        msg = 'Episode has no air date, marking it %s'
                        self.status = UNAIRED

                # if the airdate is in the past
                elif UNAIRED == self._status:
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self._status], ','.join([(' is a special', '')[0 < self._season],
                                                              ('', ' is paused')[self._show_obj.paused]])) + '%s')
                    self.status = (SKIPPED, WANTED)[0 < self._season
                                                    and not self._show_obj.paused and not very_old_airdate]

                # if still UNKNOWN or SKIPPED with the deprecated future airdate method
                elif UNKNOWN == self._status or (SKIPPED == self._status and old_airdate_future):
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self._status], ','.join([
                            ('', ' has old future date format')[SKIPPED == self._status and old_airdate_future],
                            ('', ' is being updated')[bool(update)], (' is a special', '')[0 < self._season]])) + '%s')
                    self.status = (SKIPPED, WANTED)[update and not self._show_obj.paused and 0 < self._season
                                                    and not very_old_airdate]

                else:
                    msg = 'Not touching episode status %s, with air date in the past, because there is no file'

            else:
                msg = 'Not touching episode status %s, because there is no file'

            logger.log(msg % statusStrings[self._status], logger.DEBUG)

        # if we have a media file then it's downloaded
        elif sickbeard.helpers.has_media_ext(self._location):
            if IGNORED == self._status:
                logger.log('File exists for %sx%s, ignoring because of status %s' %
                           (self._season, self._episode, statusStrings[self._status]), logger.DEBUG)
            # leave propers alone, you have to either post-process them or manually change them back
            elif self._status not in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED:
                msg = '(1) Status changes from %s to ' % statusStrings[self._status]
                self.status = Quality.statusFromNameOrFile(self._location, anime=self._show_obj.is_anime)
                logger.log('%s%s' % (msg, statusStrings[self._status]), logger.DEBUG)

        # shouldn't get here probably
        else:
            msg = '(2) Status changes from %s to ' % statusStrings[self._status]
            self.status = UNKNOWN
            logger.log('%s%s' % (msg, statusStrings[self._status]), logger.DEBUG)

    def load_from_nfo(self, location):
        """

        :param location:
        :type location: AnyStr
        """
        # noinspection PyProtectedMember
        if not ek.ek(os.path.isdir, self._show_obj._location):
            logger.log('%s: The show directory is missing, not bothering to try loading the episode NFO'
                       % self._show_obj.tvid_prodid)
            return

        logger.log('%s: Loading episode details from the NFO file associated with %s'
                   % (self.show_obj.tvid_prodid, location), logger.DEBUG)

        self.location = location

        if '' != self.location:

            if UNKNOWN == self._status and sickbeard.helpers.has_media_ext(self.location):
                status_quality = Quality.statusFromNameOrFile(self.location, anime=self._show_obj.is_anime)
                logger.log('(3) Status changes from %s to %s' % (self._status, status_quality), logger.DEBUG)
                self.status = status_quality

            nfo_file = sickbeard.helpers.replace_extension(self.location, 'nfo')
            logger.log('%s: Using NFO name %s' % (self._show_obj.tvid_prodid, nfo_file), logger.DEBUG)

            if ek.ek(os.path.isfile, nfo_file):
                try:
                    show_xml = etree.ElementTree(file=nfo_file)
                except (SyntaxError, ValueError) as e:
                    logger.log('Error loading the NFO, backing up the NFO and skipping for now: %s' % ex(e),
                               logger.ERROR)  # TODO: figure out what's wrong and fix it
                    try:
                        ek.ek(os.rename, nfo_file, '%s.old' % nfo_file)
                    except (BaseException, Exception) as e:
                        logger.log(
                            'Failed to rename your episode\'s NFO file - you need to delete it or fix it: %s' % ex(e),
                            logger.ERROR)
                    raise exceptions_helper.NoNFOException('Error in NFO format')

                # TODO: deprecated function getiterator needs to be replaced
                # for epDetails in showXML.getiterator('episodedetails'):
                for epDetails in list(show_xml.iter('episodedetails')):
                    if None is epDetails.findtext('season') or int(epDetails.findtext('season')) != self._season or \
                                    None is epDetails.findtext('episode') or int(
                            epDetails.findtext('episode')) != self._episode:
                        logger.log('%s: NFO has an <episodedetails> block for a different episode - wanted %sx%s'
                                   ' but got %sx%s' %
                                   (self._show_obj.tvid_prodid, self._season, self._episode,
                                    epDetails.findtext('season'), epDetails.findtext('episode')), logger.DEBUG)
                        continue

                    if None is epDetails.findtext('title') or None is epDetails.findtext('aired'):
                        raise exceptions_helper.NoNFOException('Error in NFO format (missing episode title or airdate)')

                    self.name = epDetails.findtext('title')
                    self.episode = int(epDetails.findtext('episode'))
                    self.season = int(epDetails.findtext('season'))

                    sickbeard.scene_numbering.xem_refresh(self._show_obj.tvid, self._show_obj.prodid)

                    self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                        self._show_obj.tvid, self._show_obj.prodid,
                        absolute_number=self._absolute_number,
                        season=self._season, episode=self._episode, show_obj=self._show_obj)

                    self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                        self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode,
                        show_obj=self._show_obj)

                    self.description = epDetails.findtext('plot')
                    if None is self._description:
                        self.description = ''

                    if epDetails.findtext('aired'):
                        raw_airdate = [int(x) for x in epDetails.findtext('aired').split("-")]
                        self.airdate = datetime.date(raw_airdate[0], raw_airdate[1], raw_airdate[2])
                    else:
                        self.airdate = datetime.date.fromordinal(1)

                    self.hasnfo = True
            else:
                self.hasnfo = False

            if ek.ek(os.path.isfile, sickbeard.helpers.replace_extension(nfo_file, 'tbn')):
                self.hastbn = True
            else:
                self.hastbn = False

    def __ne__(self, o):
        # type: (TVEpisode) -> bool
        return not self.__eq__(o)

    def __eq__(self, o):
        # type: (TVEpisode) -> bool
        if not isinstance(o, TVEpisode):
            return False
        return o._show_obj == self._show_obj and o._epid == self._epid

    def __hash__(self):
        return hash((self._show_obj, self._epid))

    def __repr__(self):
        return 'TVEpisode(%s)' % self.__str__()

    def __str__(self):

        return '%s - %sx%s - %s\n' % (self.show_obj.unique_name, self.season, self.episode, self.name) \
               + 'location: %s\n' % self.location \
               + 'description: %s\n' % self.description \
               + 'subtitles: %s\n' % ','.join(self.subtitles) \
               + 'subtitles_searchcount: %s\n' % self.subtitles_searchcount \
               + 'subtitles_lastsearch: %s\n' % self.subtitles_lastsearch \
               + 'airdate: %s (%s)\n' % (self.airdate.toordinal(), self.airdate) \
               + 'hasnfo: %s\n' % self.hasnfo \
               + 'hastbn: %s\n' % self.hastbn \
               + 'status: %s\n' % self.status

    def create_meta_files(self, force=False):

        # noinspection PyProtectedMember
        if not ek.ek(os.path.isdir, self.show_obj._location):
            logger.log('%s: The show directory is missing, not bothering to try to create metadata'
                       % self.show_obj.tvid_prodid)
            return

        self.create_nfo(force)
        self.create_thumbnail()

        if self.check_for_meta_files():
            self.save_to_db()

    def create_nfo(self, force=False):
        """

        :return:
        :rtype: bool
        """
        result = False

        for cur_provider in itervalues(sickbeard.metadata_provider_dict):
            result = cur_provider.create_episode_metadata(self, force) or result

        return result

    def create_thumbnail(self):
        """

        :return:
        :rtype: bool
        """
        result = False

        for cur_provider in itervalues(sickbeard.metadata_provider_dict):
            result = cur_provider.create_episode_thumb(self) or result

        return result

    def delete_episode(self, return_sql=False):
        # type: (bool) -> Optional[List[List]]
        """
        deletes epsiode from db, alternatively returns sql to remove episode from db

        :param return_sql: only return sql to delete episode
        """

        logger.debug('Deleting %s %sx%s from the DB' % (self._show_obj.unique_name, self._season, self._episode))

        # remove myself from the show dictionary
        if self.show_obj.get_episode(self._season, self._episode, no_create=True) == self:
            logger.log('Removing myself from my show\'s list', logger.DEBUG)
            del self.show_obj.sxe_ep_obj[self._season][self._episode]

        # delete myself from the DB
        logger.log('Deleting myself from the database', logger.DEBUG)

        sql = [['DELETE FROM tv_episodes WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?',
               [self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode]]]
        if return_sql:
            return sql

        my_db = db.DBConnection()
        my_db.mass_action(sql)

        raise exceptions_helper.EpisodeDeletedException()

    def get_sql(self, force_save=False):
        # type: (bool) -> Optional[List[AnyStr, List]]
        """
        Creates SQL queue for this episode if any of its data has been changed since the last save.

        :param force_save: If True it will create SQL queue even if no data has been changed since the last save
        (aka if the record is not dirty).
        """

        if not self.dirty and not force_save:
            logger.log('%s: Not creating SQL queue - record is not dirty' % self._show_obj.tvid_prodid, logger.DEBUG)
            return

        self.dirty = False
        return [
            """
            INSERT OR REPLACE INTO tv_episodes
            (episode_id,
            indexerid, indexer, name, description,
            subtitles, subtitles_searchcount, subtitles_lastsearch,
            airdate, hasnfo, hastbn, status, location, file_size,
            release_name, is_proper, showid, season, episode, absolute_number,
            version, release_group,
            network, network_id, network_country, network_country_code, network_is_stream,
            airtime, runtime, timestamp, timezone,
            scene_absolute_number, scene_season, scene_episode)
            VALUES
            ((SELECT episode_id FROM tv_episodes
            WHERE indexer = ? AND showid = ?
            AND season = ? AND episode = ?)
            ,?,?
            ,?,?
            ,?,?,?
            ,?,?,?,?,?,?
            ,?,?
            ,?,?,?,?
            ,?,?
            ,?,?,?,?,?
            ,?,?,?,?,
            (SELECT scene_absolute_number FROM tv_episodes
             WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),
            (SELECT scene_season FROM tv_episodes
             WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),
            (SELECT scene_episode FROM tv_episodes
             WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?));
            """, [self._show_obj.tvid, self._show_obj.prodid,
                  self._season, self._episode,
                  self._epid, self._tvid,
                  self._name, self._description,
                  ','.join([sub for sub in self._subtitles]), self._subtitles_searchcount, self._subtitles_lastsearch,
                  self._airdate.toordinal(), self._hasnfo, self._hastbn, self._status, self._location, self._file_size,
                  self._release_name, self._is_proper,
                  self._show_obj.prodid, self._season, self._episode, self._absolute_number,
                  self._version, self._release_group,
                  self._network, self._network_id,
                  self._network_country, self._network_country_code, self._network_is_stream,
                  time_to_int(self._airtime), self._runtime, self._timestamp, self._timezone,
                  self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode,
                  self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode,
                  self._show_obj.tvid, self._show_obj.prodid, self._season, self._episode]]

    def save_to_db(self, force_save=False):
        """
        Saves this episode to the database if any of its data has been changed since the last save.

        :param force_save: If True it will save to the database even if no data has been changed since the
        last save (aka if the record is not dirty).
        """

        if not self.dirty and not force_save:
            logger.log('%s: Not saving episode to db - record is not dirty' % self._show_obj.tvid_prodid, logger.DEBUG)
            return

        logger.log('%s: Saving episode details to database' % self._show_obj.tvid_prodid, logger.DEBUG)

        logger.log('STATUS IS %s' % statusStrings[self._status], logger.DEBUG)

        new_value_dict = dict(
            absolute_number=self._absolute_number,
            airdate=self._airdate.toordinal(),
            airtime=time_to_int(self._airtime),
            description=self._description,
            file_size=self._file_size,
            hasnfo=self._hasnfo,
            hastbn=self._hastbn,
            indexer=self._tvid,
            indexerid=self._epid,
            is_proper=self._is_proper,
            location=self._location,
            name=self._name,
            network=self._network,
            network_country=self._network_country,
            network_country_code=self._network_country_code,
            network_id=self._network_id,
            network_is_stream=self._network_is_stream,
            release_group=self._release_group,
            release_name=self._release_name,
            runtime=self._runtime,
            status=self._status,
            subtitles=','.join([sub for sub in self._subtitles]),
            subtitles_lastsearch=self._subtitles_lastsearch,
            subtitles_searchcount=self._subtitles_searchcount,
            timestamp=self._timestamp,
            timezone=self._timezone,
            version=self._version,
        )

        control_value_dict = dict(
            indexer=self.show_obj.tvid, showid=self.show_obj.prodid, season=self.season, episode=self.episode)

        # use a custom update/insert method to get the data into the DB
        my_db = db.DBConnection()
        my_db.upsert('tv_episodes', new_value_dict, control_value_dict)
        self.dirty = False

    # # TODO: remove if unused
    # def full_location(self):
    #     if self.location in (None, ''):
    #         return None
    #     return ek.ek(os.path.join, self.show_obj.location, self.location)
    #
    # # TODO: remove if unused
    # def create_strings(self, pattern=None):
    #     patterns = [
    #         '%S.N.S%SE%0E',
    #         '%S.N.S%0SE%E',
    #         '%S.N.S%SE%E',
    #         '%S.N.S%0SE%0E',
    #         '%SN S%SE%0E',
    #         '%SN S%0SE%E',
    #         '%SN S%SE%E',
    #         '%SN S%0SE%0E'
    #     ]
    #
    #     strings = []
    #     if not pattern:
    #         for p in patterns:
    #             strings += [self._format_pattern(p)]
    #         return strings
    #     return self._format_pattern(pattern)

    def pretty_name(self):
        """
        Returns the name of this episode in a "pretty" human-readable format. Used for logging
        and notifications and such.

        :return: A string representing the episode's name and season/ep numbers
        :rtype: AnyStr
        """

        if self._show_obj.anime and not self._show_obj.scene:
            return self._format_pattern('%SN - %AB - %EN')

        if self._show_obj.air_by_date:
            return self._format_pattern('%SN - %AD - %EN')

        return self._format_pattern('%SN - %Sx%0E - %EN')

    def _ep_name(self):
        """
        :return: the name of the episode to use during renaming. Combines the names of related episodes.
        Eg. "Ep Name (1)" and "Ep Name (2)" becomes "Ep Name"
            "Ep Name" and "Other Ep Name" becomes "Ep Name & Other Ep Name"
        :rtype: AnyStr
        """

        multi_name_regex = r'(.*) \(\d{1,2}\)'

        self.related_ep_obj = sorted(self.related_ep_obj, key=lambda se: se.episode)

        if 0 == len(self.related_ep_obj):
            good_name = self._name
        else:
            single_name = True
            known_good_name = None

            for cur_name in [self._name] + [x.name for x in self.related_ep_obj]:
                match = re.match(multi_name_regex, cur_name)
                if not match:
                    single_name = False
                    break

                if None is known_good_name:
                    known_good_name = match.group(1)
                elif known_good_name != match.group(1):
                    single_name = False
                    break

            if single_name:
                good_name = known_good_name
            else:
                good_name = self._name
                for ep_obj in self.related_ep_obj:
                    good_name += ' & ' + ep_obj.name

        return good_name or 'tba'

    def _replace_map(self):
        """
        Generates a replacement map for this episode which maps all possible custom naming patterns to the correct
        value for this episode.

        Returns: A dict with patterns as the keys and their replacement values as the values.
        """

        ep_name = self._ep_name()

        def dot(name):
            return helpers.sanitize_scene_name(name)

        def us(name):
            return re.sub('[ -]', '_', name)

        def release_name(name, is_anime=False):
            if name:
                name = helpers.remove_non_release_groups(name, is_anime)
            return name

        def release_group(show_obj, name):
            if name:
                name = helpers.remove_non_release_groups(name, show_obj.is_anime)
            else:
                return ''

            try:
                np = NameParser(name, show_obj=show_obj, naming_pattern=True)
                parse_result = np.parse(name)
            except (InvalidNameException, InvalidShowException) as e:
                logger.log('Unable to get parse release_group: %s' % ex(e), logger.DEBUG)
                return ''

            if not parse_result.release_group:
                return ''
            return parse_result.release_group

        ep_status, ep_qual = Quality.splitCompositeStatus(self._status)

        if sickbeard.NAMING_STRIP_YEAR:
            show_name = re.sub(r'\(\d+\)$', '', self._show_obj.name).rstrip()
        else:
            show_name = self._show_obj.name

        return {
            '%SN': show_name,
            '%S.N': dot(show_name),
            '%S_N': us(show_name),
            '%EN': ep_name,
            '%E.N': dot(ep_name),
            '%E_N': us(ep_name),
            '%QN': Quality.qualityStrings[ep_qual],
            '%Q.N': dot(Quality.qualityStrings[ep_qual]),
            '%Q_N': us(Quality.qualityStrings[ep_qual]),
            '%S': str(self._season),
            '%0S': '%02d' % self._season,
            '%E': str(self._episode),
            '%0E': '%02d' % self._episode,
            '%XS': str(self.scene_season),
            '%0XS': '%02d' % self.scene_season,
            '%XE': str(self.scene_episode),
            '%0XE': '%02d' % self.scene_episode,
            '%AB': '%(#)03d' % {'#': self._absolute_number},
            '%XAB': '%(#)03d' % {'#': self.scene_absolute_number},
            '%RN': release_name(self._release_name, self._show_obj.is_anime),
            '%RG': release_group(self._show_obj, self._release_name),
            '%AD': str(self._airdate).replace('-', ' '),
            '%A.D': str(self._airdate).replace('-', '.'),
            '%A_D': us(str(self._airdate)),
            '%A-D': str(self._airdate),
            '%Y': str(self._airdate.year),
            '%M': str(self._airdate.month),
            '%D': str(self._airdate.day),
            '%0M': '%02d' % self._airdate.month,
            '%0D': '%02d' % self._airdate.day,
            '%RT': "PROPER" if self.is_proper else "",
            '%V': 'v%s' % self._version if self._show_obj.is_anime and 1 < self._version else '',
        }

    @staticmethod
    def _format_string(pattern, replace_map):
        """
        Replaces all template strings with the correct value
        """

        result_name = pattern

        # do the replacements
        for cur_replacement in sorted(list_keys(replace_map), reverse=True):
            result_name = result_name.replace(cur_replacement, helpers.sanitize_filename(replace_map[cur_replacement]))
            result_name = result_name.replace(cur_replacement.lower(),
                                              helpers.sanitize_filename(replace_map[cur_replacement].lower()))

        return result_name

    def _format_pattern(self, pattern=None, multi=None, anime_type=None):
        """
        Manipulates an episode naming pattern and then fills the template in
        """

        if None is pattern:
            pattern = sickbeard.NAMING_PATTERN

        if None is multi:
            multi = sickbeard.NAMING_MULTI_EP

        if None is anime_type:
            anime_type = sickbeard.NAMING_ANIME

        replace_map = self._replace_map()

        result_name = pattern

        # if there's no release group then replace it with a reasonable facsimile
        if not replace_map['%RN']:
            if self._show_obj.air_by_date or self._show_obj.sports:
                result_name = result_name.replace('%RN', '%S.N.%A.D.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.%A.D.%e.n-SickGear')
            elif 3 != anime_type:
                result_name = result_name.replace('%RN', '%S.N.%AB.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.%ab.%e.n-SickGear')
            else:
                result_name = result_name.replace('%RN', '%S.N.S%0SE%0E.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.s%0se%0e.%e.n-SickGear')

            result_name = result_name.replace('%RG', 'SickGear')
            result_name = result_name.replace('%rg', 'SickGear')
            logger.log('Episode has no release name, replacing it with a generic one: %s' % result_name, logger.DEBUG)

        if not replace_map['%RT']:
            result_name = re.sub('([ _.-]*)%RT([ _.-]*)', r'\2', result_name)

        # split off ep name part only
        name_groups = re.split(r'[\\/]', result_name)

        # figure out the double-ep numbering style for each group, if applicable
        for cur_name_group in name_groups:

            season_ep_regex = r'''
                                (?P<pre_sep>[ _.-]*)
                                ((?:s(?:eason|eries)?\s*)?%0?S(?![._]?N))
                                (.*?)
                                (%0?E(?![._]?N))
                                (?P<post_sep>[ _.-]*)
                              '''
            ep_only_regex = '(E?%0?E(?![._]?N))'

            # try the normal way
            season_ep_match = re.search(season_ep_regex, cur_name_group, re.I | re.X)
            ep_only_match = re.search(ep_only_regex, cur_name_group, re.I | re.X)

            # if we have a season and episode then collect the necessary data
            if season_ep_match:
                season_format = season_ep_match.group(2)
                ep_sep = season_ep_match.group(3)
                ep_format = season_ep_match.group(4)
                sep = season_ep_match.group('pre_sep')
                if not sep:
                    sep = season_ep_match.group('post_sep')
                if not sep:
                    sep = ' '

                # force 2-3-4 format if they chose to extend
                if multi in (NAMING_EXTEND, NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED):
                    ep_sep = '-'

                regex_used = season_ep_regex

            # if there's no season then there's not much choice so we'll just force them to use 03-04-05 style
            elif ep_only_match:
                season_format = ''
                ep_sep = '-'
                ep_format = ep_only_match.group(1)
                sep = ''
                regex_used = ep_only_regex

            else:
                continue

            # we need at least this much info to continue
            if not ep_sep or not ep_format:
                continue

            # start with the ep string, eg. E03
            ep_string = self._format_string(ep_format.upper(), replace_map)
            for cur_ep_obj in self.related_ep_obj:

                # for limited extend we only append the last ep
                if multi in (NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED) \
                        and cur_ep_obj != self.related_ep_obj[-1]:
                    continue

                elif multi == NAMING_DUPLICATE:
                    # add " - S01"
                    ep_string += sep + season_format

                elif multi == NAMING_SEPARATED_REPEAT:
                    ep_string += sep

                # add "E04"
                ep_string += ep_sep

                if multi == NAMING_LIMITED_EXTEND_E_PREFIXED:
                    ep_string += 'E'

                # noinspection PyProtectedMember
                ep_string += cur_ep_obj._format_string(ep_format.upper(), cur_ep_obj._replace_map())

            if 3 != anime_type:
                absolute_number = (self._absolute_number, self._episode)[0 == self._absolute_number]

                if 0 != self._season:  # dont set absolute numbers if we are on specials !
                    if 1 == anime_type:  # this crazy person wants both ! (note: +=)
                        ep_string += sep + '%(#)03d' % {'#': absolute_number}
                    elif 2 == anime_type:  # total anime freak only need the absolute number ! (note: =)
                        ep_string = '%(#)03d' % {'#': absolute_number}

                    for cur_ep_obj in self.related_ep_obj:
                        if 0 != cur_ep_obj.absolute_number:
                            ep_string += '-' + '%(#)03d' % {'#': cur_ep_obj.absolute_number}
                        else:
                            ep_string += '-' + '%(#)03d' % {'#': cur_ep_obj.episode}

            regex_replacement = None
            if 2 == anime_type:
                regex_replacement = r'\g<pre_sep>' + ep_string + r'\g<post_sep>'
            elif season_ep_match:
                regex_replacement = r'\g<pre_sep>\g<2>\g<3>' + ep_string + r'\g<post_sep>'
            elif ep_only_match:
                regex_replacement = ep_string

            if regex_replacement:
                # fill out the template for this piece and then insert this piece into the actual pattern
                cur_name_group_result = re.sub('(?i)(?x)' + regex_used, regex_replacement, cur_name_group)
                # cur_name_group_result = cur_name_group.replace(ep_format, ep_string)
                # logger.log(u"found "+ep_format+" as the ep pattern using "+regex_used+"
                # and replaced it with "+regex_replacement+" to result in "+cur_name_group_result+"
                # from "+cur_name_group, logger.DEBUG)
                result_name = result_name.replace(cur_name_group, cur_name_group_result)

        result_name = self._format_string(result_name, replace_map)

        logger.log('formatting pattern: %s -> %s' % (pattern, result_name), logger.DEBUG)

        return result_name

    def proper_path(self):
        """
        Figures out the path where this episode SHOULD live according to the renaming rules, relative from the show dir
        :return:
        :rtype: AnyStr
        """

        anime_type = sickbeard.NAMING_ANIME
        if not self._show_obj.is_anime:
            anime_type = 3

        result = self.formatted_filename(anime_type=anime_type)

        # if they want us to flatten it and we're allowed to flatten it then we will
        if self._show_obj.flatten_folders and not sickbeard.NAMING_FORCE_FOLDERS:
            return result

        # if not we append the folder on and use that
        return ek.ek(os.path.join, self.formatted_dir(), result)

    def formatted_dir(self, pattern=None, multi=None):
        """
        Just the folder name of the episode
        """

        if None is pattern:
            # we only use ABD if it's enabled, this is an ABD show, AND this is not a multi-ep
            if self._show_obj.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.related_ep_obj:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self._show_obj.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.related_ep_obj:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self._show_obj.anime and sickbeard.NAMING_CUSTOM_ANIME:
                pattern = sickbeard.NAMING_ANIME_PATTERN
            else:
                pattern = sickbeard.NAMING_PATTERN

        # split off the dirs only, if they exist
        name_groups = re.split(r'[\\/]', pattern)

        if 1 == len(name_groups):
            return ''
        return self._format_pattern(ek.ek(os.sep.join, name_groups[:-1]), multi)

    def formatted_filename(self, pattern=None, multi=None, anime_type=None):
        """
        Just the filename of the episode, formatted based on the naming settings
        """

        if None is pattern:
            # we only use ABD if it's enabled, this is an ABD show, AND this is not a multi-ep
            if self._show_obj.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.related_ep_obj:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self._show_obj.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.related_ep_obj:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self._show_obj.anime and sickbeard.NAMING_CUSTOM_ANIME:
                pattern = sickbeard.NAMING_ANIME_PATTERN
            else:
                pattern = sickbeard.NAMING_PATTERN

        # split off the dirs only, if they exist
        name_groups = re.split(r'[\\/]', pattern)

        return self._format_pattern(name_groups[-1], multi, anime_type)

    def rename(self):
        """
        Renames an episode file and all related files to the location and filename as specified
        in the naming settings.
        """

        if not ek.ek(os.path.isfile, self.location):
            logger.log('Can\'t perform rename on %s when it doesn\'t exist, skipping' % self.location, logger.WARNING)
            return

        proper_path = self.proper_path()
        absolute_proper_path = ek.ek(os.path.join, self._show_obj.location, proper_path)
        absolute_current_path_no_ext, file_ext = ek.ek(os.path.splitext, self.location)
        absolute_current_path_no_ext_length = len(absolute_current_path_no_ext)

        related_subs = []

        current_path = absolute_current_path_no_ext

        if absolute_current_path_no_ext.startswith(self._show_obj.location):
            current_path = absolute_current_path_no_ext[len(self._show_obj.location):]

        logger.log('Renaming/moving episode from the base path %s to %s' % (self.location, absolute_proper_path),
                   logger.DEBUG)

        # if it's already named correctly then don't do anything
        if proper_path == current_path:
            logger.log('%s: File %s is already named correctly, skipping' % (self._epid, self.location),
                       logger.DEBUG)
            return

        related_files = postProcessor.PostProcessor(self.location).list_associated_files(
            self.location, base_name_only=True)

        if self.show_obj.subtitles and '' != sickbeard.SUBTITLES_DIR:
            related_subs = postProcessor.PostProcessor(self.location).list_associated_files(sickbeard.SUBTITLES_DIR,
                                                                                            subtitles_only=True)
            # absolute_proper_subs_path = ek.ek(os.path.join, sickbeard.SUBTITLES_DIR, self.formatted_filename())

        logger.log('Files associated to %s: %s' % (self.location, related_files), logger.DEBUG)

        # move the ep file
        result = helpers.rename_ep_file(self.location, absolute_proper_path, absolute_current_path_no_ext_length)

        # move related files
        for cur_related_file in related_files:
            renamed = helpers.rename_ep_file(cur_related_file, absolute_proper_path,
                                             absolute_current_path_no_ext_length)
            if not renamed:
                logger.log('%s: Unable to rename file %s' % (self._epid, cur_related_file), logger.ERROR)

        for cur_related_sub in related_subs:
            absolute_proper_subs_path = ek.ek(os.path.join, sickbeard.SUBTITLES_DIR, self.formatted_filename())
            renamed = helpers.rename_ep_file(cur_related_sub, absolute_proper_subs_path,
                                             absolute_current_path_no_ext_length)
            if not renamed:
                logger.log('%s: Unable to rename file %s' % (self._epid, cur_related_sub), logger.ERROR)

        # save the ep
        with self.lock:
            if result:
                self.location = absolute_proper_path + file_ext
                for ep_obj in self.related_ep_obj:
                    ep_obj.location = absolute_proper_path + file_ext

        # in case something changed with the metadata just do a quick check
        for cur_ep_obj in [self] + self.related_ep_obj:
            cur_ep_obj.check_for_meta_files()

        # save any changes to the database
        sql_l = []
        with self.lock:
            for ep_obj in [self] + self.related_ep_obj:
                result = ep_obj.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

    def airdate_modify_stamp(self):
        """
        Make the modify date and time of a file reflect the show air date and time.
        Note: Also called from postProcessor

        """
        has_timestamp = isinstance(self._timestamp, int) and 1 < self._timestamp
        if not has_timestamp and (not isinstance(self._airdate, datetime.date) or 1 == self._airdate.year):
            logger.log('%s: Did not change modify date of %s because episode date is never aired or invalid'
                       % (self._show_obj.tvid_prodid, ek.ek(os.path.basename, self.location)), logger.DEBUG)
            return

        aired_dt = None
        if not has_timestamp:
            if isinstance(self._airtime, datetime.time):
                airtime = self._airtime
            else:
                hr, m = network_timezones.parse_time(self._show_obj.airs)
                airtime = datetime.time(hr, m)

            aired_dt = SGDatetime.combine(self.airdate, airtime)

        try:
            aired_epoch = SGDatetime.to_file_timestamp(aired_dt)
            filemtime = int(ek.ek(os.path.getmtime, self.location))
        except (BaseException, Exception):
            return

        if filemtime != aired_epoch:

            result, loglevel = 'Changed', logger.MESSAGE
            if not helpers.touch_file(self.location, aired_epoch):
                result, loglevel = 'Error changing', logger.WARNING

            logger.log('%s: %s modify date of %s to show air date %s'
                       % (self._show_obj.tvid_prodid, result, ek.ek(os.path.basename, self.location),
                          'n/a' if not aired_dt else aired_dt.strftime('%b %d,%Y (%H:%M)')), loglevel)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.RLock()
        self.__dict__.update(d)

    def __bool__(self):
        return bool(self._tvid) and bool(self._epid)

    __nonzero__ = __bool__
