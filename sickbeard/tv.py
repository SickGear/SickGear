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

import os.path
import datetime
import threading
import re
import glob
import stat
import traceback
import requests
import shutil

import sickbeard

import xml.etree.cElementTree as etree

from name_parser.parser import NameParser, InvalidNameException, InvalidShowException

from lib import subliminal
import fnmatch

from lib import imdbpie
from imdbpie import ImdbAPIError

from sickbeard import db
from sickbeard import helpers, exceptions, logger, name_cache, indexermapper
from sickbeard.exceptions import ex
from sickbeard import image_cache
from sickbeard import notifiers
from sickbeard import postProcessor
from sickbeard import subtitles
from sickbeard import history
from sickbeard import network_timezones
from sickbeard.sbdatetime import sbdatetime
from sickbeard.blackandwhitelist import BlackAndWhiteList
from sickbeard.helpers import tryInt, tryFloat
from sickbeard.indexermapper import del_mapping, save_mapping, MapStatus
from sickbeard.generic_queue import QueuePriorities

from sickbeard import encodingKludge as ek

from common import Quality, Overview, statusStrings
from common import SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, SNATCHED_ANY, DOWNLOADED, ARCHIVED, \
    IGNORED, UNAIRED, WANTED, SKIPPED, UNKNOWN, FAILED, SUBTITLED
from common import NAMING_DUPLICATE, NAMING_EXTEND, NAMING_LIMITED_EXTEND, NAMING_SEPARATED_REPEAT, \
    NAMING_LIMITED_EXTEND_E_PREFIXED

concurrent_show_not_found_days = 7
show_not_found_retry_days = 7


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


def dict_prevent_None(d, key, default):
    v = getattr(d, key, default)
    return (v, default)[None is v]


