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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import re

from lxml_etree import etree

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import classes, helpers, logger
from .common import Quality
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser

from _23 import decode_str
from six import string_types

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, List, Tuple

SUBJECT_FN_MATCHER = re.compile(r'"([^"]*)"')
RE_NORMAL_NAME = re.compile(r'\.\w{1,5}$')


def platform_encode(p):
    """ Return Unicode name, if not already Unicode, decode with UTF-8 or latin1 """
    try:
        return decode_str(p)
    except (BaseException, Exception):
        return decode_str(p, sickbeard.SYS_ENCODING, errors='replace').replace('?', '!')


def name_extractor(subject):
    """ Try to extract a file name from a subject line, return `subject` if in doubt """
    result = subject
    for name in re.findall(SUBJECT_FN_MATCHER, subject):
        name = name.strip(' "')
        if name and RE_NORMAL_NAME.search(name):
            result = name
    return platform_encode(result)


def getSeasonNZBs(name, url_data, season):
    """

    :param name: name
    :type name: AnyStr
    :param url_data: url data
    :type url_data: Any
    :param season: season
    :type season: int
    :return:
    :rtype: Tuple[Dict, AnyStr]
    """
    try:
        showXML = etree.ElementTree(etree.XML(url_data))
    except SyntaxError:
        logger.log(u'Unable to parse the XML of %s, not splitting it' % name, logger.ERROR)
        return {}, ''

    filename = name.replace('.nzb', '')

    nzbElement = showXML.getroot()

    regex = r'([\w\._\ ]+)[\._ ]S%02d[\._ ]([\w\._\-\ ]+)' % season

    sceneNameMatch = re.search(regex, filename, re.I)
    if sceneNameMatch:
        showName, qualitySection = sceneNameMatch.groups()
    else:
        logger.log('%s - Not a valid season pack scene name. If it\'s a valid one, log a bug.' % name, logger.ERROR)
        return {}, ''

    regex = r'(%s[\._]S%02d(?:[E0-9]+)\.[\w\._]+)' % (re.escape(showName), season)
    regex = regex.replace(' ', '.')

    ep_files = {}
    xmlns = None

    for cur_file in list(nzbElement):
        if not isinstance(cur_file.tag, string_types):
            continue
        xmlns_match = re.match(r'[{](https?://[A-Za-z0-9_./]+/nzb)[}]file', cur_file.tag)
        if not xmlns_match:
            continue
        else:
            xmlns = xmlns_match.group(1)
        match = re.search(regex, cur_file.get("subject"), re.I)
        if not match:
            # print curFile.get("subject"), "doesn't match", regex
            continue
        cur_ep = match.group(1)
        fn = name_extractor(cur_file.get('subject', ''))
        if cur_ep == re.sub(r'\+\d+\.par2$', '', fn, flags=re.I):
            bn, ext = ek.ek(os.path.splitext, fn)
            cur_ep = re.sub(r'\.(part\d+|vol\d+(\+\d+)?)$', '', bn, flags=re.I)
        bn, ext = ek.ek(os.path.splitext, cur_ep)
        if isinstance(ext, string_types) \
                and re.search(r'^\.(nzb|r\d{2}|rar|7z|zip|par2|vol\d+|nfo|srt|txt|bat|sh|mkv|mp4|avi|wmv)$', ext,
                              flags=re.I):
            logger.log('Unable to split %s into episode nzb\'s' % name, logger.WARNING)
            return {}, ''
        if cur_ep not in ep_files:
            ep_files[cur_ep] = [cur_file]
        else:
            ep_files[cur_ep].append(cur_file)

    return ep_files, xmlns


def createNZBString(file_elements, xmlns):
    """

    :param file_elements: first element
    :param xmlns: xmlns
    :return:
    :rtype: AnyStr
    """
    rootElement = etree.Element("nzb")
    if xmlns:
        rootElement.set("xmlns", xmlns)

    for curFile in file_elements:
        rootElement.append(stripNS(curFile, xmlns))

    return etree.tostring(rootElement, encoding='utf-8')


