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
import fnmatch
import os

import re
import datetime

import sickbeard
from sickbeard import common
from sickbeard.helpers import sanitizeSceneName
from sickbeard.scene_exceptions import get_scene_exceptions
from sickbeard import logger
from sickbeard import db
from sickbeard import encodingKludge as ek
from name_parser.parser import NameParser, InvalidNameException, InvalidShowException


def pass_wordlist_checks(name, parse=True):
    """
    Filters out non-english and just all-around stupid releases by comparing
    the word list contents at boundaries or the end of name.

    name: the release name to check

    Returns: True if the release name is OK, False if it's bad.
    """

    if parse:
        err_msg = u'Unable to parse the filename %s into a valid ' % name
        try:
            NameParser().parse(name)
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

def not_contains_any(subject, lookup_words, **kwargs):

    return contains_any(subject, lookup_words, invert=True, **kwargs)

def contains_any(subject, lookup_words, invert=False, **kwargs):
    """
    Check if subject does or does not contain a match from a list or string of regular expression lookup words

    word: word to test existence of
    lookup_words: List or comma separated string of words to search
    re_prefix: insert string to all lookup words
    re_suffix: append string to all lookup words
    invert: invert function logic "contains any" into "does not contain any"

    Returns: None if no checking was done. True for first match found, or if invert is False,
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

def compile_word_list(lookup_words, re_prefix='(^|[\W_])', re_suffix='($|[\W_])'):

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
                logger.log(u'Failure to compile filter expression: %s ... Reason: %s' % (word, e.message), logger.DEBUG)

        diff = len(lookup_words) - len(result)
        if diff:
            logger.log(u'From %s expressions, %s was discarded during compilation' % (len(lookup_words), diff), logger.DEBUG)

    return result

def makeSceneShowSearchStrings(show, season=-1):
    showNames = allPossibleShowNames(show, season=season)

    # scenify the names
    return map(sanitizeSceneName, showNames)


def makeSceneSeasonSearchString(show, ep_obj, extraSearchType=None):

    if show.air_by_date or show.sports:
        numseasons = 0

        # the search string for air by date shows is just
        seasonStrings = [str(ep_obj.airdate).split('-')[0]]
    elif show.is_anime:
        numseasons = 0
        seasonEps = show.getAllEpisodes(ep_obj.season)

        # get show qualities
        anyQualities, bestQualities = common.Quality.splitQuality(show.quality)

        # compile a list of all the episode numbers we need in this 'season'
        seasonStrings = []
        for episode in seasonEps:

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
                if ab_number > 0:
                    seasonStrings.append("%02d" % ab_number)

    else:
        myDB = db.DBConnection()
        numseasonsSQlResult = myDB.select(
            "SELECT COUNT(DISTINCT season) as numseasons FROM tv_episodes WHERE showid = ? and season != 0",
            [show.indexerid])

        numseasons = int(numseasonsSQlResult[0][0])
        seasonStrings = ["S%02d" % int(ep_obj.scene_season)]

    showNames = set(makeSceneShowSearchStrings(show, ep_obj.scene_season))

    toReturn = []

    # search each show name
    for curShow in showNames:
        # most providers all work the same way
        if not extraSearchType:
            # if there's only one season then we can just use the show name straight up
            if numseasons == 1:
                toReturn.append(curShow)
            # for providers that don't allow multiple searches in one request we only search for Sxx style stuff
            else:
                for cur_season in seasonStrings:
                    if show.is_anime and show.release_groups is not None and show.release_groups.whitelist:
                        for keyword in show.release_groups.whitelist:
                            toReturn.append(keyword + '.' + curShow+ "." + cur_season)
                    else:
                        toReturn.append(curShow + "." + cur_season)


    return toReturn


def makeSceneSearchString(show, ep_obj):
    myDB = db.DBConnection()
    numseasonsSQlResult = myDB.select(
        "SELECT COUNT(DISTINCT season) as numseasons FROM tv_episodes WHERE showid = ? and season != 0",
        [show.indexerid])
    numseasons = int(numseasonsSQlResult[0][0])

    # see if we should use dates instead of episodes
    if (show.air_by_date or show.sports) and ep_obj.airdate != datetime.date.fromordinal(1):
        epStrings = [str(ep_obj.airdate)]
    elif show.is_anime:
        epStrings = ["%02i" % int(ep_obj.scene_absolute_number if ep_obj.scene_absolute_number > 0 else ep_obj.scene_episode)]
    else:
        epStrings = ["S%02iE%02i" % (int(ep_obj.scene_season), int(ep_obj.scene_episode)),
                     "%ix%02i" % (int(ep_obj.scene_season), int(ep_obj.scene_episode))]

    # for single-season shows just search for the show name -- if total ep count (exclude s0) is less than 11
    # due to the amount of qualities and releases, it is easy to go over the 50 result limit on rss feeds otherwise
    if numseasons == 1 and not ep_obj.show.is_anime:
        epStrings = ['']

    showNames = set(makeSceneShowSearchStrings(show, ep_obj.scene_season))

    toReturn = []

    for curShow in showNames:
        for curEpString in epStrings:
            if ep_obj.show.is_anime and ep_obj.show.release_groups is not None and ep_obj.show.release_groups.whitelist:
                for keyword in ep_obj.show.release_groups.whitelist:
                    toReturn.append(keyword + '.' + curShow + '.' + curEpString)
            else:
                toReturn.append(curShow + '.' + curEpString)

    return toReturn


def allPossibleShowNames(show, season=-1):
    """
    Figures out every possible variation of the name for a particular show. Includes TVDB name, TVRage name,
    country codes on the end, eg. "Show Name (AU)", and any scene exception names.

    show: a TVShow object that we should get the names of

    Returns: a list of all the possible show names
    """

    showNames = get_scene_exceptions(show.indexerid, season=season)[:]
    if not showNames:  # if we dont have any season specific exceptions fallback to generic exceptions
        season = -1
        showNames = get_scene_exceptions(show.indexerid, season=season)[:]

    if season in [-1, 1]:
        showNames.append(show.name)

    if not show.is_anime:
        newShowNames = []
        country_list = common.countryList
        country_list.update(dict(zip(common.countryList.values(), common.countryList.keys())))
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
            #newShowNames.append(re.sub('\(\d{4}\)','',curName))

        showNames += newShowNames

    return showNames

def determineReleaseName(dir_name=None, nzb_name=None):
    """Determine a release name from an nzb and/or folder name"""

    if nzb_name is not None:
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
        results = filter(reg_expr.search, files)

        if len(results) == 1:
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
