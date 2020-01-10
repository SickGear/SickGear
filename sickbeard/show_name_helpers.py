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
import datetime
import fnmatch
import os
import re

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import common, db, logger
from .helpers import sanitize_scene_name
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from .scene_exceptions import get_scene_exceptions

from _23 import filter_list, map_list, quote_plus
from six import iterkeys, itervalues

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Union


def pass_wordlist_checks(name,  # type: AnyStr
                         parse=True,  # type: bool
                         indexer_lookup=True  # type: bool
                         ):  # type: (...) -> bool
    """
    Filters out non-english and just all-around stupid releases by comparing
    the word list contents at boundaries or the end of name.

    :param name: the release name to check
    :param parse: try to parse release name
    :param indexer_lookup: try to look up on tvinfo source
    :return: True if the release name is OK, False if it's bad.
    """

    if parse:
        err_msg = u'Unable to parse the filename %s into a valid ' % name
        try:
            NameParser(indexer_lookup=indexer_lookup).parse(name)
        except InvalidNameException:
            logger.log(err_msg + 'episode', logger.DEBUG)
            return False
        except InvalidShowException:
            logger.log(err_msg + 'show', logger.DEBUG)
            return False

    word_list = ['sub(bed|ed|pack|s)', '(dk|fin|heb|kor|nor|nordic|pl|swe)sub(bed|ed|s)?',
                 '(dir|sample|sub|nfo)fix', 'sample', '(dvd)?extras',
                 'dub(bed)?']

    # if any of the bad strings are in the name then say no
    if sickbeard.IGNORE_WORDS:
        word_list = ','.join([sickbeard.IGNORE_WORDS] + word_list)

    result = contains_any(name, word_list)
    if None is not result and result:
        logger.log(u'Ignored: %s for containing ignore word' % name, logger.DEBUG)
        return False

    # if any of the good strings aren't in the name then say no
    result = not_contains_any(name, sickbeard.REQUIRE_WORDS)
    if None is not result and result:
        logger.log(u'Ignored: %s for not containing required word match' % name, logger.DEBUG)
        return False

    return True


def not_contains_any(subject,  # type: AnyStr
                     lookup_words,  # type: Union[AnyStr, List[AnyStr]]
                     **kwargs
                     ):  # type: (...) -> bool

    return contains_any(subject, lookup_words, invert=True, **kwargs)


def contains_any(subject,  # type: AnyStr
                 lookup_words,  # type: Union[AnyStr, List[AnyStr]]
                 invert=False,  # type: bool
                 **kwargs
                 ):  # type: (...) -> Union[bool, None]
    """
    Check if subject does or does not contain a match from a list or string of regular expression lookup words

    word: word to test existence of
    re_prefix: insert string to all lookup words
    re_suffix: append string to all lookup words

    :param subject:
    :param lookup_words: List or comma separated string of words to search
    :param invert: invert function logic "contains any" into "does not contain any"
    :param kwargs:
    :return: None if no checking was done. True for first match found, or if invert is False,
             then True for first pattern that does not match, or False
    """
    compiled_words = compile_word_list(lookup_words, **kwargs)
    if subject and compiled_words:
        for rc_filter in compiled_words:
            match = rc_filter.search(subject)
            if (match and not invert) or (not match and invert):
                msg = match and not invert and 'Found match' or ''
                msg = not match and invert and 'No match found' or msg
                logger.log(u'%s from pattern: %s in text: %s ' % (msg, rc_filter.pattern, subject), logger.DEBUG)
                return True
        return False
    return None


def compile_word_list(lookup_words,  # type: AnyStr
                      re_prefix=r'(^|[\W_])',  # type: AnyStr
                      re_suffix=r'($|[\W_])'  # type: AnyStr
                      ):  # type: (...) -> List[AnyStr]

    result = []
    if lookup_words:
        search_raw = isinstance(lookup_words, list)
        if not search_raw:
            search_raw = not lookup_words.startswith('regex:')
            lookup_words = lookup_words[(6, 0)[search_raw]:].split(',')
        lookup_words = [x.strip() for x in lookup_words]
        for word in [x for x in lookup_words if x]:
            try:
                # !0 == regex and subject = s / 'what\'s the "time"' / what\'s\ the\ \"time\"
                subject = search_raw and re.escape(word) or re.sub(r'([\" \'])', r'\\\1', word)
                result.append(re.compile('(?i)%s%s%s' % (re_prefix, subject, re_suffix)))
            except re.error as e:
                logger.log(u'Failure to compile filter expression: %s ... Reason: %s' % (word, ex(e)),
                           logger.DEBUG)

        diff = len(lookup_words) - len(result)
        if diff:
            logger.log(u'From %s expressions, %s was discarded during compilation' % (len(lookup_words), diff),
                       logger.DEBUG)

    return result