def saveNZB(nzb_name, nzb_string):
    """

    :param nzb_name: nzb name
    :type nzb_name: AnyStr
    :param nzb_string: nzb string
    :type nzb_string: AnyStr
    """
    try:
        with ek.ek(open, nzb_name + '.nzb', 'w') as nzb_fh:
            nzb_fh.write(nzb_string)

    except EnvironmentError as e:
        logger.log(u'Unable to save NZB: ' + ex(e), logger.ERROR)


def stripNS(element, ns):
    element.tag = element.tag.replace("{" + ns + "}", "")
    for curChild in list(element):
        stripNS(curChild, ns)

    return element


def splitResult(result):
    """

    :param result: search result
    :type result: sickbeard.classes.SearchResult
    :return: list of search results
    :rtype: List[sickbeard.classes.SearchResult]
    """
    resp = helpers.get_url(result.url)
    if None is resp:
        logger.log(u'Unable to load url %s, can\'t download season NZB' % result.url, logger.ERROR)
        return False

    # parse the season ep name
    try:
        np = NameParser(False, show_obj=result.show_obj)
        parse_result = np.parse(result.name)
    except InvalidNameException:
        logger.log(u'Unable to parse the filename %s into a valid episode' % result.name, logger.DEBUG)
        return False
    except InvalidShowException:
        logger.log(u'Unable to parse the filename %s into a valid show' % result.name, logger.DEBUG)
        return False

    # bust it up
    season = parse_result.season_number if None is not parse_result.season_number else 1

    separate_nzbs, xmlns = getSeasonNZBs(result.name, resp, season)

    result_list = []

    for new_nzb in separate_nzbs:

        logger.log(u'Split out %s from %s' % (new_nzb, result.name), logger.DEBUG)

        # parse the name
        try:
            np = NameParser(False, show_obj=result.show_obj)
            parse_result = np.parse(new_nzb)
        except InvalidNameException:
            logger.log(u"Unable to parse the filename %s into a valid episode" % new_nzb, logger.DEBUG)
            return False
        except InvalidShowException:
            logger.log(u"Unable to parse the filename %s into a valid show" % new_nzb, logger.DEBUG)
            return False

        # make sure the result is sane
        if (None is not parse_result.season_number and season != parse_result.season_number) \
                or (None is parse_result.season_number and 1 != season):
            logger.log(u'Found %s inside %s but it doesn\'t seem to belong to the same season, ignoring it'
                       % (new_nzb, result.name), logger.WARNING)
            continue
        elif 0 == len(parse_result.episode_numbers):
            logger.log(u'Found %s inside %s but it doesn\'t seem to be a valid episode NZB, ignoring it'
                       % (new_nzb, result.name), logger.WARNING)
            continue

        want_ep = True
        for ep_no in parse_result.episode_numbers:
            if not result.show_obj.want_episode(season, ep_no, result.quality):
                logger.log(u'Ignoring result %s because we don\'t want an episode that is %s'
                           % (new_nzb, Quality.qualityStrings[result.quality]), logger.DEBUG)
                want_ep = False
                break
        if not want_ep:
            continue

        # get all the associated episode objects
        ep_obj_list = []  # type: List[sickbeard.tv.TVEpisode]
        for cur_ep in parse_result.episode_numbers:
            ep_obj_list.append(result.show_obj.get_episode(season, cur_ep))

        # make a result
        nzb_result = classes.NZBDataSearchResult(ep_obj_list)
        nzb_result.name = new_nzb
        nzb_result.provider = result.provider
        nzb_result.quality = result.quality
        nzb_result.show_obj = result.show_obj
        nzb_result.extraInfo = [createNZBString(separate_nzbs[new_nzb], xmlns)]

        result_list.append(nzb_result)

    return result_list
