# Author: Dennis Lutter <lad1337@gmail.com>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import os

import adba
from adba.aniDBresponses import LoginFirstResponse
# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import db, logger
from .classes import NZBDataSearchResult, NZBSearchResult, TorrentSearchResult
from .helpers import get_system_temp_dir, make_dirs

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, List, Optional, Tuple


class BlackWhitelistNoShowIDException(Exception):
    """
    No prodid or tvid was given
    """


class BlackAndWhiteList(object):
    blacklist = []  # type: List[AnyStr]
    whitelist = []  # type: List[AnyStr]

    def __init__(self, tvid, prodid, tvid_prodid=None):
        # type: (int, int, AnyStr) -> None

        if not tvid or not prodid:
            raise BlackWhitelistNoShowIDException()
        self.tvid = tvid  # type: int
        self.prodid = prodid  # type: int
        self.tvid_prodid = tvid_prodid  # type: AnyStr
        self.load()

    def load(self):
        logger.log(u'Building black and white list for %s' % self.tvid_prodid, logger.DEBUG)
        self.blacklist = self._load_list('blacklist')
        self.whitelist = self._load_list('whitelist')

    def _load_list(self, table):
        # type: (AnyStr) -> List[AnyStr]
        """

        :param table: table name
        :return: list of words
        """
        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select('SELECT keyword FROM [%s] WHERE indexer = ? AND show_id = ?' % table,
                                  [self.tvid, self.prodid])
        if not sql_result or not len(sql_result):
            return []

        groups = []
        for cur_result in sql_result:
            groups.append(cur_result['keyword'])

        logger.log('BWL: %s loaded keywords from %s: %s' % (self.tvid_prodid, table, groups),
                   logger.DEBUG)

        return groups

    def set_black_keywords(self, values):
        # type: (List[AnyStr]) -> None
        """

        :param values: list of words
        """
        self._del_all_keywords('blacklist')
        self._add_keywords('blacklist', values)
        self.blacklist = values
        logger.log('Blacklist set to: %s' % self.blacklist, logger.DEBUG)

    def set_white_keywords(self, values):
        # type: (List[AnyStr]) -> None
        """

        :param values: list of words
        """
        self._del_all_keywords('whitelist')
        self._add_keywords('whitelist', values)
        self.whitelist = values
        logger.log('Whitelist set to: %s' % self.whitelist, logger.DEBUG)

    def _del_all_keywords(self, table):
        # type: (AnyStr) -> None
        """

        :param table: table name
        """
        my_db = db.DBConnection()
        # noinspection SqlResolve
        my_db.action('DELETE FROM [%s] WHERE indexer = ? AND show_id = ?' % table, [self.tvid, self.prodid])

    def _add_keywords(self, table, values):
        # type: (AnyStr, List[AnyStr]) -> None
        """

        :param table: table name
        :param values: list of words
        """
        my_db = db.DBConnection()
        for cur_value in values:
            # noinspection SqlResolve
            my_db.action('INSERT INTO [%s] (indexer, show_id, keyword) VALUES (?,?,?)' % table,
                         [self.tvid, self.prodid, cur_value])

    def is_valid(self, result):
        # type: (NZBSearchResult or NZBDataSearchResult or TorrentSearchResult) -> bool
        """
        Test if release group parsed from result is in white list and not in black list

        :param result: Search result
        :return: True or False
        """
        if not result.release_group:
            logger.log('Failed to detect release group, invalid result', logger.DEBUG)
            return False

        if result.release_group.lower() in [x.lower() for x in self.whitelist] or not self.whitelist:
            white_result = True
        else:
            white_result = False

        if result.release_group.lower() in [x.lower() for x in self.blacklist]:
            black_result = False
        else:
            black_result = True

        logger.log('Whitelist check passed: %s. Blacklist check passed: %s' % (white_result, black_result),
                   logger.DEBUG)

        return white_result and black_result


