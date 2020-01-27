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

import sickbeard
from . import logger
from ._legacy_classes import LegacyTVShow, LegacyTVEpisode
from .common import UNKNOWN
from .name_cache import buildNameCache

from six import string_types

# noinspection PyUnreachableCode
if False:
    from typing import Text


class TVBase(object):
    def __init__(self):

        self.dirty = True

    @staticmethod
    def dirty_setter(attr_name, types=None):
        def wrapper(self, val):
            if getattr(self, attr_name) != val:
                if None is types or isinstance(val, types):
                    setattr(self, attr_name, val)
                    self.dirty = True
                else:
                    logger.log('Didn\'t change property "%s" because expected: %s, but got: %s with value: %s' %
                               (attr_name, types, type(val), val), logger.WARNING)

        return wrapper

    @staticmethod
    def dict_prevent_nonetype(d, key, default=''):
        v = getattr(d, key, default)
        return (v, default)[None is v]


# noinspection PyAbstractClass
class TVShowBase(LegacyTVShow, TVBase):
    def __init__(self, tvid, prodid, lang=''):
        # type: (int, int, Text) -> None
        super(TVShowBase, self).__init__(tvid, prodid)
        
        self._name = ''
        self._imdbid = ''
        self._network = ''
        self._genre = ''
        self._classification = ''
        self._runtime = 0
        self._imdb_info = {}
        self._quality = int(sickbeard.QUALITY_DEFAULT)
        self._flatten_folders = int(sickbeard.FLATTEN_FOLDERS_DEFAULT)
        self._status = ''
        self._airs = ''
        self._startyear = 0
        self._air_by_date = 0
        self._subtitles = int(sickbeard.SUBTITLES_DEFAULT) if sickbeard.SUBTITLES_DEFAULT else 0
        self._dvdorder = 0
        self._upgrade_once = 0
        self._lang = lang
        self._last_update_indexer = 1
        self._sports = 0
        self._anime = 0
        self._scene = 0
        self._rls_ignore_words = ''
        self._rls_require_words = ''
        self._overview = ''
        self._prune = 0
        self._tag = ''

    # name = property(lambda self: self._name, dirty_setter('_name'))
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, *arg):
        _current_name = self._name
        self.dirty_setter('_name')(self, *arg)
        if _current_name != self._name:
            buildNameCache(self)
    
    # imdbid = property(lambda self: self._imdbid, dirty_setter('_imdbid'))
    @property
    def imdbid(self):
        return self._imdbid

    @imdbid.setter
    def imdbid(self, *arg):
        self.dirty_setter('_imdbid')(self, *arg)

    # network = property(lambda self: self._network, dirty_setter('_network'))
    @property
    def network(self):
        return self._network

    @network.setter
    def network(self, *arg):
        self.dirty_setter('_network')(self, *arg)

    # genre = property(lambda self: self._genre, dirty_setter('_genre'))
    @property
    def genre(self):
        return self._genre

    @genre.setter
    def genre(self, *arg):
        self.dirty_setter('_genre')(self, *arg)

    # classification = property(lambda self: self._classification, dirty_setter('_classification'))
    @property
    def classification(self):
        return self._classification

    @classification.setter
    def classification(self, *arg):
        self.dirty_setter('_classification')(self, *arg)

    # runtime = property(lambda self: self._runtime, dirty_setter('_runtime'))
    @property
    def runtime(self):
        return self._runtime

    @runtime.setter
    def runtime(self, *arg):
        self.dirty_setter('_runtime')(self, *arg)

    # imdb_info = property(lambda self: self._imdb_info, dirty_setter('_imdb_info'))
    @property
    def imdb_info(self):
        return self._imdb_info

    @imdb_info.setter
    def imdb_info(self, *arg):
        self.dirty_setter('_imdb_info')(self, *arg)

    # quality = property(lambda self: self._quality, dirty_setter('_quality'))
    @property
    def quality(self):
        return self._quality

    @quality.setter
    def quality(self, *arg):
        self.dirty_setter('_quality')(self, *arg)

    # flatten_folders = property(lambda self: self._flatten_folders, dirty_setter('_flatten_folders'))
    @property
    def flatten_folders(self):
        return self._flatten_folders

    @flatten_folders.setter
    def flatten_folders(self, *arg):
        self.dirty_setter('_flatten_folders')(self, *arg)

    # status = property(lambda self: self._status, dirty_setter('_status'))
    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, *arg):
        self.dirty_setter('_status')(self, *arg)

    # airs = property(lambda self: self._airs, dirty_setter('_airs'))
    @property
    def airs(self):
        return self._airs

    @airs.setter
    def airs(self, *arg):
        self.dirty_setter('_airs')(self, *arg)

    # startyear = property(lambda self: self._startyear, dirty_setter('_startyear'))
    @property
    def startyear(self):
        return self._startyear

    @startyear.setter
    def startyear(self, *arg):
        self.dirty_setter('_startyear')(self, *arg)

    # air_by_date = property(lambda self: self._air_by_date, dirty_setter('_air_by_date'))
    @property
    def air_by_date(self):
        return self._air_by_date

    @air_by_date.setter
    def air_by_date(self, *arg):
        self.dirty_setter('_air_by_date')(self, *arg)

    # subtitles = property(lambda self: self._subtitles, dirty_setter('_subtitles'))
    @property
    def subtitles(self):
        return self._subtitles

    @subtitles.setter
    def subtitles(self, *arg):
        self.dirty_setter('_subtitles')(self, *arg)

    # dvdorder = property(lambda self: self._dvdorder, dirty_setter('_dvdorder'))
    @property
    def dvdorder(self):
        return self._dvdorder

    @dvdorder.setter
    def dvdorder(self, *arg):
        self.dirty_setter('_dvdorder')(self, *arg)

    # upgrade_once = property(lambda self: self._upgrade_once, dirty_setter('_upgrade_once'))
    @property
    def upgrade_once(self):
        return self._upgrade_once

    @upgrade_once.setter
    def upgrade_once(self, *arg):
        self.dirty_setter('_upgrade_once')(self, *arg)

    # lang = property(lambda self: self._lang, dirty_setter('_lang'))
    @property
    def lang(self):
        return self._lang

    @lang.setter
    def lang(self, *arg):
        self.dirty_setter('_lang')(self, *arg)

    # last_update_indexer = property(lambda self: self._last_update_indexer, dirty_setter('_last_update_indexer'))
    @property
    def last_update_indexer(self):
        return self._last_update_indexer

    @last_update_indexer.setter
    def last_update_indexer(self, *arg):
        self.dirty_setter('_last_update_indexer')(self, *arg)

    # sports = property(lambda self: self._sports, dirty_setter('_sports'))
    @property
    def sports(self):
        return self._sports

    @sports.setter
    def sports(self, *arg):
        self.dirty_setter('_sports')(self, *arg)

    # anime = property(lambda self: self._anime, dirty_setter('_anime'))
    @property
    def anime(self):
        return self._anime

    @anime.setter
    def anime(self, *arg):
        self.dirty_setter('_anime')(self, *arg)

    # scene = property(lambda self: self._scene, dirty_setter('_scene'))
    @property
    def scene(self):
        return self._scene

    @scene.setter
    def scene(self, *arg):
        self.dirty_setter('_scene')(self, *arg)

    # rls_ignore_words = property(lambda self: self._rls_ignore_words, dirty_setter('_rls_ignore_words'))
    @property
    def rls_ignore_words(self):
        return self._rls_ignore_words

    @rls_ignore_words.setter
    def rls_ignore_words(self, *arg):
        self.dirty_setter('_rls_ignore_words')(self, *arg)

    # rls_require_words = property(lambda self: self._rls_require_words, dirty_setter('_rls_require_words'))
    @property
    def rls_require_words(self):
        return self._rls_require_words

    @rls_require_words.setter
    def rls_require_words(self, *arg):
        self.dirty_setter('_rls_require_words')(self, *arg)

    # overview = property(lambda self: self._overview, dirty_setter('_overview'))
    @property
    def overview(self):
        return self._overview

    @overview.setter
    def overview(self, *arg):
        self.dirty_setter('_overview')(self, *arg)

    # prune = property(lambda self: self._prune, dirty_setter('_prune'))
    @property
    def prune(self):
        return self._prune

    @prune.setter
    def prune(self, *arg):
        self.dirty_setter('_prune')(self, *arg)

    # tag = property(lambda self: self._tag, dirty_setter('_tag'))
    @property
    def tag(self):
        return self._tag

    @tag.setter
    def tag(self, *arg):
        self.dirty_setter('_tag')(self, *arg)


