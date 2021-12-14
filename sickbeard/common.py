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
from __future__ import division

from functools import reduce
import operator
import os.path
import platform
import re
import traceback
import uuid

import sickbeard

from _23 import map_list
from six import integer_types, iterkeys, string_types

# noinspection PyUnresolvedReferences
# noinspection PyUnreachableCode
if False:
    from typing import List, Tuple

try:
    INSTANCE_ID = str(uuid.uuid1())
except ValueError:
    INSTANCE_ID = str(uuid.uuid4())

USER_AGENT = ('SickGear/(%s; %s; %s)' % (platform.system(), platform.release(), INSTANCE_ID))

mediaExtensions = ['avi', 'mkv', 'mpg', 'mpeg', 'wmv', 'ogm', 'mp4', 'iso', 'img', 'divx', 'm2ts', 'm4v', 'ts', 'flv',
                   'f4v', 'mov', 'rmvb', 'vob', 'dvr-ms', 'wtv', 'ogv', '3gp', 'webm']

subtitleExtensions = ['srt', 'sub', 'ass', 'idx', 'ssa']

cpu_presets = {'DISABLED': 0, 'LOW': 0.01, 'NORMAL': 0.05, 'HIGH': 0.1}

# Other constants
MULTI_EP_RESULT = -1
SEASON_RESULT = -2

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
SNATCHED_ANY = [SNATCHED, SNATCHED_PROPER, SNATCHED_BEST]

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


