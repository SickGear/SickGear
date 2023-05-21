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

from collections import defaultdict

import io
import os
import re
import sys
import traceback

import sickgear
from exceptions_helper import ex
from json_helper import json_load
from . import db, helpers, logger, name_cache
from .anime import create_anidb_obj
from .classes import OrderedDefaultdict
from .indexers.indexer_config import TVINFO_TVDB
from .scheduler import Job
from .sgdatetime import SGDatetime

import lib.rarfile.rarfile as rarfile

from _23 import list_range
from six import iteritems

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import AnyStr, List, Tuple, Optional, Union
    from .tv import TVShow

MEMCACHE = {}


class ReleaseMap(Job):
    def __init__(self):
        super(ReleaseMap, self).__init__(self.job_run, thread_lock=True, kwargs={})

        MEMCACHE.setdefault('release_map', {})
        MEMCACHE.setdefault('release_map_season', {})
        MEMCACHE.setdefault('release_map_xem', defaultdict(list))

    def job_run(self):

        # update xem id lists
        self.fetch_xem_ids()

        # update release exceptions
        self.fetch_exceptions()

    def fetch_xem_ids(self):

        for cur_tvid, cur_name in iteritems(sickgear.TVInfoAPI().xem_supported_sources):
            xem_ids = self._get_xem_ids(cur_name, sickgear.TVInfoAPI(cur_tvid).config['xem_origin'])
            if len(xem_ids):
                MEMCACHE['release_map_xem'][cur_tvid] = xem_ids

    @staticmethod
    def _get_xem_ids(infosrc_name, xem_origin):
        # type: (AnyStr, AnyStr) -> List
        """

        :param infosrc_name:
        :param xem_origin:
        """
        result = []

        url = 'https://thexem.info/map/havemap?origin=%s' % xem_origin

        task = 'Fetching show ids with%s xem scene mapping%s for origin'
        logger.log(f'{task % ("", "s")} {infosrc_name}')
        parsed_json = helpers.get_url(url, parse_json=True, timeout=90)
        if not isinstance(parsed_json, dict) or not parsed_json:
            logger.error(f'Failed {task.lower() % ("", "s")} {infosrc_name},'
                         f' Unable to get URL: {url}')
        else:
            if 'success' == parsed_json.get('result', '') and 'data' in parsed_json:
                result = list(set(filter(lambda prodid: 0 < prodid,
                                         map(lambda pid: helpers.try_int(pid), parsed_json['data']))))
                if 0 == len(result):
                    logger.warning(f'Failed {task.lower() % ("", "s")} {infosrc_name},'
                                   f' no data items parsed from URL: {url}')

        logger.log(f'Finished {task.lower() % (f" {len(result)}", helpers.maybe_plural(result))} {infosrc_name}')
        return result

    def _xem_exceptions_fetcher(self):

        result = {}

        xem_list = 'xem_us'
        for cur_show_obj in sickgear.showList:
            if cur_show_obj.is_anime and not cur_show_obj.paused:
                xem_list = 'xem'
                break

        if self._should_refresh(xem_list):
            for cur_tvid in [_i for _i in sickgear.TVInfoAPI().sources
                             if 'xem_origin' in sickgear.TVInfoAPI(_i).config]:
                logger.log(f'Checking for XEM scene exception updates for {sickgear.TVInfoAPI(cur_tvid).name}')

                url = 'https://thexem.info/map/allNames?origin=%s%s&seasonNumbers=1'\
                      % (sickgear.TVInfoAPI(cur_tvid).config['xem_origin'], ('&language=us', '')['xem' == xem_list])

                parsed_json = helpers.get_url(url, parse_json=True, timeout=90)
                if not parsed_json:
                    logger.error(f'Check scene exceptions update failed for {sickgear.TVInfoAPI(cur_tvid).name},'
                                 f' Unable to get URL: {url}')
                    continue

                if 'failure' == parsed_json['result']:
                    continue

                for cur_prodid, cur_names in iteritems(parsed_json['data']):
                    try:
                        result[(cur_tvid, int(cur_prodid))] = cur_names
                    except (BaseException, Exception):
                        continue

            self._set_last_refresh(xem_list)

        return result

    def _anidb_exceptions_fetcher(self):

        result = {}

        if self._should_refresh('anidb'):
            logger.log('Checking for AniDB scene exception updates')
            for cur_show_obj in filter(lambda _s: _s.is_anime and TVINFO_TVDB == _s.tvid, sickgear.showList):
                try:
                    anime = create_anidb_obj(name=cur_show_obj.name, tvdbid=cur_show_obj.prodid, autoCorrectName=True)
                except (BaseException, Exception):
                    continue
                if anime.name and anime.name != cur_show_obj.name:
                    result[(cur_show_obj.tvid, cur_show_obj.prodid)] = [{anime.name: -1}]

            self._set_last_refresh('anidb')

        return result

    def fetch_exceptions(self):
        """
        Looks up release exceptions on GitHub, Xem, and Anidb, parses them into a dict, and inserts them into the
        scene_exceptions table in cache.db. Finally, clears the scene name cache.
        """
        def _merge_exceptions(source, dest):
            for cur_ex in source:
                dest[cur_ex] = source[cur_ex] + ([] if cur_ex not in dest else dest[cur_ex])

        exceptions = self._xem_exceptions_fetcher()  # XEM scene exceptions
        _merge_exceptions(self._anidb_exceptions_fetcher(), exceptions)  # AniDB scene exceptions
        _merge_exceptions(self._github_exceptions_fetcher(), exceptions)  # GitHub stored release exceptions

        exceptions_custom, count_updated_numbers, min_remain_iv = self._custom_exceptions_fetcher()
        _merge_exceptions(exceptions_custom, exceptions)  # Custom exceptions

        is_changed_exceptions = False

        # write all the exceptions we got off the net into the database
        my_db = db.DBConnection()
        cl = []
        for cur_tvid_prodid in exceptions:

            # get a list of the existing exceptions for this ID
            existing_exceptions = [{_x['show_name']: _x['season']} for _x in
                                   my_db.select('SELECT show_name, season'
                                                ' FROM [scene_exceptions]'
                                                ' WHERE indexer = ? AND indexer_id = ?',
                                                list(cur_tvid_prodid))]

            # if this exception isn't already in the DB then add it
            for cur_ex_dict in filter(lambda e: e not in existing_exceptions, exceptions[cur_tvid_prodid]):
                try:
                    exception, season = next(iteritems(cur_ex_dict))
                except (BaseException, Exception):
                    logger.error('release exception error')
                    logger.error(traceback.format_exc())
                    continue

                cl.append(['INSERT INTO [scene_exceptions]'
                           ' (indexer, indexer_id, show_name, season) VALUES (?,?,?,?)',
                           list(cur_tvid_prodid) + [exception, season]])
                is_changed_exceptions = True

        if cl:
            my_db.mass_action(cl)
            name_cache.build_name_cache(update_only_scene=True)

        # since this could invalidate the results of the cache we clear it out after updating
        if is_changed_exceptions:
            logger.log('Updated release exceptions')
        else:
            logger.log('No release exceptions update needed')

        # cleanup
        exceptions.clear()

        return is_changed_exceptions, count_updated_numbers, min_remain_iv

    def _github_exceptions_fetcher(self):
        """
        Looks up the exceptions on GitHub
        """

        # global exception_dict
        result = {}

        # exceptions are stored on GitHub pages
        for cur_tvid in sickgear.TVInfoAPI().sources:
            if self._should_refresh(sickgear.TVInfoAPI(cur_tvid).name):
                url = sickgear.TVInfoAPI(cur_tvid).config.get('scene_url')
                if not url:
                    continue

                logger.log(f'Checking for release exception updates for {sickgear.TVInfoAPI(cur_tvid).name}')

                url_data = helpers.get_url(url)
                if None is url_data:
                    # When None is urlData, trouble connecting to GitHub
                    logger.error(f'Check release exceptions update failed. Unable to get URL: {url}')
                    continue

                else:
                    self._set_last_refresh(sickgear.TVInfoAPI(cur_tvid).name)

                    # each exception is on one line with the format indexer_id: 'show name 1', 'show name 2', etc
                    for cur_line in url_data.splitlines():
                        prodid, sep, aliases = cur_line.partition(':')

                        if not aliases:
                            continue

                        prodid = int(prodid)

                        # regex out the list of shows, taking \' into account
                        alias_list = [{re.sub(r'\\(.)', r'\1', _x): -1} for _x in
                                      re.findall(r"'(.*?)(?<!\\)',?", aliases)]
                        result[(cur_tvid, prodid)] = alias_list
                        del alias_list
                    del url_data

        return result

    def _custom_exceptions_fetcher(self):

        src_id = 'GHSG'
        logger.log(f'Checking to update custom alternatives from {src_id}')

        dirpath = os.path.join(sickgear.CACHE_DIR, 'alts')
        tmppath = os.path.join(dirpath, 'tmp')
        file_rar = os.path.join(tmppath, 'alt.rar')
        file_cache = os.path.join(dirpath, 'alt.json')
        iv = 30 * 60  # min interval to fetch updates
        refresh = self._should_refresh(src_id, iv)
        fetch_data = not os.path.isfile(file_cache) or (not int(os.environ.get('NO_ALT_GET', 0)) and refresh)
        if fetch_data:
            if os.path.exists(tmppath):
                helpers.remove_file(tmppath, tree=True)
            helpers.make_path(tmppath)
            helpers.download_file(r'https://github.com/SickGear/sickgear.altdata/raw/main/alt.rar', file_rar)

            rar_handle = None
            if 'win32' == sys.platform:
                rarfile.UNRAR_TOOL = os.path.join(sickgear.PROG_DIR, 'lib', 'rarfile', 'UnRAR.exe')
            try:
                rar_handle = rarfile.RarFile(file_rar)
                rar_handle.extractall(path=dirpath, pwd='sickgear_alt')
            except(BaseException, Exception) as e:
                logger.error(f'Failed to unpack archive: {file_rar} with error: {ex(e)}')

            if rar_handle:
                rar_handle.close()
                del rar_handle

            helpers.remove_file(tmppath, tree=True)

        if refresh:
            self._set_last_refresh(src_id)

        result = {}
        count_updated_numbers = 0
        if fetch_data or os.path.isfile(file_cache):
            try:
                with io.open(file_cache) as fh:
                    data = json_load(fh)
                result, count_updated_numbers = self._parse_custom_exceptions(data)
            except(BaseException, Exception) as e:
                logger.error(f'Failed to unpack json data: {file_rar} with error: {ex(e)}')

        else:
            logger.debug(f'Unable to fetch custom exceptions, skipped: {file_rar}')

        return result, count_updated_numbers, self._should_refresh(src_id, iv, remaining=True)

    @staticmethod
    def _parse_custom_exceptions(data):
        # type: (AnyStr) -> tuple
        """

        :param data: json text
        """
        # handle data
        from .scene_numbering import find_scene_numbering, set_scene_numbering_helper
        from .tv import TVidProdid

        result = {}
        count_updated_numbers = 0
        for cur_tvid_prodid, cur_season_data in iteritems(data):
            show_obj = sickgear.helpers.find_show_by_id(cur_tvid_prodid, no_mapped_ids=True)
            if not show_obj:
                continue

            used = set()
            for cur_for_season, cur_data in iteritems(cur_season_data):
                cur_for_season = helpers.try_int(cur_for_season, None)
                tvid, prodid = TVidProdid(cur_tvid_prodid).tuple
                if cur_data.get('n'):  # alt names
                    result.setdefault((tvid, prodid), [])
                    result[(tvid, prodid)] += [{_name: cur_for_season} for _name in cur_data.get('n')]

                for cur_update in cur_data.get('se') or []:
                    for cur_for_episode, cur_se_range in iteritems(cur_update):  # scene episode alt numbers
                        cur_for_episode = helpers.try_int(cur_for_episode, None)

                        target_season, episode_range = cur_se_range.split('x')
                        scene_episodes = [int(_x) for _x in episode_range.split('-')
                                          if None is not helpers.try_int(_x, None)]

                        if 2 == len(scene_episodes):
                            desc = scene_episodes[0] > scene_episodes[1]
                            if desc:  # handle a descending range case
                                scene_episodes.reverse()
                            scene_episodes = list_range(*[scene_episodes[0], scene_episodes[1] + 1])
                            if desc:
                                scene_episodes.reverse()

                        target_season = helpers.try_int(target_season, None)
                        for cur_target_episode in scene_episodes:
                            sn = find_scene_numbering(tvid, prodid, cur_for_season, cur_for_episode)
                            used.add((cur_for_season, cur_for_episode, target_season, cur_target_episode))
                            if sn and ((cur_for_season, cur_for_episode) + sn) not in used \
                                    and (cur_for_season, cur_for_episode) not in used:
                                logger.debug(f'Skipped setting "{show_obj.unique_name}"'
                                             f' episode {cur_for_season}x{cur_for_episode}'
                                             f' to target a release {target_season}x{cur_target_episode}'
                                             f' because set to {sn[0]}x{sn[1]}')
                            else:
                                used.add((cur_for_season, cur_for_episode))
                                if not sn or sn != (target_season, cur_target_episode):  # not already set
                                    count_updated_numbers += int(bool(set_scene_numbering_helper(
                                        tvid, prodid, for_season=cur_for_season, for_episode=cur_for_episode,
                                        scene_season=target_season, scene_episode=cur_target_episode).get('success')))

                            cur_for_episode += 1

        return result, count_updated_numbers

    @staticmethod
    def _should_refresh(name, max_refresh_age_secs=86400, remaining=False):
        # type: (AnyStr, int, bool) -> Union[bool, int]
        """

        :param name: name
        :param max_refresh_age_secs:
        :param remaining: True to return remaining seconds
        :return:
        """
        my_db = db.DBConnection()
        rows = my_db.select('SELECT last_refreshed FROM [scene_exceptions_refresh] WHERE list = ?', [name])
        if rows:
            last_refresh = int(rows[0]['last_refreshed'])
            if remaining:
                time_left = (last_refresh + max_refresh_age_secs - SGDatetime.timestamp_near())
                return (0, time_left)[time_left > 0]
            return SGDatetime.timestamp_near() > last_refresh + max_refresh_age_secs
        return True

    @staticmethod
    def _set_last_refresh(name):
        # type: (AnyStr) -> None
        """

        :param name: name
        :type name: AnyStr
        """
        my_db = db.DBConnection()
        my_db.upsert('scene_exceptions_refresh',
                     {'last_refreshed': SGDatetime.timestamp_near()},
                     {'list': name})

    @staticmethod
    def update_exceptions(show_obj, release_exceptions):
        # type: (TVShow, list) -> None
        """
        Given a show object and a list of alternative names,
        update MEMCACHE['release_map'], the db, and rebuild name_cache.
        """
        logger.log(f'Updating release exceptions for {show_obj.unique_name or show_obj.name}')

        my_db = db.DBConnection()
        my_db.action('DELETE FROM [scene_exceptions]'
                     ' WHERE indexer = ? AND indexer_id = ?',
                     [show_obj.tvid, show_obj.prodid])

        # A change has been made to the scene exception list. Clear the cache, to make this visible
        MEMCACHE['release_map'][(show_obj.tvid, show_obj.prodid)] = defaultdict(list)

        for cur_ex in release_exceptions:

            season, alt_name = cur_ex.split('|', 1)
            try:
                season = int(season)
            except (BaseException, Exception):
                logger.error(f'invalid season for release exception: {show_obj.tvid_prodid} - {season}:{alt_name}')
                continue

            MEMCACHE['release_map'][(show_obj.tvid, show_obj.prodid)][season].append(alt_name)

            my_db.action('INSERT INTO [scene_exceptions]'
                         ' (indexer, indexer_id, show_name, season) VALUES (?,?,?,?)',
                         [show_obj.tvid, show_obj.prodid, alt_name, season])

        sickgear.name_cache.build_name_cache(update_only_scene=True)

    def has_season_exceptions(self, tvid, prodid, season):
        # type: (int, int, int) -> bool

        self.get_alt_names(tvid, prodid, season)
        return (-1 < season) and season in MEMCACHE['release_map'].get((tvid, prodid), {})

    def get_alt_names(self, tvid, prodid, season=-1):
        # type: (int, int, Optional[int]) -> List
        """
        Return a list and update MEMCACHE['release_map'] of alternative show names from db
        for all seasons, or a specific show season.

        :param tvid: show tvid
        :param prodid: show prodid
        :param season: optional season number
        """
        alt_names = MEMCACHE['release_map'].get((tvid, prodid), {}).get(season, [])

        if not alt_names:
            my_db = db.DBConnection()
            exceptions = my_db.select('SELECT show_name'
                                      ' FROM [scene_exceptions]'
                                      ' WHERE indexer = ? AND indexer_id = ?'
                                      ' AND season = ?',
                                      [tvid, prodid, season])
            if exceptions:
                alt_names = list(set([_ex['show_name'] for _ex in exceptions]))

                if (tvid, prodid) not in MEMCACHE['release_map']:
                    MEMCACHE['release_map'][(tvid, prodid)] = {}
                MEMCACHE['release_map'][(tvid, prodid)][season] = alt_names

        if 1 == season:  # if we were looking for season 1 we can add generic names
            alt_names += self.get_alt_names(tvid, prodid)

        return alt_names

    @staticmethod
    def get_show_exceptions(tvid_prodid):
        # type: (AnyStr) -> OrderedDefaultdict
        """
        return a scene exceptions dict for a show

        :param tvid_prodid: a show tvid:prodid
        """
        exceptions_dict = OrderedDefaultdict(list)

        from .tv import TVidProdid

        my_db = db.DBConnection()
        exceptions = my_db.select('SELECT show_name, season'
                                  ' FROM [scene_exceptions]'
                                  ' WHERE indexer = ? AND indexer_id = ?'
                                  ' ORDER BY season DESC, show_name DESC',
                                  TVidProdid(tvid_prodid).list)

        exceptions_seasons = []
        if exceptions:
            for cur_ex in exceptions:
                # order as, s*, and then season desc, show_name also desc (so years in names fall the newest on top)
                if -1 == cur_ex['season']:
                    exceptions_dict[-1].append(cur_ex['show_name'])
                else:
                    exceptions_seasons += [cur_ex]

            for cur_ex in exceptions_seasons:
                exceptions_dict[cur_ex['season']].append(cur_ex['show_name'])

        return exceptions_dict

    @staticmethod
    def get_exception_seasons(tvid, prodid):
        # type: (int, int) -> List[int]
        """
        return a list of season numbers that have alternative names
        :param tvid: show tvid
        :param prodid: show prodid
        """
        exception_seasons = MEMCACHE['release_map_season'].get((tvid, prodid), [])

        if not exception_seasons:
            my_db = db.DBConnection()
            sql_result = my_db.select('SELECT DISTINCT(season) AS season'
                                      ' FROM [scene_exceptions]'
                                      ' WHERE indexer = ? AND indexer_id = ?',
                                      [tvid, prodid])
            if sql_result:
                exception_seasons = list(set([int(_x['season']) for _x in sql_result]))

                if (tvid, prodid) not in MEMCACHE['release_map_season']:
                    MEMCACHE['release_map_season'][(tvid, prodid)] = {}

                MEMCACHE['release_map_season'][(tvid, prodid)] = exception_seasons

        return exception_seasons


def get_scene_exception_by_name(show_name):
    # type: (AnyStr) -> List[None, None, None] or List[int, int, int]
    """

    :param show_name: show name
    """
    return _get_scene_exception_by_name_multiple(show_name)[0]


def _get_scene_exception_by_name_multiple(show_name):
    # type: (AnyStr) -> List[List[None, None, None] or List[int, int, int]]
    """

    :param show_name: show name
    :return:  (tvid, prodid, season) of the exception, None if no exception is present.
    """
    try:
        exception_result = name_cache.sceneNameCache[helpers.full_sanitize_scene_name(show_name)]
    except (BaseException, Exception):
        return [[None, None, None]]

    return [exception_result]


def has_abs_episodes(ep_obj=None, name=None):
    # type: (Optional[sickgear.tv.TVEpisode], Optional[AnyStr]) -> bool
    """

    :param ep_obj: episode object
    :param name: name
    """
    return any((name or ep_obj.show_obj.name or '').lower().startswith(_x.lower()) for _x in [
        'The Eighties', 'The Making of the Mob', 'The Night Of', 'Roots 2016', 'Trepalium'
    ])
