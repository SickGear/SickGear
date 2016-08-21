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

from __future__ import with_statement

import os
import time
import re
import datetime
import os.path
import regexes
import sickbeard

from sickbeard import logger, helpers, scene_numbering, common, scene_exceptions, encodingKludge as ek, db
from sickbeard.exceptions import ex


class NameParser(object):
    ALL_REGEX = 0
    NORMAL_REGEX = 1
    ANIME_REGEX = 2

    def __init__(self, file_name=True, showObj=None, try_scene_exceptions=False, convert=False,
                 naming_pattern=False, testing=False):

        self.file_name = file_name
        self.showObj = showObj
        self.try_scene_exceptions = try_scene_exceptions
        self.convert = convert
        self.naming_pattern = naming_pattern
        self.testing = testing

        if self.showObj and not self.showObj.is_anime:
            self._compile_regexes(self.NORMAL_REGEX)
        elif self.showObj and self.showObj.is_anime:
            self._compile_regexes(self.ANIME_REGEX)
        else:
            self._compile_regexes(self.ALL_REGEX)

    @staticmethod
    def clean_series_name(series_name):
        """Cleans up series name by removing any . and _
        characters, along with any trailing hyphens.

        Is basically equivalent to replacing all _ and . with a
        space, but handles decimal numbers in string, for example:

        >>> clean_series_name('an.example.1.0.test')
        'an example 1.0 test'
        >>> clean_series_name('an_example_1.0_test')
        'an example 1.0 test'

        Stolen from dbr's tvnamer
        """

        series_name = re.sub('(\D)\.(?!\s)(\D)', '\\1 \\2', series_name)
        series_name = re.sub('(\d)\.(\d{4})', '\\1 \\2', series_name)  # if it ends in a year then don't keep the dot
        series_name = re.sub('(\D)\.(?!\s)', '\\1 ', series_name)
        series_name = re.sub('\.(?!\s)(\D)', ' \\1', series_name)
        series_name = series_name.replace('_', ' ')
        series_name = re.sub('-$', '', series_name)
        series_name = re.sub('^\[.*\]', '', series_name)
        return series_name.strip()

    def _compile_regexes(self, regexMode):
        if self.ANIME_REGEX == regexMode:
            logger.log(u'Using ANIME regexs', logger.DEBUG)
            uncompiled_regex = [regexes.anime_regexes]
        elif self.NORMAL_REGEX == regexMode:
            logger.log(u'Using NORMAL regexs', logger.DEBUG)
            uncompiled_regex = [regexes.normal_regexes]
        else:
            logger.log(u'Using ALL regexes', logger.DEBUG)
            uncompiled_regex = [regexes.normal_regexes, regexes.anime_regexes]

        self.compiled_regexes = {0: [], 1: []}
        index = 0
        for regexItem in uncompiled_regex:
            for cur_pattern_num, (cur_pattern_name, cur_pattern) in enumerate(regexItem):
                try:
                    cur_regex = re.compile(cur_pattern, re.VERBOSE | re.IGNORECASE)
                except re.error as errormsg:
                    logger.log(u'WARNING: Invalid episode_pattern, %s. %s' % (errormsg, cur_pattern))
                else:
                    self.compiled_regexes[index].append([cur_pattern_num, cur_pattern_name, cur_regex])
            index += 1

    def _parse_string(self, name):
        if not name:
            return

        matches = []

        for regex in self.compiled_regexes:
            for (cur_regex_num, cur_regex_name, cur_regex) in self.compiled_regexes[regex]:
                match = cur_regex.match(name)

                if not match:
                    continue

                result = ParseResult(name)
                result.which_regex = [cur_regex_name]
                result.score = 0 - cur_regex_num

                named_groups = match.groupdict().keys()

                if 'series_name' in named_groups:
                    result.series_name = match.group('series_name')
                    if result.series_name:
                        result.series_name = self.clean_series_name(result.series_name)
                        result.score += 1

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
                            if hasattr(self.showObj, 'getEpisode'):
                                ep = self.showObj.getEpisode(parse_result.season_number, ep_num)
                            else:
                                tmp_show = helpers.get_show(parse_result.series_name, True, False)
                                if tmp_show and hasattr(tmp_show, 'getEpisode'):
                                    ep = tmp_show.getEpisode(parse_result.season_number, ep_num)
                                else:
                                    ep = None
                        except:
                            ep = None
                        en = ep and ep.name and re.match(r'^\W*(\d+)', ep.name) or None
                        es = en and en.group(1) or None

                        extra_ep_num = self._convert_number(captures.group(extra_grp_name))
                        parse_result.__dict__[ep_numbers] = range(ep_num, extra_ep_num + 1) if not (
                            ep and es and es != captures.group(extra_grp_name)) and (
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
                    month = int(match.group('air_month'))
                    day = int(match.group('air_day'))
                    # make an attempt to detect YYYY-DD-MM formats
                    if 12 < month:
                        tmp_month = month
                        month = day
                        day = tmp_month
                    try:
                        result.air_date = datetime.date(year, month, day)
                    except ValueError as e:
                        raise InvalidNameException(ex(e))

                if 'extra_info' in named_groups:
                    tmp_extra_info = match.group('extra_info')

                    # Show.S04.Special or Show.S05.Part.2.Extras is almost certainly not every episode in the season
                    if tmp_extra_info and 'season_only' == cur_regex_name and re.search(
                            r'([. _-]|^)(special|extra)s?\w*([. _-]|$)', tmp_extra_info, re.I):
                        continue
                    result.extra_info = tmp_extra_info
                    result.score += 1

                if 'release_group' in named_groups:
                    result.release_group = helpers.remove_non_release_groups(match.group('release_group'))
                    result.score += 1

                if 'version' in named_groups:
                    # assigns version to anime file if detected using anime regex. Non-anime regex receives -1
                    version = match.group('version')
                    if version:
                        result.version = version
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

                show = None
                if not self.naming_pattern:
                    # try and create a show object for this result
                    show = helpers.get_show(best_result.series_name, self.try_scene_exceptions)

                # confirm passed in show object indexer id matches result show object indexer id
                if show and not self.testing:
                    if self.showObj and show.indexerid != self.showObj.indexerid:
                        show = None
                elif not show and self.showObj:
                    show = self.showObj
                best_result.show = show

                if show and show.is_anime and 1 < len(self.compiled_regexes[1]) and 1 != regex:
                    continue

                # if this is a naming pattern test then return best result
                if not show or self.naming_pattern:
                    return best_result

                # get quality
                best_result.quality = common.Quality.nameQuality(name, show.is_anime)

                new_episode_numbers = []
                new_season_numbers = []
                new_absolute_numbers = []

                # if we have an air-by-date show then get the real season/episode numbers
                if best_result.is_air_by_date:
                    airdate = best_result.air_date.toordinal()
                    my_db = db.DBConnection()
                    sql_result = my_db.select(
                        'SELECT season, episode FROM tv_episodes WHERE showid = ? and indexer = ? and airdate = ?',
                        [show.indexerid, show.indexer, airdate])

                    season_number = None
                    episode_numbers = []

                    if sql_result:
                        season_number = int(sql_result[0][0])
                        episode_numbers = [int(sql_result[0][1])]

                    if not season_number or not len(episode_numbers):
                        try:
                            lindexer_api_parms = sickbeard.indexerApi(show.indexer).api_params.copy()

                            if show.lang:
                                lindexer_api_parms['language'] = show.lang

                            t = sickbeard.indexerApi(show.indexer).indexer(**lindexer_api_parms)

                            ep_obj = t[show.indexerid].airedOn(best_result.air_date)[0]

                            season_number = int(ep_obj['seasonnumber'])
                            episode_numbers = [int(ep_obj['episodenumber'])]
                        except sickbeard.indexer_episodenotfound:
                            logger.log(u'Unable to find episode with date ' + str(best_result.air_date) + ' for show ' + show.name + ', skipping', logger.WARNING)
                            episode_numbers = []
                        except sickbeard.indexer_error as e:
                            logger.log(u'Unable to contact ' + sickbeard.indexerApi(show.indexer).name + ': ' + ex(e), logger.WARNING)
                            episode_numbers = []

                    for epNo in episode_numbers:
                        s = season_number
                        e = epNo

                        if self.convert and show.is_scene:
                            (s, e) = scene_numbering.get_indexer_numbering(show.indexerid,
                                                                           show.indexer,
                                                                           season_number,
                                                                           epNo)
                        new_episode_numbers.append(e)
                        new_season_numbers.append(s)

                elif show.is_anime and len(best_result.ab_episode_numbers) and not self.testing:
                    scene_season = scene_exceptions.get_scene_exception_by_name(best_result.series_name)[1]
                    for epAbsNo in best_result.ab_episode_numbers:
                        a = epAbsNo

                        if self.convert and show.is_scene:
                            a = scene_numbering.get_indexer_absolute_numbering(show.indexerid,
                                                                               show.indexer, epAbsNo,
                                                                               True, scene_season)

                        (s, e) = helpers.get_all_episodes_from_absolute_number(show, [a])

                        new_absolute_numbers.append(a)
                        new_episode_numbers.extend(e)
                        new_season_numbers.append(s)

                elif best_result.season_number and len(best_result.episode_numbers) and not self.testing:
                    for epNo in best_result.episode_numbers:
                        s = best_result.season_number
                        e = epNo

                        if self.convert and show.is_scene:
                            (s, e) = scene_numbering.get_indexer_numbering(show.indexerid,
                                                                           show.indexer,
                                                                           best_result.season_number,
                                                                           epNo)
                        if show.is_anime:
                            a = helpers.get_absolute_number_from_season_and_episode(show, s, e)
                            if a:
                                new_absolute_numbers.append(a)

                        new_episode_numbers.append(e)
                        new_season_numbers.append(s)

                # need to do a quick sanity check heregex.  It's possible that we now have episodes
                # from more than one season (by tvdb numbering), and this is just too much
                # for sickbeard, so we'd need to flag it.
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

                if self.convert and show.is_scene:
                    logger.log(u'Converted parsed result %s into %s'
                               % (best_result.original_name, str(best_result).decode('utf-8', 'xmlcharrefreplace')),
                               logger.DEBUG)

                helpers.cpu_sleep()

                return best_result

    @staticmethod
    def _combine_results(first, second, attr):
        # if the first doesn't exist then return the second or nothing
        if not first:
            if not second:
                return None
            else:
                return getattr(second, attr)

        # if the second doesn't exist then return the first
        if not second:
            return getattr(first, attr)

        a = getattr(first, attr)
        b = getattr(second, attr)

        # if a is good use it
        if None is not a or (list == type(a) and len(a)):
            return a
        # if not use b (if b isn't set it'll just be default)
        else:
            return b

    @staticmethod
    def _unicodify(obj, encoding='utf-8'):
        if isinstance(obj, basestring):
            if not isinstance(obj, unicode):
                obj = unicode(obj, encoding, 'replace')
        return obj

    @staticmethod
    def _convert_number(org_number):
        """
         Convert org_number into an integer
         org_number: integer or representation of a number: string or unicode
         Try force converting to int first, on error try converting from Roman numerals
         returns integer or 0
         """

        try:
            # try forcing to int
            if org_number:
                number = int(org_number)
            else:
                number = 0

        except:
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

    def parse(self, name, cache_result=True):
        name = self._unicodify(name)

        if self.naming_pattern:
            cache_result = False

        cached = name_parser_cache.get(name)
        if cached:
            return cached

        # break it into parts if there are any (dirname, file name, extension)
        dir_name, file_name = ek.ek(os.path.split, name)

        if self.file_name:
            base_file_name = helpers.remove_extension(file_name)
        else:
            base_file_name = file_name

        # set up a result to use
        final_result = ParseResult(name)

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

        final_result.show = self._combine_results(file_name_result, dir_name_result, 'show')
        final_result.quality = self._combine_results(file_name_result, dir_name_result, 'quality')

        if not final_result.show:
            if self.testing:
                pass
            else:
                raise InvalidShowException('Unable to parse %s'
                                           % name.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))

        # if there's no useful info in it then raise an exception
        if None is final_result.season_number and not final_result.episode_numbers and None is final_result.air_date and not final_result.ab_episode_numbers and not final_result.series_name:
            raise InvalidNameException('Unable to parse %s' % name.encode(sickbeard.SYS_ENCODING, 'xmlcharrefreplace'))

        if cache_result:
            name_parser_cache.add(name, final_result)

        logger.log(u'Parsed %s into %s' % (name, str(final_result).decode('utf-8', 'xmlcharrefreplace')), logger.DEBUG)
        return final_result