class TVShow(object):
    def __init__(self, indexer, indexerid, lang=''):
        self._indexerid = int(indexerid)
        self._indexer = int(indexer)
        self._name = ''
        self._imdbid = ''
        self._network = ''
        self._genre = ''
        self._classification = ''
        self._runtime = 0
        self._imdb_info = {}
        self._quality = int(sickbeard.QUALITY_DEFAULT)
        self._flatten_folders = int(sickbeard.FLATTEN_FOLDERS_DEFAULT)
        self._status = ""
        self._airs = ""
        self._startyear = 0
        self._paused = 0
        self._air_by_date = 0
        self._subtitles = int(sickbeard.SUBTITLES_DEFAULT if sickbeard.SUBTITLES_DEFAULT else 0)
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
        self._mapped_ids = {}
        self._not_found_count = None
        self._last_found_on_indexer = -1

        self.dirty = True

        self._location = ''
        self.lock = threading.Lock()
        self.isDirGood = False
        self.episodes = {}
        self.nextaired = ''
        self.release_groups = None

        otherShow = helpers.findCertainShow(sickbeard.showList, self.indexerid)
        if otherShow != None:
            raise exceptions.MultipleShowObjectsException('Can\'t create a show if it already exists')

        self.loadFromDB()

    name = property(lambda self: self._name, dirty_setter('_name'))
    indexerid = property(lambda self: self._indexerid, dirty_setter('_indexerid'))
    indexer = property(lambda self: self._indexer, dirty_setter('_indexer'))
    # location = property(lambda self: self._location, dirty_setter('_location'))
    imdbid = property(lambda self: self._imdbid, dirty_setter('_imdbid'))
    network = property(lambda self: self._network, dirty_setter('_network'))
    genre = property(lambda self: self._genre, dirty_setter('_genre'))
    classification = property(lambda self: self._classification, dirty_setter('_classification'))
    runtime = property(lambda self: self._runtime, dirty_setter('_runtime'))
    imdb_info = property(lambda self: self._imdb_info, dirty_setter('_imdb_info'))
    quality = property(lambda self: self._quality, dirty_setter('_quality'))
    flatten_folders = property(lambda self: self._flatten_folders, dirty_setter('_flatten_folders'))
    status = property(lambda self: self._status, dirty_setter('_status'))
    airs = property(lambda self: self._airs, dirty_setter('_airs'))
    startyear = property(lambda self: self._startyear, dirty_setter('_startyear'))
    air_by_date = property(lambda self: self._air_by_date, dirty_setter('_air_by_date'))
    subtitles = property(lambda self: self._subtitles, dirty_setter('_subtitles'))
    dvdorder = property(lambda self: self._dvdorder, dirty_setter('_dvdorder'))
    upgrade_once = property(lambda self: self._upgrade_once, dirty_setter('_upgrade_once'))
    lang = property(lambda self: self._lang, dirty_setter('_lang'))
    last_update_indexer = property(lambda self: self._last_update_indexer, dirty_setter('_last_update_indexer'))
    sports = property(lambda self: self._sports, dirty_setter('_sports'))
    anime = property(lambda self: self._anime, dirty_setter('_anime'))
    scene = property(lambda self: self._scene, dirty_setter('_scene'))
    rls_ignore_words = property(lambda self: self._rls_ignore_words, dirty_setter('_rls_ignore_words'))
    rls_require_words = property(lambda self: self._rls_require_words, dirty_setter('_rls_require_words'))
    overview = property(lambda self: self._overview, dirty_setter('_overview'))
    prune = property(lambda self: self._prune, dirty_setter('_prune'))
    tag = property(lambda self: self._tag, dirty_setter('_tag'))

    def _helper_load_failed_db(self):
        if None is self._not_found_count or self._last_found_on_indexer == -1:
            myDB = db.DBConnection()
            results = myDB.select('SELECT fail_count, last_success FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
                                  [self.indexer, self.indexerid])
            if results:
                self._not_found_count = helpers.tryInt(results[0]['fail_count'])
                self._last_found_on_indexer = helpers.tryInt(results[0]['last_success'])
            else:
                self._not_found_count = 0
                self._last_found_on_indexer = 0

    @property
    def not_found_count(self):
        self._helper_load_failed_db()
        return self._not_found_count

    @not_found_count.setter
    def not_found_count(self, v):
        if isinstance(v, (int, long)) and v != self._not_found_count:
            self._last_found_on_indexer = self.last_found_on_indexer
            myDB = db.DBConnection()
            # noinspection PyUnresolvedReferences
            last_check = sbdatetime.now().totimestamp(default=0)
            # in case of flag change (+/-) don't change last_check date
            if abs(v) == abs(self._not_found_count):
                results = myDB.select('SELECT last_check FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
                                      [self.indexer, self.indexerid])
                if results:
                    last_check = helpers.tryInt(results[0]['last_check'])
            myDB.upsert('tv_shows_not_found',
                        {'fail_count': v, 'last_check': last_check,
                         'last_success': self._last_found_on_indexer},
                        {'indexer': self.indexer, 'indexer_id': self.indexerid})
            self._not_found_count = v

    @property
    def last_found_on_indexer(self):
        self._helper_load_failed_db()
        return (self._last_found_on_indexer, self.last_update_indexer)[self._last_found_on_indexer <= 0]

    def inc_not_found_count(self):
        myDB = db.DBConnection()
        results = myDB.select('SELECT last_check FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
                              [self.indexer, self.indexerid])
        days = (show_not_found_retry_days - 1, 0)[abs(self.not_found_count) <= concurrent_show_not_found_days]
        if not results or datetime.datetime.fromtimestamp(helpers.tryInt(results[0]['last_check'])) + \
                datetime.timedelta(days=days, hours=18) < datetime.datetime.now():
            self.not_found_count += (-1, 1)[0 <= self.not_found_count]

    def reset_not_found_count(self):
        if 0 != self.not_found_count:
            self._not_found_count = 0
            self._last_found_on_indexer = 0
            myDB = db.DBConnection()
            myDB.action('DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?',
                        [self.indexer, self.indexerid])

    @property
    def paused(self):
        return self._paused

    @paused.setter
    def paused(self, value):
        if value != self._paused:
            if isinstance(value, bool) or (isinstance(value, (int, long)) and value in [0, 1]):
                self._paused = int(value)
                self.dirty = True
            else:
                logger.log('tried to set paused property to invalid value: %s of type: %s' % (value, type(value)),
                           logger.ERROR)

    @property
    def ids(self):
        if not self._mapped_ids:
            acquired_lock = self.lock.acquire(False)
            if acquired_lock:
                try:
                    indexermapper.map_indexers_to_show(self)
                finally:
                    self.lock.release()
        return self._mapped_ids

    @ids.setter
    def ids(self, value):
        if isinstance(value, dict):
            for k, v in value.iteritems():
                if k not in sickbeard.indexermapper.indexer_list or not isinstance(v, dict) or \
                        not isinstance(v.get('id'), (int, long)) or not isinstance(v.get('status'), (int, long)) or \
                                v.get('status') not in indexermapper.MapStatus.allstatus or \
                        not isinstance(v.get('date'), datetime.date):
                    return
            self._mapped_ids = value

    @property
    def is_anime(self):
        if int(self.anime) > 0:
            return True
        else:
            return False

    @property
    def is_sports(self):
        if int(self.sports) > 0:
            return True
        else:
            return False

    @property
    def is_scene(self):
        if int(self.scene) > 0:
            return True
        else:
            return False

    def _getLocation(self):
        # no dir check needed if missing show dirs are created during post-processing
        if sickbeard.CREATE_MISSING_SHOW_DIRS:
            return self._location

        if ek.ek(os.path.isdir, self._location):
            return self._location
        else:
            raise exceptions.ShowDirNotFoundException('Show folder does not exist: \'%s\'' % self._location)

    def _setLocation(self, newLocation):
        logger.log('Setter sets location to %s' % newLocation, logger.DEBUG)
        # Don't validate dir if user wants to add shows without creating a dir
        if sickbeard.ADD_SHOWS_WO_DIR or ek.ek(os.path.isdir, newLocation):
            dirty_setter('_location')(self, newLocation)
            self._isDirGood = True
        else:
            raise exceptions.NoNFOException('Invalid folder for the show!')

    location = property(_getLocation, _setLocation)

    # delete references to anything that's not in the internal lists
    def flushEpisodes(self):

        for curSeason in self.episodes:
            for curEp in self.episodes[curSeason]:
                myEp = self.episodes[curSeason][curEp]
                self.episodes[curSeason][curEp] = None
                del myEp

    def getAllEpisodes(self, season=None, has_location=False, check_related_eps=True):

        sql_selection = 'SELECT season, episode'

        if check_related_eps:
            # subselection to detect multi-episodes early, share_location > 0
            sql_selection += ' , (SELECT COUNT (*) FROM tv_episodes WHERE showid = tve.showid AND season = ' \
                             'tve.season AND location != "" AND location = tve.location AND episode != tve.episode) ' \
                             'AS share_location '

        sql_selection += ' FROM tv_episodes tve WHERE indexer = ? AND showid = ?'
        sql_parameter = [self.indexer, self.indexerid]

        if season is not None:
            sql_selection += ' AND season = ?'
            sql_parameter += [season]

        if has_location:
            sql_selection += ' AND location != "" '

        # need ORDER episode ASC to rename multi-episodes in order S01E01-02
        sql_selection += ' ORDER BY season ASC, episode ASC'

        myDB = db.DBConnection()
        results = myDB.select(sql_selection, sql_parameter)

        ep_list = []
        for cur_result in results:
            cur_ep = self.getEpisode(int(cur_result['season']), int(cur_result['episode']))
            if cur_ep:
                cur_ep.relatedEps = []
                if check_related_eps and cur_ep.location:
                    # if there is a location, check if it's a multi-episode (share_location > 0) and put them in relatedEps
                    if cur_result['share_location'] > 0:
                        related_eps_result = myDB.select(
                            'SELECT * FROM tv_episodes WHERE showid = ? AND season = ? AND location = ? AND '
                            'episode != ? ORDER BY episode ASC',
                            [self.indexerid, cur_ep.season, cur_ep.location, cur_ep.episode])
                        for cur_related_ep in related_eps_result:
                            related_ep = self.getEpisode(int(cur_related_ep["season"]), int(cur_related_ep["episode"]))
                            if related_ep not in cur_ep.relatedEps:
                                cur_ep.relatedEps.append(related_ep)
                ep_list.append(cur_ep)

        return ep_list

    def getEpisode(self, season=None, episode=None, file=None, noCreate=False, absolute_number=None, forceUpdate=False,
                   ep_sql=None):

        # if we get an anime get the real season and episode
        if self.is_anime and absolute_number and not season and not episode:
            myDB = db.DBConnection()
            sql = 'SELECT * FROM tv_episodes WHERE showid = ? and absolute_number = ? and season != 0'
            sqlResults = myDB.select(sql, [self.indexerid, absolute_number])

            if len(sqlResults) == 1:
                episode = int(sqlResults[0]['episode'])
                season = int(sqlResults[0]['season'])
                logger.log(
                    'Found episode by absolute_number: %s which is %sx%s' % (absolute_number, season, episode),
                    logger.DEBUG)
            elif len(sqlResults) > 1:
                logger.log('Multiple entries for absolute number: %s in show: %s  found.' %
                           (absolute_number, self.name), logger.ERROR)
                return None
            else:
                logger.log(
                    'No entries for absolute number: %s in show: %s found.' % (absolute_number, self.name), logger.DEBUG)
                return None

        if not season in self.episodes:
            self.episodes[season] = {}

        if not episode in self.episodes[season] or self.episodes[season][episode] is None:
            if noCreate:
                return None

            # logger.log('%s: An object for episode %sx%s didn\'t exist in the cache, trying to create it' %
            #            (self.indexerid, season, episode), logger.DEBUG)

            if file:
                ep = TVEpisode(self, season, episode, file, show_sql=ep_sql)
            else:
                ep = TVEpisode(self, season, episode, show_sql=ep_sql)

            if ep != None:
                self.episodes[season][episode] = ep

        return self.episodes[season][episode]

    def should_update(self, update_date=datetime.date.today()):

        cur_indexerid = self.indexerid

        # In some situations self.status = None.. need to figure out where that is!
        if not self.status:
            self.status = ''
            logger.log('Status missing for showid: [%s] with status: [%s]' %
                       (cur_indexerid, self.status), logger.DEBUG)

        last_update_indexer = datetime.date.fromordinal(self.last_update_indexer)

        # if show was not found for 1 week, only retry to update once a week
        if (concurrent_show_not_found_days < abs(self.not_found_count)) \
                and (update_date - last_update_indexer) < datetime.timedelta(days=show_not_found_retry_days):
            return False

        myDB = db.DBConnection()
        sql_result = myDB.mass_action(
            [['SELECT airdate FROM [tv_episodes] WHERE showid = ? AND season > "0" ORDER BY season DESC, episode DESC LIMIT 1', [cur_indexerid]],
             ['SELECT airdate FROM [tv_episodes] WHERE showid = ? AND season > "0" AND airdate > "1" ORDER BY airdate DESC LIMIT 1', [cur_indexerid]]])

        last_airdate_unknown = int(sql_result[0][0]['airdate']) <= 1 if sql_result and sql_result[0] else True

        last_airdate = datetime.date.fromordinal(sql_result[1][0]['airdate']) if sql_result and sql_result[1] else datetime.date.fromordinal(1)

        # if show is not 'Ended' and last episode aired less then 460 days ago or don't have an airdate for the last episode always update (status 'Continuing' or '')
        update_days_limit = 2013
        ended_limit = datetime.timedelta(days=update_days_limit)
        if 'Ended' not in self.status and (last_airdate == datetime.date.fromordinal(1) or last_airdate_unknown or (update_date - last_airdate) <= ended_limit or (update_date - last_update_indexer) > ended_limit):
            return True

        # in the first 460 days (last airdate), update regularly
        airdate_diff = update_date - last_airdate
        last_update_diff = update_date - last_update_indexer

        update_step_list = [[60, 1], [120, 3], [180, 7], [1281, 15], [update_days_limit, 30]]
        for date_diff, interval in update_step_list:
            if airdate_diff <= datetime.timedelta(days=date_diff) and last_update_diff >= datetime.timedelta(days=interval):
                return True

        # update shows without an airdate for the last episode for update_days_limit days every 7 days
        if last_airdate_unknown and airdate_diff <= ended_limit and last_update_diff >= datetime.timedelta(days=7):
            return True
        else:
            return False

    def writeShowNFO(self):

        result = False

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.indexerid)
            return False

        logger.log('%s: Writing NFOs for show' % self.indexerid)
        for cur_provider in sickbeard.metadata_provider_dict.values():
            result = cur_provider.create_show_metadata(self) or result

        return result

    def writeMetadata(self, show_only=False):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.indexerid)
            return

        self.getImages()

        self.writeShowNFO()

        if not show_only:
            self.writeEpisodeNFOs()

    def writeEpisodeNFOs(self):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.indexerid)
            return

        logger.log('%s: Writing NFOs for all episodes' % self.indexerid)

        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT * FROM tv_episodes WHERE showid = ? AND location != ''", [self.indexerid])

        for epResult in sqlResults:
            logger.log('%s: Retrieving/creating episode %sx%s' % (self.indexerid, epResult["season"], epResult["episode"]),
                       logger.DEBUG)
            curEp = self.getEpisode(epResult["season"], epResult["episode"])
            curEp.createMetaFiles()


    def updateMetadata(self):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.indexerid)
            return

        self.updateShowNFO()

    def updateShowNFO(self):

        result = False

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, skipping NFO generation' % self.indexerid)
            return False

        logger.log('%s: Updating NFOs for show with new indexer info' % self.indexerid)
        for cur_provider in sickbeard.metadata_provider_dict.values():
            result = cur_provider.update_show_indexer_metadata(self) or result

        return result

    # find all media files in the show folder and create episodes for as many as possible
    def loadEpisodesFromDir(self):

        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, not loading episodes from disk' % self.indexerid)
            return

        logger.log('%s: Loading all episodes from the show directory %s' % (self.indexerid, self._location))

        # get file list
        mediaFiles = helpers.listMediaFiles(self._location)

        # create TVEpisodes from each media file (if possible)
        sql_l = []
        for mediaFile in mediaFiles:
            parse_result = None
            curEpisode = None

            logger.log('%s: Creating episode from %s' % (self.indexerid, mediaFile), logger.DEBUG)
            try:
                curEpisode = self.makeEpFromFile(ek.ek(os.path.join, self._location, mediaFile))
            except (exceptions.ShowNotFoundException, exceptions.EpisodeNotFoundException) as e:
                logger.log('Episode %s returned an exception: %s' % (mediaFile, ex(e)), logger.ERROR)
                continue
            except exceptions.EpisodeDeletedException:
                logger.log('The episode deleted itself when I tried making an object for it', logger.DEBUG)

            if curEpisode is None:
                continue

            # see if we should save the release name in the db
            ep_file_name = ek.ek(os.path.basename, curEpisode.location)
            ep_file_name = ek.ek(os.path.splitext, ep_file_name)[0]

            try:
                parse_result = None
                np = NameParser(False, showObj=self)
                parse_result = np.parse(ep_file_name)
            except (InvalidNameException, InvalidShowException):
                pass

            if ep_file_name and parse_result and None is not parse_result.release_group and not curEpisode.release_name:
                logger.log(
                    'Name %s gave release group of %s, seems valid' % (ep_file_name ,parse_result.release_group),
                    logger.DEBUG)
                curEpisode.release_name = ep_file_name

            # store the reference in the show
            if curEpisode != None:
                if self.subtitles:
                    try:
                        curEpisode.refreshSubtitles()
                    except:
                        logger.log('%s: Could not refresh subtitles' % self.indexerid, logger.ERROR)
                        logger.log(traceback.format_exc(), logger.ERROR)

                result = curEpisode.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)

    def loadEpisodesFromDB(self, update=False):

        logger.log('Loading all episodes for [%s] from the DB' % self.name)

        myDB = db.DBConnection()
        sql = 'SELECT * FROM tv_episodes WHERE showid = ? AND indexer = ?'
        sqlResults = myDB.select(sql, [self.indexerid, self.indexer])

        scannedEps = {}

        lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()

        if self.lang:
            lINDEXER_API_PARMS['language'] = self.lang

        if self.dvdorder != 0:
            lINDEXER_API_PARMS['dvdorder'] = True

        t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)

        cachedShow = None
        try:
            cachedShow = t[self.indexerid]
        except sickbeard.indexer_error as e:
            logger.log('Unable to find cached seasons from %s: %s' % (
                sickbeard.indexerApi(self.indexer).name, ex(e)), logger.WARNING)
        if None is cachedShow:
            return scannedEps

        cachedSeasons = {}
        for curResult in sqlResults:

            deleteEp = False

            curSeason = int(curResult["season"])
            curEpisode = int(curResult["episode"])

            if curSeason not in cachedSeasons:
                try:
                    cachedSeasons[curSeason] = cachedShow[curSeason]
                except sickbeard.indexer_seasonnotfound as e:
                    logger.log('Error when trying to load the episode for [%s] from %s: %s' %
                               (self.name, sickbeard.indexerApi(self.indexer).name, e.message), logger.WARNING)
                    deleteEp = True

            if not curSeason in scannedEps:
                scannedEps[curSeason] = {}

            logger.log('Loading episode %sx%s for [%s] from the DB' % (curSeason, curEpisode, self.name), logger.DEBUG)

            try:
                curEp = self.getEpisode(curSeason, curEpisode)

                # if we found out that the ep is no longer on TVDB then delete it from our database too
                if deleteEp and helpers.should_delete_episode(curEp.status):
                    curEp.deleteEpisode()

                curEp.loadFromDB(curSeason, curEpisode)
                curEp.loadFromIndexer(tvapi=t, cachedSeason=cachedSeasons.get(curSeason), update=update)
                scannedEps[curSeason][curEpisode] = True
            except exceptions.EpisodeDeletedException:
                logger.log('Tried loading an episode from [%s] from the DB that should have been deleted, skipping it' % self.name,
                           logger.DEBUG)
                continue

        return scannedEps

    def loadEpisodesFromIndexer(self, cache=True, update=False):

        lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()

        if not cache:
            lINDEXER_API_PARMS['cache'] = False

        if self.lang:
            lINDEXER_API_PARMS['language'] = self.lang

        if self.dvdorder != 0:
            lINDEXER_API_PARMS['dvdorder'] = True

        logger.log('%s: Loading all episodes for [%s] from %s..' % (self.indexerid, self.name, sickbeard.indexerApi(self.indexer).name))

        try:
            t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)
            showObj = t[self.indexerid]
        except sickbeard.indexer_error:
            logger.log('%s timed out, unable to update episodes for [%s] from %s' %
                       (sickbeard.indexerApi(self.indexer).name, self.name, sickbeard.indexerApi(self.indexer).name), logger.ERROR)
            return None

        scannedEps = {}

        sql_l = []
        for season in showObj:
            scannedEps[season] = {}
            for episode in showObj[season]:
                # need some examples of wtf episode 0 means to decide if we want it or not
                if episode == 0:
                    continue
                try:
                    ep = self.getEpisode(season, episode)
                except exceptions.EpisodeNotFoundException:
                    logger.log('%s: %s object for %sx%s from [%s] is incomplete, skipping this episode' %
                               (self.indexerid, sickbeard.indexerApi(self.indexer).name, season, episode, self.name))
                    continue
                else:
                    try:
                        ep.loadFromIndexer(tvapi=t, update=update)
                    except exceptions.EpisodeDeletedException:
                        logger.log('The episode from [%s] was deleted, skipping the rest of the load' % self.name)
                        continue

                with ep.lock:
                    logger.log('%s: Loading info from %s for episode %sx%s from [%s]' %
                               (self.indexerid, sickbeard.indexerApi(self.indexer).name, season, episode, self.name), logger.DEBUG)
                    ep.loadFromIndexer(season, episode, tvapi=t, update=update)

                    result = ep.get_sql()
                    if None is not result:
                        sql_l.append(result)

                scannedEps[season][episode] = True

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)


        # Done updating save last update date
        self.last_update_indexer = datetime.date.today().toordinal()
        self.saveToDB()

        return scannedEps

    def getImages(self, fanart=None, poster=None):
        fanart_result = poster_result = banner_result = False
        season_posters_result = season_banners_result = season_all_poster_result = season_all_banner_result = False

        for cur_provider in sickbeard.metadata_provider_dict.values():
            # FIXME: Needs to not show this message if the option is not enabled?
            logger.log('Running metadata routines for %s' % cur_provider.name, logger.DEBUG)

            fanart_result = cur_provider.create_fanart(self) or fanart_result
            poster_result = cur_provider.create_poster(self) or poster_result
            banner_result = cur_provider.create_banner(self) or banner_result

            season_posters_result = cur_provider.create_season_posters(self) or season_posters_result
            season_banners_result = cur_provider.create_season_banners(self) or season_banners_result
            season_all_poster_result = cur_provider.create_season_all_poster(self) or season_all_poster_result
            season_all_banner_result = cur_provider.create_season_all_banner(self) or season_all_banner_result

        return fanart_result or poster_result or banner_result or season_posters_result or season_banners_result or season_all_poster_result or season_all_banner_result

    # make a TVEpisode object from a media file
    def makeEpFromFile(self, file):

        if not ek.ek(os.path.isfile, file):
            logger.log('%s: Not a real file... %s' % (self.indexerid, file))
            return None

        logger.log('%s: Creating episode object from %s' % (self.indexerid, file), logger.DEBUG)

        try:
            my_parser = NameParser(showObj=self)
            parse_result = my_parser.parse(file)
        except InvalidNameException:
            logger.log('Unable to parse the filename %s into a valid episode' % file, logger.DEBUG)
            return None
        except InvalidShowException:
            logger.log('Unable to parse the filename %s into a valid show' % file, logger.DEBUG)
            return None

        if not len(parse_result.episode_numbers):
            logger.log('parse_result: %s' % parse_result)
            logger.log('No episode number found in %s, ignoring it' % file, logger.ERROR)
            return None

        # for now lets assume that any episode in the show dir belongs to that show
        season = parse_result.season_number if None is not parse_result.season_number else 1
        episodes = parse_result.episode_numbers
        root_ep = None

        sql_l = []
        for cur_ep_num in episodes:

            episode = int(cur_ep_num)

            logger.log('%s: %s parsed to %s %sx%s' % (self.indexerid, file, self.name, season, episode), logger.DEBUG)

            check_quality_again = False
            same_file = False
            cur_ep = self.getEpisode(season, episode)

            if None is cur_ep:
                try:
                    cur_ep = self.getEpisode(season, episode, file)
                except exceptions.EpisodeNotFoundException:
                    logger.log('%s: Unable to figure out what this file is, skipping' % self.indexerid, logger.ERROR)
                    continue

            else:
                # if there is a new file associated with this ep then re-check the quality
                status, quality = sickbeard.common.Quality.splitCompositeStatus(cur_ep.status)

                if IGNORED == status:
                    continue

                if (cur_ep.location and ek.ek(os.path.normpath, cur_ep.location) != ek.ek(os.path.normpath, file)) or \
                        (not cur_ep.location and file) or \
                        (SKIPPED == status):
                    logger.log('The old episode had a different file associated with it, re-checking the quality ' +
                               'based on the new filename %s' % file, logger.DEBUG)
                    check_quality_again = True

                with cur_ep.lock:
                    old_size = cur_ep.file_size if cur_ep.location and status != SKIPPED else 0
                    cur_ep.location = file
                    # if the sizes are the same then it's probably the same file
                    if old_size and cur_ep.file_size == old_size:
                        same_file = True
                    else:
                        same_file = False

                    cur_ep.checkForMetaFiles()

            if None is root_ep:
                root_ep = cur_ep
            else:
                if cur_ep not in root_ep.relatedEps:
                    root_ep.relatedEps.append(cur_ep)

            # if it's a new file then
            if not same_file:
                cur_ep.release_name = ''

            # if they replace a file on me I'll make some attempt at re-checking the quality unless I know it's the same file
            if check_quality_again and not same_file:
                new_quality = Quality.nameQuality(file, self.is_anime)
                if Quality.UNKNOWN == new_quality:
                    new_quality = Quality.fileQuality(file)
                logger.log('Since this file was renamed, file %s was checked and quality "%s" found'
                           % (file, Quality.qualityStrings[new_quality]), logger.DEBUG)
                status, quality = sickbeard.common.Quality.splitCompositeStatus(cur_ep.status)
                if Quality.UNKNOWN != new_quality or status in (SKIPPED, UNAIRED):
                    cur_ep.status = Quality.compositeStatus(DOWNLOADED, new_quality)

            # check for status/quality changes as long as it's a new file
            elif not same_file and sickbeard.helpers.has_media_ext(file)\
                    and cur_ep.status not in Quality.DOWNLOADED + Quality.ARCHIVED + [IGNORED]:

                old_status, old_quality = Quality.splitCompositeStatus(cur_ep.status)
                new_quality = Quality.nameQuality(file, self.is_anime)
                if Quality.UNKNOWN == new_quality:
                    new_quality = Quality.fileQuality(file)
                    if Quality.UNKNOWN == new_quality:
                        new_quality = Quality.assumeQuality(file)

                new_status = None

                # if it was snatched and now exists then set the status correctly
                if SNATCHED == old_status and old_quality <= new_quality:
                    logger.log('STATUS: this episode used to be snatched with quality %s but a file exists with quality %s so setting the status to DOWNLOADED'
                               % (Quality.qualityStrings[old_quality], Quality.qualityStrings[new_quality]), logger.DEBUG)
                    new_status = DOWNLOADED

                # if it was snatched proper and we found a higher quality one then allow the status change
                elif SNATCHED_PROPER == old_status and old_quality < new_quality:
                    logger.log('STATUS: this episode used to be snatched proper with quality %s but a file exists with quality %s so setting the status to DOWNLOADED'
                               % (Quality.qualityStrings[old_quality], Quality.qualityStrings[new_quality]), logger.DEBUG)
                    new_status = DOWNLOADED

                elif old_status not in SNATCHED_ANY:
                    new_status = DOWNLOADED

                if None is not new_status:
                    with cur_ep.lock:
                        logger.log('STATUS: we have an associated file, so setting the status from %s to DOWNLOADED/%s'
                                   % (cur_ep.status, Quality.compositeStatus(new_status, new_quality)), logger.DEBUG)
                        cur_ep.status = Quality.compositeStatus(new_status, new_quality)

            elif same_file:
                status, quality = Quality.splitCompositeStatus(cur_ep.status)
                if status in (SKIPPED, UNAIRED):
                    new_quality = Quality.nameQuality(file, self.is_anime)
                    if Quality.UNKNOWN == new_quality:
                        new_quality = Quality.fileQuality(file)
                    logger.log('Since this file has status: "%s", file %s was checked and quality "%s" found'
                               % (statusStrings[status], file, Quality.qualityStrings[new_quality]), logger.DEBUG)
                    cur_ep.status = Quality.compositeStatus(DOWNLOADED, new_quality)

            with cur_ep.lock:
                result = cur_ep.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            my_db = db.DBConnection()
            my_db.mass_action(sql_l)

        # creating metafiles on the root should be good enough
        if sickbeard.USE_FAILED_DOWNLOADS and root_ep is not None:
            with root_ep.lock:
                root_ep.createMetaFiles()

        return root_ep

    def loadFromDB(self, skipNFO=False):

        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM tv_shows WHERE indexer_id = ?', [self.indexerid])

        if 1 != len(sqlResults):
            if 1 < len(sqlResults):
                lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()
                if self.lang:
                    lINDEXER_API_PARMS['language'] = self.lang
                t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)
                cached_show = t[self.indexerid]
                vals = (self.indexerid, '' if not cached_show else ' [%s]' % cached_show['seriesname'].strip())
                if 0 != len(sqlResults):
                    logger.log('%s: Loading show info%s from database' % vals)
                    raise exceptions.MultipleDBShowsException()
            logger.log('%s: Unable to find the show%s in the database' % (self.indexerid, self.name))
            return
        else:
            if not self.indexer:
                self.indexer = int(sqlResults[0]['indexer'])
            if not self.name:
                self.name = sqlResults[0]['show_name']
            if not self.network:
                self.network = sqlResults[0]['network']
            if not self.genre:
                self.genre = sqlResults[0]['genre']
            if self.classification is None:
                self.classification = sqlResults[0]['classification']

            self.runtime = sqlResults[0]['runtime']

            self.status = sqlResults[0]['status']
            if not self.status:
                self.status = ''
            self.airs = sqlResults[0]['airs']
            if not self.airs:
                self.airs = ''
            self.startyear = sqlResults[0]['startyear']
            if not self.startyear:
                self.startyear = 0

            self.air_by_date = sqlResults[0]['air_by_date']
            if not self.air_by_date:
                self.air_by_date = 0

            self.anime = sqlResults[0]['anime']
            if None is self.anime:
                self.anime = 0

            self.sports = sqlResults[0]['sports']
            if not self.sports:
                self.sports = 0

            self.scene = sqlResults[0]['scene']
            if not self.scene:
                self.scene = 0

            self.subtitles = sqlResults[0]['subtitles']
            if self.subtitles:
                self.subtitles = 1
            else:
                self.subtitles = 0

            self.dvdorder = sqlResults[0]['dvdorder']
            if not self.dvdorder:
                self.dvdorder = 0

            self.upgrade_once = sqlResults[0]['archive_firstmatch']
            if not self.upgrade_once:
                self.upgrade_once = 0

            self.quality = int(sqlResults[0]['quality'])
            self.flatten_folders = int(sqlResults[0]['flatten_folders'])
            self.paused = int(sqlResults[0]['paused'])

            try:
                self.location = sqlResults[0]['location']
            except Exception:
                dirty_setter('_location')(self, sqlResults[0]['location'])
                self._isDirGood = False

            if not self.lang:
                self.lang = sqlResults[0]['lang']

            self.last_update_indexer = sqlResults[0]['last_update_indexer']

            self.rls_ignore_words = sqlResults[0]['rls_ignore_words']
            self.rls_require_words = sqlResults[0]['rls_require_words']

            if not self.imdbid:
                imdbid = sqlResults[0]['imdb_id'] or ''
                self.imdbid = ('', imdbid)[2 < len(imdbid)]

            if self.is_anime:
                self.release_groups = BlackAndWhiteList(self.indexerid)

            if not self.overview:
                self.overview = sqlResults[0]['overview']

            self.prune = sqlResults[0]['prune']
            if not self.prune:
                self.prune = 0

            self.tag = sqlResults[0]['tag']
            if not self.tag:
                self.tag = 'Show List'

        logger.log(u'Loaded.. {: <9} {: <8} {}'.format(
            sickbeard.indexerApi(self.indexer).config.get('name') + ',', str(self.indexerid) + ',', self.name))

        # Get IMDb_info from database
        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT * FROM imdb_info WHERE indexer_id = ?', [self.indexerid])

        if 0 < len(sqlResults):
            self.imdb_info = dict(zip(sqlResults[0].keys(), [(r, '')[None is r] for r in sqlResults[0]]))
        elif sickbeard.USE_IMDB_INFO:
            logger.log('%s: The next show update will attempt to find IMDb info for [%s]' %
                       (self.indexerid, self.name), logger.DEBUG)
            return

        self.dirty = False
        return True

    def loadFromIndexer(self, cache=True, tvapi=None, cachedSeason=None):

        # There's gotta be a better way of doing this but we don't wanna
        # change the cache value elsewhere
        if tvapi is None:
            lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()

            if not cache:
                lINDEXER_API_PARMS['cache'] = False

            if self.lang:
                lINDEXER_API_PARMS['language'] = self.lang

            if self.dvdorder != 0:
                lINDEXER_API_PARMS['dvdorder'] = True

            t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)

        else:
            t = tvapi

        myEp = t[self.indexerid, False]
        if None is myEp:
            if hasattr(t, 'show_not_found') and t.show_not_found:
                self.inc_not_found_count()
                logger.log('Show [%s] not found (maybe even removed?)' % self.name, logger.WARNING)
            else:
                logger.log('Show data [%s] not found' % self.name, logger.WARNING)
            return False
        self.reset_not_found_count()

        try:
            self.name = myEp['seriesname'].strip()
        except AttributeError:
            raise sickbeard.indexer_attributenotfound(
                "Found %s, but attribute 'seriesname' was empty." % (self.indexerid))

        if myEp:
            logger.log('%s: Loading show info [%s] from %s' % (
                self.indexerid, self.name, sickbeard.indexerApi(self.indexer).name))

        self.classification = dict_prevent_None(myEp, 'classification', 'Scripted')
        self.genre = dict_prevent_None(myEp, 'genre', '')
        self.network = dict_prevent_None(myEp, 'network', '')
        self.runtime = dict_prevent_None(myEp, 'runtime', '')

        self.imdbid = dict_prevent_None(myEp, 'imdb_id', '')

        if getattr(myEp, 'airs_dayofweek', None) is not None and getattr(myEp, 'airs_time', None) is not None:
            self.airs = ('%s %s' % (myEp['airs_dayofweek'], myEp['airs_time'])).strip()

        if getattr(myEp, 'firstaired', None) is not None:
            self.startyear = int(str(myEp["firstaired"]).split('-')[0])

        self.status = dict_prevent_None(myEp, 'status', '')
        self.overview = dict_prevent_None(myEp, 'overview', '')

    def load_imdb_info(self):

        if not sickbeard.USE_IMDB_INFO:
            return

        logger.log('Retrieving show info [%s] from IMDb' % self.name, logger.DEBUG)
        try:
            self._get_imdb_info()
        except Exception as e:
            logger.log('Error loading IMDb info: %s' % ex(e), logger.ERROR)
            logger.log('%s' % traceback.format_exc(), logger.ERROR)

    def check_imdb_redirect(self, imdb_id):
        page_url = 'https://www.imdb.com/title/{0}/'.format(imdb_id)
        try:
            response = requests.head(page_url, allow_redirects=True)
            if response.history and any(h for h in response.history if h.status_code == 301):
                return re.search(r'(tt\d{7})', response.url, flags=re.I).group(1)
            else:
                return None
        except (StandardError, Exception):
            return None

    def _get_imdb_info(self):

        if not self.imdbid and self.ids.get(indexermapper.INDEXER_IMDB, {'id': 0}).get('id', 0) <= 0:
            return

        imdb_info = {'imdb_id': self.imdbid or 'tt%07d' % self.ids[indexermapper.INDEXER_IMDB]['id'],
                     'title': '',
                     'year': '',
                     'akas': '',
                     'runtimes': self.runtime,
                     'genres': '',
                     'countries': '',
                     'country_codes': '',
                     'certificates': '',
                     'rating': '',
                     'votes': '',
                     'last_update': ''}

        imdb_id = None
        imdb_certificates = None
        try:
            imdb_id = str(self.imdbid or 'tt%07d' % self.ids[indexermapper.INDEXER_IMDB]['id'])
            redirect_check = self.check_imdb_redirect(imdb_id)
            if redirect_check:
                self._imdbid = redirect_check
                imdb_id = redirect_check
                imdb_info['imdb_id'] = self.imdbid
            i = imdbpie.Imdb(exclude_episodes=True)
            if not re.search(r'tt\d{7}', imdb_id, flags=re.I):
                logger.log('Not a valid imdbid: %s for show: %s' % (imdb_id, self.name), logger.WARNING)
                return
            imdb_ratings = i.get_title_ratings(imdb_id=imdb_id)
            imdb_akas = i.get_title_versions(imdb_id=imdb_id)
            imdb_tv = i.get_title_auxiliary(imdb_id=imdb_id)
            ipie = getattr(imdbpie.__dict__.get('imdbpie'), '_SIMPLE_GET_ENDPOINTS', None)
            if ipie:
                ipie.update({
                    u'get_title_certificates': u'/title/{imdb_id}/certificates',
                    u'get_title_parentalguide': u'/title/{imdb_id}/parentalguide',
                })
                imdb_certificates = i.get_title_certificates(imdb_id=imdb_id)
        except LookupError as e:
            logger.log('imdbid: %s not found. Error: %s' % (imdb_id, ex(e)), logger.WARNING)
            return
        except ImdbAPIError as e:
            logger.log('Imdb API Error: %s' % ex(e), logger.WARNING)
            return
        except (StandardError, Exception) as e:
            logger.log('Error: %s retrieving imdb id: %s' % (ex(e), imdb_id), logger.WARNING)
            return

        # ratings
        if isinstance(imdb_ratings.get('rating'), (int, float)):
            imdb_info['rating'] = tryFloat(imdb_ratings.get('rating'), '')
        if isinstance(imdb_ratings.get('ratingCount'), int):
            imdb_info['votes'] = tryInt(imdb_ratings.get('ratingCount'), '')

        # akas
        if isinstance(imdb_akas.get('alternateTitles'), (list, tuple)):
            imdb_info['akas'] = '|'.join(['%s::%s' % (t.get('region'), t.get('title'))
                                          for t in imdb_akas.get('alternateTitles') if isinstance(t, dict) and
                                          t.get('title') and t.get('region')])

        # tv
        if isinstance(imdb_tv.get('title'), basestring):
            imdb_info['title'] = imdb_tv.get('title')
        if isinstance(imdb_tv.get('year'), (int, basestring)):
            imdb_info['year'] = tryInt(imdb_tv.get('year'), '')
        if isinstance(imdb_tv.get('runningTimeInMinutes'), (int, basestring)):
            imdb_info['runtimes'] = tryInt(imdb_tv.get('runningTimeInMinutes'), '')
        if isinstance(imdb_tv.get('genres'), (list, tuple)):
            imdb_info['genres'] = '|'.join(filter(lambda v: v, imdb_tv.get('genres')))
        if isinstance(imdb_tv.get('origins'), list):
            imdb_info['country_codes'] = '|'.join(filter(lambda v: v, imdb_tv.get('origins')))

        # certificate
        if isinstance(imdb_certificates.get('certificates'), dict):
            certs = []
            for country, values in imdb_certificates.get('certificates').iteritems():
                if country and isinstance(values, (list, tuple)):
                    for cert in values:
                        if isinstance(cert, dict) and cert.get('certificate'):
                            extra_info = ''
                            if isinstance(cert.get('attributes'), list):
                                extra_info = ' (%s)' % ', '.join(cert.get('attributes'))
                            certs.append('%s:%s%s' % (country, cert.get('certificate'), extra_info))
            imdb_info['certificates'] = '|'.join(certs)
        if (not imdb_info['certificates'] and isinstance(imdb_tv.get('certificate'), dict)
                and isinstance(imdb_tv.get('certificate').get('certificate'), basestring)):
            imdb_info['certificates'] = '%s:%s' % (u'US', imdb_tv.get('certificate').get('certificate'))

        imdb_info['last_update'] = datetime.date.today().toordinal()

        # Rename dict keys without spaces for DB upsert
        self.imdb_info = dict(
            (k.replace(' ', '_'), k(v) if hasattr(v, 'keys') else v) for k, v in imdb_info.items())
        logger.log('%s: Obtained info from IMDb -> %s' % (self.indexerid, self.imdb_info), logger.DEBUG)

        logger.log('%s: Parsed latest IMDb show info for [%s]' % (self.indexerid, self.name))

    def nextEpisode(self):
        logger.log('%s: Finding the episode which airs next for: %s' % (self.indexerid, self.name), logger.DEBUG)

        curDate = datetime.date.today().toordinal()
        if not self.nextaired or self.nextaired and curDate > self.nextaired:
            myDB = db.DBConnection()
            sqlResults = myDB.select(
                'SELECT airdate, season, episode FROM tv_episodes WHERE showid = ? AND airdate >= ? AND status in (?,?,?) ORDER BY airdate ASC LIMIT 1',
                [self.indexerid, datetime.date.today().toordinal(), UNAIRED, WANTED, FAILED])

            if sqlResults == None or len(sqlResults) == 0:
                logger.log('%s: No episode found... need to implement a show status' % self.indexerid, logger.DEBUG)
                self.nextaired = ''
            else:
                logger.log('%s: Found episode %sx%s' % (self.indexerid, sqlResults[0]['season'], sqlResults[0]['episode']),
                           logger.DEBUG)
                self.nextaired = sqlResults[0]['airdate']

        return self.nextaired

    def deleteShow(self, full=False):

        sql_l = [["DELETE FROM tv_episodes WHERE showid = ? AND indexer = ?", [self.indexerid, self.indexer]],
                 ["DELETE FROM tv_shows WHERE indexer_id = ? AND indexer = ?", [self.indexerid, self.indexer]],
                 ["DELETE FROM imdb_info WHERE indexer_id = ?", [self.indexerid]],
                 ["DELETE FROM xem_refresh WHERE indexer_id = ? AND indexer = ?", [self.indexerid, self.indexer]],
                 ["DELETE FROM scene_numbering WHERE indexer_id = ? AND indexer = ?", [self.indexerid, self.indexer]],
                 ["DELETE FROM whitelist WHERE show_id = ?", [self.indexerid]],
                 ["DELETE FROM blacklist WHERE show_id = ?", [self.indexerid]],
                 ["DELETE FROM indexer_mapping WHERE indexer_id = ? AND indexer = ?", [self.indexerid, self.indexer]],
                 ["DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?", [self.indexer, self.indexerid]]]

        myDB = db.DBConnection()
        myDB.mass_action(sql_l)

        name_cache.remove_from_namecache(self.indexerid)

        action = ('delete', 'trash')[sickbeard.TRASH_REMOVE_SHOW]

        # remove self from show list
        sickbeard.showList = [x for x in sickbeard.showList if int(x.indexerid) != self.indexerid]

        # clear the cache
        ic = image_cache.ImageCache()
        for cache_obj in ek.ek(glob.glob, ic.poster_path(self.indexerid).replace('poster.jpg', '*')) \
                + ek.ek(glob.glob, ic.poster_thumb_path(self.indexerid).replace('poster.jpg', '*')) \
                + ek.ek(glob.glob, ic.fanart_path(self.indexerid).replace('%s.fanart.jpg' % self.indexerid, '')):
            cache_dir = ek.ek(os.path.isdir, cache_obj)
            result = helpers.remove_file(cache_obj, tree=cache_dir, log_level=logger.WARNING)
            if result:
                logger.log('%s cache %s %s' % (result, cache_dir and 'dir' or 'file', cache_obj))

        show_id = '%s' % self.indexerid
        if show_id in sickbeard.FANART_RATINGS:
            del sickbeard.FANART_RATINGS[show_id]

        # remove entire show folder
        if full:
            try:
                logger.log('Attempt to %s show folder %s' % (action, self._location))
                # check first the read-only attribute
                file_attribute = ek.ek(os.stat, self.location)[0]
                if not file_attribute & stat.S_IWRITE:
                    # File is read-only, so make it writeable
                    logger.log('Attempting to make writeable the read only folder %s' % self._location, logger.DEBUG)
                    try:
                        ek.ek(os.chmod, self.location, stat.S_IWRITE)
                    except:
                        logger.log('Unable to change permissions of %s' % self._location, logger.WARNING)

                result = helpers.remove_file(self.location, tree=True)
                if result:
                    logger.log('%s show folder %s' % (result, self._location))

            except exceptions.ShowDirNotFoundException:
                logger.log('Show folder does not exist, no need to %s %s' % (action, self._location), logger.WARNING)
            except OSError as e:
                logger.log('Unable to %s %s: %s / %s' % (action, self._location, repr(e), str(e)), logger.WARNING)

    def populateCache(self, force=False):
        cache_inst = image_cache.ImageCache()

        logger.log('Checking & filling cache for show %s' % self.name)
        cache_inst.fill_cache(self, force)

    def refreshDir(self):

        # make sure the show dir is where we think it is unless dirs are created on the fly
        if not ek.ek(os.path.isdir, self._location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
            return False

        # load from dir
        self.loadEpisodesFromDir()

        # run through all locations from DB, check that they exist
        logger.log('%s: Loading all episodes for [%s] with a location from the database' % (self.indexerid, self.name))

        myDB = db.DBConnection()
        sqlResults = myDB.select(
            'SELECT * FROM tv_episodes'
            ' WHERE showid = ? AND location != ""'
            ' ORDER BY season, episode DESC',
            [self.indexerid])

        kept = 0
        deleted = 0
        attempted = []
        sql_l = []
        for ep in sqlResults:
            curLoc = ek.ek(os.path.normpath, ep['location'])
            season = int(ep['season'])
            episode = int(ep['episode'])

            try:
                curEp = self.getEpisode(season, episode)
            except exceptions.EpisodeDeletedException:
                logger.log('The episode from [%s] was deleted while we were refreshing it, moving on to the next one' % self.name,
                           logger.DEBUG)
                continue

            # if the path exist and if it's in our show dir
            if (self.prune and curEp.location not in attempted and 0 < helpers.get_size(curEp.location) and
                    ek.ek(os.path.normpath, curLoc).startswith(ek.ek(os.path.normpath, self.location))):
                with curEp.lock:
                    if curEp.status in Quality.DOWNLOADED:
                        # locations repeat but attempt to delete once
                        attempted += curEp.location
                        if kept >= self.prune:
                            result = helpers.remove_file(curEp.location, prefix_failure=u'%s: ' % self.indexerid)
                            if result:
                                logger.log(u'%s: %s file %s' % (self.indexerid,
                                                                result, curEp.location), logger.DEBUG)
                                deleted += 1
                        else:
                            kept += 1

            # if the path doesn't exist or if it's not in our show dir
            if not ek.ek(os.path.isfile, curLoc) or not ek.ek(os.path.normpath, curLoc).startswith(
                    ek.ek(os.path.normpath, self.location)):

                # check if downloaded files still exist, update our data if this has changed
                if 1 != sickbeard.SKIP_REMOVED_FILES:
                    with curEp.lock:
                        # if it used to have a file associated with it and it doesn't anymore then set it to IGNORED
                        if curEp.location and curEp.status in Quality.DOWNLOADED:
                            if ARCHIVED == sickbeard.SKIP_REMOVED_FILES:
                                curEp.status = Quality.compositeStatus(
                                    ARCHIVED, Quality.qualityDownloaded(curEp.status))
                            else:
                                curEp.status = (sickbeard.SKIP_REMOVED_FILES, IGNORED)[not sickbeard.SKIP_REMOVED_FILES]
                            logger.log('%s: File no longer at location for s%02de%02d, episode removed and status changed to %s'
                                       % (str(self.indexerid), season, episode, statusStrings[curEp.status]),
                                       logger.DEBUG)
                            curEp.subtitles = list()
                            curEp.subtitles_searchcount = 0
                            curEp.subtitles_lastsearch = str(datetime.datetime.min)
                        curEp.location = ''
                        curEp.hasnfo = False
                        curEp.hastbn = False
                        curEp.release_name = ''

                        result = curEp.get_sql()
                        if None is not result:
                            sql_l.append(result)
            else:
                # the file exists, set its modify file stamp
                if sickbeard.AIRDATE_EPISODES:
                    curEp.airdateModifyStamp()

        if deleted:
            logger.log('%s: %s %s media file%s and kept %s most recent downloads' % (
                self.indexerid, ('Permanently deleted', 'Trashed')[sickbeard.TRASH_REMOVE_SHOW],
                deleted, helpers.maybe_plural(deleted), kept))

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)

    def downloadSubtitles(self, force=False):
        # TODO: Add support for force option
        if not ek.ek(os.path.isdir, self._location):
            logger.log('%s: Show directory doesn\'t exist, can\'t download subtitles' % self.indexerid, logger.DEBUG)
            return
        logger.log('%s: Downloading subtitles' % self.indexerid, logger.DEBUG)

        try:
            myDB = db.DBConnection()
            episodes = myDB.select(
                "SELECT location FROM tv_episodes WHERE showid = ? AND location NOT LIKE '' ORDER BY season DESC, episode DESC",
                [self.indexerid])

            for episodeLoc in episodes:
                episode = self.makeEpFromFile(episodeLoc['location'])
                subtitles = episode.downloadSubtitles(force=force)
        except Exception as e:
            logger.log('Error occurred when downloading subtitles: %s' % traceback.format_exc(), logger.ERROR)
            return

    def switchIndexer(self, old_indexer, old_indexerid, pausestatus_after=None):
        myDB = db.DBConnection()
        myDB.mass_action([['UPDATE tv_shows SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                        [self.indexer, self.indexerid, old_indexer, old_indexerid]],
                    ['UPDATE tv_episodes SET showid = ?, indexer = ?, indexerid = 0 WHERE indexer = ? AND showid = ?',
                        [self.indexerid, self.indexer, old_indexer, old_indexerid]],
                    ['UPDATE blacklist SET show_id = ? WHERE show_id = ?', [self.indexerid, old_indexerid]],
                    ['UPDATE history SET showid = ? WHERE showid = ?', [self.indexerid, old_indexerid]],
                    ['UPDATE imdb_info SET indexer_id = ? WHERE indexer_id = ?', [self.indexerid, old_indexerid]],
                    ['UPDATE scene_exceptions SET indexer_id = ? WHERE indexer_id = ?', [self.indexerid, old_indexerid]],
                    ['UPDATE scene_numbering SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                        [self.indexer, self.indexerid, old_indexer, old_indexerid]],
                    ['UPDATE whitelist SET show_id = ? WHERE show_id = ?', [self.indexerid, old_indexerid]],
                    ['UPDATE xem_refresh SET indexer = ?, indexer_id = ? WHERE indexer = ? AND indexer_id = ?',
                        [self.indexer, self.indexerid, old_indexer, old_indexerid]],
                    ['DELETE FROM tv_shows_not_found WHERE indexer = ? AND indexer_id = ?', [old_indexer, old_indexerid]]])

        myFailedDB = db.DBConnection('failed.db')
        myFailedDB.action('UPDATE history SET showid = ? WHERE showid = ?', [self.indexerid, old_indexerid])
        del_mapping(old_indexer, old_indexerid)
        self.ids[old_indexer]['status'] = MapStatus.NONE
        self.ids[self.indexer]['status'] = MapStatus.SOURCE
        self.ids[self.indexer]['id'] = self.indexerid
        if isinstance(self.imdb_info, dict):
            self.imdb_info['indexer_id'] = self.indexerid
        save_mapping(self)
        name_cache.remove_from_namecache(old_indexerid)

        image_cache_dir = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images')
        for path, dirs, files in ek.ek(os.walk, image_cache_dir):
            for filename in ek.ek(fnmatch.filter, files, '%s.*' % old_indexerid):
                cache_file = ek.ek(os.path.join, path, filename)
                new_cachefile = ek.ek(os.path.join, path, filename.replace(str(old_indexerid), str(self.indexerid)))
                try:
                    helpers.moveFile(cache_file, new_cachefile)
                except Exception as e:
                    logger.log('Unable to rename %s to %s: %s / %s' % (cache_file, new_cachefile, repr(e), str(e)),
                               logger.WARNING)

        ic = image_cache.ImageCache()
        cache_dir = ic.fanart_path(old_indexerid).replace('%s.fanart.jpg' % old_indexerid, '').rstrip('\/')
        new_cache_dir = ic.fanart_path(self.indexerid).replace('%s.fanart.jpg' % self.indexerid, '').rstrip('\/')
        try:
            helpers.moveFile(cache_dir, new_cache_dir)
        except Exception as e:
            logger.log('Unable to rename %s to %s: %s / %s' % (cache_dir, new_cache_dir, repr(e), str(e)),
                       logger.WARNING)

        rating = sickbeard.FANART_RATINGS.get('%s' % old_indexerid)
        if rating:
            del sickbeard.FANART_RATINGS['%s' % old_indexerid]
            sickbeard.FANART_RATINGS['%s' % self.indexerid] = rating
            sickbeard.save_config()

        name_cache.buildNameCache(self)
        self.reset_not_found_count()

        # force the update
        try:
            sickbeard.showQueueScheduler.action.updateShow(
                self, force=True, web=True, priority=QueuePriorities.VERYHIGH, pausestatus_after=pausestatus_after)
        except exceptions.CantUpdateException as e:
            logger.log('Unable to update this show. %s' % ex(e), logger.ERROR)

    def saveToDB(self, forceSave=False):

        if not self.dirty and not forceSave:
            logger.log('%s: Not saving show to db - record is not dirty' % self.indexerid, logger.DEBUG)
            return

        logger.log('%s: Saving show info to database' % self.indexerid, logger.DEBUG)

        controlValueDict = {'indexer_id': self.indexerid}
        newValueDict = {'indexer': self.indexer,
                        'show_name': self.name,
                        'location': self._location,
                        'network': self.network,
                        'genre': self.genre,
                        'classification': self.classification,
                        'runtime': self.runtime,
                        'quality': self.quality,
                        'airs': self.airs,
                        'status': self.status,
                        'flatten_folders': self.flatten_folders,
                        'paused': self.paused,
                        'air_by_date': self.air_by_date,
                        'anime': self.anime,
                        'scene': self.scene,
                        'sports': self.sports,
                        'subtitles': self.subtitles,
                        'dvdorder': self.dvdorder,
                        'archive_firstmatch': self.upgrade_once,
                        'startyear': self.startyear,
                        'lang': self.lang,
                        'imdb_id': self.imdbid,
                        'last_update_indexer': self.last_update_indexer,
                        'rls_ignore_words': self.rls_ignore_words,
                        'rls_require_words': self.rls_require_words,
                        'overview': self.overview,
                        'prune': self.prune,
                        'tag': self.tag,
        }

        myDB = db.DBConnection()
        myDB.upsert('tv_shows', newValueDict, controlValueDict)
        self.dirty = False

        if sickbeard.USE_IMDB_INFO and len(self.imdb_info):
            controlValueDict = {'indexer_id': self.indexerid}
            newValueDict = self.imdb_info

            myDB = db.DBConnection()
            myDB.upsert('imdb_info', newValueDict, controlValueDict)

    def __str__(self):
        return 'indexerid: %s\n' % self.indexerid \
               + 'indexer: %s\n' % self.indexerid \
               + 'name: %s\n' % self.name \
               + 'location: %s\n' % self._location \
               + ('', 'network: %s\n' % self.network)[self.network] \
               + ('', 'airs: %s\n' % self.airs)[self.airs] \
               + ('', 'status: %s\n' % self.status)[self.status] \
               + 'startyear: %s\n' % self.startyear \
               + ('', 'genre: %s\n' % self.genre)[self.genre] \
               + 'classification: %s\n' % self.classification \
               + 'runtime: %s\n' % self.runtime \
               + 'quality: %s\n' % self.quality \
               + 'scene: %s\n' % self.is_scene \
               + 'sports: %s\n' % self.is_sports \
               + 'anime: %s\n' % self.is_anime \
               + 'prune: %s\n' % self.prune

    def wantEpisode(self, season, episode, quality, manualSearch=False, multi_ep=False):

        logger.log('Checking if found %sepisode %sx%s is wanted at quality %s' %
                   (('', 'multi-part ')[multi_ep], season, episode, Quality.qualityStrings[quality]), logger.DEBUG)

        if not multi_ep:
            try:
                wq = getattr(self.episodes.get(season, {}).get(episode, {}), 'wantedQuality', None)
                if None is not wq:
                    if quality in wq:
                        curStatus, curQuality = Quality.splitCompositeStatus(self.episodes[season][episode].status)
                        if curStatus in (WANTED, UNAIRED, SKIPPED, FAILED):
                            logger.log('Existing episode status is wanted/unaired/skipped/failed, getting found episode',
                                       logger.DEBUG)
                            return True
                        elif manualSearch:
                            logger.log('Usually ignoring found episode, but forced search allows the quality, getting found'
                                       ' episode', logger.DEBUG)
                            return True
                        elif quality > curQuality:
                            logger.log(
                                'Episode already exists but the found episode has better quality, getting found episode',
                                logger.DEBUG)
                            return True
                    logger.log('None of the conditions were met, ignoring found episode', logger.DEBUG)
                    return False
            except (StandardError, Exception):
                pass

        # if the quality isn't one we want under any circumstances then just say no
        initialQualities, archiveQualities = Quality.splitQuality(self.quality)
        allQualities = list(set(initialQualities + archiveQualities))

        initial = '= (%s)' % ','.join([Quality.qualityStrings[qual] for qual in initialQualities])
        if 0 < len(archiveQualities):
            initial = '+ upgrade to %s + (%s)'\
                      % (initial, ','.join([Quality.qualityStrings[qual] for qual in archiveQualities]))
        logger.log('Want initial %s and found %s' % (initial, Quality.qualityStrings[quality]), logger.DEBUG)

        if quality not in allQualities:
            logger.log('Don\'t want this quality, ignoring found episode', logger.DEBUG)
            return False

        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT status FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ?',
                                 [self.indexerid, season, episode])

        if not sqlResults or not len(sqlResults):
            logger.log('Unable to find a matching episode in database, ignoring found episode', logger.DEBUG)
            return False

        curStatus, curQuality = Quality.splitCompositeStatus(int(sqlResults[0]['status']))
        epStatus_text = statusStrings[curStatus]

        logger.log('Existing episode status: %s (%s)' % (statusStrings[curStatus], epStatus_text), logger.DEBUG)

        # if we know we don't want it then just say no
        if curStatus in [IGNORED, ARCHIVED] + ([SKIPPED], [])[multi_ep] and not manualSearch:
            logger.log('Existing episode status is %signored/archived, ignoring found episode' %
                       ('skipped/', '')[multi_ep], logger.DEBUG)
            return False

        # if it's one of these then we want it as long as it's in our allowed initial qualities
        if quality in allQualities:
            if curStatus in [WANTED, UNAIRED, SKIPPED, FAILED] + ([], SNATCHED_ANY)[multi_ep]:
                logger.log('Existing episode status is wanted/unaired/skipped/failed, getting found episode', logger.DEBUG)
                return True
            elif manualSearch:
                logger.log(
                    'Usually ignoring found episode, but forced search allows the quality, getting found episode',
                    logger.DEBUG)
                return True
            else:
                logger.log('Quality is on wanted list, need to check if it\'s better than existing quality',
                           logger.DEBUG)

        downloadedStatusList = SNATCHED_ANY + [DOWNLOADED]
        # special case: already downloaded quality is not in any of the wanted Qualities
        if curStatus in downloadedStatusList and curQuality not in allQualities:
            wantedQualities = allQualities
        else:
            wantedQualities = archiveQualities

        # if we are re-downloading then we only want it if it's in our archiveQualities list and better than what we have
        if curStatus in downloadedStatusList and quality in wantedQualities and quality > curQuality:
            logger.log('Episode already exists but the found episode has better quality, getting found episode',
                       logger.DEBUG)
            return True
        else:
            logger.log('Episode already exists and the found episode has same/lower quality, ignoring found episode',
                       logger.DEBUG)

        logger.log('None of the conditions were met, ignoring found episode', logger.DEBUG)
        return False

    def getOverview(self, epStatus):
        return helpers.getOverview(epStatus, self.quality, self.upgrade_once)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.Lock()
        self.__dict__.update(d)


class TVEpisode(object):
    def __init__(self, show, season, episode, file='', show_sql=None):
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
        self._indexerid = 0
        self._file_size = 0
        self._release_name = ''
        self._is_proper = False
        self._version = 0
        self._release_group = ''

        # setting any of the above sets the dirty flag
        self.dirty = True

        self.show = show

        self.scene_season = 0
        self.scene_episode = 0
        self.scene_absolute_number = 0

        self._location = file

        self._indexer = int(self.show.indexer)

        self.lock = threading.Lock()

        self.specifyEpisode(self.season, self.episode, show_sql)

        self.relatedEps = []

        self.checkForMetaFiles()

        self.wantedQuality = []

    name = property(lambda self: self._name, dirty_setter('_name', basestring))
    season = property(lambda self: self._season, dirty_setter('_season'))
    episode = property(lambda self: self._episode, dirty_setter('_episode'))
    absolute_number = property(lambda self: self._absolute_number, dirty_setter('_absolute_number'))
    description = property(lambda self: self._description, dirty_setter('_description'))
    subtitles = property(lambda self: self._subtitles, dirty_setter('_subtitles'))
    subtitles_searchcount = property(lambda self: self._subtitles_searchcount, dirty_setter('_subtitles_searchcount'))
    subtitles_lastsearch = property(lambda self: self._subtitles_lastsearch, dirty_setter('_subtitles_lastsearch'))
    airdate = property(lambda self: self._airdate, dirty_setter('_airdate'))
    hasnfo = property(lambda self: self._hasnfo, dirty_setter('_hasnfo'))
    hastbn = property(lambda self: self._hastbn, dirty_setter('_hastbn'))
    status = property(lambda self: self._status, dirty_setter('_status'))
    indexer = property(lambda self: self._indexer, dirty_setter('_indexer'))
    indexerid = property(lambda self: self._indexerid, dirty_setter('_indexerid'))
    # location = property(lambda self: self._location, dirty_setter('_location'))
    file_size = property(lambda self: self._file_size, dirty_setter('_file_size'))
    release_name = property(lambda self: self._release_name, dirty_setter('_release_name'))
    is_proper = property(lambda self: self._is_proper, dirty_setter('_is_proper'))
    version = property(lambda self: self._version, dirty_setter('_version'))
    release_group = property(lambda self: self._release_group, dirty_setter('_release_group'))

    def _set_location(self, new_location):
        log_vals = (('clears', ''), ('sets', ' to ' + new_location))[any(new_location)]
        logger.log(u'Setter %s location%s' % log_vals, logger.DEBUG)

        # self._location = newLocation
        dirty_setter('_location')(self, new_location)

        if new_location and ek.ek(os.path.isfile, new_location):
            self.file_size = ek.ek(os.path.getsize, new_location)
        else:
            self.file_size = 0

    location = property(lambda self: self._location, _set_location)

    def refreshSubtitles(self):
        """Look for subtitles files and refresh the subtitles property"""
        self.subtitles = subtitles.subtitlesLanguages(self.location)

    def downloadSubtitles(self, force=False):
        # TODO: Add support for force option
        if not ek.ek(os.path.isfile, self.location):
            logger.log('%s: Episode file doesn\'t exist, can\'t download subtitles for episode %sx%s' %
                       (self.show.indexerid, self.season, self.episode), logger.DEBUG)
            return
        logger.log('%s: Downloading subtitles for episode %sx%s' % (self.show.indexerid, self.season, self.episode),
                   logger.DEBUG)

        previous_subtitles = self.subtitles

        try:
            need_languages = set(sickbeard.SUBTITLES_LANGUAGES) - set(self.subtitles)
            subtitles = subliminal.download_subtitles([self.location], languages=need_languages,
                                                      services=sickbeard.subtitles.getEnabledServiceList(), force=force,
                                                      multi=True, cache_dir=sickbeard.CACHE_DIR)

            if sickbeard.SUBTITLES_DIR:
                for video in subtitles:
                    subs_new_path = ek.ek(os.path.join, ek.ek(os.path.dirname, video.path), sickbeard.SUBTITLES_DIR)
                    dir_exists = helpers.makeDir(subs_new_path)
                    if not dir_exists:
                        logger.log('Unable to create subtitles folder %s' % subs_new_path, logger.ERROR)
                    else:
                        helpers.chmodAsParent(subs_new_path)

                    for subtitle in subtitles.get(video):
                        new_file_path = ek.ek(os.path.join, subs_new_path, ek.ek(os.path.basename, subtitle.path))
                        helpers.moveFile(subtitle.path, new_file_path)
                        helpers.chmodAsParent(new_file_path)
            else:
                for video in subtitles:
                    for subtitle in subtitles.get(video):
                        helpers.chmodAsParent(subtitle.path)

        except Exception as e:
            logger.log('Error occurred when downloading subtitles: %s' % traceback.format_exc(), logger.ERROR)
            return

        self.refreshSubtitles()
        self.subtitles_searchcount = self.subtitles_searchcount + 1 if self.subtitles_searchcount else 1  # added the if because sometime it raise an error
        self.subtitles_lastsearch = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.saveToDB()

        newsubtitles = set(self.subtitles).difference(set(previous_subtitles))

        if newsubtitles:
            try:
                subtitleList = ", ".join(subliminal.language.Language(x).name for x in newsubtitles)
            except(StandardError, Exception):
                logger.log('Could not parse a language to use to fetch subtitles for episode %sx%s' %
                           (self.season, self.episode), logger.DEBUG)
                return
            logger.log('%s: Downloaded %s subtitles for episode %sx%s' %
                       (self.show.indexerid, subtitleList, self.season, self.episode), logger.DEBUG)

            notifiers.notify_subtitle_download(self.prettyName(), subtitleList)

        else:
            logger.log('%s: No subtitles downloaded for episode %sx%s' % (self.show.indexerid, self.season, self.episode),
                       logger.DEBUG)

        if sickbeard.SUBTITLES_HISTORY:
            for video in subtitles:
                for subtitle in subtitles.get(video):
                    history.log_subtitle(self.show.indexerid, self.season, self.episode, self.status, subtitle)

        return subtitles

    def checkForMetaFiles(self):

        oldhasnfo = self.hasnfo
        oldhastbn = self.hastbn

        cur_nfo = False
        cur_tbn = False

        # check for nfo and tbn
        if ek.ek(os.path.isfile, self.location):
            for cur_provider in sickbeard.metadata_provider_dict.values():
                if cur_provider.episode_metadata:
                    new_result = cur_provider._has_episode_metadata(self)
                else:
                    new_result = False
                cur_nfo = new_result or cur_nfo

                if cur_provider.episode_thumbnails:
                    new_result = cur_provider._has_episode_thumb(self)
                else:
                    new_result = False
                cur_tbn = new_result or cur_tbn

        self.hasnfo = cur_nfo
        self.hastbn = cur_tbn

        # if either setting has changed return true, if not return false
        return oldhasnfo != self.hasnfo or oldhastbn != self.hastbn

    def specifyEpisode(self, season, episode, show_sql=None):

        sqlResult = self.loadFromDB(season, episode, show_sql)

        if not sqlResult:
            # only load from NFO if we didn't load from DB
            if ek.ek(os.path.isfile, self.location):
                try:
                    self.loadFromNFO(self.location)
                except exceptions.NoNFOException:
                    logger.log('%s: There was an error loading the NFO for episode %sx%s' %
                               (self.show.indexerid, season, episode), logger.ERROR)
                    pass

                # if we tried loading it from NFO and didn't find the NFO, try the Indexers
                if not self.hasnfo:
                    try:
                        result = self.loadFromIndexer(season, episode)
                    except exceptions.EpisodeDeletedException:
                        result = False

                    # if we failed SQL *and* NFO, Indexers then fail
                    if not result:
                        raise exceptions.EpisodeNotFoundException(
                            'Couldn\'t find episode %sx%s' % (season, episode))

    def loadFromDB(self, season, episode, show_sql=None):
        logger.log('%s: Loading episode details from DB for episode %sx%s' % (self.show.indexerid, season, episode),
                   logger.DEBUG)

        sql_results = None
        if show_sql:
            sql_results = [s for s in show_sql if episode == s['episode'] and season == s['season']]
        if not sql_results:
            myDB = db.DBConnection()
            sql_results = myDB.select('SELECT * FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ?',
                                     [self.show.indexerid, season, episode])

        if len(sql_results) > 1:
            raise exceptions.MultipleDBEpisodesException('Your DB has two records for the same show somehow.')
        elif len(sql_results) == 0:
            logger.log('%s: Episode %sx%s not found in the database' % (self.show.indexerid, self.season, self.episode),
                       logger.DEBUG)
            return False
        else:
            # NAMEIT logger.log(u'AAAAA from' + str(self.season)+'x'+str(self.episode) + ' -' + self.name + ' to ' + str(sql_results[0]['name']))
            if sql_results[0]['name']:
                self.name = sql_results[0]['name']

            self.season = season
            self.episode = episode
            self.absolute_number = sql_results[0]['absolute_number']
            self.description = sql_results[0]['description']
            if not self.description:
                self.description = ''
            if sql_results[0]['subtitles'] and sql_results[0]['subtitles']:
                self.subtitles = sql_results[0]['subtitles'].split(',')
            self.subtitles_searchcount = sql_results[0]['subtitles_searchcount']
            self.subtitles_lastsearch = sql_results[0]['subtitles_lastsearch']
            self.airdate = datetime.date.fromordinal(int(sql_results[0]['airdate']))
            # logger.log(u'1 Status changes from ' + str(self.status) + ' to ' + str(sql_results[0]['status']), logger.DEBUG)
            if sql_results[0]['status'] is not None:
                self.status = int(sql_results[0]['status'])

            # don't overwrite my location
            if sql_results[0]['location'] and sql_results[0]['location']:
                self.location = ek.ek(os.path.normpath, sql_results[0]['location'])
            if sql_results[0]['file_size']:
                self.file_size = int(sql_results[0]['file_size'])
            else:
                self.file_size = 0

            self.indexerid = int(sql_results[0]['indexerid'])
            self.indexer = int(sql_results[0]['indexer'])

            sickbeard.scene_numbering.xem_refresh(self.show.indexerid, self.show.indexer)

            try:
                self.scene_season = int(sql_results[0]['scene_season'])
            except:
                self.scene_season = 0

            try:
                self.scene_episode = int(sql_results[0]['scene_episode'])
            except:
                self.scene_episode = 0

            try:
                self.scene_absolute_number = int(sql_results[0]['scene_absolute_number'])
            except:
                self.scene_absolute_number = 0

            if self.scene_absolute_number == 0:
                self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                    self.show.indexerid,
                    self.show.indexer,
                    absolute_number=self.absolute_number,
                    season=self.season, episode=episode
                )

            if self.scene_season == 0 or self.scene_episode == 0:
                self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                    self.show.indexerid,
                    self.show.indexer,
                    self.season, self.episode
                )

            if sql_results[0]['release_name'] is not None:
                self.release_name = sql_results[0]['release_name']

            if sql_results[0]['is_proper']:
                self.is_proper = int(sql_results[0]['is_proper'])

            if sql_results[0]['version']:
                self.version = int(sql_results[0]['version'])

            if sql_results[0]['release_group'] is not None:
                self.release_group = sql_results[0]['release_group']

            self.dirty = False
            return True

    def loadFromIndexer(self, season=None, episode=None, cache=True, tvapi=None, cachedSeason=None, update=False):

        if None is season:
            season = self.season
        if None is episode:
            episode = self.episode

        logger.log('%s: Loading episode details from %s  for episode %sx%s' %
                   (self.show.indexerid, sickbeard.indexerApi(self.show.indexer).name, season, episode), logger.DEBUG)

        indexer_lang = self.show.lang

        try:
            if None is cachedSeason:
                if None is tvapi:
                    lINDEXER_API_PARMS = sickbeard.indexerApi(self.indexer).api_params.copy()

                    if not cache:
                        lINDEXER_API_PARMS['cache'] = False

                    if indexer_lang:
                        lINDEXER_API_PARMS['language'] = indexer_lang

                    if 0 != self.show.dvdorder:
                        lINDEXER_API_PARMS['dvdorder'] = True

                    t = sickbeard.indexerApi(self.indexer).indexer(**lINDEXER_API_PARMS)
                else:
                    t = tvapi
                myEp = t[self.show.indexerid][season][episode]
            else:
                myEp = cachedSeason[episode]

        except (sickbeard.indexer_error, IOError) as e:
            logger.log('%s threw up an error: %s' % (sickbeard.indexerApi(self.indexer).name, ex(e)), logger.DEBUG)
            # if the episode is already valid just log it, if not throw it up
            if self.name:
                logger.log('%s timed out but we have enough info from other sources, allowing the error' %
                           sickbeard.indexerApi(self.indexer).name, logger.DEBUG)
                return
            else:
                logger.log('%s timed out, unable to create the episode' % sickbeard.indexerApi(self.indexer).name,
                           logger.ERROR)
                return False
        except (sickbeard.indexer_episodenotfound, sickbeard.indexer_seasonnotfound):
            logger.log('Unable to find the episode on %s... has it been removed? Should I delete from db?' %
                       sickbeard.indexerApi(self.indexer).name, logger.DEBUG)
            # if I'm no longer on the Indexers but I once was then delete myself from the DB
            if -1 != self.indexerid and helpers.should_delete_episode(self.status):
                self.deleteEpisode()
            return

        if getattr(myEp, 'absolute_number', None) in (None, ''):
            logger.log('This episode (%s - %sx%s) has no absolute number on %s' %
                       (self.show.name, season, episode, sickbeard.indexerApi(self.indexer).name), logger.DEBUG)
        else:
            logger.log('%s: The absolute_number for %sx%s is : %s' %
                       (self.show.indexerid, season, episode, myEp['absolute_number']), logger.DEBUG)
            self.absolute_number = int(myEp['absolute_number'])

        self.name = dict_prevent_None(myEp, 'episodename', '')
        self.season = season
        self.episode = episode

        sickbeard.scene_numbering.xem_refresh(self.show.indexerid, self.show.indexer)

        self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
            self.show.indexerid,
            self.show.indexer,
            absolute_number=self.absolute_number,
            season=self.season, episode=self.episode
        )

        self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
            self.show.indexerid,
            self.show.indexer,
            self.season, self.episode
        )

        self.description = dict_prevent_None(myEp, 'overview', '')

        firstaired = getattr(myEp, 'firstaired', None)
        if None is firstaired or firstaired in '0000-00-00':
            firstaired = str(datetime.date.fromordinal(1))
        rawAirdate = [int(x) for x in firstaired.split('-')]

        old_airdate_future = self.airdate == datetime.date.fromordinal(1) or self.airdate >= datetime.date.today()
        try:
            self.airdate = datetime.date(rawAirdate[0], rawAirdate[1], rawAirdate[2])
        except (ValueError, IndexError):
            logger.log('Malformed air date retrieved from %s (%s - %sx%s)' %
                       (sickbeard.indexerApi(self.indexer).name, self.show.name, season, episode), logger.ERROR)
            # if I'm incomplete on TVDB but I once was complete then just delete myself from the DB for now
            if -1 != self.indexerid and helpers.should_delete_episode(self.status):
                self.deleteEpisode()
            return False

        # early conversion to int so that episode doesn't get marked dirty
        self.indexerid = getattr(myEp, 'id', None)
        if None is self.indexerid:
            logger.log('Failed to retrieve ID from %s' % sickbeard.indexerApi(self.indexer).name, logger.ERROR)
            if helpers.should_delete_episode(self.status):
                self.deleteEpisode()
            return False

        # don't update show status if show dir is missing, unless it's missing on purpose
        if not ek.ek(os.path.isdir,
                     self.show._location) and not sickbeard.CREATE_MISSING_SHOW_DIRS and not sickbeard.ADD_SHOWS_WO_DIR:
            logger.log(
                'The show directory is missing, not bothering to change the episode statuses since it\'d probably be invalid')
            return

        if self.location:
            logger.log('%s: Setting status for %sx%s based on status %s and existence of %s' %
                       (self.show.indexerid, season, episode, statusStrings[self.status], self.location), logger.DEBUG)

        # if we don't have the file
        if not ek.ek(os.path.isfile, self.location):

            if self.status in [SKIPPED, UNAIRED, UNKNOWN, WANTED]:
                today = datetime.date.today()
                delta = datetime.timedelta(days=1)
                very_old_delta = datetime.timedelta(days=90)
                show_time = network_timezones.parse_date_time(self.airdate.toordinal(), self.show.airs, self.show.network)
                show_length = datetime.timedelta(minutes=helpers.tryInt(self.show.runtime, 60))
                tz_now = datetime.datetime.now(network_timezones.sb_timezone)
                future_airtime = (self.airdate > (today + delta) or
                                  (not self.airdate < (today - delta) and ((show_time + show_length) > tz_now)))
                very_old_airdate = datetime.date.fromordinal(1) < self.airdate < (today - very_old_delta)

                # if this episode hasn't aired yet set the status to UNAIRED
                if future_airtime:
                    msg = 'Episode airs in the future, marking it %s'
                    self.status = UNAIRED

                # if there's no airdate then set it to unaired (and respect ignored)
                elif self.airdate == datetime.date.fromordinal(1):
                    if IGNORED == self.status:
                        msg = 'Episode has no air date and marked %s, no change'
                    else:
                        msg = 'Episode has no air date, marking it %s'
                        self.status = UNAIRED

                # if the airdate is in the past
                elif UNAIRED == self.status:
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self.status], ','.join([(' is a special', '')[0 < self.season],
                                                              ('', ' is paused')[self.show.paused]])) + '%s')
                    self.status = (SKIPPED, WANTED)[0 < self.season and not self.show.paused and not very_old_airdate]

                # if still UNKNOWN or SKIPPED with the deprecated future airdate method
                elif UNKNOWN == self.status or (SKIPPED == self.status and old_airdate_future):
                    msg = ('Episode status %s%s, with air date in the past, marking it ' % (
                        statusStrings[self.status], ','.join([
                            ('', ' has old future date format')[SKIPPED == self.status and old_airdate_future],
                            ('', ' is being updated')[bool(update)], (' is a special', '')[0 < self.season]])) + '%s')
                    self.status = (SKIPPED, WANTED)[update and not self.show.paused and 0 < self.season
                                                    and not very_old_airdate]

                else:
                    msg = 'Not touching episode status %s, with air date in the past, because there is no file'

            else:
                msg = 'Not touching episode status %s, because there is no file'

            logger.log(msg % statusStrings[self.status], logger.DEBUG)

        # if we have a media file then it's downloaded
        elif sickbeard.helpers.has_media_ext(self.location):
            # leave propers alone, you have to either post-process them or manually change them back
            if self.status not in Quality.SNATCHED_ANY + Quality.DOWNLOADED + Quality.ARCHIVED:
                msg = '(1) Status changes from %s to ' % statusStrings[self.status]
                self.status = Quality.statusFromNameOrFile(self.location, anime=self.show.is_anime)
                logger.log('%s%s' % (msg, statusStrings[self.status]), logger.DEBUG)

        # shouldn't get here probably
        else:
            msg = '(2) Status changes from %s to ' % statusStrings[self.status]
            self.status = UNKNOWN
            logger.log('%s%s' % (msg, statusStrings[self.status]), logger.DEBUG)

    def loadFromNFO(self, location):

        if not ek.ek(os.path.isdir, self.show._location):
            logger.log('%s: The show directory is missing, not bothering to try loading the episode NFO' % self.show.indexerid)
            return

        logger.log('%s: Loading episode details from the NFO file associated with %s' % (self.show.indexerid, location),
            logger.DEBUG)

        self.location = location

        if self.location != "":

            if UNKNOWN == self.status and sickbeard.helpers.has_media_ext(self.location):
                status_quality = Quality.statusFromNameOrFile(self.location, anime=self.show.is_anime)
                logger.log('(3) Status changes from %s to %s' % (self.status, status_quality), logger.DEBUG)
                self.status = status_quality

            nfoFile = sickbeard.helpers.replaceExtension(self.location, 'nfo')
            logger.log('%s: Using NFO name %s' % (self.show.indexerid, nfoFile), logger.DEBUG)

            if ek.ek(os.path.isfile, nfoFile):
                try:
                    showXML = etree.ElementTree(file=nfoFile)
                except (SyntaxError, ValueError) as e:
                    logger.log('Error loading the NFO, backing up the NFO and skipping for now: %s' % ex(e),
                               logger.ERROR)  # TODO: figure out what's wrong and fix it
                    try:
                        ek.ek(os.rename, nfoFile, '%s.old' % nfoFile)
                    except Exception as e:
                        logger.log(
                            'Failed to rename your episode\'s NFO file - you need to delete it or fix it: %s' % ex(e),
                            logger.ERROR)
                    raise exceptions.NoNFOException('Error in NFO format')

                for epDetails in showXML.getiterator('episodedetails'):
                    if epDetails.findtext('season') is None or int(epDetails.findtext('season')) != self.season or \
                                    epDetails.findtext('episode') is None or int(
                            epDetails.findtext('episode')) != self.episode:
                        logger.log('%s: NFO has an <episodedetails> block for a different episode - wanted %sx%s but got %sx%s' %
                                   (self.show.indexerid, self.season, self.episode, epDetails.findtext('season'),
                                    epDetails.findtext('episode')), logger.DEBUG)
                        continue

                    if epDetails.findtext('title') is None or epDetails.findtext('aired') is None:
                        raise exceptions.NoNFOException('Error in NFO format (missing episode title or airdate)')

                    self.name = epDetails.findtext('title')
                    self.episode = int(epDetails.findtext('episode'))
                    self.season = int(epDetails.findtext('season'))

                    sickbeard.scene_numbering.xem_refresh(self.show.indexerid, self.show.indexer)

                    self.scene_absolute_number = sickbeard.scene_numbering.get_scene_absolute_numbering(
                        self.show.indexerid,
                        self.show.indexer,
                        absolute_number=self.absolute_number,
                        season=self.season, episode=self.episode
                    )

                    self.scene_season, self.scene_episode = sickbeard.scene_numbering.get_scene_numbering(
                        self.show.indexerid,
                        self.show.indexer,
                        self.season, self.episode
                    )

                    self.description = epDetails.findtext('plot')
                    if self.description is None:
                        self.description = ''

                    if epDetails.findtext('aired'):
                        rawAirdate = [int(x) for x in epDetails.findtext('aired').split("-")]
                        self.airdate = datetime.date(rawAirdate[0], rawAirdate[1], rawAirdate[2])
                    else:
                        self.airdate = datetime.date.fromordinal(1)

                    self.hasnfo = True
            else:
                self.hasnfo = False

            if ek.ek(os.path.isfile, sickbeard.helpers.replaceExtension(nfoFile, 'tbn')):
                self.hastbn = True
            else:
                self.hastbn = False

    def __str__(self):

        return '%s - %sx%s - %s\n' % (self.show.name, self.season, self.episode, self.name) \
               + 'location: %s\n' % self.location \
               + 'description: %s\n' % self.description \
               + 'subtitles: %s\n' % ','.join(self.subtitles) \
               + 'subtitles_searchcount: %s\n' % self.subtitles_searchcount \
               + 'subtitles_lastsearch: %s\n' % self.subtitles_lastsearch \
               + 'airdate: %s (%s)\n' % (self.airdate.toordinal(), self.airdate) \
               + 'hasnfo: %s\n' % self.hasnfo \
               + 'hastbn: %s\n' % self.hastbn \
               + 'status: %s\n' % self.status

    def createMetaFiles(self):

        if not ek.ek(os.path.isdir, self.show._location):
            logger.log('%s: The show directory is missing, not bothering to try to create metadata' % self.show.indexerid)
            return

        self.createNFO()
        self.createThumbnail()

        if self.checkForMetaFiles():
            self.saveToDB()

    def createNFO(self):

        result = False

        for cur_provider in sickbeard.metadata_provider_dict.values():
            result = cur_provider.create_episode_metadata(self) or result

        return result

    def createThumbnail(self):

        result = False

        for cur_provider in sickbeard.metadata_provider_dict.values():
            result = cur_provider.create_episode_thumb(self) or result

        return result

    def deleteEpisode(self):

        logger.log('Deleting %s %sx%s from the DB' % (self.show.name, self.season, self.episode), logger.DEBUG)

        # remove myself from the show dictionary
        if self.show.getEpisode(self.season, self.episode, noCreate=True) == self:
            logger.log('Removing myself from my show\'s list', logger.DEBUG)
            del self.show.episodes[self.season][self.episode]

        # delete myself from the DB
        logger.log('Deleting myself from the database', logger.DEBUG)
        myDB = db.DBConnection()
        sql = 'DELETE FROM tv_episodes WHERE showid=%s AND indexer=%s AND season=%s AND episode=%s' % \
              (self.show.indexerid, self.show.indexer, self.season, self.episode)
        myDB.action(sql)

        raise exceptions.EpisodeDeletedException()

    def get_sql(self, forceSave=False):
        """
        Creates SQL queue for this episode if any of its data has been changed since the last save.

        forceSave: If True it will create SQL queue even if no data has been changed since the
                    last save (aka if the record is not dirty).
        """

        if not self.dirty and not forceSave:
            logger.log('%s: Not creating SQL queue - record is not dirty' % self.show.indexerid, logger.DEBUG)
            return

        self.dirty = False
        return [
            'INSERT OR REPLACE INTO tv_episodes (episode_id, indexerid, indexer, name, description, subtitles, '
            'subtitles_searchcount, subtitles_lastsearch, airdate, hasnfo, hastbn, status, location, file_size, '
            'release_name, is_proper, showid, season, episode, absolute_number, version, release_group, '
            'scene_absolute_number, scene_season, scene_episode) VALUES '
            '((SELECT episode_id FROM tv_episodes WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?)'
            ',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'
            '(SELECT scene_absolute_number FROM tv_episodes WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),'
            '(SELECT scene_season FROM tv_episodes WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?),'
            '(SELECT scene_episode FROM tv_episodes WHERE indexer = ? AND showid = ? AND season = ? AND episode = ?));',
            [self.show.indexer, self.show.indexerid, self.season, self.episode, self.indexerid, self.indexer, self.name,
             self.description,
             ','.join([sub for sub in self.subtitles]), self.subtitles_searchcount, self.subtitles_lastsearch,
             self.airdate.toordinal(), self.hasnfo, self.hastbn, self.status, self.location, self.file_size,
             self.release_name, self.is_proper, self.show.indexerid, self.season, self.episode,
             self.absolute_number, self.version, self.release_group,
             self.show.indexer, self.show.indexerid, self.season, self.episode,
             self.show.indexer, self.show.indexerid, self.season, self.episode,
             self.show.indexer, self.show.indexerid, self.season, self.episode]]

    def saveToDB(self, forceSave=False):
        """
        Saves this episode to the database if any of its data has been changed since the last save.

        forceSave: If True it will save to the database even if no data has been changed since the
                    last save (aka if the record is not dirty).
        """

        if not self.dirty and not forceSave:
            logger.log('%s: Not saving episode to db - record is not dirty' % self.show.indexerid, logger.DEBUG)
            return

        logger.log('%s: Saving episode details to database' % self.show.indexerid, logger.DEBUG)

        logger.log('STATUS IS %s' % statusStrings[self.status], logger.DEBUG)

        newValueDict = {'indexerid': self.indexerid,
                        'indexer': self.indexer,
                        'name': self.name,
                        'description': self.description,
                        'subtitles': ','.join([sub for sub in self.subtitles]),
                        'subtitles_searchcount': self.subtitles_searchcount,
                        'subtitles_lastsearch': self.subtitles_lastsearch,
                        'airdate': self.airdate.toordinal(),
                        'hasnfo': self.hasnfo,
                        'hastbn': self.hastbn,
                        'status': self.status,
                        'location': self.location,
                        'file_size': self.file_size,
                        'release_name': self.release_name,
                        'is_proper': self.is_proper,
                        'absolute_number': self.absolute_number,
                        'version': self.version,
                        'release_group': self.release_group
        }
        controlValueDict = {'showid': self.show.indexerid,
                            'season': self.season,
                            'episode': self.episode}

        # use a custom update/insert method to get the data into the DB
        myDB = db.DBConnection()
        myDB.upsert('tv_episodes', newValueDict, controlValueDict)
        self.dirty = False

    def fullPath(self):
        if self.location == None or self.location == "":
            return None
        else:
            return ek.ek(os.path.join, self.show.location, self.location)

    def createStrings(self, pattern=None):
        patterns = [
            '%S.N.S%SE%0E',
            '%S.N.S%0SE%E',
            '%S.N.S%SE%E',
            '%S.N.S%0SE%0E',
            '%SN S%SE%0E',
            '%SN S%0SE%E',
            '%SN S%SE%E',
            '%SN S%0SE%0E'

        ]

        strings = []
        if not pattern:
            for p in patterns:
                strings += [self._format_pattern(p)]
            return strings
        return self._format_pattern(pattern)

    def prettyName(self):
        """
        Returns the name of this episode in a "pretty" human-readable format. Used for logging
        and notifications and such.

        Returns: A string representing the episode's name and season/ep numbers
        """

        if self.show.anime and not self.show.scene:
            return self._format_pattern('%SN - %AB - %EN')
        elif self.show.air_by_date:
            return self._format_pattern('%SN - %AD - %EN')

        return self._format_pattern('%SN - %Sx%0E - %EN')

    def _ep_name(self):
        """
        Returns the name of the episode to use during renaming. Combines the names of related episodes.
        Eg. "Ep Name (1)" and "Ep Name (2)" becomes "Ep Name"
            "Ep Name" and "Other Ep Name" becomes "Ep Name & Other Ep Name"
        """

        multiNameRegex = '(.*) \(\d{1,2}\)'

        self.relatedEps = sorted(self.relatedEps, key=lambda x: x.episode)

        if len(self.relatedEps) == 0:
            goodName = self.name

        else:
            goodName = ''

            singleName = True
            curGoodName = None

            for curName in [self.name] + [x.name for x in self.relatedEps]:
                match = re.match(multiNameRegex, curName)
                if not match:
                    singleName = False
                    break

                if curGoodName == None:
                    curGoodName = match.group(1)
                elif curGoodName != match.group(1):
                    singleName = False
                    break

            if singleName:
                goodName = curGoodName
            else:
                goodName = self.name
                for relEp in self.relatedEps:
                    goodName += " & " + relEp.name

        return goodName

    def _replace_map(self):
        """
        Generates a replacement map for this episode which maps all possible custom naming patterns to the correct
        value for this episode.

        Returns: A dict with patterns as the keys and their replacement values as the values.
        """

        ep_name = self._ep_name()

        def dot(name):
            return helpers.sanitizeSceneName(name)

        def us(name):
            return re.sub('[ -]', '_', name)

        def release_name(name, is_anime=False):
            if name:
                name = helpers.remove_non_release_groups(name, is_anime)
            return name

        def release_group(show, name):
            if name:
                name = helpers.remove_non_release_groups(name, show.is_anime)
            else:
                return ''

            try:
                np = NameParser(name, showObj=show, naming_pattern=True)
                parse_result = np.parse(name)
            except (InvalidNameException, InvalidShowException) as e:
                logger.log('Unable to get parse release_group: %s' % ex(e), logger.DEBUG)
                return ''

            if not parse_result.release_group:
                return ''
            return parse_result.release_group

        epStatus, epQual = Quality.splitCompositeStatus(self.status)  # @UnusedVariable

        if sickbeard.NAMING_STRIP_YEAR:
            show_name = re.sub('\(\d+\)$', '', self.show.name).rstrip()
        else:
            show_name = self.show.name

        return {
            '%SN': show_name,
            '%S.N': dot(show_name),
            '%S_N': us(show_name),
            '%EN': ep_name,
            '%E.N': dot(ep_name),
            '%E_N': us(ep_name),
            '%QN': Quality.qualityStrings[epQual],
            '%Q.N': dot(Quality.qualityStrings[epQual]),
            '%Q_N': us(Quality.qualityStrings[epQual]),
            '%S': str(self.season),
            '%0S': '%02d' % self.season,
            '%E': str(self.episode),
            '%0E': '%02d' % self.episode,
            '%XS': str(self.scene_season),
            '%0XS': '%02d' % self.scene_season,
            '%XE': str(self.scene_episode),
            '%0XE': '%02d' % self.scene_episode,
            '%AB': '%(#)03d' % {'#': self.absolute_number},
            '%XAB': '%(#)03d' % {'#': self.scene_absolute_number},
            '%RN': release_name(self.release_name, self.show.is_anime),
            '%RG': release_group(self.show, self.release_name),
            '%AD': str(self.airdate).replace('-', ' '),
            '%A.D': str(self.airdate).replace('-', '.'),
            '%A_D': us(str(self.airdate)),
            '%A-D': str(self.airdate),
            '%Y': str(self.airdate.year),
            '%M': str(self.airdate.month),
            '%D': str(self.airdate.day),
            '%0M': '%02d' % self.airdate.month,
            '%0D': '%02d' % self.airdate.day,
            '%RT': "PROPER" if self.is_proper else "",
            '%V': 'v%s' % self.version if self.show.is_anime and self.version > 1 else '',
        }

    def _format_string(self, pattern, replace_map):
        """
        Replaces all template strings with the correct value
        """

        result_name = pattern

        # do the replacements
        for cur_replacement in sorted(replace_map.keys(), reverse=True):
            result_name = result_name.replace(cur_replacement, helpers.sanitizeFileName(replace_map[cur_replacement]))
            result_name = result_name.replace(cur_replacement.lower(),
                                              helpers.sanitizeFileName(replace_map[cur_replacement].lower()))

        return result_name

    def _format_pattern(self, pattern=None, multi=None, anime_type=None):
        """
        Manipulates an episode naming pattern and then fills the template in
        """

        if pattern == None:
            pattern = sickbeard.NAMING_PATTERN

        if multi == None:
            multi = sickbeard.NAMING_MULTI_EP

        if anime_type == None:
            anime_type = sickbeard.NAMING_ANIME

        replace_map = self._replace_map()

        result_name = pattern

        # if there's no release group then replace it with a reasonable facsimile
        if not replace_map['%RN']:
            if self.show.air_by_date or self.show.sports:
                result_name = result_name.replace('%RN', '%S.N.%A.D.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.%A.D.%e.n-SickGear')
            elif anime_type != 3:
                result_name = result_name.replace('%RN', '%S.N.%AB.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.%ab.%e.n-SickGear')
            else:
                result_name = result_name.replace('%RN', '%S.N.S%0SE%0E.%E.N-SickGear')
                result_name = result_name.replace('%rn', '%s.n.s%0se%0e.%e.n-SickGear')

            result_name = result_name.replace('%RG', 'SickGear')
            result_name = result_name.replace('%rg', 'SickGear')
            logger.log('Episode has no release name, replacing it with a generic one: %s' % result_name, logger.DEBUG)

        if not replace_map['%RT']:
            result_name = re.sub('([ _.-]*)%RT([ _.-]*)', r'\2', result_name)

        # split off ep name part only
        name_groups = re.split(r'[\\/]', result_name)

        # figure out the double-ep numbering style for each group, if applicable
        for cur_name_group in name_groups:

            season_format = sep = ep_sep = ep_format = None

            season_ep_regex = '''
                                (?P<pre_sep>[ _.-]*)
                                ((?:s(?:eason|eries)?\s*)?%0?S(?![._]?N))
                                (.*?)
                                (%0?E(?![._]?N))
                                (?P<post_sep>[ _.-]*)
                              '''
            ep_only_regex = '(E?%0?E(?![._]?N))'

            # try the normal way
            season_ep_match = re.search(season_ep_regex, cur_name_group, re.I | re.X)
            ep_only_match = re.search(ep_only_regex, cur_name_group, re.I | re.X)

            # if we have a season and episode then collect the necessary data
            if season_ep_match:
                season_format = season_ep_match.group(2)
                ep_sep = season_ep_match.group(3)
                ep_format = season_ep_match.group(4)
                sep = season_ep_match.group('pre_sep')
                if not sep:
                    sep = season_ep_match.group('post_sep')
                if not sep:
                    sep = ' '

                # force 2-3-4 format if they chose to extend
                if multi in (NAMING_EXTEND, NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED):
                    ep_sep = '-'

                regex_used = season_ep_regex

            # if there's no season then there's not much choice so we'll just force them to use 03-04-05 style
            elif ep_only_match:
                season_format = ''
                ep_sep = '-'
                ep_format = ep_only_match.group(1)
                sep = ''
                regex_used = ep_only_regex

            else:
                continue

            # we need at least this much info to continue
            if not ep_sep or not ep_format:
                continue

            # start with the ep string, eg. E03
            ep_string = self._format_string(ep_format.upper(), replace_map)
            for other_ep in self.relatedEps:

                # for limited extend we only append the last ep
                if multi in (NAMING_LIMITED_EXTEND, NAMING_LIMITED_EXTEND_E_PREFIXED) and other_ep != self.relatedEps[
                    -1]:
                    continue

                elif multi == NAMING_DUPLICATE:
                    # add " - S01"
                    ep_string += sep + season_format

                elif multi == NAMING_SEPARATED_REPEAT:
                    ep_string += sep

                # add "E04"
                ep_string += ep_sep

                if multi == NAMING_LIMITED_EXTEND_E_PREFIXED:
                    ep_string += 'E'

                ep_string += other_ep._format_string(ep_format.upper(), other_ep._replace_map())

            if anime_type != 3:
                if self.absolute_number == 0:
                    curAbsolute_number = self.episode
                else:
                    curAbsolute_number = self.absolute_number

                if self.season != 0:  # dont set absolute numbers if we are on specials !
                    if anime_type == 1:  # this crazy person wants both ! (note: +=)
                        ep_string += sep + '%(#)03d' % {
                            '#': curAbsolute_number}
                    elif anime_type == 2:  # total anime freak only need the absolute number ! (note: =)
                        ep_string = '%(#)03d' % {'#': curAbsolute_number}

                    for relEp in self.relatedEps:
                        if relEp.absolute_number != 0:
                            ep_string += '-' + '%(#)03d' % {'#': relEp.absolute_number}
                        else:
                            ep_string += '-' + '%(#)03d' % {'#': relEp.episode}

            regex_replacement = None
            if anime_type == 2:
                regex_replacement = r'\g<pre_sep>' + ep_string + r'\g<post_sep>'
            elif season_ep_match:
                regex_replacement = r'\g<pre_sep>\g<2>\g<3>' + ep_string + r'\g<post_sep>'
            elif ep_only_match:
                regex_replacement = ep_string

            if regex_replacement:
                # fill out the template for this piece and then insert this piece into the actual pattern
                cur_name_group_result = re.sub('(?i)(?x)' + regex_used, regex_replacement, cur_name_group)
                # cur_name_group_result = cur_name_group.replace(ep_format, ep_string)
                # logger.log(u"found "+ep_format+" as the ep pattern using "+regex_used+" and replaced it with "+regex_replacement+" to result in "+cur_name_group_result+" from "+cur_name_group, logger.DEBUG)
                result_name = result_name.replace(cur_name_group, cur_name_group_result)

        result_name = self._format_string(result_name, replace_map)

        logger.log('formatting pattern: %s -> %s' % (pattern, result_name), logger.DEBUG)

        return result_name

    def proper_path(self):
        """
        Figures out the path where this episode SHOULD live according to the renaming rules, relative from the show dir
        """

        anime_type = sickbeard.NAMING_ANIME
        if not self.show.is_anime:
            anime_type = 3

        result = self.formatted_filename(anime_type=anime_type)

        # if they want us to flatten it and we're allowed to flatten it then we will
        if self.show.flatten_folders and not sickbeard.NAMING_FORCE_FOLDERS:
            return result

        # if not we append the folder on and use that
        else:
            result = ek.ek(os.path.join, self.formatted_dir(), result)

        return result

    def formatted_dir(self, pattern=None, multi=None):
        """
        Just the folder name of the episode
        """

        if pattern == None:
            # we only use ABD if it's enabled, this is an ABD show, AND this is not a multi-ep
            if self.show.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.relatedEps:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self.show.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.relatedEps:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self.show.anime and sickbeard.NAMING_CUSTOM_ANIME:
                pattern = sickbeard.NAMING_ANIME_PATTERN
            else:
                pattern = sickbeard.NAMING_PATTERN

        # split off the dirs only, if they exist
        name_groups = re.split(r'[\\/]', pattern)

        if len(name_groups) == 1:
            return ''
        else:
            return self._format_pattern(ek.ek(os.sep.join, name_groups[:-1]), multi)

    def formatted_filename(self, pattern=None, multi=None, anime_type=None):
        """
        Just the filename of the episode, formatted based on the naming settings
        """

        if pattern == None:
            # we only use ABD if it's enabled, this is an ABD show, AND this is not a multi-ep
            if self.show.air_by_date and sickbeard.NAMING_CUSTOM_ABD and not self.relatedEps:
                pattern = sickbeard.NAMING_ABD_PATTERN
            elif self.show.sports and sickbeard.NAMING_CUSTOM_SPORTS and not self.relatedEps:
                pattern = sickbeard.NAMING_SPORTS_PATTERN
            elif self.show.anime and sickbeard.NAMING_CUSTOM_ANIME:
                pattern = sickbeard.NAMING_ANIME_PATTERN
            else:
                pattern = sickbeard.NAMING_PATTERN

        # split off the dirs only, if they exist
        name_groups = re.split(r'[\\/]', pattern)

        return self._format_pattern(name_groups[-1], multi, anime_type)

    def rename(self):
        """
        Renames an episode file and all related files to the location and filename as specified
        in the naming settings.
        """

        if not ek.ek(os.path.isfile, self.location):
            logger.log('Can\'t perform rename on %s when it doesn\'t exist, skipping' % self.location, logger.WARNING)
            return

        proper_path = self.proper_path()
        absolute_proper_path = ek.ek(os.path.join, self.show.location, proper_path)
        absolute_current_path_no_ext, file_ext = ek.ek(os.path.splitext, self.location)
        absolute_current_path_no_ext_length = len(absolute_current_path_no_ext)

        related_subs = []

        current_path = absolute_current_path_no_ext

        if absolute_current_path_no_ext.startswith(self.show.location):
            current_path = absolute_current_path_no_ext[len(self.show.location):]

        logger.log('Renaming/moving episode from the base path %s to %s' % (self.location, absolute_proper_path),
                   logger.DEBUG)

        # if it's already named correctly then don't do anything
        if proper_path == current_path:
            logger.log('%s: File %s is already named correctly, skipping' % (self.indexerid, self.location),
                       logger.DEBUG)
            return

        related_files = postProcessor.PostProcessor(self.location).list_associated_files(
            self.location, base_name_only=True)

        if self.show.subtitles and sickbeard.SUBTITLES_DIR != '':
            related_subs = postProcessor.PostProcessor(self.location).list_associated_files(sickbeard.SUBTITLES_DIR,
                                                                                            subtitles_only=True)
            absolute_proper_subs_path = ek.ek(os.path.join, sickbeard.SUBTITLES_DIR, self.formatted_filename())

        logger.log('Files associated to %s: %s' % (self.location, related_files), logger.DEBUG)

        # move the ep file
        result = helpers.rename_ep_file(self.location, absolute_proper_path, absolute_current_path_no_ext_length)

        # move related files
        for cur_related_file in related_files:
            cur_result = helpers.rename_ep_file(cur_related_file, absolute_proper_path,
                                                absolute_current_path_no_ext_length)
            if not cur_result:
                logger.log('%s: Unable to rename file %s' % (self.indexerid, cur_related_file), logger.ERROR)

        for cur_related_sub in related_subs:
            absolute_proper_subs_path = ek.ek(os.path.join, sickbeard.SUBTITLES_DIR, self.formatted_filename())
            cur_result = helpers.rename_ep_file(cur_related_sub, absolute_proper_subs_path,
                                                absolute_current_path_no_ext_length)
            if not cur_result:
                logger.log('%s: Unable to rename file %s' % (self.indexerid, cur_related_sub), logger.ERROR)

        # save the ep
        with self.lock:
            if result:
                self.location = absolute_proper_path + file_ext
                for relEp in self.relatedEps:
                    relEp.location = absolute_proper_path + file_ext

        # in case something changed with the metadata just do a quick check
        for curEp in [self] + self.relatedEps:
            curEp.checkForMetaFiles()

        # save any changes to the databas
        sql_l = []
        with self.lock:
            for relEp in [self] + self.relatedEps:
                result = relEp.get_sql()
                if None is not result:
                    sql_l.append(result)

        if 0 < len(sql_l):
            myDB = db.DBConnection()
            myDB.mass_action(sql_l)

    def airdateModifyStamp(self):
        """
        Make the modify date and time of a file reflect the show air date and time.
        Note: Also called from postProcessor

        """
        if not datetime.date == type(self.airdate) or 1 == self.airdate.year:
            logger.log('%s: Did not change modify date of %s because episode date is never aired or invalid'
                       % (self.show.indexerid, ek.ek(os.path.basename, self.location)), logger.DEBUG)
            return

        hr, m = network_timezones.parse_time(self.show.airs)
        airtime = datetime.time(hr, m)

        aired_dt = datetime.datetime.combine(self.airdate, airtime)
        try:
            aired_epoch = helpers.datetime_to_epoch(aired_dt)
            filemtime = int(ek.ek(os.path.getmtime, self.location))
        except (StandardError, Exception):
            return

        if filemtime != aired_epoch:

            result, loglevel = 'Changed', logger.MESSAGE
            if not helpers.touch_file(self.location, aired_epoch):
                result, loglevel = 'Error changing', logger.WARNING

            logger.log('%s: %s modify date of %s to show air date %s'
                       % (self.show.indexerid, result, ek.ek(os.path.basename, self.location),
                          aired_dt.strftime('%b %d,%Y (%H:%M)')), loglevel)

    def __getstate__(self):
        d = dict(self.__dict__)
        del d['lock']
        return d

    def __setstate__(self, d):
        d['lock'] = threading.Lock()
        self.__dict__.update(d)