def url_encode(show_names, spacer='.'):
    # type: (List[AnyStr], AnyStr) -> List[AnyStr]
    """

    :param show_names: show name
    :param spacer: spacer
    :return:
    """
    return [quote_plus(n.replace('.', spacer).encode('utf-8', errors='replace')) for n in show_names]


def get_show_names(ep_obj, spacer='.'):
    # type: (sickbeard.tv.TVEpisode, AnyStr) -> List[AnyStr]
    """

    :param ep_obj: episode object
    :param spacer: spacer
    :return:
    """
    old_anime, old_dirty = ep_obj.show_obj.is_anime, ep_obj.show_obj.dirty
    ep_obj.show_obj.anime = 1  # used to limit results from all_possible(...)
    show_names = get_show_names_all_possible(ep_obj.show_obj, season=ep_obj.season, spacer=spacer)
    ep_obj.show_obj.anime = old_anime  # temporary measure, so restore property then dirty flag
    ep_obj.show_obj.dirty = old_dirty
    return show_names


def get_show_names_all_possible(show_obj, season=-1, scenify=True, spacer='.'):
    # type: (sickbeard.tv.TVShow, int, bool, AnyStr) -> List[AnyStr]
    """

    :param show_obj: show object
    :param season: season
    :param scenify:
    :param spacer: spacer
    :return:
    """
    show_names = list(set(allPossibleShowNames(show_obj, season=season)))  # type: List[AnyStr]
    if scenify:
        show_names = map_list(sanitize_scene_name, show_names)
    return url_encode(show_names, spacer)


def makeSceneSeasonSearchString(show_obj,  # type: sickbeard.tv.TVShow
                                ep_obj,  # type: sickbeard.tv.TVEpisode
                                ignore_wl=False,  # type: bool
                                extra_search_type=None
                                ):  # type: (...) -> List[AnyStr]
    """

    :param show_obj: show object
    :param ep_obj: episode object
    :param ignore_wl:
    :param extra_search_type:
    :return: list of search strings
    """
    if show_obj.air_by_date or show_obj.sports:
        numseasons = 0

        # the search string for air by date shows is just
        seasonStrings = [str(ep_obj.airdate).split('-')[0]]
    elif show_obj.is_anime:
        numseasons = 0
        ep_obj_list = show_obj.get_all_episodes(ep_obj.season)

        # get show qualities
        anyQualities, bestQualities = common.Quality.splitQuality(show_obj.quality)

        # compile a list of all the episode numbers we need in this 'season'
        seasonStrings = []
        for episode in ep_obj_list:

            # get quality of the episode
            curCompositeStatus = episode.status
            curStatus, curQuality = common.Quality.splitCompositeStatus(curCompositeStatus)

            if bestQualities:
                highestBestQuality = max(bestQualities)
            else:
                highestBestQuality = 0

            # if we need a better one then add it to the list of episodes to fetch
            if (curStatus in (
                    common.DOWNLOADED,
                    common.SNATCHED) and curQuality < highestBestQuality) or curStatus == common.WANTED:
                ab_number = episode.scene_absolute_number
                if 0 < ab_number:
                    seasonStrings.append("%02d" % ab_number)

    else:
        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT COUNT(DISTINCT season) AS numseasons'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?'
            ' AND season != 0',
            [show_obj.tvid, show_obj.prodid])

        numseasons = int(sql_result[0][0])
        seasonStrings = ["S%02d" % int(ep_obj.scene_season)]

    show_names = get_show_names_all_possible(show_obj, ep_obj.scene_season)

    to_return = []

    # search each show name
    for cur_name in show_names:
        # most providers all work the same way
        if not extra_search_type:
            # if there's only one season then we can just use the show name straight up
            if 1 == numseasons:
                to_return.append(cur_name)
            # for providers that don't allow multiple searches in one request we only search for Sxx style stuff
            else:
                for cur_season in seasonStrings:
                    if not ignore_wl and show_obj.is_anime \
                            and None is not show_obj.release_groups and show_obj.release_groups.whitelist:
                        for keyword in show_obj.release_groups.whitelist:

                            to_return.append(keyword + '.' + cur_name + "." + cur_season)
                    else:
                        to_return.append(cur_name + "." + cur_season)

    return to_return


