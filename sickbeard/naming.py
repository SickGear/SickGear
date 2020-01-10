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

import datetime
import os

import sickbeard
from . import common, logger, tv
from .common import Quality, DOWNLOADED
from .name_parser.parser import NameParser

# noinspection PyPep8Naming
import encodingKludge as ek

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, List

name_presets = (
    '%SN - %Sx%0E - %EN',
    '%S.N.S%0SE%0E.%E.N',
    '%Sx%0E - %EN',
    'S%0SE%0E - %EN',
    'Season %0S/%S.N.S%0SE%0E.%Q.N-%RG'
)

name_anime_presets = name_presets

name_abd_presets = (
    '%SN - %A-D - %EN',
    '%S.N.%A.D.%E.N.%Q.N',
    '%Y/%0M/%S.N.%A.D.%E.N-%RG'
)

name_sports_presets = (
    '%SN - %A-D - %EN',
    '%S.N.%A.D.%E.N.%Q.N',
    '%Y/%0M/%S.N.%A.D.%E.N-%RG'
)


class TVShowSample(object):
    def __init__(self):
        self.name = 'Show Name'  # type: AnyStr
        self.genre = 'Comedy'  # type: AnyStr
        self.tvid = 1  # type: int
        self.prodid = 1  # type: int
        self.air_by_date = 0  # type: int
        self.sports = 0  # type: int or bool
        self.anime = 0  # type: int or bool
        self.scene = 0  # type: int or bool

    def _is_anime(self):
        """
        :rtype: bool
        """
        return 0 < self.anime

    is_anime = property(_is_anime)  # type: bool

    def _is_sports(self):
        """
        :rtype: bool
        """
        return 0 < self.sports

    is_sports = property(_is_sports)  # type: bool

    def _is_scene(self):
        """
        :rtype: bool
        """
        return 0 < self.scene

    is_scene = property(_is_scene)  # type: bool


class TVEpisodeSample(tv.TVEpisode):
    # noinspection PyMissingConstructor
    def __init__(self, season, episode, absolute_number, name):
        """

        :param season: season number
        :type season: int
        :param episode: episode number
        :type episode: int
        :param absolute_number: absolute number
        :type absolute_number: int
        :param name: name
        :type name: AnyStr
        """
        self.related_ep_obj = []  # type: List
        self._name = name  # type: AnyStr
        self._season = season  # type: int
        self._episode = episode  # type: int
        self._absolute_number = absolute_number  # type: int
        self.scene_season = season  # type: int
        self.scene_episode = episode  # type: int
        self.scene_absolute_number = absolute_number  # type: int
        self._airdate = datetime.date(2010, 3, 9)  # type: datetime.date
        self.show_obj = TVShowSample()  # type: TVShowSample
        self._status = Quality.compositeStatus(common.DOWNLOADED, common.Quality.SDTV)  # type: int
        self._release_name = 'Show.Name.S02E03.HDTV.XviD-RLSGROUP'  # type: AnyStr
        self._is_proper = True  # type: bool
        self._version = 2  # type: int


def check_force_season_folders(pattern=None, multi=None, anime_type=None):
    """
    Checks if the name can still be parsed if you strip off the folders to determine if we need to force season folders
    to be enabled or not.

    Returns true if season folders need to be forced on or false otherwise.
    :param pattern: String Naming Pattern
    :type pattern: AnyStr or None
    :param multi: Bool Multi-episode pattern
    :type multi: bool or None
    :param anime_type: Integer Numbering type to use for anime pattern
    :type anime_type: int or None
    :return:
    :rtype: bool
    """
    if None is pattern:
        pattern = sickbeard.NAMING_PATTERN

    if None is anime_type:
        anime_type = sickbeard.NAMING_ANIME

    valid = not validate_name(pattern, None, anime_type, file_only=True)

    if None is not multi:
        valid = valid or not validate_name(pattern, multi, anime_type, file_only=True)

    return valid


def check_valid_naming(pattern=None, multi=None, anime_type=None):
    """
    Checks if the name is can be parsed back to its original form for both single and multi episodes.

    Returns true if the naming is valid, false if not.
    :param pattern: String Naming Pattern
    :type pattern: AnyStr or None
    :param multi: Bool Multi-episode pattern
    :type multi: bool or None
    :param anime_type: Integer Numbering type to use for anime pattern
    :type anime_type: int or None
    :return:
    :rtype: bool
    """
    if None is pattern:
        pattern = sickbeard.NAMING_PATTERN

    if None is anime_type:
        anime_type = sickbeard.NAMING_ANIME

    logger.log(u'Checking whether the pattern %s is valid for a single episode' % pattern, logger.DEBUG)
    valid = validate_name(pattern, None, anime_type)

    if None is not multi:
        logger.log(u'Checking whether the pattern %s is valid for a multi episode' % pattern, logger.DEBUG)
        valid = valid and validate_name(pattern, multi, anime_type)

    return valid


def check_valid_abd_naming(pattern=None):
    """
    Checks if the name is can be parsed back to its original form for an air-by-date format.

    Returns true if the naming is valid, false if not.
    :param pattern: String Naming Pattern
    :type pattern: AnyStr or None
    :return:
    :rtype: bool
    """
    if None is pattern:
        pattern = sickbeard.NAMING_PATTERN

    logger.log(u'Checking whether the pattern %s is valid for an air-by-date episode' % pattern, logger.DEBUG)
    valid = validate_name(pattern, abd=True)

    return valid


def check_valid_sports_naming(pattern=None):
    """
    Checks if the name is can be parsed back to its original form for an sports format.

    Returns true if the naming is valid, false if not.
    :param pattern: String Naming Pattern
    :type pattern: AnyStr or None
    :return:
    :rtype: bool
    """
    if None is pattern:
        pattern = sickbeard.NAMING_PATTERN

    logger.log(u'Checking whether the pattern %s is valid for an sports episode' % pattern, logger.DEBUG)
    valid = validate_name(pattern, sports=True)

    return valid


