# coding=utf-8
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

import time
import datetime
import os
import re
import itertools
from base64 import b16encode, b32decode

import sickbeard
import requests
from sickbeard import helpers, classes, logger, db, tvcache, encodingKludge as ek
from sickbeard.common import Quality, MULTI_EP_RESULT, SEASON_RESULT, USER_AGENT
from sickbeard.exceptions import SickBeardException, AuthException, ex
from sickbeard.helpers import maybe_plural
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard.show_name_helpers import allPossibleShowNames
from hachoir_parser import createParser


class HaltParseException(SickBeardException):
    """Something requires the current processing to abort"""


class GenericProvider:
    NZB = "nzb"
    TORRENT = "torrent"

    def __init__(self, name, supports_backlog=False, anime_only=False):
        # these need to be set in the subclass
        self.providerType = None
        self.name = name
        self.supportsBacklog = supports_backlog
        self.anime_only = anime_only
        self.url = ''

        self.show = None

        self.search_mode = None
        self.search_fallback = False
        self.enabled = False
        self.enable_recentsearch = False
        self.enable_backlog = False

        self.cache = tvcache.TVCache(self)

        self.session = requests.session()

        self.headers = {
            # Using USER_AGENT instead of Mozilla to keep same user agent along authentication and download phases,
            #otherwise session might be broken and download fail, asking again for authentication
            #'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.107 Safari/537.36'}
            'User-Agent': USER_AGENT}

    def getID(self):
        return GenericProvider.makeID(self.name)

    @staticmethod
    def makeID(name):
        return re.sub("[^\w\d_]", "_", name.strip().lower())

    def imageName(self, *default_name):

        for name in ['%s.%s' % (self.getID(), image_ext) for image_ext in ['png', 'gif', 'jpg']]:
            if ek.ek(os.path.isfile,
                     ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', sickbeard.GUI_NAME, 'images', 'providers', name)):
                return name

        return '%s.png' % ('newznab', default_name[0])[any(default_name)]

    def _checkAuth(self):
        return True

    def _doLogin(self):
        return True

    def isActive(self):
        if self.providerType == GenericProvider.NZB and sickbeard.USE_NZBS:
            return self.isEnabled()
        elif self.providerType == GenericProvider.TORRENT and sickbeard.USE_TORRENTS:
            return self.isEnabled()
        else:
            return False

    def isEnabled(self):
        """
        This should be overridden and should return the config setting eg. sickbeard.MYPROVIDER
        """
        return self.enabled

    def getResult(self, episodes):
        """
        Returns a result of the correct type for this provider
        """

        if self.providerType == GenericProvider.NZB:
            result = classes.NZBSearchResult(episodes)
        elif self.providerType == GenericProvider.TORRENT:
            result = classes.TorrentSearchResult(episodes)
        else:
            result = classes.SearchResult(episodes)

        result.provider = self

        return result

    def getURL(self, url, post_data=None, params=None, timeout=30, json=False):
        """
        By default this is just a simple urlopen call but this method should be overridden
        for providers with special URL requirements (like cookies)
        """

        # check for auth
        if not self._doLogin():
            return

        return helpers.getURL(url, post_data=post_data, params=params, headers=self.headers, timeout=timeout,
                              session=self.session, json=json)

    def downloadResult(self, result):
        """
        Save the result to disk.
        """

        # check for auth
        if not self._doLogin():
            return False

        if self.providerType == GenericProvider.TORRENT:
            try:
                torrent_hash = re.findall('urn:btih:([0-9a-f]{32,40})', result.url)[0].upper()

                if 32 == len(torrent_hash):
                    torrent_hash = b16encode(b32decode(torrent_hash)).lower()

                if not torrent_hash:
                    logger.log("Unable to extract torrent hash from link: " + ex(result.url), logger.ERROR)
                    return False

                urls = ['https://%s/%s.torrent' % (u, torrent_hash)
                        for u in ('torcache.net/torrent', 'torrage.com/torrent', 'getstrike.net/torrents/api/download')]
            except:
                urls = [result.url]

            filename = ek.ek(os.path.join, sickbeard.TORRENT_DIR,
                             helpers.sanitizeFileName(result.name) + '.' + self.providerType)
        elif self.providerType == GenericProvider.NZB:
            urls = [result.url]

            filename = ek.ek(os.path.join, sickbeard.NZB_DIR,
                             helpers.sanitizeFileName(result.name) + '.' + self.providerType)
        else:
            return

        for url in urls:
            if helpers.download_file(url, filename, session=self.session):
                logger.log(u"Downloading a result from " + self.name + " at " + url)

                if self.providerType == GenericProvider.TORRENT:
                    logger.log(u"Saved magnet link to " + filename, logger.MESSAGE)
                else:
                    logger.log(u"Saved result to " + filename, logger.MESSAGE)

                if self._verify_download(filename):
                    return True
                elif ek.ek(os.path.isfile, filename):
                    ek.ek(os.remove, filename)

        logger.log(u"Failed to download result", logger.ERROR)
        return False

    def _verify_download(self, file_name=None):
        """
        Checks the saved file to see if it was actually valid, if not then consider the download a failure.
        """

        # primitive verification of torrents, just make sure we didn't get a text file or something
        if self.providerType == GenericProvider.TORRENT:
            parser = createParser(file_name)
            if parser:
                mime_type = parser._getMimeType()
                try:
                    parser.stream._input.close()
                except:
                    pass
                if mime_type == 'application/x-bittorrent':
                    return True

            logger.log(u"Result is not a valid torrent file", logger.WARNING)
            return False

        return True

    def searchRSS(self, episodes):
        return self.cache.findNeededEpisodes(episodes)

    def getQuality(self, item, anime=False):
        """
        Figures out the quality of the given RSS item node
        
        item: An elementtree.ElementTree element representing the <item> tag of the RSS feed
        
        Returns a Quality value obtained from the node's data 
        """
        (title, url) = self._get_title_and_url(item)  # @UnusedVariable
        quality = Quality.sceneQuality(title, anime)
        return quality

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):
        return []

    def _get_season_search_strings(self, episode):
        return []

    def _get_episode_search_strings(self, eb_obj, add_string=''):
        return []

    def _get_title_and_url(self, item):
        """
        Retrieves the title and URL data from the item

        item: An elementtree.ElementTree element representing the <item> tag of the RSS feed, or a two part tup

        Returns: A tuple containing two strings representing title and URL respectively
        """

        title, url = None, None

        try:
            if isinstance(item, tuple):
                title = item[0]
                url = item[1]
            else:
                if 'title' in item:
                    title = item.title

                if 'link' in item:
                    url = item.link
        except Exception:
            pass

        if title:
            title = re.sub(r'\s+', '.', u'' + title)

        if url:
            url = url.replace('&amp;', '&')

        return title, url

    def findSearchResults(self, show, episodes, search_mode, manualSearch=False):

        self._checkAuth()
        self.show = show

        results = {}
        itemList = []

        searched_scene_season = None
        for epObj in episodes:
            # search cache for episode result
            cacheResult = self.cache.searchCache(epObj, manualSearch)
            if cacheResult:
                if epObj.episode not in results:
                    results[epObj.episode] = cacheResult
                else:
                    results[epObj.episode].extend(cacheResult)

                # found result, search next episode
                continue

            # skip if season already searched
            if len(episodes) > 1 and searched_scene_season == epObj.scene_season:
                continue

            # mark season searched for season pack searches so we can skip later on
            searched_scene_season = epObj.scene_season

            if 'sponly' == search_mode:
                # get season search results
                for curString in self._get_season_search_strings(epObj):
                    itemList += self._doSearch(curString, search_mode, len(episodes))
            else:
                # get single episode search results
                for curString in self._get_episode_search_strings(epObj):
                    itemList += self._doSearch(curString, 'eponly', len(episodes))

        # if we found what we needed already from cache then return results and exit
        if len(results) == len(episodes):
            return results

        # sort list by quality
        if len(itemList):
            items = {}
            itemsUnknown = []
            for item in itemList:
                quality = self.getQuality(item, anime=show.is_anime)
                if quality == Quality.UNKNOWN:
                    itemsUnknown += [item]
                else:
                    if quality not in items:
                        items[quality] = [item]
                    else:
                        items[quality].append(item)

            itemList = list(itertools.chain(*[v for (k, v) in sorted(items.items(), reverse=True)]))
            itemList += itemsUnknown if itemsUnknown else []

        # filter results
        cl = []
        for item in itemList:
            (title, url) = self._get_title_and_url(item)

            # parse the file name
            try:
                myParser = NameParser(False, convert=True)
                parse_result = myParser.parse(title)
            except InvalidNameException:
                logger.log(u"Unable to parse the filename " + title + " into a valid episode", logger.DEBUG)
                continue
            except InvalidShowException:
                logger.log(u'No show name or scene exception matched the parsed filename ' + title, logger.DEBUG)
                continue

            showObj = parse_result.show
            quality = parse_result.quality
            release_group = parse_result.release_group
            version = parse_result.version

            addCacheEntry = False
            if not (showObj.air_by_date or showObj.sports):
                if search_mode == 'sponly': 
                    if len(parse_result.episode_numbers):
                        logger.log(
                            u"This is supposed to be a season pack search but the result " + title + " is not a valid season pack, skipping it",
                            logger.DEBUG)
                        addCacheEntry = True
                    if len(parse_result.episode_numbers) and (
                                    parse_result.season_number not in set([ep.season for ep in episodes]) or not [ep for ep in episodes if
                                                                                 ep.scene_episode in parse_result.episode_numbers]):
                        logger.log(
                            u"The result " + title + " doesn't seem to be a valid episode that we are trying to snatch, ignoring",
                            logger.DEBUG)
                        addCacheEntry = True
                else:
                    if not len(parse_result.episode_numbers) and parse_result.season_number and not [ep for ep in
                                                                                                     episodes if
                                                                                                     ep.season == parse_result.season_number and ep.episode in parse_result.episode_numbers]:
                        logger.log(
                            u"The result " + title + " doesn't seem to be a valid season that we are trying to snatch, ignoring",
                            logger.DEBUG)
                        addCacheEntry = True
                    elif len(parse_result.episode_numbers) and not [ep for ep in episodes if
                                                                    ep.season == parse_result.season_number and ep.episode in parse_result.episode_numbers]:
                        logger.log(
                            u"The result " + title + " doesn't seem to be a valid episode that we are trying to snatch, ignoring",
                            logger.DEBUG)
                        addCacheEntry = True

                if not addCacheEntry:
                    # we just use the existing info for normal searches
                    actual_season = parse_result.season_number
                    actual_episodes = parse_result.episode_numbers
            else:
                if not (parse_result.is_air_by_date):
                    logger.log(
                        u"This is supposed to be a date search but the result " + title + " didn't parse as one, skipping it",
                        logger.DEBUG)
                    addCacheEntry = True
                else:
                    airdate = parse_result.air_date.toordinal()
                    myDB = db.DBConnection()
                    sql_results = myDB.select(
                        "SELECT season, episode FROM tv_episodes WHERE showid = ? AND airdate = ?",
                        [showObj.indexerid, airdate])

                    if len(sql_results) != 1:
                        logger.log(
                            u"Tried to look up the date for the episode " + title + " but the database didn't give proper results, skipping it",
                            logger.WARNING)
                        addCacheEntry = True

                if not addCacheEntry:
                    actual_season = int(sql_results[0]["season"])
                    actual_episodes = [int(sql_results[0]["episode"])]

            # add parsed result to cache for usage later on
            if addCacheEntry:
                logger.log(u"Adding item from search to cache: " + title, logger.DEBUG)
                ci = self.cache._addCacheEntry(title, url, parse_result=parse_result)
                if ci is not None:
                    cl.append(ci)
                continue

            # make sure we want the episode
            wantEp = True
            for epNo in actual_episodes:
                if not showObj.wantEpisode(actual_season, epNo, quality, manualSearch):
                    wantEp = False
                    break

            if not wantEp:
                logger.log(
                    u"Ignoring result " + title + " because we don't want an episode that is " +
                    Quality.qualityStrings[
                        quality], logger.DEBUG)

                continue

            logger.log(u"Found result " + title + " at " + url, logger.DEBUG)

            # make a result object
            epObj = []
            for curEp in actual_episodes:
                epObj.append(showObj.getEpisode(actual_season, curEp))

            result = self.getResult(epObj)
            result.show = showObj
            result.url = url
            result.name = title
            result.quality = quality
            result.release_group = release_group
            result.content = None
            result.version = version

            if len(epObj) == 1:
                epNum = epObj[0].episode
                logger.log(u"Single episode result.", logger.DEBUG)
            elif len(epObj) > 1:
                epNum = MULTI_EP_RESULT
                logger.log(u"Separating multi-episode result to check for later - result contains episodes: " + str(
                    parse_result.episode_numbers), logger.DEBUG)
            elif len(epObj) == 0:
                epNum = SEASON_RESULT
                logger.log(u"Separating full season result to check for later", logger.DEBUG)

            if epNum not in results:
                results[epNum] = [result]
            else:
                results[epNum].append(result)

        # check if we have items to add to cache
        if len(cl) > 0:
            myDB = self.cache._getDB()
            myDB.mass_action(cl)

        return results

    def findPropers(self, search_date=None):

        results = self.cache.listPropers(search_date)

        return [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show) for x in
                results]

    def seedRatio(self):
        '''
        Provider should override this value if custom seed ratio enabled
        It should return the value of the provider seed ratio
        '''
        return ''

    @staticmethod
    def _log_result(mode='cache', count=0, url='url missing'):
        """
        Simple function to log the result of a search
        :param count: count of successfully processed items
        :param url: source url of item(s)
        """
        mode = mode.lower()
        logger.log(u'%s in response from %s' % (('No %s items' % mode,
                                                 '%s %s item%s' % (count, mode, maybe_plural(count)))[0 < count], url))


