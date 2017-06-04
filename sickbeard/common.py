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

import operator
import os.path
import platform
import re
import traceback
import uuid

import logger
import sickbeard

INSTANCE_ID = str(uuid.uuid1())

USER_AGENT = ('SickGear/(%s; %s; %s)' % (platform.system(), platform.release(), INSTANCE_ID))

mediaExtensions = ['avi', 'mkv', 'mpg', 'mpeg', 'wmv', 'ogm', 'mp4', 'iso', 'img', 'divx', 'm2ts', 'm4v', 'ts', 'flv',
                   'f4v', 'mov', 'rmvb', 'vob', 'dvr-ms', 'wtv', 'ogv', '3gp', 'webm']

subtitleExtensions = ['srt', 'sub', 'ass', 'idx', 'ssa']

cpu_presets = {'DISABLED': 0, 'LOW': 0.01, 'NORMAL': 0.05, 'HIGH': 0.1}

# Other constants
MULTI_EP_RESULT = -1
SEASON_RESULT = -2

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2
NOTIFY_SUBTITLE_DOWNLOAD = 3
NOTIFY_GIT_UPDATE = 4
NOTIFY_GIT_UPDATE_TEXT = 5

notifyStrings = {NOTIFY_SNATCH: 'Started Download',
                 NOTIFY_DOWNLOAD: 'Download Finished',
                 NOTIFY_SUBTITLE_DOWNLOAD: 'Subtitle Download Finished',
                 NOTIFY_GIT_UPDATE: 'SickGear Updated',
                 NOTIFY_GIT_UPDATE_TEXT: 'SickGear Updated To Commit#: '}

# Episode statuses
UNKNOWN = -1  # should never happen
UNAIRED = 1  # episodes that haven't aired yet
SNATCHED = 2  # qualified with quality
WANTED = 3  # episodes we don't have but want to get
DOWNLOADED = 4  # qualified with quality
SKIPPED = 5  # episodes we don't want
ARCHIVED = 6  # episodes that you don't have locally (counts toward download completion stats)
IGNORED = 7  # episodes that you don't want included in your download stats
SNATCHED_PROPER = 9  # qualified with quality
SUBTITLED = 10  # qualified with quality
FAILED = 11  # episode downloaded or snatched we don't want
SNATCHED_BEST = 12  # episode redownloaded using best quality

NAMING_REPEAT = 1
NAMING_EXTEND = 2
NAMING_DUPLICATE = 4
NAMING_LIMITED_EXTEND = 8
NAMING_SEPARATED_REPEAT = 16
NAMING_LIMITED_EXTEND_E_PREFIXED = 32

multiEpStrings = {NAMING_REPEAT: 'Repeat',
                  NAMING_SEPARATED_REPEAT: 'Repeat (Separated)',
                  NAMING_DUPLICATE: 'Duplicate',
                  NAMING_EXTEND: 'Extend',
                  NAMING_LIMITED_EXTEND: 'Extend (Limited)',
                  NAMING_LIMITED_EXTEND_E_PREFIXED: 'Extend (Limited, E-prefixed)'}