class ParseResult(object):
    def __init__(self,
                 original_name,
                 series_name=None,
                 season_number=None,
                 episode_numbers=None,
                 extra_info=None,
                 release_group=None,
                 air_date=None,
                 ab_episode_numbers=None,
                 show=None,
                 score=None,
                 quality=None,
                 version=None):

        self.original_name = original_name

        self.series_name = series_name
        self.season_number = season_number
        if not episode_numbers:
            self.episode_numbers = []
        else:
            self.episode_numbers = episode_numbers

        if not ab_episode_numbers:
            self.ab_episode_numbers = []
        else:
            self.ab_episode_numbers = ab_episode_numbers

        if not quality:
            self.quality = common.Quality.UNKNOWN
        else:
            self.quality = quality

        self.extra_info = extra_info
        self.release_group = release_group

        self.air_date = air_date

        self.which_regex = None
        self.show = show
        self.score = score

        self.version = version

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

    def __str__(self):
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

        return to_return.encode('utf-8')

    @property
    def is_air_by_date(self):
        if self.air_date:
            return True
        return False

    @property
    def is_anime(self):
        if len(self.ab_episode_numbers):
            return True
        return False


class NameParserCache(object):
    _previous_parsed = {}
    _cache_size = 100

    def add(self, name, parse_result):
        self._previous_parsed[name] = parse_result
        _current_cache_size = len(self._previous_parsed)
        if _current_cache_size > self._cache_size:
            for i in range(_current_cache_size - self._cache_size):
                del self._previous_parsed[self._previous_parsed.keys()[0]]

    def get(self, name):
        if name in self._previous_parsed:
            logger.log('Using cached parse result for: ' + name, logger.DEBUG)
            return self._previous_parsed[name]


name_parser_cache = NameParserCache()


class InvalidNameException(Exception):
    """The given release name is not valid"""


class InvalidShowException(Exception):
    """The given show name is not valid"""