# noinspection PyAbstractClass
class TVEpisodeBase(LegacyTVEpisode, TVBase):

    def __init__(self, season, episode, tvid):
        super(TVEpisodeBase, self).__init__(tvid)

        self._name = ''
        self._season = season
        self._episode = episode
        self._absolute_number = 0
        self._description = ''
        self._subtitles = list()
        self._subtitles_searchcount = 0
        self._subtitles_lastsearch = str(datetime.datetime.min)
        self._airdate = datetime.date.fromordinal(1)
        self._hasnfo = False
        self._hastbn = False
        self._status = UNKNOWN
        self._file_size = 0
        self._release_name = ''
        self._is_proper = False
        self._version = 0
        self._release_group = ''

    # name = property(lambda self: self._name, dirty_setter('_name', string_types))
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, *arg):
        self.dirty_setter('_name', string_types)(self, *arg)

    # season = property(lambda self: self._season, dirty_setter('_season'))
    @property
    def season(self):
        """ Season number.

        :return: Season number
        :rtype: int
        """
        return self._season

    @season.setter
    def season(self, *arg):
        self.dirty_setter('_season')(self, *arg)

    # episode = property(lambda self: self._episode, dirty_setter('_episode'))
    @property
    def episode(self):
        """ Episode number.

        :return: Episode number
        :rtype: int
        """
        return self._episode

    @episode.setter
    def episode(self, *arg):
        self.dirty_setter('_episode')(self, *arg)

    # absolute_number = property(lambda self: self._absolute_number, dirty_setter('_absolute_number'))
    @property
    def absolute_number(self):
        return self._absolute_number

    @absolute_number.setter
    def absolute_number(self, *arg):
        self.dirty_setter('_absolute_number')(self, *arg)

    # description = property(lambda self: self._description, dirty_setter('_description'))
    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, *arg):
        self.dirty_setter('_description')(self, *arg)

    # subtitles = property(lambda self: self._subtitles, dirty_setter('_subtitles'))
    @property
    def subtitles(self):
        return self._subtitles

    @subtitles.setter
    def subtitles(self, *arg):
        self.dirty_setter('_subtitles')(self, *arg)

    # subtitles_searchcount = property(lambda self: self._subtitles_searchcount, dirty_setter('_subtitles_searchcount'))
    @property
    def subtitles_searchcount(self):
        return self._subtitles_searchcount

    @subtitles_searchcount.setter
    def subtitles_searchcount(self, *arg):
        self.dirty_setter('_subtitles_searchcount')(self, *arg)

    # subtitles_lastsearch = property(lambda self: self._subtitles_lastsearch, dirty_setter('_subtitles_lastsearch'))
    @property
    def subtitles_lastsearch(self):
        return self._subtitles_lastsearch

    @subtitles_lastsearch.setter
    def subtitles_lastsearch(self, *arg):
        self.dirty_setter('_subtitles_lastsearch')(self, *arg)

    # airdate = property(lambda self: self._airdate, dirty_setter('_airdate'))
    @property
    def airdate(self):
        return self._airdate

    @airdate.setter
    def airdate(self, *arg):
        self.dirty_setter('_airdate')(self, *arg)

    # hasnfo = property(lambda self: self._hasnfo, dirty_setter('_hasnfo'))
    @property
    def hasnfo(self):
        return self._hasnfo

    @hasnfo.setter
    def hasnfo(self, *arg):
        self.dirty_setter('_hasnfo')(self, *arg)

    # hastbn = property(lambda self: self._hastbn, dirty_setter('_hastbn'))
    @property
    def hastbn(self):
        return self._hastbn

    @hastbn.setter
    def hastbn(self, *arg):
        self.dirty_setter('_hastbn')(self, *arg)

    # status = property(lambda self: self._status, dirty_setter('_status'))
    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, *arg):
        self.dirty_setter('_status')(self, *arg)

    # file_size = property(lambda self: self._file_size, dirty_setter('_file_size'))
    @property
    def file_size(self):
        return self._file_size

    @file_size.setter
    def file_size(self, *arg):
        self.dirty_setter('_file_size')(self, *arg)

    # release_name = property(lambda self: self._release_name, dirty_setter('_release_name'))
    @property
    def release_name(self):
        return self._release_name

    @release_name.setter
    def release_name(self, *arg):
        self.dirty_setter('_release_name')(self, *arg)

    # is_proper = property(lambda self: self._is_proper, dirty_setter('_is_proper'))
    @property
    def is_proper(self):
        return self._is_proper

    @is_proper.setter
    def is_proper(self, *arg):
        self.dirty_setter('_is_proper')(self, *arg)

    # version = property(lambda self: self._version, dirty_setter('_version'))
    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, *arg):
        self.dirty_setter('_version')(self, *arg)

    # release_group = property(lambda self: self._release_group, dirty_setter('_release_group'))
    @property
    def release_group(self):
        return self._release_group

    @release_group.setter
    def release_group(self, *arg):
        self.dirty_setter('_release_group')(self, *arg)