class Quality(object):
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

    real_check = r'\breal\b\W?' \
                 r'(?=proper|repack|e?ac3|aac|dts|read\Wnfo|(ws\W)?[ph]dtv|(ws\W)?dsr|web|dvd|blu|\d{2,3}0([pi]))' \
                 r'(?!.*\d+([ex])\d+)'

    proper_levels = [(re.compile(r'\brepack\b(?!.*\d+([ex])\d+)', flags=re.I), True),
                     (re.compile(r'\bproper\b(?!.*\d+([ex])\d+)', flags=re.I), False),
                     (re.compile(real_check, flags=re.I), False)]

    @staticmethod
    def get_proper_level(extra_no_name, version, is_anime=False, check_is_repack=False):
        """

        :param extra_no_name: extra info
        :type extra_no_name: AnyStr
        :param version: version
        :type version: int
        :param is_anime: is anime
        :type is_anime: bool
        :param check_is_repack: check for repack
        :type check_is_repack: bool
        :return: proper level or tuple of is_repack, proper level
        :rtype: int or Tuple[bool, int]
        """
        level = 0
        is_repack = False
        if is_anime:
            if isinstance(version, integer_types):
                level = (0, version - 1)[1 < version]
        elif isinstance(extra_no_name, string_types):
            for p, r_check in Quality.proper_levels:
                a = len(p.findall(extra_no_name))
                level += a
                if 0 < a and r_check:
                    is_repack = True
        if check_is_repack:
            return is_repack, level
        return level

    @staticmethod
    def get_quality_css(quality):
        """

        :param quality: quality
        :type quality: int
        :return:
        :rtype: AnyStr
        """
        return (Quality.qualityStrings[quality].replace('2160p', 'UHD2160p').replace('1080p', 'HD1080p')
                .replace('720p', 'HD720p').replace('HD TV', 'HD720p').replace('RawHD TV', 'RawHD'))

    @staticmethod
    def get_quality_ui(quality):
        """

        :param quality: quality
        :type quality: int
        :return:
        :rtype: AnyStr
        """
        return Quality.qualityStrings[quality].replace('SD DVD', 'SD DVD/BR/BD')

    @staticmethod
    def _getStatusStrings(status):
        """

        :param status: status
        :type status: int
        :return:
        :rtype: AnyStr
        """
        toReturn = {}
        for _x in Quality.qualityStrings:
            toReturn[Quality.compositeStatus(status, _x)] = '%s (%s)' % (
                Quality.statusPrefixes[status], Quality.qualityStrings[_x])
        return toReturn

    @staticmethod
    def combineQualities(any_qualities, best_qualities):
        # type: (List[int], List[int]) -> int
        """

        :param any_qualities: any qualities
        :param best_qualities: best qualities
        """
        any_quality = 0
        best_quality = 0
        if any_qualities:
            any_quality = reduce(operator.or_, any_qualities)
        if best_qualities:
            best_quality = reduce(operator.or_, best_qualities)
        return any_quality | (best_quality << 16)

    @staticmethod
    def splitQuality(quality):
        # type: (int) -> Tuple[List[int], List[int]]
        """

        :param quality: show quality
        """
        any_qualities = []
        best_qualities = []
        for cur_quality in Quality.qualityStrings:
            if cur_quality & quality:
                any_qualities.append(cur_quality)
            if cur_quality << 16 & quality:
                best_qualities.append(cur_quality)

        return sorted(any_qualities), sorted(best_qualities)

    @staticmethod
    def nameQuality(name, anime=False):
        """
        Return The quality from an episode File renamed by SickGear
        If no quality is achieved it will try sceneQuality regex
        :param name: name
        :type name: AnyStr
        :param anime: is anmie
        :type anime: bool
        :return:
        :rtype: int
        """

        # noinspection PyPep8Naming
        import encodingKludge as ek
        name = ek.ek(os.path.basename, name)

        # if we have our exact text then assume we put it there
        for _x in sorted(iterkeys(Quality.qualityStrings), reverse=True):
            if Quality.UNKNOWN == _x:
                continue

            if Quality.NONE == _x:  # Last chance
                return Quality.sceneQuality(name, anime)

            regex = r'\W' + Quality.qualityStrings[_x].replace(' ', r'\W') + r'\W'
            regex_match = re.search(regex, name, re.I)
            if regex_match:
                return _x

    @staticmethod
    def sceneQuality(name, anime=False):
        """
        Return The quality from the scene episode File
        :param name: name
        :type name: AnyStr
        :param anime: is anmie
        :type anime: bool
        :return:
        :rtype: int
        """
        # noinspection PyPep8Naming
        import encodingKludge as ek
        from sickbeard import logger
        name = ek.ek(os.path.basename, name)

        name_has = (lambda quality_list, func=all: func([re.search(q, name, re.I) for q in quality_list]))

        if anime:
            sd_options = name_has(['360p', '480p', '848x480', 'XviD'], any)
            sd_options |= name_has([r'^SD\.|\.SD$'], any)  # specific to a provider
            dvd_options = name_has(['dvd', 'dvdrip'], any)
            blue_ray_options = name_has(['bluray', 'blu-ray', 'BD'], any)

            if sd_options and not dvd_options and not blue_ray_options:
                return Quality.SDTV
            if dvd_options:
                return Quality.SDDVD

            hd_options = name_has(['720p', r'\[720\]', '1280x720', '960x720'], any)
            hd_options |= name_has([r'^HD\s*720\.|\.HD\s*720$'], any)  # specific to a provider
            full_hd = name_has(['1080p', r'\[1080\]', '1920x1080'], any)
            full_hd |= name_has([r'^HD(\s*1080)?\.|\.HD(\s*1080)?$'], any)  # specific to a provider
            if not blue_ray_options:
                if hd_options and not full_hd:
                    return Quality.HDTV
                if not hd_options and full_hd:
                    return Quality.FULLHDTV
                # this cond already checked above, commented out for now
                # if hd_options and not full_hd:
                #     return Quality.HDWEBDL
            else:
                if hd_options and not full_hd:
                    return Quality.HDBLURAY
                if not hd_options and full_hd:
                    return Quality.FULLHDBLURAY
            if sickbeard.ANIME_TREAT_AS_HDTV:
                logger.log(u'Treating file: %s with "unknown" quality as HDTV per user settings' % name, logger.DEBUG)
                return Quality.HDTV
            return Quality.UNKNOWN

        fmt = '((h.?|x)26[45]|vp9|av1|hevc)'
        webfmt = 'web.?(dl|rip|.%s)' % fmt
        rips = 'b[r|d]rip'
        hd_rips = 'blu.?ray|hddvd|%s' % rips

        if not name_has(['(720|1080|2160)[pi]|720hd']):
            if name_has(['(dvd.?rip|%s)(.ws)?(.(xvid|divx|%s))?' % (rips, fmt)]):
                return Quality.SDDVD
            if (not name_has(['hr.ws.pdtv.(h.?|x)264'])
                and (name_has([r'(hdtv|pdtv|dsr|tvrip)([-]|.((aac|ac3|dd).?\d\.?\d.)*(xvid|%s))' % fmt])
                     or name_has(['(xvid|divx|480p|hevc|x265)']))) \
                    or name_has([webfmt, 'xvid|%s' % fmt]):
                return Quality.SDTV

        if not name_has(['(1080|2160)[pi]']):
            if name_has(['720p']):
                if name_has([hd_rips, fmt]):
                    return Quality.HDBLURAY
                if name_has([webfmt]) or name_has(['itunes', fmt]):
                    return Quality.HDWEBDL
                if name_has([fmt]):
                    return Quality.HDTV
            # p2p
            if name_has(['720hd']) \
                    or name_has(['hr.ws.pdtv.%s' % fmt]):
                return Quality.HDTV
        if name_has(['720p|1080i', 'hdtv', 'mpeg-?2']) or name_has(['1080[pi].hdtv', 'h.?264']):
            return Quality.RAWHDTV
        if name_has(['1080[pi]', 'remux']) and not name_has(['hdtv']):
            return Quality.FULLHDBLURAY
        if name_has(['1080p']):
            if name_has([hd_rips, fmt]) or name_has([hd_rips, 'avc|vc[ -.]?1']):
                return Quality.FULLHDBLURAY
            if name_has([webfmt]) or name_has(['itunes', fmt]):
                return Quality.FULLHDWEBDL
            if name_has([fmt]):
                return Quality.FULLHDTV
        if name_has(['2160p', webfmt]):
            return Quality.UHD4KWEB

        return Quality.UNKNOWN

    @staticmethod
    def fileQuality(filename):
        """

        :param filename: filename
        :type filename: AnyStr
        :return:
        :rtype: int
        """
        # noinspection PyPep8Naming
        import encodingKludge as ek
        from exceptions_helper import ex
        from sickbeard import logger
        if ek.ek(os.path.isfile, filename):

            from hachoir.parser import createParser
            from hachoir.metadata import extractMetadata
            from hachoir.stream import InputStreamError

            parser = height = None
            msg = 'Hachoir can\'t parse file "%s" content quality because it found error: %s'
            try:
                parser = ek.ek(createParser, filename)
            except InputStreamError as e:
                logger.log(msg % (filename, ex(e)), logger.WARNING)
            except (BaseException, Exception) as e:
                logger.log(msg % (filename, ex(e)), logger.ERROR)
                logger.log(traceback.format_exc(), logger.ERROR)

            if parser:
                extract = None
                try:
                    args = ({}, {'scan_index': False})['.avi' == filename[-4::].lower()]
                    parser.parse_exif = False
                    parser.parse_photoshop_content = False
                    parser.parse_comments = False
                    extract = extractMetadata(parser, **args)
                except (BaseException, Exception) as e:
                    logger.log(msg % (filename, ex(e)), logger.WARNING)
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

                    # noinspection PyProtectedMember
                    parser.stream._input.close()

                    tolerance = (lambda value, percent: int(round(value - (value * percent / 100.0))))
                    if None is not height and height >= tolerance(352, 5):
                        if height <= tolerance(720, 2):
                            return Quality.SDTV
                        return (Quality.HDTV, Quality.FULLHDTV)[height >= tolerance(1080, 1)]
        return Quality.UNKNOWN

    @staticmethod
    def assumeQuality(name):
        """

        :param name: name
        :type name: AnyStr
        :return:
        :rtype: int
        """
        if name.lower().endswith(('.avi', '.mp4', '.mkv')):
            return Quality.SDTV
        elif name.lower().endswith('.ts'):
            return Quality.RAWHDTV
        return Quality.UNKNOWN

    @staticmethod
    def compositeStatus(status, quality):
        """

        :param status: status
        :type status: int
        :param quality: quality
        :type quality: int
        :return:
        :rtype: int or long
        """
        return status + 100 * quality

    @staticmethod
    def qualityDownloaded(status):
        # type: (int) -> int
        """

        :param status: status
        :type status: int or long
        :return:
        :rtype: int or long
        """
        return (status - DOWNLOADED) // 100

    @staticmethod
    def splitCompositeStatus(status):
        # type: (int) -> Tuple[int, int]
        """Returns a tuple containing (status, quality)
        :param status: status
        """
        if UNKNOWN == status:
            return UNKNOWN, Quality.UNKNOWN

        for q in sorted(iterkeys(Quality.qualityStrings), reverse=True):
            if status > q * 100:
                return status - q * 100, q

        return status, Quality.NONE

    @staticmethod
    def statusFromName(name, assume=True, anime=False):
        """

        :param name: name
        :type name: AnyStr
        :param assume:
        :type assume: bool
        :param anime: is anime
        :type anime: bool
        :return:
        :rtype: int or long
        """
        quality = Quality.nameQuality(name, anime)
        if assume and Quality.UNKNOWN == quality:
            quality = Quality.assumeQuality(name)
        return Quality.compositeStatus(DOWNLOADED, quality)

    @staticmethod
    def statusFromNameOrFile(file_path, assume=True, anime=False):
        """

        :param file_path: file path
        :type file_path: AnyStr
        :param assume:
        :type assume: bool
        :param anime: is anime
        :type anime: bool
        :return:
        :rtype: int or long
        """
        quality = Quality.nameQuality(file_path, anime)
        if Quality.UNKNOWN == quality:
            quality = Quality.fileQuality(file_path)
            if assume and Quality.UNKNOWN == quality:
                quality = Quality.assumeQuality(file_path)
        return Quality.compositeStatus(DOWNLOADED, quality)

    SNATCHED = None
    SNATCHED_PROPER = None
    SNATCHED_BEST = None
    SNATCHED_ANY = None
    DOWNLOADED = None
    ARCHIVED = None
    FAILED = None