def makeSceneSearchString(show_obj,  # type: sickbeard.tv.TVShow
                          ep_obj,  # type: sickbeard.tv.TVEpisode
                          ignore_wl=False  # type: bool
                          ):  # type: (...) -> List[AnyStr]
    """

    :param show_obj: show object
    :param ep_obj: episode object
    :param ignore_wl:
    :return: list or search strings
    """
    my_db = db.DBConnection()
    sql_result = my_db.select(
        'SELECT COUNT(DISTINCT season) AS numseasons'
        ' FROM tv_episodes'
        ' WHERE indexer = ? AND showid = ? AND season != 0',
        [show_obj.tvid, show_obj.prodid])
    num_seasons = int(sql_result[0][0])

    # see if we should use dates instead of episodes
    if (show_obj.air_by_date or show_obj.sports) and ep_obj.airdate != datetime.date.fromordinal(1):
        ep_strings = [str(ep_obj.airdate)]
    elif show_obj.is_anime:
        ep_strings = ['%02i' % int(ep_obj.scene_absolute_number
                                   if 0 < ep_obj.scene_absolute_number else ep_obj.scene_episode)]
    else:
        ep_strings = ['S%02iE%02i' % (int(ep_obj.scene_season), int(ep_obj.scene_episode)),
                      '%ix%02i' % (int(ep_obj.scene_season), int(ep_obj.scene_episode))]

    # for single-season shows just search for the show name -- if total ep count (exclude s0) is less than 11
    # due to the amount of qualities and releases, it is easy to go over the 50 result limit on rss feeds otherwise
    if 1 == num_seasons and not ep_obj.show_obj.is_anime:
        ep_strings = ['']

    show_names = get_show_names_all_possible(show_obj, ep_obj.scene_season)

    to_return = []

    for cur_show_obj in show_names:
        for cur_ep_string in ep_strings:
            if not ignore_wl and ep_obj.show_obj.is_anime and \
                    None is not ep_obj.show_obj.release_groups and ep_obj.show_obj.release_groups.whitelist:
                for keyword in ep_obj.show_obj.release_groups.whitelist:
                    to_return.append(keyword + '.' + cur_show_obj + '.' + cur_ep_string)
            else:
                to_return.append(cur_show_obj + '.' + cur_ep_string)

    return to_return


def allPossibleShowNames(show_obj, season=-1):
    # type: (sickbeard.tv.TVShow, int) -> List[AnyStr]
    """
    Figures out every possible variation of the name for a particular show. Includes TVDB name, TVRage name,
    country codes on the end, eg. "Show Name (AU)", and any scene exception names.

    :param show_obj: a TVShow object that we should get the names of
    :param season: season
    :return: a list of all the possible show names
    """

    showNames = get_scene_exceptions(show_obj.tvid, show_obj.prodid, season=season)[:]
    if not showNames:  # if we dont have any season specific exceptions fallback to generic exceptions
        season = -1
        showNames = get_scene_exceptions(show_obj.tvid, show_obj.prodid, season=season)[:]

    if season in [-1, 1]:
        showNames.append(show_obj.name)

    if not show_obj.is_anime:
        newShowNames = []
        country_list = common.countryList
        country_list.update(dict(zip(itervalues(common.countryList), iterkeys(common.countryList))))
        for curName in set(showNames):
            if not curName:
                continue

            # if we have "Show Name Australia" or "Show Name (Australia)" this will add "Show Name (AU)" for
            # any countries defined in common.countryList
            # (and vice versa)
            for curCountry in country_list:
                if curName.endswith(' ' + curCountry):
                    newShowNames.append(curName.replace(' ' + curCountry, ' (' + country_list[curCountry] + ')'))
                elif curName.endswith(' (' + curCountry + ')'):
                    newShowNames.append(curName.replace(' (' + curCountry + ')', ' (' + country_list[curCountry] + ')'))

            # if we have "Show Name (2013)" this will strip the (2013) show year from the show name
            # newShowNames.append(re.sub('\(\d{4}\)','',curName))

        showNames += newShowNames

    return showNames


def determineReleaseName(dir_name=None, nzb_name=None):
    # type: (AnyStr, AnyStr) -> Union[AnyStr, None]
    """Determine a release name from an nzb and/or folder name
    :param dir_name: dir name
    :param nzb_name: nzb name
    :return: None or release name
    """

    if None is not nzb_name:
        logger.log(u'Using nzb name for release name.')
        return nzb_name.rpartition('.')[0]

    if not dir_name or not ek.ek(os.path.isdir, dir_name):
        return None

    # try to get the release name from nzb/nfo
    file_types = ["*.nzb", "*.nfo"]

    for search in file_types:

        reg_expr = re.compile(fnmatch.translate(search), re.IGNORECASE)
        files = [file_name for file_name in ek.ek(os.listdir, dir_name) if
                 ek.ek(os.path.isfile, ek.ek(os.path.join, dir_name, file_name))]
        results = filter_list(reg_expr.search, files)

        if 1 == len(results):
            found_file = ek.ek(os.path.basename, results[0])
            found_file = found_file.rpartition('.')[0]
            if pass_wordlist_checks(found_file):
                logger.log(u"Release name (" + found_file + ") found from file (" + results[0] + ")")
                return found_file.rpartition('.')[0]

    # If that fails, we try the folder
    folder = ek.ek(os.path.basename, dir_name)
    if pass_wordlist_checks(folder):
        # NOTE: Multiple failed downloads will change the folder name.
        # (e.g., appending #s)
        # Should we handle that?
        logger.log(u"Folder name (" + folder + ") appears to be a valid release name. Using it.")
        return folder

    return None