class NZBProvider(GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False):
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.NZB

    def imageName(self):

        return GenericProvider.imageName(self, 'newznab')

    def _find_propers(self, search_date=None):

        cache_results = self.cache.listPropers(search_date)
        results = [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show) for x in
                   cache_results]

        index = 0
        alt_search = ('nzbs_org' == self.getID())
        term_items_found = False
        do_search_alt = False

        search_terms = ['.proper.', '.repack.']
        proper_check = re.compile(r'(?i)\b(proper)|(repack)\b')

        while index < len(search_terms):
            search_params = {'q': search_terms[index]}
            if alt_search:

                if do_search_alt:
                    index += 1

                if term_items_found:
                    do_search_alt = True
                    term_items_found = False
                else:
                    if do_search_alt:
                        search_params['t'] = 'search'

                    do_search_alt = (True, False)[do_search_alt]

            else:
                index += 1

            for item in self._doSearch(search_params, age=4):

                (title, url) = self._get_title_and_url(item)

                if not proper_check.search(title):
                    continue

                if 'published_parsed' in item and item['published_parsed']:
                    result_date = item.published_parsed
                    if result_date:
                        result_date = datetime.datetime(*result_date[0:6])
                else:
                    logger.log(u'Unable to figure out the date for entry %s, skipping it', title)
                    continue

                if not search_date or result_date > search_date:
                    search_result = classes.Proper(title, url, result_date, self.show)
                    results.append(search_result)
                    term_items_found = True
                    do_search_alt = False

            time.sleep(0.2)

        return results


