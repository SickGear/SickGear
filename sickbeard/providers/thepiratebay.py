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
import datetime
import urllib
import traceback

from . import generic
from sickbeard import config, logger, tvcache, show_name_helpers
from sickbeard.common import Quality, mediaExtensions
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard.bs4_parser import BS4Parser
from lib.unidecode import unidecode


class ThePirateBayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'The Pirate Bay')

        self.urls = {'config_provider_home_uri': ['https://thepiratebay.se/', 'https://thepiratebay.gd/',
                                                  'https://thepiratebay.mn/', 'https://thepiratebay.vg/',
                                                  'https://thepiratebay.la/'],
                     'search': 'search/%s/0/7/200',
                     'cache': 'tv/latest/'}  # order by seed

        self.url = self.urls['config_provider_home_uri'][0]

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False
        self.cache = ThePirateBayCache(self)

    def _find_season_quality(self, title, torrent_id, ep_number):
        """ Return the modified title of a Season Torrent with the quality found inspecting torrent file list """

        quality = Quality.UNKNOWN
        file_name = None
        data = None
        has_signature = False
        details_url = '/ajax_details_filelist.php?id=%s' % torrent_id
        for idx, url in enumerate(self.urls['config_provider_home_uri']):
            data = self.get_url(url + details_url)
            if data and re.search(r'<title>The\sPirate\sBay', data[33:200:]):
                has_signature = True
                break
            else:
                data = None

        if not has_signature:
            logger.log(u'Failed to identify a page from ThePirateBay at %s attempted urls (tpb blocked? general network issue or site dead)' % len(self.urls['config_provider_home_uri']), logger.ERROR)

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

    def _get_season_search_strings(self, ep_obj, **kwargs):

        if ep_obj.show.air_by_date or ep_obj.show.sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            ep_detail = [airdate, 'Season ' + airdate]
        elif ep_obj.show.anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            ep_detail = ['S%02d' % int(ep_obj.scene_season),
                         'Season %s -Ep*' % ep_obj.scene_season]

        return [{'Season': self._build_search_strings(ep_detail)}]

    def _get_episode_search_strings(self, ep_obj, add_string='', **kwargs):

        if self.show.air_by_date or self.show.sports:
            ep_detail = str(ep_obj.airdate).replace('-', ' ')
            if self.show.sports:
                ep_detail += '|' + ep_obj.airdate.strftime('%b')
        elif self.show.anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            ep_detail = '%s|%s' % (config.naming_ep_type[2] % {'seasonnumber': ep_obj.scene_season,
                                                               'episodenumber': ep_obj.scene_episode},
                                   config.naming_ep_type[0] % {'seasonnumber': ep_obj.scene_season,
                                                               'episodenumber': ep_obj.scene_episode})

        return [{'Episode': self._build_search_strings(ep_detail, append=(add_string, '')[self.show.anime])}]

    def _do_search(self, search_params, search_mode='eponly', epcount=0, age=0):

        results = []
        items = {'Season': [], 'Episode': [], 'Cache': []}

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'info': 'detail', 'get': 'download[^"]+magnet', 'tid': r'.*/(\d{5,}).*',
                                 'verify': '(?:helper|moderator|trusted|vip)'}.items())
        has_signature = False
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                if isinstance(search_string, unicode):
                    search_string = unidecode(search_string)

                log_url = '%s %s' % (self.name, search_string)   # placebo value
                for idx, search_url in enumerate(self.urls['config_provider_home_uri']):
                    search_url += self.urls['cache'] if 'Cache' == mode\
                        else self.urls['search'] % (urllib.quote(search_string))

                    log_url = u'(%s/%s): %s' % (idx + 1, len(self.urls['config_provider_home_uri']), search_url)

                    html = self.get_url(search_url)
                    if html and re.search(r'Pirate\sBay', html[33:7632:]):
                        has_signature = True
                        break
                    else:
                        html = None

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'id': 'searchResult'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_table.find_all('tr')[1:]:
                            try:
                                seeders, leechers = [int(tr.find_all('td')[x].get_text().strip()) for x in (-2, -1)]
                                if 'Cache' != mode and (seeders < self.minseed or leechers < self.minleech):
                                    continue

                                info = tr.find('a', title=rc['info'])
                                title = info.get_text().strip().replace('_', '.')
                                tid = rc['tid'].sub(r'\1', str(info['href']))

                                download_magnet = tr.find('a', title=rc['get'])['href']
                            except (AttributeError, TypeError):
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
                                items[mode].append((title, download_magnet, seeders))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_result(mode, len(items[mode]) - cnt, log_url)

            # For each search mode sort all the items by seeders
            items[mode].sort(key=lambda tup: tup[2], reverse=True)

            results += items[mode]

        if not has_signature:
            logger.log(u'Failed to identify a page from ThePirateBay at %s attempted urls (tpb blocked? general network issue or site dead)' % len(self.urls['config_provider_home_uri']), logger.ERROR)

        return results

    def find_propers(self, search_date=datetime.datetime.today()):

        return self._find_propers(search_date, '')


class ThePirateBayCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 20  # cache update frequency

    def _getRSSData(self):

        return self.provider.get_cache_data()


provider = ThePirateBayProvider()