def short_group_names(groups):
    # type: (AnyStr) -> List[AnyStr]
    """

    :param groups: groups
    :return: list of groups
    """
    group_list = groups.split(',')
    short_group_list = []
    if set_up_anidb_connection():
        for group_name in group_list:
            adba_result = None
            try:
                # no such group is returned for utf8 groups like interrobang
                adba_result = sickbeard.ADBA_CONNECTION.group(gname=group_name)
            except(BaseException, Exception):
                pass
            if isinstance(adba_result, LoginFirstResponse):
                break
            if None is adba_result or not adba_result.hasattr('datalines'):
                continue
            for line in adba_result.datalines:
                if line['shortname']:
                    short_group_list.append(line['shortname'])
                else:
                    if group_name not in short_group_list:
                        short_group_list.append(group_name)
    else:
        short_group_list = group_list
    return short_group_list


def anidb_cache_dir():
    # type: (...) -> Optional[AnyStr]
    cache_dir = ek.ek(os.path.join, sickbeard.CACHE_DIR or get_system_temp_dir(), 'anidb')
    if not make_dirs(cache_dir):
        cache_dir = None
    return cache_dir


def create_anidb_obj(**kwargs):

    return adba.Anime(sickbeard.ADBA_CONNECTION, cache_path=anidb_cache_dir(), **kwargs)


def set_up_anidb_connection():
    if not sickbeard.USE_ANIDB:
        logger.log(u'Usage of anidb disabled. Skipping', logger.DEBUG)
        return False

    if not sickbeard.ANIDB_USERNAME and not sickbeard.ANIDB_PASSWORD:
        logger.log(u'anidb username and/or password are not set. Aborting anidb lookup.', logger.DEBUG)
        return False

    if not sickbeard.ADBA_CONNECTION:
        # anidb_logger = (lambda x: logger.log('ANIDB: ' + str(x)), logger.DEBUG)
        sickbeard.ADBA_CONNECTION = adba.Connection(keepAlive=True)  # , log=anidb_logger)

    auth = False
    try:
        auth = sickbeard.ADBA_CONNECTION.authed()
    except (BaseException, Exception) as e:
        logger.log(u'exception msg: ' + ex(e))
        pass

    if not auth:
        try:
            sickbeard.ADBA_CONNECTION.auth(sickbeard.ANIDB_USERNAME, sickbeard.ANIDB_PASSWORD)
        except (BaseException, Exception) as e:
            logger.log(u'exception msg: ' + ex(e))
            return False
    else:
        return True

    return sickbeard.ADBA_CONNECTION.authed()


def pull_anidb_groups(show_name):
    # type: (AnyStr) -> Optional[bool, List]
    if set_up_anidb_connection():
        try:
            anime = create_anidb_obj(name=show_name)
            return anime.get_groups()
        except (BaseException, Exception) as e:
            logger.log(u'Anidb exception: %s' % ex(e), logger.DEBUG)
            return False


def push_anidb_mylist(filepath, anidb_episode):
    # type: (AnyStr, Any) -> Tuple[Optional[bool], Optional[Tuple[AnyStr, int]]]
    """
    :param filepath: file path
    :type filepath: AnyStr
    :param anidb_episode:
    :type anidb_episode:
    :return
    """
    result, log = None, None
    if set_up_anidb_connection():
        if not anidb_episode:  # seems like we could parse the name before, build the anidb object
            # build an anidb episode
            anidb_episode = adba.Episode(
                sickbeard.ADBA_CONNECTION,
                filePath=filepath,
                paramsF=['quality', 'anidb_file_name', 'crc32'],
                paramsA=['epno', 'english_name', 'short_name_list', 'other_name', 'synonym_list'])

        try:
            anidb_episode.add_to_mylist(state=1)  # status = 1 sets the status of the file to "internal HDD"
            log = ('Adding the file to the anidb mylist', logger.DEBUG)
            result = True
        except (BaseException, Exception) as e:
            log = (u'exception msg: %s' % ex(e), logger.MESSAGE)
            result = False

    return result, log
