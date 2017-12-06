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

try:
    from lxml import etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        import xml.etree.ElementTree as etree

import re
import os

from name_parser.parser import NameParser, InvalidNameException, InvalidShowException

from sickbeard import logger, classes, helpers
from sickbeard.common import Quality
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
import sickbeard


SUBJECT_FN_MATCHER = re.compile(r'"([^"]*)"')
RE_NORMAL_NAME = re.compile(r'\.\w{1,5}$')


def platform_encode(p):
    """ Return Unicode name, if not already Unicode, decode with UTF-8 or latin1 """
    if isinstance(p, str):
        try:
            return p.decode('utf-8')
        except:
            return p.decode(sickbeard.SYS_ENCODING, errors='replace').replace('?', '!')
    else:
        return p


def name_extractor(subject):
    """ Try to extract a file name from a subject line, return `subject` if in doubt """
    result = subject
    for name in re.findall(SUBJECT_FN_MATCHER, subject):
        name = name.strip(' "')
        if name and RE_NORMAL_NAME.search(name):
            result = name
    return platform_encode(result)


def getSeasonNZBs(name, urlData, season):
    try:
        showXML = etree.ElementTree(etree.XML(urlData))
    except SyntaxError:
        logger.log(u"Unable to parse the XML of " + name + ", not splitting it", logger.ERROR)
        return {}, ''

    filename = name.replace(".nzb", "")

    nzbElement = showXML.getroot()

    regex = '([\w\._\ ]+)[\._ ]S%02d[\._ ]([\w\._\-\ ]+)' % season

    sceneNameMatch = re.search(regex, filename, re.I)
    if sceneNameMatch:
        showName, qualitySection = sceneNameMatch.groups()  # @UnusedVariable
    else:
        logger.log("%s - Not a valid season pack scene name. If it's a valid one, log a bug." % name, logger.ERROR)
        return {}, ''

    regex = '(' + re.escape(showName) + '[\._]S%02d(?:[E0-9]+)\.[\w\._]+' % season + ')'
    regex = regex.replace(' ', '.')

    epFiles = {}
    xmlns = None

    for curFile in nzbElement.getchildren():
        if not isinstance(curFile.tag, basestring):
            continue
        xmlnsMatch = re.match("\{(https?:\/\/[A-Za-z0-9_\.\/]+\/nzb)\}file", curFile.tag)
        if not xmlnsMatch:
            continue
        else:
            xmlns = xmlnsMatch.group(1)
        match = re.search(regex, curFile.get("subject"), re.I)
        if not match:
            #print curFile.get("subject"), "doesn't match", regex
            continue
        curEp = match.group(1)
        fn = name_extractor(curFile.get('subject', ''))
        if curEp == re.sub(r'\+\d+\.par2$', '', fn, flags=re.I):
            bn, ext = ek.ek(os.path.splitext, fn)
            curEp = re.sub(r'\.(part\d+|vol\d+(\+\d+)?)$', '', bn, flags=re.I)
        bn, ext = ek.ek(os.path.splitext, curEp)
        if isinstance(ext, basestring) \
                and re.search(r'^\.(nzb|r\d{2}|rar|7z|zip|par2|vol\d+|nfo|srt|txt|bat|sh|mkv|mp4|avi|wmv)$', ext,
                              flags=re.I):
            logger.log('Unable to split %s into episode nzb\'s' % name, logger.WARNING)
            return {}, ''
        if curEp not in epFiles:
            epFiles[curEp] = [curFile]
        else:
            epFiles[curEp].append(curFile)

    return epFiles, xmlns


def createNZBString(fileElements, xmlns):
    rootElement = etree.Element("nzb")
    if xmlns:
        rootElement.set("xmlns", xmlns)

    for curFile in fileElements:
        rootElement.append(stripNS(curFile, xmlns))

    return etree.tostring(rootElement, encoding='utf-8')


def saveNZB(nzbName, nzbString):
    try:
        with ek.ek(open, nzbName + ".nzb", 'w') as nzb_fh:
            nzb_fh.write(nzbString)

    except EnvironmentError as e:
        logger.log(u"Unable to save NZB: " + ex(e), logger.ERROR)


def stripNS(element, ns):
    element.tag = element.tag.replace("{" + ns + "}", "")
    for curChild in element.getchildren():
        stripNS(curChild, ns)

    return element


def splitResult(result):
    urlData = helpers.getURL(result.url)
    if urlData is None:
        logger.log(u"Unable to load url " + result.url + ", can't download season NZB", logger.ERROR)
        return False

    # parse the season ep name
    try:
        np = NameParser(False, showObj=result.show)
        parse_result = np.parse(result.name)
    except InvalidNameException:
        logger.log(u"Unable to parse the filename " + result.name + " into a valid episode", logger.DEBUG)
        return False
    except InvalidShowException:
        logger.log(u"Unable to parse the filename " + result.name + " into a valid show", logger.DEBUG)
        return False

    # bust it up
    season = parse_result.season_number if parse_result.season_number != None else 1

    separateNZBs, xmlns = getSeasonNZBs(result.name, urlData, season)

    resultList = []

    for newNZB in separateNZBs:

        logger.log(u"Split out " + newNZB + " from " + result.name, logger.DEBUG)

        # parse the name
        try:
            np = NameParser(False, showObj=result.show)
            parse_result = np.parse(newNZB)
        except InvalidNameException:
            logger.log(u"Unable to parse the filename " + newNZB + " into a valid episode", logger.DEBUG)
            return False
        except InvalidShowException:
            logger.log(u"Unable to parse the filename " + newNZB + " into a valid show", logger.DEBUG)
            return False

        # make sure the result is sane
        if (parse_result.season_number != None and parse_result.season_number != season) or (
                parse_result.season_number == None and season != 1):
            logger.log(
                u"Found " + newNZB + " inside " + result.name + " but it doesn't seem to belong to the same season, ignoring it",
                logger.WARNING)
            continue
        elif len(parse_result.episode_numbers) == 0:
            logger.log(
                u"Found " + newNZB + " inside " + result.name + " but it doesn't seem to be a valid episode NZB, ignoring it",
                logger.WARNING)
            continue

        wantEp = True
        for epNo in parse_result.episode_numbers:
            if not result.show.wantEpisode(season, epNo, result.quality):
                logger.log(u"Ignoring result " + newNZB + " because we don't want an episode that is " +
                           Quality.qualityStrings[result.quality], logger.DEBUG)
                wantEp = False
                break
        if not wantEp:
            continue

        # get all the associated episode objects
        epObjList = []
        for curEp in parse_result.episode_numbers:
            epObjList.append(result.show.getEpisode(season, curEp))

        # make a result
        curResult = classes.NZBDataSearchResult(epObjList)
        curResult.name = newNZB
        curResult.provider = result.provider
        curResult.quality = result.quality
        curResult.show = result.show
        curResult.extraInfo = [createNZBString(separateNZBs[newNZB], xmlns)]

        resultList.append(curResult)

    return resultList
