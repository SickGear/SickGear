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

from collections import OrderedDict
import datetime
import glob
import inspect
import os.path
import re
import requests
import stat
import threading
import traceback

coreid_warnings = False
if coreid_warnings:
    import warnings
    warnings.simplefilter('always', DeprecationWarning)

from lxml_etree import etree
from lib import imdbpie
from imdbpie import ImdbAPIError
from lib import subliminal

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex

import sickbeard
from . import db, helpers, history, image_cache, indexermapper, logger, \
    name_cache, network_timezones, notifiers, postProcessor, subtitles
from .anime import BlackAndWhiteList
from .common import Quality, statusStrings, \
    ARCHIVED, DOWNLOADED, FAILED, IGNORED, SNATCHED, SNATCHED_PROPER, SNATCHED_ANY, SKIPPED, UNAIRED, UNKNOWN, WANTED, \
    NAMING_DUPLICATE, NAMING_EXTEND, NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED, NAMING_SEPARATED_REPEAT
from .generic_queue import QueuePriorities
from .name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from .helpers import try_int, try_float
from .indexermapper import del_mapping, save_mapping, MapStatus
from .indexers.indexer_config import TVINFO_TVDB, TVINFO_TVRAGE
from .indexers.indexer_exceptions import BaseTVinfoAttributenotfound, check_exception_type, ExceptionTuples
from .sgdatetime import SGDatetime
from .tv_base import TVEpisodeBase, TVShowBase

from _23 import filter_list, filter_iter, list_keys
from six import integer_types, iteritems, itervalues, string_types

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, List, Optional, Text


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
        self._tvid = None
        self._prodid = None
        self._sid_int = None

        if isinstance(tvid_prodid, dict) and 1 == len(tvid_prodid):
            try:
                for (tvid, prodid) in iteritems(tvid_prodid):
                    self._tvid, self._prodid = int(tvid), int(prodid)
            except ValueError:
                pass
        elif isinstance(tvid_prodid, string_types):
            if self.glue in tvid_prodid:
                try:
                    for (tvid, prodid) in [re.findall(r'(\d+)\s*%s\s*(\d+)' % self.glue, tvid_prodid)[0]]:
                        self._tvid, self._prodid = int(tvid), int(prodid)
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
                        self._tvid, self._prodid = show_obj.tvid, legacy_showid

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
            self._tvid = tvid_prodid & tvid_bitmask
            self._prodid = tvid_prodid >> prodid_bitshift
            self._sid_int = tvid_prodid
            return

        if None not in (self._prodid, self._tvid):
            self._sid_int = self._prodid << prodid_bitshift | self._tvid

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
                return self._sid_int
            elif self._checktype(kind, dict):
                return {self.tvid: self.prodid}
            elif self._checktype(kind, tuple):
                return self.tvid, self.prodid
        if None is kind or self._checktype(kind, string_types):
            return '%s%s%s' % (self.tvid, self.glue, self.prodid)
        return [self.tvid, self.prodid]

    @property
    def tvid(self):
        return self._tvid

    @property
    def prodid(self):
        return self._prodid


