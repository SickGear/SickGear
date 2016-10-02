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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import re
import traceback
import urllib

from . import generic
from sickbeard import config, logger, show_name_helpers
from sickbeard.bs4_parser import BS4Parser
from sickbeard.common import Quality, mediaExtensions
from sickbeard.helpers import tryInt
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from lib.unidecode import unidecode


class ThePirateBayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'The Pirate Bay', cache_update_freq=20)

        self.url_home = ['https://thepiratebay.%s/' % u for u in 'se', 'org'] + \
                        ['https://piratebay.usbypass.xyz/']

        self.url_vars = {'search': 'search/%s/0/7/200', 'browse': 'tv/latest/'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s',
                         'browse': '%(home)s%(vars)s'}

        self.proper_search_terms = None

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'Pirate\sBay', data[33:7632:])

    def _find_season_quality(self, title, torrent_id, ep_number):
        """ Return the modified title of a Season Torrent with the quality found inspecting torrent file list """

        if not self.url:
            return False

        quality = Quality.UNKNOWN
        file_name = None
        data = self.get_url('%sajax_details_filelist.php?id=%s' % (self.url, torrent_id))
        if not data:
            return None

        files_list = re.findall('<td.+>(.*?)</td>', data)

        if not files_list:
            logger.log(u'Unable to get the torrent file list for ' + title, logger.ERROR)

        video_files = filter(lambda x: x.rpartition('.')[2].lower() in mediaExtensions, files_list)

        # Filtering SingleEpisode/MultiSeason Torrent
        if ep_number > len(video_files) or float(ep_number * 1.1) < len(video_files):
            logger.log(u'Result %s has episode %s and total episodes retrieved in torrent are %s'
                       % (title, str(ep_number), str(len(video_files))), logger.DEBUG)
            logger.log(u'Result %s seems to be a single episode or multiseason torrent, skipping result...'
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
            title = '%s S%02d %s' % (parse_result.series_name,
                                     int(parse_result.season_number),
                                     self._reverse_quality(quality))

        return title

    def _season_strings(self, ep_obj, **kwargs):

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            ep_detail = [airdate, 'Season ' + airdate]
        elif ep_obj.show.anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            season = (ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)]
            ep_detail = ['S%02d' % int(season), 'Season %s -Ep*' % season]

        return [{'Season': self._build_search_strings(ep_detail)}]

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, date_or=True,
                                                        ep_detail=lambda x: '%s|%s' % (config.naming_ep_type[2] % x,
                                                                                       config.naming_ep_type[0] % x),
                                                        ep_detail_anime=lambda x: '%02i' % x, **kwargs)

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'detail', 'get': 'download[^"]+magnet', 'tid': r'.*/(\d{5,}).*',
            'verify': '(?:helper|moderator|trusted|vip)', 'size': 'size[^\d]+(\d+(?:[.,]\d+)?\W*[bkmgt]\w+)'}.items())

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] if 'Cache' == mode \
                    else self.urls['search'] % (urllib.quote(search_string))
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive'], attr='id="searchResult"') as soup:
                        torrent_table = soup.find(id='searchResult')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_table.find_all('tr')[1:]:
                            cells = tr.find_all('td')
                            if 3 > len(cells):
                                continue
                            try:
                                seeders, leechers = [tryInt(cells[x].get_text().strip()) for x in -2, -1]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('a', title=rc['info'])
                                title = info.get_text().strip().replace('_', '.')
                                tid = rc['tid'].sub(r'\1', str(info['href']))
                                download_magnet = tr.find('a', title=rc['get'])['href']
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if self.confirmed and not tr.find('img', title=rc['verify']):
                                logger.log(u'Skipping untrusted non-verified result: ' + title, logger.DEBUG)
                                continue

                            # Check number video files = episode in season and
                            # find the real Quality for full season torrent analyzing files in torrent
                            if 'Season' == mode and 'sponly' == search_mode:
                                ep_number = int(epcount / len(set(show_name_helpers.allPossibleShowNames(self.show))))
                                title = self._find_season_quality(title, tid, ep_number)

                            if title and download_magnet:
                                size = None
                                try:
                                    size = rc['size'].findall(tr.find_all(class_='detDesc')[0].get_text())[0]
                                except (StandardError, Exception):
                                    pass

                                items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = ThePirateBayProvider()