class TorrentProvider(GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False):
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.TORRENT

        self._seed_ratio = None

    def imageName(self):

        return GenericProvider.imageName(self, 'torrent')

    def seedRatio(self):

        return self._seed_ratio

    def getQuality(self, item, anime=False):

        if isinstance(item, tuple):
            name = item[0]
        elif isinstance(item, dict):
            name, url = self._get_title_and_url(item)
        else:
            name = item.title
        return Quality.sceneQuality(name, anime)

    @staticmethod
    def _reverse_quality(quality):

        return {
            Quality.SDTV: 'HDTV x264',
            Quality.SDDVD: 'DVDRIP',
            Quality.HDTV: '720p HDTV x264',
            Quality.FULLHDTV: '1080p HDTV x264',
            Quality.RAWHDTV: '1080i HDTV mpeg2',
            Quality.HDWEBDL: '720p WEB-DL h264',
            Quality.FULLHDWEBDL: '1080p WEB-DL h264',
            Quality.HDBLURAY: '720p Bluray x264',
            Quality.FULLHDBLURAY: '1080p Bluray x264'
        }.get(quality, '')

    def _get_season_search_strings(self, ep_obj, detail_only=False, scene=True):

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            ep_detail = str(ep_obj.airdate).split('-')[0]
        elif ep_obj.show.anime:
            ep_detail = ep_obj.scene_absolute_number
        else:
            ep_detail = 'S%02d' % int(ep_obj.scene_season)

        detail = ({}, {'Season_only': [ep_detail]})[detail_only and not self.show.sports and not self.show.anime]
        return [dict({'Season': self._build_search_strings(ep_detail, scene)}.items() + detail.items())]

    def _get_episode_search_strings(self, ep_obj, add_string='', detail_only=False, scene=True, sep_date=' ', use_or=True):

        if not ep_obj:
            return []

        if self.show.air_by_date or self.show.sports:
            ep_detail = str(ep_obj.airdate).replace('-', sep_date)
            if self.show.sports:
                month = ep_obj.airdate.strftime('%b')
                ep_detail = ([ep_detail] + [month], '%s|%s' % (ep_detail, month))[use_or]
        elif self.show.anime:
            ep_detail = ep_obj.scene_absolute_number
        else:
            ep_detail = sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                              'episodenumber': ep_obj.scene_episode}
        append = (add_string, '')[self.show.anime]
        detail = ({}, {'Episode_only': [ep_detail]})[detail_only and not self.show.sports and not self.show.anime]
        return [dict({'Episode': self._build_search_strings(ep_detail, scene, append)}.items() + detail.items())]

    def _build_search_strings(self, ep_detail, process_name=True, append=''):
        """
        Build a list of search strings for querying a provider
        :param ep_detail: String of episode detail or List of episode details
        :param process_name: Bool Whether to call sanitizeSceneName() on show name
        :param append: String to append to search strings
        :return: List of search string parameters
        """
        if not isinstance(ep_detail, list):
            ep_detail = [ep_detail]
        if not isinstance(append, list):
            append = [append]

        search_params = []
        crop = re.compile(r'([\.\s])(?:\1)+')
        for name in set(allPossibleShowNames(self.show)):
            if process_name:
                name = helpers.sanitizeSceneName(name)
            for detail in ep_detail:
                search_params += [crop.sub(r'\1', '%s %s' % (name, detail) + ('', ' ' + x)[any(x)]) for x in append]
        return search_params

    def _checkAuth(self):

        if hasattr(self, 'username') and hasattr(self, 'password'):
            if self.username and self.password:
                return True
            setting = 'Password or Username'
        elif hasattr(self, 'username') and hasattr(self, 'passkey'):
            if self.username and self.passkey:
                return True
            setting = 'Passkey or Username'
        elif hasattr(self, 'api_key'):
            if self.api_key:
                return True
            setting = 'Apikey'
        elif hasattr(self, 'passkey'):
            if self.passkey:
                return True
            setting = 'Passkey'
        else:
            return GenericProvider._checkAuth(self)

        raise AuthException('%s for %s is empty in config provider options' % (setting, self.name))

    def _find_propers(self, search_date=datetime.datetime.today(), search_terms=None):
        """
        Search for releases of type PROPER
        :param search_date: Filter search on episodes since this date
        :param search_terms: String or list of strings that qualify PROPER release types
        :return: list of Proper objects
        """
        results = []

        my_db = db.DBConnection()
        sql_results = my_db.select(
            'SELECT s.show_name, e.showid, e.season, e.episode, e.status, e.airdate FROM tv_episodes AS e' +
            ' INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id)' +
            ' WHERE e.airdate >= ' + str(search_date.toordinal()) +
            ' AND (e.status IN (%s)' % ','.join([str(x) for x in Quality.DOWNLOADED]) +
            ' OR (e.status IN (%s)))' % ','.join([str(x) for x in Quality.SNATCHED])
        )

        if not sql_results:
            return results

        clean_term = re.compile(r'(?i)[^a-z\|\.]+')
        for sqlshow in sql_results:
            showid, season, episode = [int(sqlshow[item]) for item in ('showid', 'season', 'episode')]

            self.show = helpers.findCertainShow(sickbeard.showList, showid)
            if not self.show:
                continue

            cur_ep = self.show.getEpisode(season, episode)

            if None is search_terms:
                search_terms = ['proper', 'repack']
            elif not isinstance(search_terms, list):
                if '' == search_terms:
                    search_terms = 'proper|repack'
                search_terms = [search_terms]

            for proper_term in search_terms:
                proper_check = re.compile(r'(?i)(?:%s)' % clean_term.sub('', proper_term))

                search_string = self._get_episode_search_strings(cur_ep, add_string=proper_term)
                for item in self._doSearch(search_string[0]):
                    title, url = self._get_title_and_url(item)
                    if not proper_check.search(title):
                        continue
                    results.append(classes.Proper(title, url, datetime.datetime.today(), self.show))

        return results

    @staticmethod
    def _has_no_results(*html):
        return re.search(r'(?i)<(?:h\d|strong)[^>]*>(?:'
                         + 'your\ssearch\sdid\snot\smatch|'
                         + 'nothing\sfound|'
                         + 'no\storrents\sfound|'
                         + '.*?there\sare\sno\sresults|'
                         + '.*?no\shits\.\sTry\sadding'
                         + ')', html[0])

    def get_cache_data(self, *args, **kwargs):

        search_params = {'Cache': ['']}
        return self._doSearch(search_params)