class TVShow(TVShowBase):

    def __init__(self, tvid, prodid, lang=''):
        # type: (int, int, Text) -> None
        super(TVShow, self).__init__(tvid, prodid, lang)

        self._tvid = int(tvid)
        self._prodid = int(prodid)
        self._sid_int = self.create_sid(self._tvid, self._prodid)
        self._paused = 0
        self._mapped_ids = {}  # type: Dict
        self._not_found_count = None  # type: None or int
        self._last_found_on_indexer = -1  # type: int

        self._location = ''  # type: AnyStr
        # self._is_location_good = None
        self.lock = threading.Lock()
        self.sxe_ep_obj = {}   # type: Dict
        self.nextaired = ''  # type: AnyStr

        # noinspection added so that None _can_ be excluded from type annotation
        # so that this property evaluates directly to the class on ctrl+hover instead of "multiple implementations"
        # noinspection PyTypeChecker
        self.release_groups = None  # type: BlackAndWhiteList

        show_obj = helpers.find_show_by_id(self._sid_int)
        if None is not show_obj:
            raise exceptions_helper.MultipleShowObjectsException('Can\'t create a show if it already exists')

        self.load_from_db()

    @staticmethod
    def create_sid(tvid, prodid):
        # type: (int, int) -> int
        return int(prodid) << prodid_bitshift | int(tvid)

    @property
    def tvid(self):
        return self._tvid

    @tvid.setter
    def tvid(self, val):
        self.dirty_setter('_tvid')(self, int(val))
        self.tvid_prodid = self.create_sid(val, self._prodid)
        # TODO: remove the following when indexer is gone
        # in deprecation transition, tvid also sets indexer so that existing uses continue to work normally
        self.dirty_setter('_indexer')(self, int(val))

    @property
    def prodid(self):
        return self._prodid

    @prodid.setter
    def prodid(self, val):
        # type: (int) -> None
        self.dirty_setter('_prodid')(self, int(val))
        self.tvid_prodid = self.create_sid(self._tvid, val)
        # TODO: remove the following when indexerid is gone
        # in deprecation transition, prodid also sets indexerid so that existing usages continue as normal
        self.dirty_setter('_indexerid')(self, int(val))

    @property
    def tvid_prodid(self):
        # type: (...) -> AnyStr
        return TVidProdid({self._tvid: self._prodid})()

    @property
    def sid_int(self):
        return self._sid_int

    @tvid_prodid.setter
    def tvid_prodid(self, val):
        tvid_prodid_obj = TVidProdid(val)
        if getattr(self, 'tvid_prodid') != tvid_prodid_obj():
            self.tvid, self.prodid = tvid_prodid_obj.list
            self.dirty = True
        tvid_prodid_int = int(tvid_prodid_obj)
        if getattr(self, '_sid_int') != tvid_prodid_int:
            self._sid_int = tvid_prodid_int

    def _helper_load_failed_db(self):
        if None is self._not_found_count or self._last_found_on_indexer == -1:
            my_db = db.DBConnection()
            results = my_db.select('SELECT fail_count, last_success'
                                   ' FROM tv_shows_not_found'
                                   ' WHERE indexer = ? AND indexer_id = ?',
                                   [self.tvid, self.prodid])
            if results:
                self._not_found_count = helpers.try_int(results[0]['fail_count'])
                self._last_found_on_indexer = helpers.try_int(results[0]['last_success'])
            else:
                self._not_found_count = 0
                self._last_found_on_indexer = 0

    @property
    def not_found_count(self):
        self._helper_load_failed_db()
        return self._not_found_count

    @not_found_count.setter
    def not_found_count(self, v):
        if isinstance(v, integer_types) and v != self._not_found_count:
            self._last_found_on_indexer = self.last_found_on_indexer
            my_db = db.DBConnection()
            # noinspection PyUnresolvedReferences
            last_check = SGDatetime.now().totimestamp(default=0)
            # in case of flag change (+/-) don't change last_check date
            if abs(v) == abs(self._not_found_count):
                results = my_db.select('SELECT last_check'
                                       ' FROM tv_shows_not_found'
                                       ' WHERE indexer = ? AND indexer_id = ?',
                                       [self.tvid, self.prodid])
                if results:
                    last_check = helpers.try_int(results[0]['last_check'])
            my_db.upsert('tv_shows_not_found',
                         dict(fail_count=v, last_check=last_check, last_success=self._last_found_on_indexer),
                         dict(indexer=self.tvid, indexer_id=self.prodid))
            self._not_found_count = v

    @property
    def last_found_on_indexer(self):
        self._helper_load_failed_db()
        return (self._last_found_on_indexer, self.last_update_indexer)[0 >= self._last_found_on_indexer]

    def inc_not_found_count(self):
        my_db = db.DBConnection()
        results = my_db.select('SELECT last_check'
                               ' FROM tv_shows_not_found'
                               ' WHERE indexer = ? AND indexer_id = ?',
                               [self.tvid, self.prodid])
        days = (show_not_found_retry_days - 1, 0)[abs(self.not_found_count) <= concurrent_show_not_found_days]
        if not results or datetime.datetime.fromtimestamp(helpers.try_int(results[0]['last_check'])) + \
                datetime.timedelta(days=days, hours=18) < datetime.datetime.now():
            self.not_found_count += (-1, 1)[0 <= self.not_found_count]

    def reset_not_found_count(self):
        if 0 != self.not_found_count:
            self._not_found_count = 0
            self._last_found_on_indexer = 0
            my_db = db.DBConnection()
            my_db.action('DELETE FROM tv_shows_not_found'
                         ' WHERE indexer = ? AND indexer_id = ?',
                         [self.tvid, self.prodid])

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
        if not self._mapped_ids:
            acquired_lock = self.lock.acquire(False)
            if acquired_lock:
                try:
                    indexermapper.map_indexers_to_show(self)
                finally:
                    self.lock.release()
        return self._mapped_ids

    @ids.setter
    def ids(self, value):
        if isinstance(value, dict):
            for k, v in iteritems(value):
                if k not in sickbeard.indexermapper.indexer_list or \
                        not isinstance(v, dict) or \
                        not isinstance(v.get('id'), integer_types) or \
                        not isinstance(v.get('status'), integer_types) or \
                        v.get('status') not in indexermapper.MapStatus.allstatus or \
                        not isinstance(v.get('date'), datetime.date):
                    return
            self._mapped_ids = value

    @property
    def is_anime(self):
        """
        :rtype: bool
        """
        return 0 < int(self.anime)

    @property
    def is_sports(self):
        """
        :rtype: bool
        """
        return 0 < int(self.sports)

    @property
    def is_scene(self):
        """
        :rtype: bool
        """
        return 0 < int(self.scene)

    def _get_location(self):
        # no dir check needed if missing show dirs are created during post-processing
        if sickbeard.CREATE_MISSING_SHOW_DIRS:
            return self._location

        if ek.ek(os.path.isdir, self._location):
            return self._location

        raise exceptions_helper.ShowDirNotFoundException('Show folder does not exist: \'%s\'' % self._location)

    def _set_location(self, new_location):
        logger.log('Setter sets location to %s' % new_location, logger.DEBUG)
        # Don't validate dir if user wants to add shows without creating a dir
        if sickbeard.ADD_SHOWS_WO_DIR or ek.ek(os.path.isdir, new_location):
            self.dirty_setter('_location')(self, new_location)
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
        """

        :param season: None or season number
        :type season: None or int
        :param has_location:  return only with location
        :type has_location: bool
        :param check_related_eps: get related episodes
        :type check_related_eps: bool
        :return: List of TVEpisode objects
        :rtype: List[TVEpisode]
        """
        sql_selection = 'SELECT season, episode'

        if check_related_eps:
            # subselection to detect multi-episodes early, share_location > 0
            sql_selection += ' , (SELECT COUNT (*) FROM tv_episodes WHERE showid = tve.showid AND ' \
                             'indexer = tve.indexer AND season = tve.season AND location != "" AND ' \
                             'location = tve.location AND episode != tve.episode) AS share_location '

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
        results = my_db.select(sql_selection, sql_parameter)

        ep_obj_list = []
        for cur_result in results:
            ep_obj = self.get_episode(int(cur_result['season']), int(cur_result['episode']))
            if ep_obj:
                ep_obj.related_ep_obj = []
                if check_related_eps and ep_obj.location:
                    # if there is a location, check if it's a multi-episode (share_location > 0)
                    # and put into related_ep_obj
                    if cur_result['share_location'] > 0:
                        # noinspection SqlRedundantOrderingDirection
                        related_ep_result = my_db.select(
                            'SELECT * FROM tv_episodes'
                            ' WHERE indexer = ? AND showid = ?'
                            ' AND season = ? AND location = ? AND episode != ? ORDER BY episode ASC',
                            [self.tvid, self.prodid,
                             ep_obj.season, ep_obj.location, ep_obj.episode])
                        for cur_ep_result in related_ep_result:
                            related_ep_obj = self.get_episode(int(cur_ep_result['season']),
                                                              int(cur_ep_result['episode']))
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
                    ep_sql=None  # type: Optional
                    ):  # type: (...) -> Optional[TVEpisode]
        """
        Initialise sxe_ep_obj with db fetched season keys, and then fill the TVShow episode property
        and return an TVEpisode object if no_create is False

        :param season: Season number
        :param episode: Episode number
        :param path: path to file episode
        :param no_create: return None instead of an instantiated TVEpisode object
        :param absolute_number: absolute number
        :param ep_sql:
        :return: TVEpisode object
        """
        # if we get an anime get the real season and episode
        if self.is_anime and absolute_number and not season and not episode:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                'SELECT season, episode FROM tv_episodes' 
                ' WHERE indexer = ? AND showid = ?'
                ' AND absolute_number = ? AND season != 0'
                ' LIMIT 2',
                [self.tvid, self.prodid,
                 absolute_number])

            if 1 == len(sql_result):
                season = int(sql_result[0]['season'])
                episode = int(sql_result[0]['episode'])
                logger.log('Found episode by absolute_number: %s which is %sx%s' % (absolute_number, season, episode),
                           logger.DEBUG)
            elif 1 < len(sql_result):
                logger.log('Multiple entries for absolute number: %s in show: %s  found.' %
                           (absolute_number, self.name), logger.ERROR)
                return None
            else:
                logger.log('No entries for absolute number: %s in show: %s found.'
                           % (absolute_number, self.name), logger.DEBUG)
                return None

        if season not in self.sxe_ep_obj:
            self.sxe_ep_obj[season] = {}

        if episode not in self.sxe_ep_obj[season] or None is self.sxe_ep_obj[season][episode]:
            if no_create:
                return None

            # logger.log('%s: An object for episode %sx%s did not exist in the cache, trying to create it' %
            #            (self.tvid_prodid, season, episode), logger.DEBUG)

            if path:
                ep_obj = TVEpisode(self, season, episode, path, show_sql=ep_sql)
            else:
                ep_obj = TVEpisode(self, season, episode, show_sql=ep_sql)

            if None is not ep_obj:
                self.sxe_ep_obj[season][episode] = ep_obj

        return self.sxe_ep_obj[season][episode]

    def should_update(self, update_date=datetime.date.today()):

        # In some situations self.status = None.. need to figure out where that is!
        if not self.status:
            self.status = ''
            logger.log('Status missing for show: [%s] with status: [%s]' %
                       (self.tvid_prodid, self.status), logger.DEBUG)

        last_update_indexer = datetime.date.fromordinal(self.last_update_indexer)

        # if show was not found for 1 week, only retry to update once a week
        if (concurrent_show_not_found_days < abs(self.not_found_count)) \
                and (update_date - last_update_indexer) < datetime.timedelta(days=show_not_found_retry_days):
            return False

        my_db = db.DBConnection()
        sql_result = my_db.mass_action(
            [['SELECT airdate FROM [tv_episodes]' +
              ' WHERE indexer = ? AND showid = ?' +
              ' AND season > 0'
              ' ORDER BY season DESC, episode DESC LIMIT 1',
              [self.tvid, self.prodid]],
             ['SELECT airdate FROM [tv_episodes]'
              + ' WHERE indexer = ? AND showid = ?'
              + ' AND season > 0 AND airdate > 1'
              + ' ORDER BY airdate DESC LIMIT 1',
              [self.tvid, self.prodid]]])

        last_airdate_unknown = 1 >= int(sql_result[0][0]['airdate']) if sql_result and sql_result[0] else True

        last_airdate = datetime.date.fromordinal(sql_result[1][0]['airdate']) \
            if sql_result and sql_result[1] else datetime.date.fromordinal(1)

        # if show is not 'Ended' and last episode aired less then 460 days ago
        # or don't have an airdate for the last episode always update (status 'Continuing' or '')
        update_days_limit = 2013
        ended_limit = datetime.timedelta(days=update_days_limit)
        if 'Ended' not in self.status and (last_airdate == datetime.date.fromordinal(1)
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

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.tvid_prodid)
            return

        logger.log('%s: Writing NFOs for all episodes' % self.tvid_prodid)

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            'SELECT season, episode FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?'
            ' AND location != ""',
            [self.tvid, self.prodid])

        processed = []
        for cur_result in sql_result:
            if (cur_result['season'], cur_result['episode']) in processed:
                continue
            logger.log('%s: Retrieving/creating episode %sx%s'
                       % (self.tvid_prodid, cur_result['season'], cur_result['episode']), logger.DEBUG)
            ep_obj = self.get_episode(cur_result['season'], cur_result['episode'])
            if not ep_obj.related_ep_obj:
                processed += [(cur_result['season'], cur_result['episode'])]
            else:
                logger.log('%s: Found related to %sx%s episode(s)... %s'
                           % (self.tvid_prodid, cur_result['season'], cur_result['episode'],
                              ', '.join(['%sx%s' % (x.season, x.episode) for x in ep_obj.related_ep_obj])),
                           logger.DEBUG)
                processed += list(set([(cur_result['season'], cur_result['episode'])] +
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
                if self.subtitles:
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
        logger.log('Loading all episodes for [%s] from the DB' % self.name)

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT season, episode FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?',
            [self.tvid, self.prodid])

        scannedEps = {}

        tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

        if self.lang:
            tvinfo_config['language'] = self.lang

        if 0 != self.dvdorder:
            tvinfo_config['dvdorder'] = True

        t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)

        cachedShow = None
        try:
            cachedShow = t[self.prodid]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log('Unable to find cached seasons from %s: %s' % (
                    sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.WARNING)
            else:
                raise e
        if None is cachedShow:
            return scannedEps

        cachedSeasons = {}
        for cur_result in sql_result:

            delete_ep = False

            season = int(cur_result['season'])
            episode = int(cur_result['episode'])

            if season not in cachedSeasons:
                try:
                    cachedSeasons[season] = cachedShow[season]
                except Exception as e:
                    if check_exception_type(e, ExceptionTuples.tvinfo_seasonnotfound):
                        logger.log('Error when trying to load the episode for [%s] from %s: %s' %
                                   (self.name, sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.WARNING)
                        delete_ep = True
                    else:
                        raise e

            if season not in scannedEps:
                scannedEps[season] = {}

            logger.log('Loading episode %sx%s for [%s] from the DB' % (season, episode, self.name), logger.DEBUG)

            try:
                ep_obj = self.get_episode(season, episode)

                # if we found out that the ep is no longer on TVDB then delete it from our database too
                if delete_ep and helpers.should_delete_episode(ep_obj.status):
                    ep_obj.delete_episode()

                ep_obj.load_from_db(season, episode)
                ep_obj.load_from_tvinfo(tvapi=t, update=update)
                scannedEps[season][episode] = True
            except exceptions_helper.EpisodeDeletedException:
                logger.log('Tried loading an episode that should have been deleted from the DB [%s], skipping it'
                           % self.name, logger.DEBUG)
                continue

        return scannedEps

    def load_episodes_from_tvinfo(self, cache=True, update=False):
        # type: (bool, bool) -> Optional[Dict[int, Dict[int, TVEpisode]]]
        """

        :param cache:
        :param update:
        :return:
        """
        tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

        if not cache:
            tvinfo_config['cache'] = False

        if self.lang:
            tvinfo_config['language'] = self.lang

        if 0 != self.dvdorder:
            tvinfo_config['dvdorder'] = True

        logger.log('%s: Loading all episodes for [%s] from %s..'
                   % (self.tvid_prodid, self.name, sickbeard.TVInfoAPI(self.tvid).name))

        try:
            t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
            show_obj = t[self.prodid]
        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_error):
                logger.log('%s timed out, unable to update episodes for [%s] from %s' %
                           (sickbeard.TVInfoAPI(self.tvid).name, self.name, sickbeard.TVInfoAPI(self.tvid).name),
                           logger.ERROR)
                return None
            else:
                raise e

        scannedEps = {}

        sql_l = []
        for season in show_obj:
            scannedEps[season] = {}
            for episode in show_obj[season]:
                # need some examples of wtf episode 0 means to decide if we want it or not
                if 0 == episode:
                    continue
                try:
                    ep_obj = self.get_episode(season, episode)
                except exceptions_helper.EpisodeNotFoundException:
                    logger.log('%s: %s object for %sx%s from [%s] is incomplete, skipping this episode' %
                               (self.tvid_prodid, sickbeard.TVInfoAPI(self.tvid).name, season, episode, self.name))
                    continue
                else:
                    try:
                        ep_obj.load_from_tvinfo(tvapi=t, update=update)
                    except exceptions_helper.EpisodeDeletedException:
                        logger.log('The episode from [%s] was deleted, skipping the rest of the load' % self.name)
                        continue

                with ep_obj.lock:
                    logger.log('%s: Loading info from %s for episode %sx%s from [%s]' %
                               (self.tvid_prodid, sickbeard.TVInfoAPI(self.tvid).name, season, episode, self.name),
                               logger.DEBUG)
                    ep_obj.load_from_tvinfo(season, episode, tvapi=t, update=update)

                    result = ep_obj.get_sql()
                    if None is not result:
                        sql_l.append(result)

                scannedEps[season][episode] = True

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # Done updating save last update date
        self.last_update_indexer = datetime.date.today().toordinal()
        self.save_to_db()

        return scannedEps

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
        """

        :param path:
        :type path: AnyStr
        :return:
        :rtype: TVEpisode or None
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

            logger.log('%s: %s parsed to %s %sx%s' % (self.tvid_prodid, path, self.name, season_number, cur_ep_num),
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

    def load_from_db(self):
        """

        :return:
        :rtype: bool or None
        """
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM tv_shows'
                                  ' WHERE indexer = ? AND indexer_id = ?',
                                  [self.tvid, self.prodid])

        if 1 != len(sql_result):
            if 1 < len(sql_result):
                tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()
                if self.lang:
                    tvinfo_config['language'] = self.lang
                t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
                cached_show = t[self.prodid]
                vals = (self.prodid, '' if not cached_show else ' [%s]' % cached_show['seriesname'].strip())
                if 0 != len(sql_result):
                    logger.log('%s: Loading show info%s from database' % vals)
                    raise exceptions_helper.MultipleDBShowsException()
            logger.log('%s-%s: Unable to find the show%s in the database' % (self.tvid, self.prodid, self.name))
            return
        else:
            if not self._tvid:
                self.tvid, self.prodid = int(sql_result[0]['indexer']), int(sql_result[0]['indexer_id'])
            if not self._name:
                self._name = sql_result[0]['show_name']
            if not self._network:
                self._network = sql_result[0]['network']
            if not self._genre:
                self._genre = sql_result[0]['genre']
            if None is self._classification:
                self._classification = sql_result[0]['classification']

            self._runtime = sql_result[0]['runtime']

            self._status = sql_result[0]['status']
            if not self._status:
                self._status = ''
            self._airs = sql_result[0]['airs']
            if not self._airs:
                self._airs = ''
            self._startyear = sql_result[0]['startyear']
            if not self._startyear:
                self._startyear = 0

            self._air_by_date = sql_result[0]['air_by_date']
            if not self._air_by_date:
                self._air_by_date = 0

            self._anime = sql_result[0]['anime']
            if None is self._anime:
                self._anime = 0

            self._sports = sql_result[0]['sports']
            if not self._sports:
                self._sports = 0

            self._scene = sql_result[0]['scene']
            if not self._scene:
                self._scene = 0

            self._subtitles = sql_result[0]['subtitles']
            if self._subtitles:
                self._subtitles = 1
            else:
                self._subtitles = 0

            self._dvdorder = sql_result[0]['dvdorder']
            if not self._dvdorder:
                self._dvdorder = 0

            self._upgrade_once = sql_result[0]['archive_firstmatch']
            if not self._upgrade_once:
                self._upgrade_once = 0

            self._quality = int(sql_result[0]['quality'])
            self._flatten_folders = int(sql_result[0]['flatten_folders'])
            self._paused = int(sql_result[0]['paused'])

            try:
                self.location = sql_result[0]['location']
            except (BaseException, Exception):
                self.dirty_setter('_location')(self, sql_result[0]['location'])
                # self._is_location_good = False

            if not self._lang:
                self._lang = sql_result[0]['lang']

            self._last_update_indexer = sql_result[0]['last_update_indexer']

            self._rls_ignore_words = sql_result[0]['rls_ignore_words']
            self._rls_require_words = sql_result[0]['rls_require_words']

            if not self._imdbid:
                imdbid = sql_result[0]['imdb_id'] or ''
                self._imdbid = ('', imdbid)[2 < len(imdbid)]

            if self._anime:
                self.release_groups = BlackAndWhiteList(self.tvid, self.prodid, self.tvid_prodid)

            if not self._overview:
                self._overview = sql_result[0]['overview']

            self._prune = sql_result[0]['prune']
            if not self._prune:
                self._prune = 0

            self._tag = sql_result[0]['tag']
            if not self._tag:
                self._tag = 'Show List'

        logger.log(u'Loaded.. {: <9} {: <8} {}'.format(
            sickbeard.TVInfoAPI(self.tvid).config.get('name') + ',', '%s,' % self.prodid, self.name))

        # Get IMDb_info from database
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT *'
                                  ' FROM imdb_info'
                                  ' WHERE indexer = ? AND indexer_id = ?',
                                  [self.tvid, self.prodid])

        if 0 < len(sql_result):
            # this keys() is not a dict
            self._imdb_info = dict(zip(sql_result[0].keys(), [(r, '')[None is r] for r in sql_result[0]]))
        elif sickbeard.USE_IMDB_INFO:
            logger.log('%s: The next show update will attempt to find IMDb info for [%s]' %
                       (self.tvid_prodid, self.name), logger.DEBUG)
            return

        self.dirty = False
        return True

    def load_from_tvinfo(self, cache=True, tvapi=None):
        """

        :param cache:
        :type cache: bool
        :param tvapi:
        :type tvapi:
        """
        # There's gotta be a better way of doing this but we don't wanna
        # change the cache value elsewhere
        if None is tvapi:
            tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

            if not cache:
                tvinfo_config['cache'] = False

            if self.lang:
                tvinfo_config['language'] = self.lang

            if 0 != self.dvdorder:
                tvinfo_config['dvdorder'] = True

            t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)

        else:
            t = tvapi

        ep_info = t[self.prodid, False]
        if None is ep_info or getattr(t, 'show_not_found', False):
            if getattr(t, 'show_not_found', False):
                self.inc_not_found_count()
                logger.log('Show [%s] not found (maybe even removed?)' % self.name, logger.WARNING)
            else:
                logger.log('Show data [%s] not found' % self.name, logger.WARNING)
            return False
        self.reset_not_found_count()

        try:
            self.name = ep_info['seriesname'].strip()
        except AttributeError:
            raise BaseTVinfoAttributenotfound(
                "Found %s, but attribute 'seriesname' was empty." % self.tvid_prodid)

        if ep_info:
            logger.log('%s: Loading show info [%s] from %s' % (
                self.tvid_prodid, self.name, sickbeard.TVInfoAPI(self.tvid).name))

        self.classification = self.dict_prevent_nonetype(ep_info, 'classification', 'Scripted')
        self.genre = self.dict_prevent_nonetype(ep_info, 'genre')
        self.network = self.dict_prevent_nonetype(ep_info, 'network')
        self.runtime = self.dict_prevent_nonetype(ep_info, 'runtime')

        self.imdbid = self.dict_prevent_nonetype(ep_info, 'imdb_id')

        if None is not getattr(ep_info, 'airs_dayofweek', None) and None is not getattr(ep_info, 'airs_time', None):
            self.airs = ('%s %s' % (ep_info['airs_dayofweek'], ep_info['airs_time'])).strip()

        if None is not getattr(ep_info, 'firstaired', None):
            self.startyear = int(str(ep_info["firstaired"]).split('-')[0])

        self.status = self.dict_prevent_nonetype(ep_info, 'status')
        self.overview = self.dict_prevent_nonetype(ep_info, 'overview')

    def load_imdb_info(self):

        if not sickbeard.USE_IMDB_INFO:
            return

        logger.log('Retrieving show info [%s] from IMDb' % self.name, logger.DEBUG)
        try:
            self._get_imdb_info()
        except (BaseException, Exception) as e:
            logger.log('Error loading IMDb info: %s' % ex(e), logger.ERROR)
            logger.log('%s' % traceback.format_exc(), logger.ERROR)

    @staticmethod
    def check_imdb_redirect(imdb_id):
        """

        :param imdb_id: imdb id
        :type imdb_id: AnyStr or int or long
        """
        page_url = 'https://www.imdb.com/title/{0}/'.format(imdb_id)
        try:
            response = requests.head(page_url, allow_redirects=True)
            if response.history and any([h for h in response.history if 301 == h.status_code]):
                return re.search(r'(tt\d{7})', response.url, flags=re.I).group(1)
        except (BaseException, Exception):
            pass

    def _get_imdb_info(self, retry=False):

        if not self.imdbid and 0 >= self.ids.get(indexermapper.TVINFO_IMDB, {'id': 0}).get('id', 0):
            return

        imdb_info = {'imdb_id': self.imdbid or 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id'],
                     'title': '',
                     'year': '',
                     'akas': '',
                     'runtimes': self.runtime,
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
            imdb_id = str(self.imdbid or 'tt%07d' % self.ids[indexermapper.TVINFO_IMDB]['id'])
            redirect_check = self.check_imdb_redirect(imdb_id)
            if redirect_check:
                self._imdbid = redirect_check
                imdb_id = redirect_check
                imdb_info['imdb_id'] = self.imdbid
            i = imdbpie.Imdb(exclude_episodes=True, cachedir=ek.ek(os.path.join, sickbeard.CACHE_DIR, 'imdb-pie'))
            if not re.search(r'tt\d{7}', imdb_id, flags=re.I):
                logger.log('Not a valid imdbid: %s for show: %s' % (imdb_id, self.name), logger.WARNING)
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
        if isinstance(imdb_tv.get('runningTimeInMinutes'), (int, string_types)):
            imdb_info['runtimes'] = try_int(imdb_tv.get('runningTimeInMinutes'), '')
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
        logger.log('%s: Obtained info from IMDb -> %s' % (self.tvid_prodid, self.imdb_info), logger.DEBUG)

        logger.log('%s: Parsed latest IMDb show info for [%s]' % (self.tvid_prodid, self.name))

    def next_episode(self):
        logger.log('%s: Finding the episode which airs next for: %s' % (self.tvid_prodid, self.name), logger.DEBUG)

        curDate = datetime.date.today().toordinal()
        if not self.nextaired or self.nextaired and curDate > self.nextaired:
            my_db = db.DBConnection()
            # noinspection SqlRedundantOrderingDirection
            sql_result = my_db.select(
                'SELECT airdate, season, episode FROM tv_episodes'
                + ' WHERE indexer = ? AND showid = ?'
                + ' AND airdate >= ? AND status in (?,?,?)'
                + ' ORDER BY airdate ASC LIMIT 1',
                [self.tvid, self.prodid,
                 datetime.date.today().toordinal(), UNAIRED, WANTED, FAILED])

            if None is sql_result or 0 == len(sql_result):
                logger.log('%s: No episode found... need to implement a show status' % self.tvid_prodid, logger.DEBUG)
                self.nextaired = ''
            else:
                logger.log('%s: Found episode %sx%s' % (
                    self.tvid_prodid, sql_result[0]['season'], sql_result[0]['episode']), logger.DEBUG)
                self.nextaired = sql_result[0]['airdate']

        return self.nextaired

    def delete_show(self, full=False):
        """

        :param full:
        :type full: bool
        """
        sql_l = [["DELETE FROM tv_episodes WHERE indexer = ? AND showid = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM tv_shows WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM imdb_info WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM xem_refresh WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM scene_numbering WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM whitelist WHERE indexer = ? AND show_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM blacklist WHERE indexer = ? AND show_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM indexer_mapping WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]],
                 ["DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?", [self.tvid, self.prodid]]]

        my_db = db.DBConnection()
        my_db.mass_action(sql_l)

        name_cache.remove_from_namecache(self.tvid, self.prodid)

        action = ('delete', 'trash')[sickbeard.TRASH_REMOVE_SHOW]

        # remove self from show list
        sickbeard.showList = filter_list(lambda so: so.tvid_prodid != self.tvid_prodid, sickbeard.showList)

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
        """

        :param force:
        :type force: bool
        """
        cache_inst = image_cache.ImageCache()

        logger.log('Checking & filling cache for show %s' % self.name)
        cache_inst.fill_cache(self, force)

    def refresh_dir(self):

        # make sure the show dir is where we think it is unless dirs are created on the fly
        if not ek.ek(os.path.isdir, self._location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
            return False

        # load from dir
        self.load_episodes_from_dir()

        # run through all locations from DB, check that they exist
        logger.log('%s: Loading all episodes for [%s] with a location from the database'
                   % (self.tvid_prodid, self.name))

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            'SELECT season, episode, location'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND location != ""'
            ' ORDER BY season DESC , episode DESC',
            [self.tvid, self.prodid])

        kept = 0
        deleted = 0
        attempted = []
        sql_l = []
        for cur_result in sql_result:
            season = int(cur_result['season'])
            episode = int(cur_result['episode'])
            location = ek.ek(os.path.normpath, cur_result['location'])

            try:
                ep_obj = self.get_episode(season, episode)
            except exceptions_helper.EpisodeDeletedException:
                logger.log('The episode from [%s] was deleted while we were refreshing it, moving on to the next one'
                           % self.name, logger.DEBUG)
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
        """

        :param force:
        :type force: bool
        """
        # TODO: Add support for force option
        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, can\'t download subtitles' % self.tvid_prodid, logger.DEBUG)
            return
        logger.log('%s: Downloading subtitles' % self.tvid_prodid, logger.DEBUG)

        try:
            my_db = db.DBConnection()
            sql_result = my_db.select(
                'SELECT location FROM tv_episodes'
                + ' WHERE indexer = ? AND showid = ?'
                  ' AND LENGTH(location) != 0'
                + ' ORDER BY season DESC, episode DESC',
                [self.tvid, self.prodid])

            for cur_result in sql_result:
                ep_obj = self.ep_obj_from_file(cur_result['location'])
                _ = ep_obj.download_subtitles(force=force)
        except (BaseException, Exception):
            logger.log('Error occurred when downloading subtitles: %s' % traceback.format_exc(), logger.ERROR)
            return

    def switch_infosrc(self, old_tvid, old_prodid, pausestatus_after=None):
        """

        :param old_tvid: old tvid
        :type old_tvid: int
        :param old_prodid: old prodid
        :type old_prodid: int or long
        :param pausestatus_after: pause after switch
        :type pausestatus_after: bool or None
        """
        my_db = db.DBConnection()
        my_db.mass_action([
            ['UPDATE tv_shows SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE tv_episodes SET indexer = ?, showid = ?, indexerid = 0 WHERE indexer = ? AND showid = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE blacklist SET indexer = ?, show_id = ? WHERE indexer = ? AND show_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE history SET indexer = ?, showid = ? WHERE indexer = ? AND showid = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE imdb_info SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE scene_exceptions SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE scene_numbering SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE whitelist SET indexer = ?, show_id = ? WHERE indexer = ? AND show_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['UPDATE xem_refresh SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
             [self.tvid, self.prodid, old_tvid, old_prodid]],
            ['DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
             [old_tvid, old_prodid]]])

        myFailedDB = db.DBConnection('failed.db')
        myFailedDB.action('UPDATE history SET indexer = ?, showid = ? WHERE indexer = ? AND showid = ?',
                          [self.tvid, self.prodid, old_tvid, old_prodid])
        del_mapping(old_tvid, old_prodid)
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

        # force the update
        try:
            sickbeard.showQueueScheduler.action.updateShow(
                self, force=True, web=True, priority=QueuePriorities.VERYHIGH, pausestatus_after=pausestatus_after)
        except exceptions_helper.CantUpdateException as e:
            logger.log('Unable to update this show. %s' % ex(e), logger.ERROR)

    def save_to_db(self, force_save=False):
        """

        :param force_save:
        :type force_save: bool
        """
        if not self.dirty and not force_save:
            logger.log('%s: Not saving show to db - record is not dirty' % self.tvid_prodid, logger.DEBUG)
            return

        logger.log('%s: Saving show info to database' % self.tvid_prodid, logger.DEBUG)

        newValueDict = dict(
            indexer=self.tvid,
            show_name=self.name,
            location=self._location,
            network=self.network,
            genre=self.genre,
            classification=self.classification,
            runtime=self.runtime,
            quality=self.quality,
            airs=self.airs,
            status=self.status,
            flatten_folders=self.flatten_folders,
            paused=self.paused,
            air_by_date=self.air_by_date,
            anime=self.anime,
            scene=self.scene,
            sports=self.sports,
            subtitles=self.subtitles,
            dvdorder=self.dvdorder,
            archive_firstmatch=self.upgrade_once,
            startyear=self.startyear,
            lang=self.lang, imdb_id=self.imdbid,
            last_update_indexer=self.last_update_indexer,
            rls_ignore_words=self.rls_ignore_words,
            rls_require_words=self.rls_require_words,
            overview=self.overview,
            prune=self.prune,
            tag=self.tag)

        control_value_dict = dict(indexer=self.tvid, indexer_id=self.prodid)

        my_db = db.DBConnection()
        my_db.upsert('tv_shows', newValueDict, control_value_dict)
        self.dirty = False

        if sickbeard.USE_IMDB_INFO and len(self.imdb_info):
            newValueDict = self.imdb_info

            my_db = db.DBConnection()
            my_db.upsert('imdb_info', newValueDict, control_value_dict)

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
        """

        :param season: season number
        :type season: int
        :param episode: episode number
        :type episode: int
        :param quality: quality
        :type quality: int
        :param manual_search: manual search
        :type manual_search: bool
        :param multi_ep: multiple episodes
        :type multi_ep: bool
        :return:
        :rtype: bool
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
        initial_qualities, archive_qualities = Quality.splitQuality(self.quality)
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
        sql_result = my_db.select('SELECT status FROM tv_episodes'
                                  ' WHERE indexer = ? AND showid = ?'
                                  ' AND season = ? AND episode = ?',
                                  [self.tvid, self.prodid, season, episode])

        if not sql_result or not len(sql_result):
            logger.log('Unable to find a matching episode in database, ignoring found episode', logger.DEBUG)
            return False

        cur_status, cur_quality = Quality.splitCompositeStatus(int(sql_result[0]['status']))
        epStatus_text = statusStrings[cur_status]

        logger.log('Existing episode status: %s (%s)' % (statusStrings[cur_status], epStatus_text), logger.DEBUG)

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

        downloadedStatusList = SNATCHED_ANY + [DOWNLOADED]
        # special case: already downloaded quality is not in any of the wanted Qualities
        if cur_status in downloadedStatusList and cur_quality not in all_qualities:
            wanted_qualities = all_qualities
        else:
            wanted_qualities = archive_qualities

        # if re-downloading then only keep items in the archiveQualities list and better than what we have
        if cur_status in downloadedStatusList and quality in wanted_qualities and quality > cur_quality:
            logger.log('Episode already exists but the found episode has better quality, getting found episode',
                       logger.DEBUG)
            return True
        else:
            logger.log('Episode already exists and the found episode has same/lower quality, ignoring found episode',
                       logger.DEBUG)

        logger.log('None of the conditions were met, ignoring found episode', logger.DEBUG)
        return False

    def get_overview(self, ep_status):
        """

        :param ep_status: episode status
        :type ep_status: int
        :return:
        :rtype: int
        """
        return helpers.get_overview(ep_status, self.quality, self.upgrade_once)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.Lock()
        self.__dict__.update(d)


class TVEpisode(TVEpisodeBase):

    def __init__(self, show_obj, season, episode, path='', show_sql=None):
        super(TVEpisode, self).__init__(season, episode, int(show_obj.tvid))
        
        self._show_obj = show_obj  # type: TVShow

        self.scene_season = 0  # type: int
        self.scene_episode = 0  # type: int
        self.scene_absolute_number = 0  # type: int

        self._location = path  # type: AnyStr

        self._tvid = int(self.show_obj.tvid)  # type: int
        self._epid = 0  # type: int

        self.lock = threading.Lock()

        self.specify_episode(self.season, self.episode, show_sql)

        self.related_ep_obj = []  # type: List

        self.check_for_meta_files()

        self.wanted_quality = []  # type: List

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
        self.subtitles = subtitles.subtitles_languages(self.location)

    def download_subtitles(self, force=False):
        """

        :param force:
        :type force: bool
        :return:
        :rtype:
        """
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
                subtitleList = ", ".join([subliminal.language.Language(x).name for x in newsubtitles])
            except (BaseException, Exception):
                logger.log('Could not parse a language to use to fetch subtitles for episode %sx%s' %
                           (self.season, self.episode), logger.DEBUG)
                return
            logger.log('%s: Downloaded %s subtitles for episode %sx%s' %
                       (self.show_obj.tvid_prodid, subtitleList, self.season, self.episode), logger.DEBUG)

            notifiers.notify_subtitle_download(self.pretty_name(), subtitleList)

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
        oldhasnfo = self.hasnfo
        oldhastbn = self.hastbn

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
        return oldhasnfo != self.hasnfo or oldhastbn != self.hastbn

    def specify_episode(self, season, episode, show_sql=None):
        """

        :param season: season number
        :type season: int
        :param episode: episode number
        :type episode: int
        :param show_sql:
        :type show_sql:
        """
        sqlResult = self.load_from_db(season, episode, show_sql)

        if not sqlResult:
            # only load from NFO if we didn't load from DB
            if ek.ek(os.path.isfile, self.location):
                try:
                    self.load_from_nfo(self.location)
                except exceptions_helper.NoNFOException:
                    logger.log('%s: There was an error loading the NFO for episode %sx%s' %
                               (self.show_obj.tvid_prodid, season, episode), logger.ERROR)
                    pass

                # if we tried loading it from NFO and didn't find the NFO, try the Indexers
                if not self.hasnfo:
                    try:
                        result = self.load_from_tvinfo(season, episode)
                    except exceptions_helper.EpisodeDeletedException:
                        result = False

                    # if we failed SQL *and* NFO, Indexers then fail
                    if not result:
                        raise exceptions_helper.EpisodeNotFoundException(
                            'Couldn\'t find episode %sx%s' % (season, episode))

    def load_from_db(self, season, episode, show_sql=None):
        """

        :param season: season number
        :type season: int
        :param episode: episode number
        :type episode: int
        :param show_sql:
        :type show_sql:
        :return:
        :rtype: bool
        """
        logger.log('%s: Loading episode details from DB for episode %sx%s'
                   % (self.show_obj.tvid_prodid, season, episode), logger.DEBUG)

        sql_result = None
        if show_sql:
            sql_result = [s for s in show_sql if episode == s['episode'] and season == s['season']]
        if not sql_result:
            my_db = db.DBConnection()
            sql_result = my_db.select('SELECT *'
                                      ' FROM tv_episodes'
                                      ' WHERE indexer = ? AND showid = ?'
                                      ' AND season = ? AND episode = ?'
                                      ' LIMIT 2',
                                      [self.show_obj.tvid, self.show_obj.prodid,
                                       season, episode])

        if 1 < len(sql_result):
            raise exceptions_helper.MultipleDBEpisodesException('Your DB has two records for the same show somehow.')
        elif 0 == len(sql_result):
            logger.log('%s: Episode %sx%s not found in the database'
                       % (self.show_obj.tvid_prodid, self.season, self.episode), logger.DEBUG)
            return False
        else:
            # NAMEIT logger.log(u'AAAAA from' + str(self.season)+'x'+str(self.episode)
            # + ' -' + self.name + ' to ' + str(sql_result[0]['name']))
            if sql_result[0]['name']:
                self._name = sql_result[0]['name']

            self._season = season
            self._episode = episode
            self._absolute_number = sql_result[0]['absolute_number']
            self._description = sql_result[0]['description']
            if not self._description:
                self._description = ''
            if sql_result[0]['subtitles'] and sql_result[0]['subtitles']:
                self._subtitles = sql_result[0]['subtitles'].split(',')
            self._subtitles_searchcount = sql_result[0]['subtitles_searchcount']
            self._subtitles_lastsearch = sql_result[0]['subtitles_lastsearch']
            self._airdate = datetime.date.fromordinal(int(sql_result[0]['airdate']))
            # logger.log(u'1 Status changes from ' + str(self.status) +
            # ' to ' + str(sql_result[0]['status']), logger.DEBUG)
            if None is not sql_result[0]['status']:
                self._status = int(sql_result[0]['status'])

            # don't overwrite my location
            if sql_result[0]['location'] and sql_result[0]['location']:
                self.location = ek.ek(os.path.normpath, sql_result[0]['location'])
            if sql_result[0]['file_size']:
                self._file_size = int(sql_result[0]['file_size'])
            else:
                self._file_size = 0

            # todo: change to _tvid , _epid after removing indexer, indexerid 
            self.tvid = int(sql_result[0]['indexer'])
            self.epid = int(sql_result[0]['indexerid'])

            sickbeard.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid)

            try:
                self.scene_season = int(sql_result[0]['scene_season'])
            except (BaseException, Exception):
                self.scene_season = 0

            try:
                self.scene_episode = int(sql_result[0]['scene_episode'])
            except (BaseException, Exception):
                self.scene_episode = 0

            try:
                self.scene_absolute_number = int(sql_result[0]['scene_absolute_number'])
            except (BaseException, Exception):
                self.scene_absolute_number = 0

            if 0 == self.scene_absolute_number:
                self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                    self.show_obj.tvid, self.show_obj.prodid,
                    absolute_number=self.absolute_number, 
                    season=self.season, episode=episode)

            if 0 == self.scene_season or 0 == self.scene_episode:
                self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                    self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode)

            if None is not sql_result[0]['release_name']:
                self._release_name = sql_result[0]['release_name']

            if sql_result[0]['is_proper']:
                self._is_proper = int(sql_result[0]['is_proper'])

            if sql_result[0]['version']:
                self._version = int(sql_result[0]['version'])

            if None is not sql_result[0]['release_group']:
                self._release_group = sql_result[0]['release_group']

            self.dirty = False
            return True

    def load_from_tvinfo(self, season=None, episode=None, cache=True, tvapi=None, cached_season=None, update=False):
        """

        :param season: season number
        :type season: int or None
        :param episode: episode number
        :type episode: int or None
        :param cache:
        :type cache: bool
        :param tvapi:
        :type tvapi:
        :param cached_season:
        :type cached_season:
        :param update:
        :type update: bool
        :return:
        :rtype: bool or None
        """
        if None is season:
            season = self.season
        if None is episode:
            episode = self.episode

        logger.log('%s: Loading episode details from %s for episode %sx%s' %
                   (self.show_obj.tvid_prodid, sickbeard.TVInfoAPI(self.show_obj.tvid).name, season, episode),
                   logger.DEBUG)

        show_lang = self.show_obj.lang

        try:
            if None is cached_season:
                if None is tvapi:
                    tvinfo_config = sickbeard.TVInfoAPI(self.tvid).api_params.copy()

                    if not cache:
                        tvinfo_config['cache'] = False

                    if show_lang:
                        tvinfo_config['language'] = show_lang

                    if 0 != self.show_obj.dvdorder:
                        tvinfo_config['dvdorder'] = True

                    t = sickbeard.TVInfoAPI(self.tvid).setup(**tvinfo_config)
                else:
                    t = tvapi
                ep_info = t[self.show_obj.prodid][season][episode]
            else:
                ep_info = cached_season[episode]

        except Exception as e:
            if check_exception_type(e, ExceptionTuples.tvinfo_error, IOError):
                logger.log('%s threw up an error: %s' % (sickbeard.TVInfoAPI(self.tvid).name, ex(e)), logger.DEBUG)
                # if the episode is already valid just log it, if not throw it up
                if UNKNOWN == self.status:
                    self.status = SKIPPED
                if self.name:
                    logger.log('%s timed out but we have enough info from other sources, allowing the error' %
                               sickbeard.TVInfoAPI(self.tvid).name, logger.DEBUG)
                    return
                else:
                    logger.log('%s timed out, unable to create the episode' % sickbeard.TVInfoAPI(self.tvid).name,
                               logger.ERROR)
                    return False
            elif check_exception_type(e, ExceptionTuples.tvinfo_episodenotfound,
                                      ExceptionTuples.tvinfo_seasonnotfound):
                logger.log('Unable to find the episode on %s... has it been removed? Should I delete from db?' %
                           sickbeard.TVInfoAPI(self.tvid).name, logger.DEBUG)
                # if I'm no longer on the Indexers but I once was then delete myself from the DB
                if -1 != self.epid and helpers.should_delete_episode(self.status):
                    self.delete_episode()
                elif UNKNOWN == self.status:
                    self.status = SKIPPED
                return
            else:
                raise e

        if getattr(ep_info, 'absolute_number', None) in (None, ''):
            logger.log('This episode (%s - %sx%s) has no absolute number on %s' %
                       (self.show_obj.name, season, episode, sickbeard.TVInfoAPI(self.tvid).name), logger.DEBUG)
        else:
            logger.log('%s: The absolute_number for %sx%s is : %s' %
                       (self.show_obj.tvid_prodid, season, episode, ep_info['absolute_number']), logger.DEBUG)
            self.absolute_number = int(ep_info['absolute_number'])

        self.name = self.dict_prevent_nonetype(ep_info, 'episodename')
        self.season = season
        self.episode = episode

        sickbeard.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid)

        self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
            self.show_obj.tvid, self.show_obj.prodid,
            absolute_number=self.absolute_number,
            season=self.season, episode=self.episode)

        self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
            self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode)

        self.description = self.dict_prevent_nonetype(ep_info, 'overview')

        firstaired = getattr(ep_info, 'firstaired', None)
        if None is firstaired or firstaired in '0000-00-00':
            firstaired = str(datetime.date.fromordinal(1))
        rawAirdate = [int(x) for x in firstaired.split('-')]

        old_airdate_future = self.airdate == datetime.date.fromordinal(1) or self.airdate >= datetime.date.today()
        try:
            self.airdate = datetime.date(rawAirdate[0], rawAirdate[1], rawAirdate[2])
        except (ValueError, IndexError):
            logger.log('Malformed air date retrieved from %s (%s - %sx%s)' %
                       (sickbeard.TVInfoAPI(self.tvid).name, self.show_obj.name, season, episode), logger.ERROR)
            # if I'm incomplete on TVDB but I once was complete then just delete myself from the DB for now
            if -1 != self.epid and helpers.should_delete_episode(self.status):
                self.delete_episode()
            elif UNKNOWN == self.status:
                self.status = SKIPPED
            return False

        today = datetime.date.today()
        delta = datetime.timedelta(days=1)
        show_time = network_timezones.parse_date_time(self.airdate.toordinal(),
                                                      self.show_obj.airs,
                                                      self.show_obj.network)
        show_length = datetime.timedelta(minutes=helpers.try_int(self.show_obj.runtime, 60))
        tz_now = datetime.datetime.now(network_timezones.sb_timezone)
        future_airtime = (self.airdate > (today + delta) or
                          (not self.airdate < (today - delta) and ((show_time + show_length) > tz_now)))

        # early conversion to int so that episode doesn't get marked dirty
        self.epid = getattr(ep_info, 'id', None)
        if None is self.epid:
            logger.log('Failed to retrieve ID from %s' % sickbeard.TVInfoAPI(self.tvid).name, logger.ERROR)
            if helpers.should_delete_episode(self.status):
                self.delete_episode()
            elif UNKNOWN == self.status:
                self.status = (SKIPPED, UNAIRED)[future_airtime]
            return False

        # don't update show status if show dir is missing, unless it's missing on purpose
        # noinspection PyProtectedMember
        if not ek.ek(os.path.isdir, self.show_obj._location) \
                and not sickbeard.CREATE_MISSING_SHOW_DIRS and not sickbeard.ADD_SHOWS_WO_DIR:
            if UNKNOWN == self.status:
                self.status = (SKIPPED, UNAIRED)[future_airtime]
                logger.log('The show directory is missing but an episode status found at Unknown is set Skipped')
            else:
                logger.log('The show directory is missing,'
                           ' not bothering to change the episode statuses since it\'d probably be invalid')
            return

        if self.location:
            logger.log('%s: Setting status for %sx%s based on status %s and existence of %s' %
                       (self.show_obj.tvid_prodid, season, episode, statusStrings[self.status], self.location),
                       logger.DEBUG)

        # if we don't have the file
        if not ek.ek(os.path.isfile, self.location):

            if self.status in [SKIPPED, UNAIRED, UNKNOWN, WANTED]:
                very_old_delta = datetime.timedelta(days=90)
                very_old_airdate = datetime.date.fromordinal(1) < self.airdate < (today - very_old_delta)

                # if this episode hasn't aired yet set the status to UNAIRED
                if future_airtime:
                    msg = 'Episode airs in the future, marking it %s'
                    self.status = UNAIRED

                # if there's no airdate then set it to unaired (and respect ignored)
                elif self.airdate == datetime.date.fromordinal(1):
                    if IGNORED == self.status:
                        msg = 'Episode has no air date and marked %s, no change'
                    else:
                        msg = 'Episode has no air date, marking it %s'
                        self.status = UNAIRED

                # if the airdate is in the past
                elif UNAIRED == self.status:
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self.status], ','.join([(' is a special', '')[0 < self.season],
                                                              ('', ' is paused')[self.show_obj.paused]])) + '%s')
                    self.status = (SKIPPED, WANTED)[0 < self.season
                                                    and not self.show_obj.paused and not very_old_airdate]

                # if still UNKNOWN or SKIPPED with the deprecated future airdate method
                elif UNKNOWN == self.status or (SKIPPED == self.status and old_airdate_future):
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self.status], ','.join([
                            ('', ' has old future date format')[SKIPPED == self.status and old_airdate_future],
                            ('', ' is being updated')[bool(update)], (' is a special', '')[0 < self.season]])) + '%s')
                    self.status = (SKIPPED, WANTED)[update and not self.show_obj.paused and 0 < self.season
                                                    and not very_old_airdate]

                else:
                    msg = 'Not touching episode status %s, with air date in the past, because there is no file'

            else:
                msg = 'Not touching episode status %s, because there is no file'

            logger.log(msg % statusStrings[self.status], logger.DEBUG)

        # if we have a media file then it's downloaded
        elif sickbeard.helpers.has_media_ext(self.location):
            if IGNORED == self.status:
                logger.log('File exists for %sx%s, ignoring because of status %s' %
                           (self.season, self.episode, statusStrings[self.status]), logger.DEBUG)
            # leave propers alone, you have to either post-process them or manually change them back
            elif self.status not in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED:
                msg = '(1) Status changes from %s to ' % statusStrings[self.status]
                self.status = Quality.statusFromNameOrFile(self.location, anime=self.show_obj.is_anime)
                logger.log('%s%s' % (msg, statusStrings[self.status]), logger.DEBUG)

        # shouldn't get here probably
        else:
            msg = '(2) Status changes from %s to ' % statusStrings[self.status]
            self.status = UNKNOWN
            logger.log('%s%s' % (msg, statusStrings[self.status]), logger.DEBUG)

    def load_from_nfo(self, location):
        """

        :param location:
        :type location: AnyStr
        """
        # noinspection PyProtectedMember
        if not ek.ek(os.path.isdir, self.show_obj._location):
            logger.log('%s: The show directory is missing, not bothering to try loading the episode NFO'
                       % self.show_obj.tvid_prodid)
            return

        logger.log('%s: Loading episode details from the NFO file associated with %s'
                   % (self.show_obj.tvid_prodid, location), logger.DEBUG)

        self.location = location

        if "" != self.location:

            if UNKNOWN == self.status and sickbeard.helpers.has_media_ext(self.location):
                status_quality = Quality.statusFromNameOrFile(self.location, anime=self.show_obj.is_anime)
                logger.log('(3) Status changes from %s to %s' % (self.status, status_quality), logger.DEBUG)
                self.status = status_quality

            nfoFile = sickbeard.helpers.replace_extension(self.location, 'nfo')
            logger.log('%s: Using NFO name %s' % (self.show_obj.tvid_prodid, nfoFile), logger.DEBUG)

            if ek.ek(os.path.isfile, nfoFile):
                try:
                    showXML = etree.ElementTree(file=nfoFile)
                except (SyntaxError, ValueError) as e:
                    logger.log('Error loading the NFO, backing up the NFO and skipping for now: %s' % ex(e),
                               logger.ERROR)  # TODO: figure out what's wrong and fix it
                    try:
                        ek.ek(os.rename, nfoFile, '%s.old' % nfoFile)
                    except (BaseException, Exception) as e:
                        logger.log(
                            'Failed to rename your episode\'s NFO file - you need to delete it or fix it: %s' % ex(e),
                            logger.ERROR)
                    raise exceptions_helper.NoNFOException('Error in NFO format')

                # TODO: deprecated function getiterator needs to be replaced
                # for epDetails in showXML.getiterator('episodedetails'):
                for epDetails in list(showXML.iter('episodedetails')):
                    if None is epDetails.findtext('season') or int(epDetails.findtext('season')) != self.season or \
                                    None is epDetails.findtext('episode') or int(
                            epDetails.findtext('episode')) != self.episode:
                        logger.log('%s: NFO has an <episodedetails> block for a different episode - wanted %sx%s'
                                   ' but got %sx%s' %
                                   (self.show_obj.tvid_prodid, self.season, self.episode, epDetails.findtext('season'),
                                    epDetails.findtext('episode')), logger.DEBUG)
                        continue

                    if None is epDetails.findtext('title') or None is epDetails.findtext('aired'):
                        raise exceptions_helper.NoNFOException('Error in NFO format (missing episode title or airdate)')

                    self.name = epDetails.findtext('title')
                    self.episode = int(epDetails.findtext('episode'))
                    self.season = int(epDetails.findtext('season'))

                    sickbeard.scene_numbering.xem_refresh(self.show_obj.tvid, self.show_obj.prodid)

                    self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                        self.show_obj.tvid, self.show_obj.prodid,
                        absolute_number=self.absolute_number,
                        season=self.season, episode=self.episode)

                    self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                        self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode)

                    self.description = epDetails.findtext('plot')
                    if None is self.description:
                        self.description = ''

                    if epDetails.findtext('aired'):
                        rawAirdate = [int(x) for x in epDetails.findtext('aired').split("-")]
                        self.airdate = datetime.date(rawAirdate[0], rawAirdate[1], rawAirdate[2])
                    else:
                        self.airdate = datetime.date.fromordinal(1)

                    self.hasnfo = True
            else:
                self.hasnfo = False

            if ek.ek(os.path.isfile, sickbeard.helpers.replace_extension(nfoFile, 'tbn')):
                self.hastbn = True
            else:
                self.hastbn = False

    def __repr__(self):
        return 'TVEpisode(%s)' % self.__str__()

    def __str__(self):

        return '%s - %sx%s - %s\n' % (self.show_obj.name, self.season, self.episode, self.name) \
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

    def delete_episode(self):

        logger.log('Deleting %s %sx%s from the DB' % (self.show_obj.name, self.season, self.episode), logger.DEBUG)

        # remove myself from the show dictionary
        if self.show_obj.get_episode(self.season, self.episode, no_create=True) == self:
            logger.log('Removing myself from my show\'s list', logger.DEBUG)
            del self.show_obj.sxe_ep_obj[self.season][self.episode]

        # delete myself from the DB
        logger.log('Deleting myself from the database', logger.DEBUG)
        my_db = db.DBConnection()
        sql = 'DELETE FROM tv_episodes' \
              ' WHERE indexer=%s AND showid=%s' \
              ' AND season=%s AND episode=%s' % \
              (self.show_obj.tvid, self.show_obj.prodid,
               self.season, self.episode)
        my_db.action(sql)

        raise exceptions_helper.EpisodeDeletedException()

    def get_sql(self, force_save=False):
        # type: (bool) -> Optional[List[AnyStr, List]]
        """
        Creates SQL queue for this episode if any of its data has been changed since the last save.

        :param force_save: If True it will create SQL queue even if no data has been changed since the last save
        (aka if the record is not dirty).
        """

        if not self.dirty and not force_save:
            logger.log('%s: Not creating SQL queue - record is not dirty' % self.show_obj.tvid_prodid, logger.DEBUG)
            return

        self.dirty = False
        return [
            'INSERT OR REPLACE INTO tv_episodes'
            ' (episode_id,'
            ' indexerid, indexer, name, description,'
            ' subtitles, subtitles_searchcount, subtitles_lastsearch,'
            ' airdate, hasnfo, hastbn, status, location, file_size,'
            ' release_name, is_proper, showid, season, episode, absolute_number,'
            ' version, release_group,'
            ' scene_absolute_number, scene_season, scene_episode)'
            ' VALUES'
            ' ((SELECT episode_id FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?'
            ' AND season = ? AND episode = ?)'
            ',?,?'
            ',?,?'
            ',?,?,?'
            ',?,?,?,?,?,?'
            ',?,?'
            ',?,?,?,?'
            ',?,?,'
            '(SELECT scene_absolute_number FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),'
            '(SELECT scene_season FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),'
            '(SELECT scene_episode FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?));',
            [self.show_obj.tvid, self.show_obj.prodid,
             self.season, self.episode,
             self.epid, self.tvid,
             self.name, self.description,
             ','.join([sub for sub in self.subtitles]), self.subtitles_searchcount, self.subtitles_lastsearch,
             self.airdate.toordinal(), self.hasnfo, self.hastbn, self.status, self.location, self.file_size,
             self.release_name, self.is_proper,
             self.show_obj.prodid, self.season, self.episode, self.absolute_number,
             self.version, self.release_group,
             self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode,
             self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode,
             self.show_obj.tvid, self.show_obj.prodid, self.season, self.episode]]

    def save_to_db(self, force_save=False):
        """
        Saves this episode to the database if any of its data has been changed since the last save.

        :param force_save: If True it will save to the database even if no data has been changed since the
        last save (aka if the record is not dirty).
        """

        if not self.dirty and not force_save:
            logger.log('%s: Not saving episode to db - record is not dirty' % self.show_obj.tvid_prodid, logger.DEBUG)
            return

        logger.log('%s: Saving episode details to database' % self.show_obj.tvid_prodid, logger.DEBUG)

        logger.log('STATUS IS %s' % statusStrings[self.status], logger.DEBUG)

        newValueDict = dict(
            indexer=self.tvid,
            indexerid=self.epid,
            name=self.name,
            description=self.description,
            subtitles=','.join([sub for sub in self.subtitles]),
            subtitles_searchcount=self.subtitles_searchcount,
            subtitles_lastsearch=self.subtitles_lastsearch,
            airdate=self.airdate.toordinal(),
            hasnfo=self.hasnfo,
            hastbn=self.hastbn,
            status=self.status,
            location=self.location,
            file_size=self.file_size,
            release_name=self.release_name,
            is_proper=self.is_proper,
            absolute_number=self.absolute_number,
            version=self.version,
            release_group=self.release_group)

        control_value_dict = dict(
            indexer=self.show_obj.tvid, showid=self.show_obj.prodid, season=self.season, episode=self.episode)

        # use a custom update/insert method to get the data into the DB
        my_db = db.DBConnection()
        my_db.upsert('tv_episodes', newValueDict, control_value_dict)
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

        if self.show_obj.anime and not self.show_obj.scene:
            return self._format_pattern('%SN - %AB - %EN')
        elif self.show_obj.air_by_date:
            return self._format_pattern('%SN - %AD - %EN')

        return self._format_pattern('%SN - %Sx%0E - %EN')

    def _ep_name(self):
        """
        :return: the name of the episode to use during renaming. Combines the names of related episodes.
        Eg. "Ep Name (1)" and "Ep Name (2)" becomes "Ep Name"
            "Ep Name" and "Other Ep Name" becomes "Ep Name & Other Ep Name"
        :rtype: AnyStr
        """

        multiNameRegex = r'(.*) \(\d{1,2}\)'

        self.related_ep_obj = sorted(self.related_ep_obj, key=lambda se: se.episode)

        if 0 == len(self.related_ep_obj):
            goodName = self.name
        else:
            singleName = True
            curGoodName = None

            for curName in [self.name] + [x.name for x in self.related_ep_obj]:
                match = re.match(multiNameRegex, curName)
                if not match:
                    singleName = False
                    break

                if None is curGoodName:
                    curGoodName = match.group(1)
                elif curGoodName != match.group(1):
                    singleName = False
                    break

            if singleName:
                goodName = curGoodName
            else:
                goodName = self.name
                for ep_obj in self.related_ep_obj:
                    goodName += ' & ' + ep_obj.name

        return goodName or 'tba'

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

        epStatus, epQual = Quality.splitCompositeStatus(self.status)

        if sickbeard.NAMING_STRIP_YEAR:
            show_name = re.sub(r'\(\d+\)$', '', self.show_obj.name).rstrip()
        else:
            show_name = self.show_obj.name

        return {
            '%SN': show_name,
            '%S.N': dot(show_name),
            '%S_N': us(show_name),
            '%EN': ep_name,
            '%E.N': dot(ep_name),
            '%E_N': us(ep_name),
            '%QN': Quality.qualityStrings[epQual],
            '%Q.N': dot(Quality.qualityStrings[epQual]),
            '%Q_N': us(Quality.qualityStrings[epQual]),
            '%S': str(self.season),
            '%0S': '%02d' % self.season,
            '%E': str(self.episode),
            '%0E': '%02d' % self.episode,
            '%XS': str(self.scene_season),
            '%0XS': '%02d' % self.scene_season,
            '%XE': str(self.scene_episode),
            '%0XE': '%02d' % self.scene_episode,
            '%AB': '%(#)03d' % {'#': self.absolute_number},
            '%XAB': '%(#)03d' % {'#': self.scene_absolute_number},
            '%RN': release_name(self.release_name, self.show_obj.is_anime),
            '%RG': release_group(self.show_obj, self.release_name),
            '%AD': str(self.airdate).replace('-', ' '),
            '%A.D': str(self.airdate).replace('-', '.'),
            '%A_D': us(str(self.airdate)),
            '%A-D': str(self.airdate),
            '%Y': str(self.airdate.year),
            '%M': str(self.airdate.month),
            '%D': str(self.airdate.day),
            '%0M': '%02d' % self.airdate.month,
            '%0D': '%02d' % self.airdate.day,
            '%RT': "PROPER" if self.is_proper else "",
            '%V': 'v%s' % self.version if self.show_obj.is_anime and 1 < self.version else '',
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
            if self.show_obj.air_by_date or self.show_obj.sports:
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
                curAbsolute_number = (self.absolute_number, self.episode)[0 == self.absolute_number]

                if 0 != self.season:  # dont set absolute numbers if we are on specials !
                    if 1 == anime_type:  # this crazy person wants both ! (note: +=)
                        ep_string += sep + '%(#)03d' % {
                            '#': curAbsolute_number}
                    elif 2 == anime_type:  # total anime freak only need the absolute number ! (note: =)
                        ep_string = '%(#)03d' % {'#': curAbsolute_number}

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
        if not self.show_obj.is_anime:
            anime_type = 3

        result = self.formatted_filename(anime_type=anime_type)

        # if they want us to flatten it and we're allowed to flatten it then we will
        if self.show_obj.flatten_folders and not sickbeard.NAMING_FORCE_FOLDERS:
            return result

        # if not we append the folder on and use that
        else:
            result = ek.ek(os.path.join, self.formatted_dir(), result)

        return result

    def formatted_dir(self, pattern=None, multi=None):
        """
        Just the folder name of the episode
        """

        if None is pattern:
            # we only use ABD if it's enabled, this is an ABD show, AND this is not a multi-ep
            if self.show_obj.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.related_ep_obj:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self.show_obj.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.related_ep_obj:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self.show_obj.anime and sickbeard.NAMING_CUSTOM_ANIME:
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
            if self.show_obj.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.related_ep_obj:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self.show_obj.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.related_ep_obj:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self.show_obj.anime and sickbeard.NAMING_CUSTOM_ANIME:
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
        absolute_proper_path = ek.ek(os.path.join, self.show_obj.location, proper_path)
        absolute_current_path_no_ext, file_ext = ek.ek(os.path.splitext, self.location)
        absolute_current_path_no_ext_length = len(absolute_current_path_no_ext)

        related_subs = []

        current_path = absolute_current_path_no_ext

        if absolute_current_path_no_ext.startswith(self.show_obj.location):
            current_path = absolute_current_path_no_ext[len(self.show_obj.location):]

        logger.log('Renaming/moving episode from the base path %s to %s' % (self.location, absolute_proper_path),
                   logger.DEBUG)

        # if it's already named correctly then don't do anything
        if proper_path == current_path:
            logger.log('%s: File %s is already named correctly, skipping' % (self.epid, self.location),
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
            cur_result = helpers.rename_ep_file(cur_related_file, absolute_proper_path,
                                                absolute_current_path_no_ext_length)
            if not cur_result:
                logger.log('%s: Unable to rename file %s' % (self.epid, cur_related_file), logger.ERROR)

        for cur_related_sub in related_subs:
            absolute_proper_subs_path = ek.ek(os.path.join, sickbeard.SUBTITLES_DIR, self.formatted_filename())
            cur_result = helpers.rename_ep_file(cur_related_sub, absolute_proper_subs_path,
                                                absolute_current_path_no_ext_length)
            if not cur_result:
                logger.log('%s: Unable to rename file %s' % (self.epid, cur_related_sub), logger.ERROR)

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
        if not datetime.date == type(self.airdate) or 1 == self.airdate.year:
            logger.log('%s: Did not change modify date of %s because episode date is never aired or invalid'
                       % (self.show_obj.tvid_prodid, ek.ek(os.path.basename, self.location)), logger.DEBUG)
            return

        hr, m = network_timezones.parse_time(self.show_obj.airs)
        airtime = datetime.time(hr, m)

        aired_dt = datetime.datetime.combine(self.airdate, airtime)
        try:
            aired_epoch = helpers.datetime_to_epoch(aired_dt)
            filemtime = int(ek.ek(os.path.getmtime, self.location))
        except (BaseException, Exception):
            return

        if filemtime != aired_epoch:

            result, loglevel = 'Changed', logger.MESSAGE
            if not helpers.touch_file(self.location, aired_epoch):
                result, loglevel = 'Error changing', logger.WARNING

            logger.log('%s: %s modify date of %s to show air date %s'
                       % (self.show_obj.tvid_prodid, result, ek.ek(os.path.basename, self.location),
                          aired_dt.strftime('%b %d,%Y (%H:%M)')), loglevel)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.Lock()
        self.__dict__.update(d)