class Quality:
    NONE = 0  # 0
    SDTV = 1  # 1
    SDDVD = 1 << 1  # 2
    HDTV = 1 << 2  # 4
    RAWHDTV = 1 << 3  # 8  -- 720p/1080i mpeg2 (trollhd releases)
    FULLHDTV = 1 << 4  # 16 -- 1080p HDTV (QCF releases)
    HDWEBDL = 1 << 5  # 32
    FULLHDWEBDL = 1 << 6  # 64 -- 1080p web-dl
    HDBLURAY = 1 << 7  # 128
    FULLHDBLURAY = 1 << 8  # 256
    # UHD4KTV = 1 << 9 # reserved for the future
    UHD4KWEB = 1 << 10
    # UHD4KBLURAY = 1 << 11 # reserved for the future

    # put these bits at the other end of the spectrum, far enough out that they shouldn't interfere
    UNKNOWN = 1 << 15  # 32768

    qualityStrings = {NONE: 'N/A',
                      UNKNOWN: 'Unknown',
                      SDTV: 'SD TV',
                      SDDVD: 'SD DVD',
                      HDTV: 'HD TV',
                      RAWHDTV: 'RawHD TV',
                      FULLHDTV: '1080p HD TV',
                      HDWEBDL: '720p WEB-DL',
                      FULLHDWEBDL: '1080p WEB-DL',
                      HDBLURAY: '720p BluRay',
                      FULLHDBLURAY: '1080p BluRay',
                      UHD4KWEB: '2160p UHD 4K WEB'}

    statusPrefixes = {DOWNLOADED: 'Downloaded',
                      SNATCHED: 'Snatched',
                      SNATCHED_PROPER: 'Snatched (Proper)',
                      FAILED: 'Failed',
                      SNATCHED_BEST: 'Snatched (Best)'}

    @staticmethod
    def get_quality_css(quality):
        return (Quality.qualityStrings[quality].replace('2160p', 'UHD2160p').replace('1080p', 'HD1080p')
                .replace('720p', 'HD720p').replace('HD TV', 'HD720p').replace('RawHD TV', 'RawHD'))

    @staticmethod
    def _getStatusStrings(status):
        toReturn = {}
        for x in Quality.qualityStrings.keys():
            toReturn[Quality.compositeStatus(status, x)] = '%s (%s)' % (
                Quality.statusPrefixes[status], Quality.qualityStrings[x])
        return toReturn

    @staticmethod
    def combineQualities(anyQualities, bestQualities):
        anyQuality = 0
        bestQuality = 0
        if anyQualities:
            anyQuality = reduce(operator.or_, anyQualities)
        if bestQualities:
            bestQuality = reduce(operator.or_, bestQualities)
        return anyQuality | (bestQuality << 16)

    @staticmethod
    def splitQuality(quality):
        anyQualities = []
        bestQualities = []
        for curQual in Quality.qualityStrings.keys():
            if curQual & quality:
                anyQualities.append(curQual)
            if curQual << 16 & quality:
                bestQualities.append(curQual)

        return sorted(anyQualities), sorted(bestQualities)

    @staticmethod
    def nameQuality(name, anime=False):
        """
        Return The quality from an episode File renamed by SickGear
        If no quality is achieved it will try sceneQuality regex
        """

        name = os.path.basename(name)

        # if we have our exact text then assume we put it there
        for x in sorted(Quality.qualityStrings.keys(), reverse=True):
            if x == Quality.UNKNOWN:
                continue

            if x == Quality.NONE:  # Last chance
                return Quality.sceneQuality(name, anime)

            regex = '\W' + Quality.qualityStrings[x].replace(' ', '\W') + '\W'
            regex_match = re.search(regex, name, re.I)
            if regex_match:
                return x

    @staticmethod
    def sceneQuality(name, anime=False):
        """
        Return The quality from the scene episode File
        """

        name = os.path.basename(name)

        checkName = lambda quality_list, func: func([re.search(x, name, re.I) for x in quality_list])

        if anime:
            dvdOptions = checkName(['dvd', 'dvdrip'], any)
            blueRayOptions = checkName(['bluray', 'blu-ray', 'BD'], any)
            sdOptions = checkName(['360p', '480p', '848x480', 'XviD'], any)
            hdOptions = checkName(['720p', '1280x720', '960x720'], any)
            fullHD = checkName(['1080p', '1920x1080'], any)

            if sdOptions and not blueRayOptions and not dvdOptions:
                return Quality.SDTV
            elif dvdOptions:
                return Quality.SDDVD
            elif hdOptions and not blueRayOptions and not fullHD:
                return Quality.HDTV
            elif fullHD and not blueRayOptions and not hdOptions:
                return Quality.FULLHDTV
            elif hdOptions and not blueRayOptions and not fullHD:
                return Quality.HDWEBDL
            elif blueRayOptions and hdOptions and not fullHD:
                return Quality.HDBLURAY
            elif blueRayOptions and fullHD and not hdOptions:
                return Quality.FULLHDBLURAY
            elif sickbeard.ANIME_TREAT_AS_HDTV:
                logger.log(u'Treating file: %s with "unknown" quality as HDTV per user settings' % name, logger.DEBUG)
                return Quality.HDTV
            else:
                return Quality.UNKNOWN

        if checkName(['(pdtv|hdtv|dsr|tvrip)([-]|.((aac|ac3|dd).?\d\.?\d.)*(xvid|x264|h.?264))'], all) and not checkName(['(720|1080|2160)[pi]'], all) \
                and not checkName(['hr.ws.pdtv.(x264|h.?264)'], any):
            return Quality.SDTV
        elif checkName(['web.?(dl|rip|.[hx]26[45])', 'xvid|x26[45]|.?26[45]'], all) and not checkName(['(720|1080|2160)[pi]'], all):
            return Quality.SDTV
        elif checkName(['(dvd.?rip|b[r|d]rip)(.ws)?(.(xvid|divx|x264|h.?264))?'], any) and not checkName(['(720|1080|2160)[pi]'], all):
            return Quality.SDDVD
        elif checkName(['(xvid|divx|480p)'], any) and not checkName(['(720|1080|2160)[pi]'], all) \
                and not checkName(['hr.ws.pdtv.(x264|h.?264)'], any):
            return Quality.SDTV
        elif checkName(['720p', 'hdtv', 'x264|h.?264'], all) or checkName(['hr.ws.pdtv.(x264|h.?264)'], any) \
                and not checkName(['(1080|2160)[pi]'], all):
            return Quality.HDTV
        elif checkName(['720p|1080i', 'hdtv', 'mpeg-?2'], all) or checkName(['1080[pi].hdtv', 'h.?264'], all):
            return Quality.RAWHDTV
        elif checkName(['1080p', 'hdtv', 'x264'], all):
            return Quality.FULLHDTV
        elif checkName(['720p', 'web.?(dl|rip|.[hx]26[45])'], all) or checkName(['720p', 'itunes', 'x264|h.?264'], all):
            return Quality.HDWEBDL
        elif checkName(['1080p', 'web.?(dl|rip|.[hx]26[45])'], all) or checkName(['1080p', 'itunes', 'x264|h.?264'], all):
            return Quality.FULLHDWEBDL
        elif checkName(['720p', 'blu.?ray|hddvd|b[r|d]rip', 'x264|h.?264'], all):
            return Quality.HDBLURAY
        elif checkName(['1080p', 'blu.?ray|hddvd|b[r|d]rip', 'x264|h.?264'], all) or \
                (checkName(['1080[pi]', 'remux'], all) and not checkName(['hdtv'], all)):
            return Quality.FULLHDBLURAY
        elif checkName(['2160p', 'web.?(dl|rip|.[hx]26[45])'], all):
            return Quality.UHD4KWEB
        else:
            return Quality.UNKNOWN

    @staticmethod
    def fileQuality(filename):

        from sickbeard import encodingKludge as ek
        from sickbeard.exceptions import ex
        if ek.ek(os.path.isfile, filename):

            from hachoir_parser import createParser
            from hachoir_metadata import extractMetadata
            from hachoir_core.stream import InputStreamError

            parser = height = None
            msg = u'Hachoir can\'t parse file "%s" content quality because it found error: %s'
            try:
                parser = ek.ek(createParser, filename)
            except InputStreamError as e:
                logger.log(msg % (filename, e.text), logger.WARNING)
            except Exception as e:
                logger.log(msg % (filename, ex(e)), logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            if parser:
                if '.avi' == filename[-4::].lower():
                    extract = extractMetadata(parser, scan_index=False)
                else:
                    extract = extractMetadata(parser)
                if extract:
                    try:
                        height = extract.get('height')
                    except (AttributeError, ValueError):
                        try:
                            for metadata in extract.iterGroups():
                                if re.search('(?i)video', metadata.header):
                                    height = metadata.get('height')
                                    break
                        except (AttributeError, ValueError):
                            pass

                    parser.stream._input.close()

                    tolerance = lambda value, percent: int(round(value - (value * percent / 100.0)))
                    if height >= tolerance(352, 5):
                        if height <= tolerance(720, 2):
                            return Quality.SDTV
                        return (Quality.HDTV, Quality.FULLHDTV)[height >= tolerance(1080, 1)]
        return Quality.UNKNOWN

    @staticmethod
    def assumeQuality(name):
        if name.lower().endswith(('.avi', '.mp4', '.mkv')):
            return Quality.SDTV
        elif name.lower().endswith('.ts'):
            return Quality.RAWHDTV
        else:
            return Quality.UNKNOWN

    @staticmethod
    def compositeStatus(status, quality):
        return status + 100 * quality

    @staticmethod
    def qualityDownloaded(status):
        return (status - DOWNLOADED) / 100

    @staticmethod
    def splitCompositeStatus(status):
        """Returns a tuple containing (status, quality)"""
        if status == UNKNOWN:
            return UNKNOWN, Quality.UNKNOWN

        for x in sorted(Quality.qualityStrings.keys(), reverse=True):
            if status > x * 100:
                return status - x * 100, x

        return status, Quality.NONE

    @staticmethod
    def statusFromName(name, assume=True, anime=False):
        quality = Quality.nameQuality(name, anime)
        if assume and Quality.UNKNOWN == quality:
            quality = Quality.assumeQuality(name)
        return Quality.compositeStatus(DOWNLOADED, quality)

    @staticmethod
    def statusFromNameOrFile(file_path, assume=True, anime=False):
        quality = Quality.nameQuality(file_path, anime)
        if Quality.UNKNOWN == quality:
            quality = Quality.fileQuality(file_path)
            if assume and Quality.UNKNOWN == quality:
                quality = Quality.assumeQuality(file_path)
        return Quality.compositeStatus(DOWNLOADED, quality)

    DOWNLOADED = None
    SNATCHED = None
    SNATCHED_PROPER = None
    FAILED = None
    SNATCHED_BEST = None


Quality.DOWNLOADED = [Quality.compositeStatus(DOWNLOADED, x) for x in Quality.qualityStrings.keys()]
Quality.SNATCHED = [Quality.compositeStatus(SNATCHED, x) for x in Quality.qualityStrings.keys()]
Quality.SNATCHED_PROPER = [Quality.compositeStatus(SNATCHED_PROPER, x) for x in Quality.qualityStrings.keys()]
Quality.FAILED = [Quality.compositeStatus(FAILED, x) for x in Quality.qualityStrings.keys()]
Quality.SNATCHED_BEST = [Quality.compositeStatus(SNATCHED_BEST, x) for x in Quality.qualityStrings.keys()]

SD = Quality.combineQualities([Quality.SDTV, Quality.SDDVD], [])
HD = Quality.combineQualities(
    [Quality.HDTV, Quality.FULLHDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.HDBLURAY, Quality.FULLHDBLURAY],
    [])  # HD720p + HD1080p
HD720p = Quality.combineQualities([Quality.HDTV, Quality.HDWEBDL, Quality.HDBLURAY], [])
HD1080p = Quality.combineQualities([Quality.FULLHDTV, Quality.FULLHDWEBDL, Quality.FULLHDBLURAY], [])
UHD2160p = Quality.combineQualities([Quality.UHD4KWEB], [])
ANY = Quality.combineQualities(
    [Quality.SDTV, Quality.SDDVD, Quality.HDTV, Quality.FULLHDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL,
     Quality.HDBLURAY, Quality.FULLHDBLURAY, Quality.UNKNOWN], [])  # SD + HD

# legacy template, cant remove due to reference in mainDB upgrade?
BEST = Quality.combineQualities([Quality.SDTV, Quality.HDTV, Quality.HDWEBDL], [Quality.HDTV])

qualityPresets = (SD, HD, HD720p, HD1080p, UHD2160p, ANY)

qualityPresetStrings = {SD: 'SD',
                        HD: 'HD',
                        HD720p: 'HD720p',
                        HD1080p: 'HD1080p',
                        UHD2160p: 'UHD2160p',
                        ANY: 'Any'}


class StatusStrings:
    def __init__(self):
        self.statusStrings = {UNKNOWN: 'Unknown',
                              UNAIRED: 'Unaired',
                              SNATCHED: 'Snatched',
                              DOWNLOADED: 'Downloaded',
                              SKIPPED: 'Skipped',
                              SNATCHED_PROPER: 'Snatched (Proper)',
                              WANTED: 'Wanted',
                              ARCHIVED: 'Archived',
                              IGNORED: 'Ignored',
                              SUBTITLED: 'Subtitled',
                              FAILED: 'Failed',
                              SNATCHED_BEST: 'Snatched (Best)'}

    def __getitem__(self, name):
        if name in Quality.DOWNLOADED + Quality.SNATCHED + Quality.SNATCHED_PROPER + Quality.SNATCHED_BEST:
            status, quality = Quality.splitCompositeStatus(name)
            if quality == Quality.NONE:
                return self.statusStrings[status]
            else:
                return '%s (%s)' % (self.statusStrings[status], Quality.qualityStrings[quality])
        else:
            return self.statusStrings[name] if self.statusStrings.has_key(name) else ''

    def has_key(self, name):
        return name in self.statusStrings or name in Quality.DOWNLOADED or name in Quality.SNATCHED \
            or name in Quality.SNATCHED_PROPER or name in Quality.SNATCHED_BEST


statusStrings = StatusStrings()


class Overview:
    UNAIRED = UNAIRED  # 1
    QUAL = 2
    WANTED = WANTED  # 3
    GOOD = 4
    SKIPPED = SKIPPED  # 5

    # For both snatched statuses. Note: SNATCHED/QUAL have same value and break dict.
    SNATCHED = SNATCHED_PROPER = SNATCHED_BEST  # 9

    overviewStrings = {UNKNOWN: 'unknown',
                       SKIPPED: 'skipped',
                       WANTED: 'wanted',
                       QUAL: 'qual',
                       GOOD: 'good',
                       UNAIRED: 'unaired',
                       SNATCHED: 'snatched'}

countryList = {'Australia': 'AU',
               'Canada': 'CA',
               'USA': 'US'}