class WantedQualities(dict):
    wantedlist = 1
    bothlists = 2
    upgradelist = 3

    def __init__(self, **kwargs):
        super(WantedQualities, self).__init__(**kwargs)

    def _generate_wantedlist(self, qualities):
        initial_qualities, upgrade_qualities = Quality.splitQuality(qualities)
        max_initial_quality = max(initial_qualities or [Quality.NONE])
        min_upgrade_quality = min(upgrade_qualities or [1 << 16])
        self[qualities] = {0: {self.bothlists: False, self.wantedlist: initial_qualities, self.upgradelist: False}}
        for q in Quality.qualityStrings:
            if 0 < q:
                self[qualities][q] = {self.wantedlist: [i for i in upgrade_qualities if q < i], self.upgradelist: False}
                if q not in upgrade_qualities and q in initial_qualities:
                    # quality is only in initial_qualities
                    w = {self.bothlists: False}
                elif q in upgrade_qualities and q in initial_qualities:
                    # quality is in initial_qualities and upgrade_qualities
                    w = {self.bothlists: True, self.upgradelist: True}
                elif q in upgrade_qualities:
                    # quality is only in upgrade_qualities
                    w = {self.bothlists: False, self.upgradelist: True}
                else:
                    # quality is not in any selected quality for the show (known as "unwanted")
                    w = {self.bothlists: max_initial_quality >= q >= min_upgrade_quality}
                self[qualities][q].update(w)

    def __getitem__(self, k):
        if k not in self:
            self._generate_wantedlist(k)
        return super(WantedQualities, self).__getitem__(k)

    def get(self, k, *args, **kwargs):
        if k not in self:
            self._generate_wantedlist(k)
        return super(WantedQualities, self).get(k, *args, **kwargs)

    def get_wantedlist(self, qualities, upgradeonce, quality, status, unaired=False, manual=False):
        if not manual:
            if status in [ARCHIVED, IGNORED, SKIPPED] + ([UNAIRED], [])[unaired]:
                return []
            if upgradeonce:
                if status == SNATCHED_BEST or \
                        (not self[qualities][quality][self.bothlists] and self[qualities][quality][self.upgradelist] and
                         status in (DOWNLOADED, SNATCHED, SNATCHED_BEST, SNATCHED_PROPER)):
                    return []
        return self[qualities][quality][self.wantedlist]