def validate_name(pattern, multi=None, anime_type=None, file_only=False, abd=False, sports=False):
    """

    :param pattern:
    :type pattern: AnyStr or None
    :param multi:
    :type multi: bool or None
    :param anime_type:
    :type anime_type: int or None
    :param file_only:
    :type file_only: bool
    :param abd:
    :type abd: bool
    :param sports:
    :type sports: bool
    :return:
    :rtype: bool
    """
    sample_ep_obj = generate_sample_ep(multi, abd, sports, anime_type=anime_type)

    new_name = u'%s.ext' % sample_ep_obj.formatted_filename(pattern, multi, anime_type)
    new_path = sample_ep_obj.formatted_dir(pattern, multi)
    if not file_only:
        new_name = ek.ek(os.path.join, new_path, new_name)

    if not new_name:
        logger.log(u'Unable to create a name out of %s' % pattern, logger.DEBUG)
        return False

    logger.log(u'Trying to parse %s' % new_name, logger.DEBUG)

    parser = NameParser(True, show_obj=sample_ep_obj.show_obj, naming_pattern=True)

    try:
        result = parser.parse(new_name)
    except (BaseException, Exception):
        logger.log(u'Unable to parse %s, not valid' % new_name, logger.DEBUG)
        return False

    logger.log(u'The name %s parsed into %s' % (new_name, result), logger.DEBUG)

    if abd or sports:
        if result.air_date != sample_ep_obj.airdate:
            logger.log(u'Air date incorrect in parsed episode, pattern isn\'t valid', logger.DEBUG)
            return False
    elif 3 == anime_type:
        if result.season_number != sample_ep_obj.season:
            logger.log(u'Season number incorrect in parsed episode, pattern isn\'t valid', logger.DEBUG)
            return False
        if result.episode_numbers != [x.episode for x in [sample_ep_obj] + sample_ep_obj.related_ep_obj]:
            logger.log(u'Episode numbering incorrect in parsed episode, pattern isn\'t valid', logger.DEBUG)
            return False
    else:
        if len(result.ab_episode_numbers) \
                and result.ab_episode_numbers != [x.absolute_number
                                                  for x in [sample_ep_obj] + sample_ep_obj.related_ep_obj]:
            logger.log(u'Absolute numbering incorrect in parsed episode, pattern isn\'t valid', logger.DEBUG)
            return False

    return True


def generate_sample_ep(multi=None, abd=False, sports=False, anime=False, anime_type=None):
    """

    :param multi:
    :type multi: None or bool
    :param abd:
    :type abd: bool
    :param sports:
    :type sports: bool
    :param anime:
    :type anime: bool
    :param anime_type:
    :type anime_type: int or None
    :return:
    :rtype: TVEpisodeSample
    """
    # make a fake episode object
    sample_ep_obj = TVEpisodeSample(2, 3, 3, 'Ep Name')

    sample_ep_obj._status = Quality.compositeStatus(DOWNLOADED, Quality.HDTV)
    sample_ep_obj._airdate = datetime.date(2011, 3, 9)

    if abd:
        sample_ep_obj._release_name = 'Show.Name.2011.03.09.HDTV.XviD-RLSGROUP'
        sample_ep_obj.show_obj.air_by_date = 1
    elif sports:
        sample_ep_obj._release_name = 'Show.Name.2011.03.09.HDTV.XviD-RLSGROUP'
        sample_ep_obj.show_obj.sports = 1
    else:
        if not anime or 3 == anime_type:
            sample_ep_obj._release_name = 'Show.Name.S02E03.HDTV.XviD-RLSGROUP'
        else:
            sample_ep_obj._release_name = 'Show.Name.003.HDTV.XviD-RLSGROUP'
            sample_ep_obj.show_obj.anime = 1

    if None is not multi:
        sample_ep_obj._name = 'Ep Name (1)'
        second_ep = TVEpisodeSample(2, 4, 4, 'Ep Name (2)')
        second_ep._status = Quality.compositeStatus(DOWNLOADED, Quality.HDTV)
        normal_naming = not anime or 3 == anime_type
        release_name = sample_ep_obj._release_name = second_ep._release_name = \
            ('Show.Name.003-004.HDTV.XviD-RLSGROUP', 'Show.Name.S02E03E04E05.HDTV.XviD-RLSGROUP')[normal_naming]
        sample_ep_obj.related_ep_obj.append(second_ep)
        if normal_naming:
            third_ep = TVEpisodeSample(2, 5, 5, 'Ep Name (3)')
            third_ep._status = Quality.compositeStatus(DOWNLOADED, Quality.HDTV)
            third_ep._release_name = release_name
            sample_ep_obj.related_ep_obj.append(third_ep)
        else:
            sample_ep_obj.show_obj.anime = 1

    return sample_ep_obj


def test_name(pattern, multi=None, abd=False, sports=False, anime=False, anime_type=None):
    """

    :param pattern:
    :type pattern: AnyStr or None
    :param multi:
    :type multi: bool or None
    :param abd:
    :type abd: bool
    :param sports:
    :type sports: bool
    :param anime:
    :type anime: bool
    :param anime_type:
    :type anime_type: int or None
    :return:
    :rtype: Dict[AnyStr, AnyStr]
    """
    sample_ep_obj = generate_sample_ep(multi, abd, sports, anime, anime_type)

    return {'name': sample_ep_obj.formatted_filename(pattern, multi, anime_type),
            'dir': sample_ep_obj.formatted_dir(pattern, multi)}
