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

import datetime
import os
import os.path
import re
import time
import threading

try:
    import regex
    # noinspection PyUnresolvedReferences
    from math import trunc  # positioned here to import only if regex is available
except ImportError:
    regex = None

from . import regexes
# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex
import sickbeard
from .. import common, db, helpers, logger, scene_exceptions, scene_numbering
from lib.tvinfo_base.exceptions import *
from ..classes import OrderedDefaultdict

from .._legacy_classes import LegacyParseResult
from _23 import decode_str, list_keys, list_range
from six import iteritems, iterkeys, itervalues, PY2, string_types, text_type

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, List, Optional
    from ..tv import TVShow


class NameParser(object):
    ALL_REGEX = 0
    NORMAL_REGEX = 1
    ANIME_REGEX = 2

    def __init__(self, file_name=True, show_obj=None, try_scene_exceptions=True, convert=False,
                 naming_pattern=False, testing=False, indexer_lookup=True):

        self.file_name = file_name  # type: bool
        self.show_obj = show_obj  # type: sickbeard.tv.TVShow or None
        self.try_scene_exceptions = try_scene_exceptions  # type: bool
        self.convert = convert  # type: bool
        self.naming_pattern = naming_pattern  # type: bool
        self.testing = testing  # type: bool
        self.indexer_lookup = indexer_lookup  # type: bool

        if self.show_obj and not self.show_obj.is_anime:
            self.compiled_regexes = compiled_regexes[self.NORMAL_REGEX]
        elif self.show_obj and self.show_obj.is_anime:
            self.compiled_regexes = compiled_regexes[self.ANIME_REGEX]
        else:
            self.compiled_regexes = compiled_regexes[self.ALL_REGEX]

    @classmethod
    def compile_regexes(cls, regex_mode):
        # type: (int) -> Dict[int, List]
        """

        :param regex_mode:  mode from NameParser
        :type regex_mode: int
        :return:
        :rtype: Dict[List]
        """
        if cls.ANIME_REGEX == regex_mode:
            uncompiled_regex = [regexes.anime_regexes]
        elif cls.NORMAL_REGEX == regex_mode:
            uncompiled_regex = [regexes.normal_regexes]
        else:
            uncompiled_regex = [regexes.normal_regexes, regexes.anime_regexes]

        cls.compiled_regexes = {0: [], 1: []}
        index = 0
        strip_comment = re.compile(r'\(\?#[^)]+\)')
        for regexItem in uncompiled_regex:
            for cur_pattern_num, (cur_pattern_name, cur_pattern) in enumerate(regexItem):
                try:
                    cur_pattern = strip_comment.sub('', cur_pattern)
                    cur_regex = re.compile('(?x)' + cur_pattern, re.VERBOSE | re.IGNORECASE)
                except re.error as errormsg:
                    logger.log(u'WARNING: Invalid episode_pattern, %s. %s' % (errormsg, cur_pattern))
                else:
                    cls.compiled_regexes[index].append([cur_pattern_num, cur_pattern_name, cur_regex])
            index += 1

        return cls.compiled_regexes

    @staticmethod
    def clean_series_name(series_name):
        # type: (AnyStr) -> AnyStr
        """Cleans up series name by removing any . and _
        characters, along with any trailing hyphens.

        Is basically equivalent to replacing all _ and . with a
        space, but handles decimal numbers in string, for example:

        >>> # noinspection PyUnresolvedReferences
        clean_series_name('an.example.1.0.test')
        'an example 1.0 test'
        >>> # noinspection PyUnresolvedReferences
        clean_series_name('an_example_1.0_test')
        'an example 1.0 test'

        Stolen from dbr's tvnamer
        :param series_name: show name
        :type series_name: AnyStr
        :return: cleaned up show name
        :rtype: AnyStr
        """

        series_name = re.sub(r'(\D)\.(?!\s)(\D)', '\\1 \\2', series_name)
        series_name = re.sub(r'(\d)\.(\d{4})', '\\1 \\2', series_name)  # if it ends in a year then don't keep the dot
        series_name = re.sub(r'(\D)\.(?!\s)', '\\1 ', series_name)
        series_name = re.sub(r'\.(?!\s)(\D)', ' \\1', series_name)
        series_name = series_name.replace('_', ' ')
        series_name = re.sub('-$', '', series_name)
        series_name = re.sub(r'^\[.*\]', '', series_name)
        return series_name.strip()

    def _parse_string(self, name):
        # type: (AnyStr) -> Optional[ParseResult]
        """

        :param name: name to parse
        :type name: AnyStr
        :return:
        :rtype: ParseResult or None
        """
        if not name:
            return

        matches = []
        initial_best_result = None
        for reg_ex in self.compiled_regexes:
            for (cur_regex_num, cur_regex_name, cur_regex) in self.compiled_regexes[reg_ex]:
                new_name = helpers.remove_non_release_groups(name, 'anime' in cur_regex_name)
                match = cur_regex.match(new_name)

                if not match:
                    continue

                if 'garbage_name' == cur_regex_name:
                    return

                result = ParseResult(new_name)
                result.which_regex = [cur_regex_name]
                result.score = 0 - cur_regex_num

                named_groups = list_keys(match.groupdict())

                if 'series_name' in named_groups:
                    result.series_name = match.group('series_name')
                    if result.series_name:
                        result.series_name = self.clean_series_name(result.series_name)
                        name_parts = re.match(r'(?i)(.*)[ -]((?:part|pt)[ -]?\w+)$', result.series_name)
                        try:
                            result.series_name = name_parts.group(1)
                            result.extra_info = name_parts.group(2)
                        except (AttributeError, IndexError):
                            pass

                        result.score += 1

                if 'anime' in cur_regex_name and not (self.show_obj and self.show_obj.is_anime):
                    p_show_obj = helpers.get_show(result.series_name, True)
                    if p_show_obj and self.show_obj and not (p_show_obj.tvid == self.show_obj.tvid and
                                                             p_show_obj.prodid == self.show_obj.prodid):
                        p_show_obj = None
                    if not p_show_obj and self.show_obj:
                        p_show_obj = self.show_obj
                    if p_show_obj and not p_show_obj.is_anime:
                        continue

                if 'series_num' in named_groups and match.group('series_num'):
                    result.score += 1

                if 'season_num' in named_groups:
                    tmp_season = int(match.group('season_num'))
                    if 'bare' == cur_regex_name and tmp_season in (19, 20):
                        continue
                    result.season_number = tmp_season
                    result.score += 1

                def _process_epnum(captures, capture_names, grp_name, extra_grp_name, ep_numbers, parse_result):
                    ep_num = self._convert_number(captures.group(grp_name))
                    extra_grp_name = 'extra_%s' % extra_grp_name
                    ep_numbers = '%sepisode_numbers' % ep_numbers
                    if extra_grp_name in capture_names and captures.group(extra_grp_name):
                        try:
                            if hasattr(self.show_obj, 'get_episode'):
                                _ep_obj = self.show_obj.get_episode(parse_result.season_number, ep_num)
                            else:
                                tmp_show_obj = helpers.get_show(parse_result.series_name, True)
                                if tmp_show_obj and hasattr(tmp_show_obj, 'get_episode'):
                                    _ep_obj = tmp_show_obj.get_episode(parse_result.season_number, ep_num)
                                else:
                                    _ep_obj = None
                        except (BaseException, Exception):
                            _ep_obj = None
                        en = _ep_obj and _ep_obj.name and re.match(r'^\W*(\d+)', _ep_obj.name) or None
                        es = en and en.group(1) or None

                        extra_ep_num = self._convert_number(captures.group(extra_grp_name))
                        parse_result.__dict__[ep_numbers] = list_range(ep_num, extra_ep_num + 1) if (
                            not _ep_obj or not es or (_ep_obj and es and es != captures.group(extra_grp_name))) and (
                            0 < extra_ep_num - ep_num < 10) else [ep_num]
                        parse_result.score += 1
                    else:
                        parse_result.__dict__[ep_numbers] = [ep_num]
                    parse_result.score += 1
                    return parse_result

                if 'ep_num' in named_groups:
                    result = _process_epnum(match, named_groups, 'ep_num', 'ep_num', '', result)

                if 'ep_ab_num' in named_groups:
                    result = _process_epnum(match, named_groups, 'ep_ab_num', 'ab_ep_num', 'ab_', result)

                if 'air_year' in named_groups and 'air_month' in named_groups and 'air_day' in named_groups:
                    year = int(match.group('air_year'))
                    try:
                        month = int(match.group('air_month'))
                    except ValueError:
                        try:
                            month = time.strptime(match.group('air_month')[0:3], '%b').tm_mon
                        except ValueError as e:
                            raise InvalidNameException(ex(e))
                    day = int(match.group('air_day'))
                    # make an attempt to detect YYYY-DD-MM formats
                    if 12 < month:
                        tmp_month = month
                        month = day
                        day = tmp_month
                    try:
                        result.air_date = datetime.date(
                            year + ((1900, 2000)[0 < year < 28], 0)[1900 < year], month, day)
                    except ValueError as e:
                        raise InvalidNameException(ex(e))

                if 'extra_info' in named_groups:
                    tmp_extra_info = match.group('extra_info')

                    # Show.S04.Special or Show.S05.Part.2.Extras is almost certainly not every episode in the season
                    if tmp_extra_info and 'season_only' == cur_regex_name and re.search(
                            r'([. _-]|^)(special|extra)s?\w*([. _-]|$)', tmp_extra_info, re.I):
                        continue
                    if tmp_extra_info:
                        if result.extra_info:
                            tmp_extra_info = '%s %s' % (result.extra_info, tmp_extra_info)
                        result.extra_info = tmp_extra_info
                    result.score += 1

                if 'release_group' in named_groups:
                    result.release_group = match.group('release_group')
                    result.score += 1

                if 'version' in named_groups:
                    # assigns version to anime file if detected using anime regex. Non-anime regex receives -1
                    version = match.group('version')
                    if version:
                        result.version = helpers.try_int(version)
                    else:
                        result.version = 1
                else:
                    result.version = -1

                if None is result.season_number and result.episode_numbers and not result.air_date and \
                        cur_regex_name in ['no_season', 'no_season_general', 'no_season_multi_ep'] and \
                        re.search(r'(?i)\bpart.?\d{1,2}\b', result.original_name):
                    result.season_number = 1

                matches.append(result)

            if len(matches):
                # pick best match with highest score based on placement
                best_result = max(sorted(matches, reverse=True, key=lambda x: x.which_regex), key=lambda x: x.score)

                show_obj = None
                if not self.naming_pattern:
                    # try and create a show object for this result
                    show_obj = helpers.get_show(best_result.series_name, self.try_scene_exceptions)

                # confirm passed in show object tvid_prodid matches result show object tvid_prodid
                if show_obj and not self.testing:
                    if self.show_obj and show_obj.tvid_prodid != self.show_obj.tvid_prodid:
                        show_obj = None
                elif not show_obj and self.show_obj:
                    show_obj = self.show_obj
                best_result.show_obj = show_obj
                if not best_result.series_name and getattr(show_obj, 'name', None):
                    best_result.series_name = show_obj.name

                if show_obj and show_obj.is_anime and 1 < len(self.compiled_regexes[1]) and 1 != reg_ex:
                    continue

                # if this is a naming pattern test then return best result
                if not show_obj or self.naming_pattern:
                    if not show_obj and not self.naming_pattern and not self.testing:
                        # ensure anime regex test but use initial best if show still not found
                        if 0 == reg_ex:
                            initial_best_result = best_result
                            matches = []  # clear non-anime match scores
                            continue
                        return initial_best_result
                    return best_result

                # get quality
                new_name = helpers.remove_non_release_groups(name, show_obj.is_anime)
                best_result.quality = common.Quality.nameQuality(new_name, show_obj.is_anime)

                new_episode_numbers = []
                new_season_numbers = []
                new_absolute_numbers = []

                # if we have an air-by-date show then get the real season/episode numbers
                if best_result.is_air_by_date:
                    season_number, episode_numbers = None, []

                    airdate = best_result.air_date.toordinal()
                    my_db = db.DBConnection()
                    sql_result = my_db.select(
                        'SELECT season, episode, name'
                        ' FROM tv_episodes'
                        ' WHERE indexer = ? AND showid = ?'
                        ' AND airdate = ?',
                        [show_obj.tvid, show_obj.prodid, airdate])

                    if sql_result:
                        season_number = int(sql_result[0]['season'])
                        episode_numbers = [int(sql_result[0]['episode'])]
                        if 1 < len(sql_result):
                            # multi-eps broadcast on this day
                            nums = {'1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
                                    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten'}
                            patt = '(?i)(?:e(?:p(?:isode)?)?|part|pt)[. _-]?(%s)'
                            try:
                                src_num = str(re.findall(patt % r'\w+', best_result.extra_info)[0])
                                alt_num = nums.get(src_num) or list(iterkeys(nums))[
                                    list(itervalues(nums)).index(src_num)]
                                re_partnum = re.compile(patt % ('%s|%s' % (src_num, alt_num)))
                                for ep_details in sql_result:
                                    if re_partnum.search(ep_details['name']):
                                        season_number = int(ep_details['season'])
                                        episode_numbers = [int(ep_details['episode'])]
                                        break
                            except (BaseException, Exception):
                                pass

                    if self.indexer_lookup and not season_number or not len(episode_numbers):
                        try:
                            tvinfo_config = sickbeard.TVInfoAPI(show_obj.tvid).api_params.copy()

                            if show_obj.lang:
                                tvinfo_config['language'] = show_obj.lang

                            t = sickbeard.TVInfoAPI(show_obj.tvid).setup(**tvinfo_config)

                            ep_obj = t[show_obj.prodid].aired_on(best_result.air_date)[0]

                            season_number = int(ep_obj['seasonnumber'])
                            episode_numbers = [int(ep_obj['episodenumber'])]
                        except BaseTVinfoEpisodenotfound as e:
                            logger.warning(u'Unable to find episode with date %s for show %s, skipping' %
                                           (best_result.air_date, show_obj.unique_name))
                            episode_numbers = []
                        except BaseTVinfoError as e:
                            logger.log(u'Unable to contact ' + sickbeard.TVInfoAPI(show_obj.tvid).name
                                       + ': ' + ex(e), logger.WARNING)
                            episode_numbers = []

                    for epNo in episode_numbers:
                        s = season_number
                        e = epNo

                        if self.convert and show_obj.is_scene:
                            (s, e) = scene_numbering.get_indexer_numbering(
                                show_obj.tvid, show_obj.prodid, season_number, epNo)
                        new_episode_numbers.append(e)
                        new_season_numbers.append(s)

                elif show_obj.is_anime and len(best_result.ab_episode_numbers) and not self.testing:
                    scene_season = scene_exceptions.get_scene_exception_by_name(best_result.series_name)[2]
                    for epAbsNo in best_result.ab_episode_numbers:
                        a = epAbsNo

                        if self.convert and show_obj.is_scene:
                            a = scene_numbering.get_indexer_absolute_numbering(
                                show_obj.tvid, show_obj.prodid, epAbsNo, True, scene_season)

                        (s, e) = helpers.get_all_episodes_from_absolute_number(show_obj, [a])

                        new_absolute_numbers.append(a)
                        new_episode_numbers.extend(e)
                        new_season_numbers.append(s)

                elif best_result.season_number and len(best_result.episode_numbers) and not self.testing:
                    for epNo in best_result.episode_numbers:
                        s = best_result.season_number
                        e = epNo

                        if self.convert and show_obj.is_scene:
                            (s, e) = scene_numbering.get_indexer_numbering(
                                show_obj.tvid, show_obj.prodid, best_result.season_number, epNo)
                        if show_obj.is_anime:
                            a = helpers.get_absolute_number_from_season_and_episode(show_obj, s, e)
                            if a:
                                new_absolute_numbers.append(a)

                        new_episode_numbers.append(e)
                        new_season_numbers.append(s)

                # need to do a quick sanity check here.  It's possible that we now have episodes
                # from more than one season (by tvdb numbering), and this is just too much, so flag it.
                new_season_numbers = list(set(new_season_numbers))  # remove duplicates
                if 1 < len(new_season_numbers):
                    raise InvalidNameException('Scene numbering results episodes from '
                                               'seasons %s, (i.e. more than one) and '
                                               'SickGear does not support this.  '
                                               'Sorry.' % (str(new_season_numbers)))

                # I guess it's possible that we'd have duplicate episodes too, so lets
                # eliminate them
                new_episode_numbers = list(set(new_episode_numbers))
                new_episode_numbers.sort()

                # maybe even duplicate absolute numbers so why not do them as well
                new_absolute_numbers = list(set(new_absolute_numbers))
                new_absolute_numbers.sort()

                if len(new_absolute_numbers):
                    best_result.ab_episode_numbers = new_absolute_numbers

                if len(new_season_numbers) and len(new_episode_numbers):
                    best_result.episode_numbers = new_episode_numbers
                    best_result.season_number = new_season_numbers[0]

                if self.convert and show_obj.is_scene:
                    logger.log(u'Converted parsed result %s into %s'
                               % (best_result.original_name, decode_str(str(best_result), errors='xmlcharrefreplace')),
                               logger.DEBUG)

                helpers.cpu_sleep()

                return best_result

    @staticmethod
    def _combine_results(first, second, attr):
        # type: (ParseResult, ParseResult, AnyStr) -> Any
        """

        :param first:
        :type first: ParseResult
        :param second:
        :type second: ParseResult
        :param attr:
        :type attr: AnyStr
        :return:
        :rtype: Any
        """
        # if the first doesn't exist then return the second or nothing
        if not first:
            if not second:
                return None
            return getattr(second, attr)

        # if the second doesn't exist then return the first
        if not second:
            return getattr(first, attr)

        a = getattr(first, attr, [])
        b = getattr(second, attr)

        # if a is good use it
        if None is not a or (isinstance(a, list) and len(a)):
            return a
        # if not use b (if b isn't set it'll just be default)
        return b

    @staticmethod
    def _unicodify(obj, encoding='utf-8'):
        if PY2 and isinstance(obj, string_types):
            if not isinstance(obj, text_type):
                obj = text_type(obj, encoding, 'replace')
        if not PY2 and isinstance(obj, text_type):
            try:
                return obj.encode('latin1').decode('utf8')
            except (BaseException, Exception):
                pass
        return obj

    @staticmethod
    def _convert_number(org_number):
        """
         Convert org_number into an integer
         org_number: integer or representation of a number: string or unicode
         Try force converting to int first, on error try converting from Roman numerals

         :param org_number:
         :type org_number: int or AnyStr
         :return:
         :rtype: int
         """

        try:
            # try forcing to int
            if org_number:
                number = int(org_number)
            else:
                number = 0

        except (BaseException, Exception):
            # on error try converting from Roman numerals
            roman_to_int_map = (('M', 1000), ('CM', 900), ('D', 500), ('CD', 400), ('C', 100),
                                ('XC', 90), ('L', 50), ('XL', 40), ('X', 10),
                                ('IX', 9), ('V', 5), ('IV', 4), ('I', 1))

            roman_numeral = str(org_number).upper()
            number = 0
            index = 0

            for numeral, integer in roman_to_int_map:
                while roman_numeral[index:index + len(numeral)] == numeral:
                    number += integer
                    index += len(numeral)

        return number

    def parse(self, name, cache_result=True, release_group=None):
        # type: (AnyStr, bool, AnyStr) -> ParseResult
        """

        :param name:
        :param cache_result:
        :param release_group: Name to use if anime and no group, otherwise pick_best_result will fail
        :return:
        """
        name = self._unicodify(name)

        if self.naming_pattern:
            cache_result = False

        cached = name_parser_cache.get(name)
        show_obj_given = bool(self.show_obj)
        if cached and ((not show_obj_given and not cached.show_obj_match)
                       or (show_obj_given and self.show_obj == cached.show_obj)):
            return cached

        # break it into parts if there are any (dirname, file name, extension)
        dir_name, file_name = ek.ek(os.path.split, name)

        if self.file_name:
            base_file_name = helpers.remove_extension(file_name)
        else:
            base_file_name = file_name

        # set up a result to use
        # set if parsed with given show_obj set
        final_result = ParseResult(name, show_obj_match=show_obj_given)

        # try parsing the file name
        file_name_result = self._parse_string(base_file_name)

        # use only the direct parent dir
        dir_name = ek.ek(os.path.basename, dir_name)

        # parse the dirname for extra info if needed
        dir_name_result = self._parse_string(dir_name)

        # build the ParseResult object
        final_result.air_date = self._combine_results(file_name_result, dir_name_result, 'air_date')

        # anime absolute numbers
        final_result.ab_episode_numbers = self._combine_results(file_name_result, dir_name_result, 'ab_episode_numbers')

        # season and episode numbers
        final_result.season_number = self._combine_results(file_name_result, dir_name_result, 'season_number')
        final_result.episode_numbers = self._combine_results(file_name_result, dir_name_result, 'episode_numbers')

        # if the dirname has a release group/show name I believe it over the filename
        final_result.series_name = self._combine_results(dir_name_result, file_name_result, 'series_name')
        final_result.extra_info = self._combine_results(dir_name_result, file_name_result, 'extra_info')
        final_result.release_group = self._combine_results(dir_name_result, file_name_result, 'release_group')
        final_result.version = self._combine_results(dir_name_result, file_name_result, 'version')

        final_result.which_regex = []
        if final_result == file_name_result:
            final_result.which_regex = file_name_result.which_regex
        elif final_result == dir_name_result:
            final_result.which_regex = dir_name_result.which_regex
        else:
            if file_name_result:
                final_result.which_regex += file_name_result.which_regex
            if dir_name_result:
                final_result.which_regex += dir_name_result.which_regex

        final_result.show_obj = self._combine_results(file_name_result, dir_name_result, 'show_obj')
        final_result.quality = self._combine_results(file_name_result, dir_name_result, 'quality')

        if not final_result.show_obj:
            if self.testing:
                pass
            else:
                raise InvalidShowException('Unable to parse %s'
                                           % name.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))

        # if there's no useful info in it then raise an exception
        if None is final_result.season_number and not final_result.episode_numbers and None is final_result.air_date \
                and not final_result.ab_episode_numbers and not final_result.series_name:
            raise InvalidNameException('Unable to parse %s' % name.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))

        if final_result.show_obj and final_result.show_obj.is_anime \
                and not final_result.release_group and None is not release_group:
            final_result.release_group = release_group  # use provider ID otherwise pick_best_result fails

        if cache_result and final_result.show_obj \
                and any('anime' in wr for wr in final_result.which_regex) == bool(final_result.show_obj.is_anime):
            name_parser_cache.add(name, final_result)

        logger.log(u'Parsed %s into %s' % (name, final_result), logger.DEBUG)
        return final_result


