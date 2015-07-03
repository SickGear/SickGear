# coding=utf-8
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

import os
import traceback
import urllib
import re
import datetime
import urlparse

import sickbeard
import generic
from sickbeard.common import Quality, mediaExtensions
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard import logger, tvcache, helpers, db, classes
from sickbeard.show_name_helpers import allPossibleShowNames, sanitizeSceneName
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class KATProvider(generic.TorrentProvider):
    def __init__(self):
        generic.TorrentProvider.__init__(self, 'KickAssTorrents', True, False)

        self.confirmed = False
        self.ratio = None
        self.minseed = None
        self.minleech = None

        self.urls = ['https://kat.ph/', 'http://katproxy.com/']

        self.url = self.urls[0]

        self.cache = KATCache(self)

    def getQuality(self, item, anime=False):

        quality = Quality.sceneQuality(item[0], anime)
        return quality

    @staticmethod
    def _reverse_quality(quality):

        quality_string = ''

        if quality == Quality.SDTV:
            quality_string = 'HDTV x264'
        if quality == Quality.SDDVD:
            quality_string = 'DVDRIP'
        elif quality == Quality.HDTV:
            quality_string = '720p HDTV x264'
        elif quality == Quality.FULLHDTV:
            quality_string = '1080p HDTV x264'
        elif quality == Quality.RAWHDTV:
            quality_string = '1080i HDTV mpeg2'
        elif quality == Quality.HDWEBDL:
            quality_string = '720p WEB-DL h264'
        elif quality == Quality.FULLHDWEBDL:
            quality_string = '1080p WEB-DL h264'
        elif quality == Quality.HDBLURAY:
            quality_string = '720p Bluray x264'
        elif quality == Quality.FULLHDBLURAY:
            quality_string = '1080p Bluray x264'

        return quality_string

    def _find_season_quality(self, title, torrent_link, ep_number):
        """ Return the modified title of a Season Torrent with the quality found inspecting torrent file list """

        quality = Quality.UNKNOWN

        file_name = None

        data = self.getURL(torrent_link)
        if not data:
            return None

        try:
            with BS4Parser(data, features=['html5lib', 'permissive']) as soup:
                file_table = soup.find('table', attrs={'class': 'torrentFileList'})

                if not file_table:
                    return None

                files = [x.text for x in file_table.find_all('td', attrs={'class': 'torFileName'})]
                video_files = filter(lambda i: i.rpartition('.')[2].lower() in mediaExtensions, files)

                # Filtering SingleEpisode/MultiSeason Torrent
                if len(video_files) < ep_number or len(video_files) > float(ep_number * 1.1):
                    logger.log(u'Result %s lists %s episodes with %s episodes retrieved in torrent'
                               % (title, ep_number, len(video_files)), logger.DEBUG)
                    logger.log(u'Result %s seem to be a single episode or multi-season torrent, skipping result...'
                               % title, logger.DEBUG)
                    return None

                if Quality.UNKNOWN != Quality.sceneQuality(title):
                    return title

                for file_name in video_files:
                    quality = Quality.sceneQuality(os.path.basename(file_name))
                    if Quality.UNKNOWN != quality:
                        break

                if None is not file_name and Quality.UNKNOWN == quality:
                    quality = Quality.assumeQuality(os.path.basename(file_name))

                if Quality.UNKNOWN == quality:
                    logger.log(u'Unable to obtain a Season Quality for ' + title, logger.DEBUG)
                    return None

                try:
                    my_parser = NameParser(showObj=self.show)
                    parse_result = my_parser.parse(file_name)
                except (InvalidNameException, InvalidShowException):
                    return None

                logger.log(u'Season quality for %s is %s' % (title, Quality.qualityStrings[quality]), logger.DEBUG)

                if parse_result.series_name and parse_result.season_number:
                    title = parse_result.series_name + ' S%02d %s' % (int(parse_result.season_number),
                                                                      self._reverse_quality(quality))

                return title

        except Exception:
            logger.log(u'Failed to quality parse ' + self.name + ' Traceback: ' + traceback.format_exc(), logger.ERROR)

    def _get_season_search_strings(self, ep_obj):
        search_string = {'Season': []}

        for show_name in set(allPossibleShowNames(self.show)):
            if ep_obj.show.air_by_date or ep_obj.show.sports:
                ep_string = show_name + ' ' + str(ep_obj.airdate).split('-')[0]
                search_string['Season'].append(ep_string)
                ep_string = show_name + ' Season ' + str(ep_obj.airdate).split('-')[0]
                search_string['Season'].append(ep_string)
            elif ep_obj.show.anime:
                ep_string = show_name + ' ' + '%02d' % ep_obj.scene_absolute_number
                search_string['Season'].append(ep_string)
            else:
                ep_string = show_name + ' S%02d' % int(ep_obj.scene_season) + ' -S%02d' % int(
                    ep_obj.scene_season) + 'E' + ' category:tv'  # 1) showName SXX -SXXE
                search_string['Season'].append(ep_string)
                ep_string = show_name + ' Season ' + str(
                    ep_obj.scene_season) + ' -Ep*' + ' category:tv'  # 2) showName Season X
                search_string['Season'].append(ep_string)

        return [search_string]

    def _get_episode_search_strings(self, ep_obj, add_string=''):
        search_string = {'Episode': []}

        if self.show.air_by_date:
            for show_name in set(allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    str(ep_obj.airdate).replace('-', ' ')
                search_string['Episode'].append(ep_string)
        elif self.show.sports:
            for show_name in set(allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    str(ep_obj.airdate).replace('-', '|') + '|' + \
                    ep_obj.airdate.strftime('%b')
                search_string['Episode'].append(ep_string)
        elif self.show.anime:
            for show_name in set(allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    '%02i' % int(ep_obj.scene_absolute_number)
                search_string['Episode'].append(ep_string)
        else:
            for show_name in set(allPossibleShowNames(self.show)):
                ep_string = sanitizeSceneName(show_name) + ' ' + \
                    sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                          'episodenumber': ep_obj.scene_episode} + '|' + \
                    sickbeard.config.naming_ep_type[0] % {'seasonnumber': ep_obj.scene_season,
                                                          'episodenumber': ep_obj.scene_episode} + ' %s category:tv' % add_string
                search_string['Episode'].append(re.sub('\s+', ' ', ep_string))

        return [search_string]

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        for mode in search_params.keys():
            for search_string in search_params[mode]:

                for url in self.urls:
                    search_url = url
                    if 'RSS' == mode:
                        search_url += 'tv/?field=time_add&sorder=desc'
                        logger.log(u'KAT cache update URL: ' + search_url, logger.DEBUG)
                    else:
                        search_url += 'usearch/%s/?field=seeders&sorder=desc' % (urllib.quote(unidecode(search_string)))
                        logger.log(u'Search string: ' + search_url, logger.DEBUG)

                    html = self.getURL(search_url)
                    if html:
                        self.url = url
                        break

                if not html:
                    continue

                try:
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'data'})
                        torrent_rows = torrent_table.find_all('tr') if torrent_table else []

                        # Continue only if one Release is found
                        if len(torrent_rows) < 2:
                            logger.log(u'The data returned from ' + self.name + ' does not contain any torrents',
                                       logger.WARNING)
                            continue

                        for tr in torrent_rows[1:]:
                            try:
                                link = urlparse.urljoin(self.url,
                                                        (tr.find('div', {'class': 'torrentname'}).find_all('a')[1])['href'])
                                tid = tr.get('id')[-7:]
                                title = (tr.find('div', {'class': 'torrentname'}).find_all('a')[1]).text \
                                    or (tr.find('div', {'class': 'torrentname'}).find_all('a')[2]).text
                                url = tr.find('a', 'imagnet')['href']
                                verified = True if tr.find('a', 'iverify') else False
                                # trusted = True if tr.find('img', {'alt': 'verified'}) else False
                                seeders = int(tr.find_all('td')[-2].text)
                                leechers = int(tr.find_all('td')[-1].text)
                            except (AttributeError, TypeError):
                                continue

                            if 'RSS' != mode and (seeders < self.minseed or leechers < self.minleech):
                                continue

                            if self.confirmed and not verified:
                                logger.log(
                                    u'KAT Provider found result ' + title + ' but that doesn\'t seem like a verified result so I\'m ignoring it',
                                    logger.DEBUG)
                                continue

                            # Check number video files = episode in season and find the real Quality for full season torrent analyzing files in torrent
                            if 'Season' == mode and 'sponly' == search_mode:
                                ep_number = int(epcount / len(set(allPossibleShowNames(self.show))))
                                title = self._find_season_quality(title, link, ep_number)

                            if not title or not url:
                                continue

                            item = title, url, tid, seeders, leechers

                            items[mode].append(item)

                except Exception:
                    logger.log(u'Failed to parse ' + self.name + ' Traceback: ' + traceback.format_exc(),
                               logger.ERROR)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def _get_title_and_url(self, item):

        title, url, tid, seeders, leechers = item

        if title:
            title = u'' + title.replace(' ', '.')

        if url:
            url = url.replace('&amp;', '&')

        return title, url

    def findPropers(self, search_date=datetime.datetime.today()):

        results = []

        my_db = db.DBConnection()
        sql_results = my_db.select(
            'SELECT s.show_name, e.showid, e.season, e.episode, e.status, e.airdate, s.indexer FROM tv_episodes AS e' +
            ' INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id)' +
            ' WHERE e.airdate >= ' + str(search_date.toordinal()) +
            ' AND (e.status IN (' + ','.join([str(x) for x in Quality.DOWNLOADED]) + ')' +
            ' OR (e.status IN (' + ','.join([str(x) for x in Quality.SNATCHED]) + ')))'
        )

        if not sql_results:
            return []

        for sqlshow in sql_results:
            self.show = helpers.findCertainShow(sickbeard.showList, int(sqlshow['showid']))
            if self.show:
                cur_ep = self.show.getEpisode(int(sqlshow['season']), int(sqlshow['episode']))

                search_string = self._get_episode_search_strings(cur_ep, add_string='PROPER|REPACK')

                for item in self._doSearch(search_string[0]):
                    title, url = self._get_title_and_url(item)
                    results.append(classes.Proper(title, url, datetime.datetime.today(), self.show))

        return results

    def seedRatio(self):
        return self.ratio


class KATCache(tvcache.TVCache):
    def __init__(self, this_provider):

        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):
        search_params = {'RSS': ['rss']}
        return self.provider._doSearch(search_params)


provider = KATProvider()