for (attr_name, qual_val) in [
    ('SNATCHED', SNATCHED), ('SNATCHED_PROPER', SNATCHED_PROPER), ('SNATCHED_BEST', SNATCHED_BEST),
    ('DOWNLOADED', DOWNLOADED), ('ARCHIVED', ARCHIVED), ('FAILED', FAILED),
]:
    setattr(Quality, attr_name, map_list(lambda qk: Quality.compositeStatus(qual_val, qk),
                                         iterkeys(Quality.qualityStrings)))
Quality.SNATCHED_ANY = Quality.SNATCHED + Quality.SNATCHED_PROPER + Quality.SNATCHED_BEST

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


class StatusStrings(object):
    def __init__(self):
        self.statusStrings = {UNKNOWN: 'Unknown',
                              UNAIRED: 'Unaired',
                              SNATCHED: 'Snatched',
                              SNATCHED_PROPER: 'Snatched (Proper)',
                              SNATCHED_BEST: 'Snatched (Best)',
                              DOWNLOADED: 'Downloaded',
                              ARCHIVED: 'Archived',
                              SKIPPED: 'Skipped',
                              WANTED: 'Wanted',
                              IGNORED: 'Ignored',
                              SUBTITLED: 'Subtitled',
                              FAILED: 'Failed'}

    def __getitem__(self, name):
        if name in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED:
            status, quality = Quality.splitCompositeStatus(name)
            if quality == Quality.NONE:
                return self.statusStrings[status]
            return '%s (%s)' % (self.statusStrings[status], Quality.qualityStrings[quality])
        return self.statusStrings[name] if name in self.statusStrings else ''

    def __contains__(self, item):
        return item in self.statusStrings or item in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED


statusStrings = StatusStrings()


class Overview(object):
    UNAIRED = UNAIRED  # 1
    QUAL = 2
    WANTED = WANTED  # 3
    GOOD = 4
    SKIPPED = SKIPPED  # 5

    # For both snatched statuses. Note: SNATCHED/QUAL have same value and break dict.
    SNATCHED = SNATCHED_PROPER = SNATCHED_BEST  # 9

    SNATCHED_QUAL = 15

    overviewStrings = {UNKNOWN: 'unknown',
                       SKIPPED: 'skipped',
                       WANTED: 'wanted',
                       QUAL: 'qual',
                       GOOD: 'good',
                       UNAIRED: 'unaired',
                       SNATCHED: 'snatched',
                       SNATCHED_QUAL: 'snatched/qual'}


countryList = {'Australia': 'AU',
               'Canada': 'CA',
               'USA': 'US'}


class NeededQualities(object):
    def __init__(self, need_anime=False, need_sports=False, need_sd=False, need_hd=False, need_uhd=False,
                 need_webdl=False, need_all_qualities=False, need_all_types=False, need_all=False):
        self.need_anime = need_anime or need_all_types or need_all
        self.need_sports = need_sports or need_all_types or need_all
        self.need_sd = need_sd or need_all_qualities or need_all
        self.need_hd = need_hd or need_all_qualities or need_all
        self.need_uhd = need_uhd or need_all_qualities or need_all
        self.need_webdl = need_webdl or need_all_qualities or need_all

    max_sd = Quality.SDDVD
    hd_qualities = [Quality.HDTV, Quality.FULLHDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL,
                    Quality.HDBLURAY, Quality.FULLHDBLURAY]
    webdl_qualities = [Quality.SDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB]
    max_hd = Quality.FULLHDBLURAY

    @property
    def all_needed(self):
        """
        :rtype: bool
        """
        return self.all_qualities_needed and self.all_types_needed

    @property
    def all_types_needed(self):
        """
        :rtype: bool
        """
        return self.need_anime and self.need_sports

    @property
    def all_qualities_needed(self):
        """
        :rtype: bool
        """
        return self.need_sd and self.need_hd and self.need_uhd and self.need_webdl

    @all_qualities_needed.setter
    def all_qualities_needed(self, v):
        """
        :param v:
        :type v: bool
        """
        if isinstance(v, bool) and True is v:
            self.need_sd = self.need_hd = self.need_uhd = self.need_webdl = True

    def all_show_qualities_needed(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        :return:
        :rtype: bool
        """
        from sickbeard.tv import TVShow
        if isinstance(show_obj, TVShow):
            init, upgrade = Quality.splitQuality(show_obj.quality)
            all_qual = set(init + upgrade)
            need_sd = need_hd = need_uhd = need_webdl = False
            for wanted_qualities in all_qual:
                if not need_sd and wanted_qualities <= NeededQualities.max_sd:
                    need_sd = True
                if not need_hd and wanted_qualities in NeededQualities.hd_qualities:
                    need_hd = True
                if not need_webdl and wanted_qualities in NeededQualities.webdl_qualities:
                    need_webdl = True
                if not need_uhd and wanted_qualities > NeededQualities.max_hd:
                    need_uhd = True
            return self.need_sd == need_sd and self.need_hd == need_hd and self.need_webdl == need_webdl and \
                self.need_uhd == need_uhd

    def check_needed_types(self, show_obj):
        """

        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow
        """
        if getattr(show_obj, 'is_anime', False):
            self.need_anime = True
        if getattr(show_obj, 'is_sports', False):
            self.need_sports = True

    def check_needed_qualities(self, wanted_qualities):
        # type: (List[int]) -> None
        """

        :param wanted_qualities: wanted qualities list
        """
        if wanted_qualities:
            if Quality.UNKNOWN in wanted_qualities:
                self.need_sd = self.need_hd = self.need_uhd = self.need_webdl = True
            else:
                if not self.need_sd and min(wanted_qualities) <= NeededQualities.max_sd:
                    self.need_sd = True
                if not self.need_hd and any([i in NeededQualities.hd_qualities for i in wanted_qualities]):
                    self.need_hd = True
                if not self.need_webdl and any([i in NeededQualities.webdl_qualities for i in wanted_qualities]):
                    self.need_webdl = True
                if not self.need_uhd and max(wanted_qualities) > NeededQualities.max_hd:
                    self.need_uhd = True