compiled_regexes = {NameParser.NORMAL_REGEX: NameParser.compile_regexes(NameParser.NORMAL_REGEX),
                    NameParser.ANIME_REGEX: NameParser.compile_regexes(NameParser.ANIME_REGEX),
                    NameParser.ALL_REGEX: NameParser.compile_regexes(NameParser.ALL_REGEX)}


class ParseResult(LegacyParseResult):
    def __init__(self,
                 original_name,
                 series_name=None,
                 season_number=None,
                 episode_numbers=None,
                 extra_info=None,
                 release_group=None,
                 air_date=None,
                 ab_episode_numbers=None,
                 show_obj=None,
                 score=None,
                 quality=None,
                 version=None,
                 show_obj_match=False,
                 **kwargs):

        self.original_name = original_name  # type: AnyStr

        self.series_name = series_name  # type: Optional[AnyStr]
        self.season_number = season_number  # type: Optional[int]
        if not episode_numbers:
            self.episode_numbers = []
        else:
            self.episode_numbers = episode_numbers  # type: List[int]

        if not ab_episode_numbers:
            self.ab_episode_numbers = []
        else:
            self.ab_episode_numbers = ab_episode_numbers  # type: List[int]

        if not quality:
            self.quality = common.Quality.UNKNOWN
        else:
            self.quality = quality  # type: int

        self.extra_info = extra_info  # type: Optional[AnyStr]
        self._extra_info_no_name = None  # type: Optional[AnyStr]
        self.release_group = release_group  # type: Optional[AnyStr]

        self.air_date = air_date

        self.which_regex = None

        self._show_obj = show_obj  # type: sickbeard.tv.TVShow

        self.score = score  # type: Optional[int]

        self.version = version  # type: Optional[int]

        self.show_obj_match = show_obj_match  # type: bool

        super(ParseResult, self).__init__(**kwargs)

    @property
    def show_obj(self):
        # type: (...) -> Optional[sickbeard.tv.TVShow]
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        # type: (sickbeard.tv.TVShow) -> None
        self._show_obj = val

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not other:
            return False

        if self.series_name != other.series_name:
            return False
        if self.season_number != other.season_number:
            return False
        if self.episode_numbers != other.episode_numbers:
            return False
        if self.extra_info != other.extra_info:
            return False
        if self.release_group != other.release_group:
            return False
        if self.air_date != other.air_date:
            return False
        if self.ab_episode_numbers != other.ab_episode_numbers:
            return False

        return True

    def __hash__(self):
        return hash((self.series_name, self.season_number, tuple(self.episode_numbers), self.extra_info,
                     self.release_group, self.air_date, tuple(self.ab_episode_numbers)))

    def __str__(self):
        if not PY2:
            return self.__unicode__()
        return self.__unicode__().encode('utf-8', errors='ignore')

    def __unicode__(self):
        if None is not self.series_name:
            to_return = self.series_name + u' - '
        else:
            to_return = u''
        if None is not self.season_number:
            to_return += 'S' + str(self.season_number)
        if self.episode_numbers and len(self.episode_numbers):
            for e in self.episode_numbers:
                to_return += 'E' + str(e)

        if self.is_air_by_date:
            to_return += str(self.air_date)
        if self.ab_episode_numbers:
            to_return += ' [ABS: %s]' % str(self.ab_episode_numbers)
        if self.is_anime:
            if self.version:
                to_return += ' [ANIME VER: %s]' % str(self.version)

        if self.release_group:
            to_return += ' [GROUP: %s]' % self.release_group

        to_return += ' [ABD: %s]' % str(self.is_air_by_date)
        to_return += ' [ANIME: %s]' % str(self.is_anime)
        to_return += ' [whichReg: %s]' % str(self.which_regex)

        return decode_str(to_return, errors='xmlcharrefreplace')

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def _replace_ep_name_helper(e_i_n_n, n):
        # type: (AnyStr, AnyStr) -> AnyStr
        ep_regex = r'\W*%s(\W*)' % re.sub(r' ', r'\\W', re.sub(r'[^a-zA-Z0-9 ]', r'\\W?',
                                                               re.sub(r'\W+$', '', n.strip())))
        if None is regex:
            return re.sub(r'^\W+', '', re.sub(ep_regex, r'\1', e_i_n_n, flags=re.I))

        er = trunc(len(re.findall(r'\w', ep_regex)) // 5)
        try:
            me = trunc(len(e_i_n_n) // 5)
            me = min(3, me)
        except (BaseException, Exception):
            me = 3
        # noinspection PyUnresolvedReferences
        return re.sub(r'^\W+', '', regex.sub(r'(?:%s){e<=%d}' % (ep_regex, (er, me)[er > me]), r'\1',
                                             e_i_n_n, flags=regex.I | regex.B))

    def get_extra_info_no_name(self):
        # type: (...) -> AnyStr
        extra_info_no_name = self.extra_info
        if isinstance(extra_info_no_name, string_types) and self.show_obj and hasattr(self.show_obj, 'tvid'):
            for e in self.episode_numbers:
                if not hasattr(self.show_obj, 'get_episode'):
                    continue
                ep_obj = self.show_obj.get_episode(self.season_number, e)
                if ep_obj and isinstance(getattr(ep_obj, 'name', None), string_types) and ep_obj.name.strip():
                    extra_info_no_name = self._replace_ep_name_helper(extra_info_no_name, ep_obj.name)
            if hasattr(self.show_obj, 'get_all_episodes'):
                for e in [ep_obj.name for ep_obj in self.show_obj.get_all_episodes(check_related_eps=False)
                          if getattr(ep_obj, 'name', None) and re.search(r'real|proper|repack', ep_obj.name, re.I)]:
                    extra_info_no_name = self._replace_ep_name_helper(extra_info_no_name, e)

        return extra_info_no_name

    def extra_info_no_name(self):
        # type: (...) -> AnyStr
        if None is self._extra_info_no_name and None is not self.extra_info:
            self._extra_info_no_name = self.get_extra_info_no_name()
        return self._extra_info_no_name

    @property
    def is_air_by_date(self):
        # type: (...) -> bool
        if self.air_date:
            return True
        return False

    @property
    def is_anime(self):
        # type: (...) -> bool
        if len(self.ab_episode_numbers):
            return True
        return False


class NameParserCache(object):
    def __init__(self):
        super(NameParserCache, self).__init__()
        self._previous_parsed = OrderedDefaultdict()  # type: Dict[AnyStr, ParseResult]
        self._cache_size = 1000
        self.lock = threading.Lock()

    def add(self, name, parse_result):
        # type: (AnyStr, ParseResult) -> None
        """

        :param name: name
        :type name: AnyStr
        :param parse_result:
        :type parse_result: ParseResult
        """
        with self.lock:
            self._previous_parsed[name] = parse_result
            _current_cache_size = len(self._previous_parsed)
            if _current_cache_size > self._cache_size:
                key = None
                for i in range(_current_cache_size - self._cache_size):
                    try:
                        key = self._previous_parsed.first_key()
                        del self._previous_parsed[key]
                    except KeyError:
                        logger.log('Could not remove old NameParserCache entry: %s' % key, logger.DEBUG)

    def get(self, name):
        # type: (AnyStr) -> ParseResult
        """

        :param name:
        :type name: AnyStr
        :return:
        :rtype: ParseResult
        """
        with self.lock:
            if name in self._previous_parsed:
                logger.log('Using cached parse result for: ' + name, logger.DEBUG)
                self._previous_parsed.move_to_end(name)
                return self._previous_parsed[name]

    def flush(self, show_obj):
        # type: (TVShow) -> None
        """
        removes all entries corresponding to the given show_obj

        :param show_obj: TVShow object
        """
        with self.lock:
            self._previous_parsed = OrderedDefaultdict(None, [(k, v) for k, v in iteritems(self._previous_parsed)
                                                       if v.show_obj != show_obj])


name_parser_cache = NameParserCache()


class InvalidNameException(Exception):
    """The given release name is not valid"""


class InvalidShowException(Exception):
    """The given show name is not valid"""
