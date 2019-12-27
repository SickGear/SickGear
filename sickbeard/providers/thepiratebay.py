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

from __future__ import with_statement, division

import os
import re
import traceback

from . import generic
from .. import logger, show_name_helpers
from ..common import mediaExtensions, Quality
from ..helpers import try_int
from ..name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from bs4_parser import BS4Parser

from _23 import b64decodestring, filter_list, quote, unidecode
from six import iteritems


class ThePirateBayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'The Pirate Bay')

        self.url_home = ['https://thepiratebay.se/'] + \
                        ['https://%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'[h\sI]+', '', x[::-1]) for x in [
                                'm IY', '5  F', 'HhIc', 'vI J', 'HIhe', 'uI k', '2  d', 'uh l']],
                            [re.sub(r'[N\sQ]+', '', x[::-1]) for x in [
                                'lN Gc', 'X  Yy', 'c lNR', 'vNJNH', 'kQNHe', 'GQdQu', 'wNN9']],
                        ]]]

        self.url_vars = {'search': 'search/%s/0/7/200', 'browse': 'tv/latest/',
                         'search2': 'search.php?q=%s&video=on&category=0&page=0&orderby=99', 'browse2': '?load=/recent'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s',
                         'search': '%(home)s%(vars)s', 'search2': '%(home)s%(vars)s',
                         'browse': '%(home)s%(vars)s', 'browse2': '%(home)s%(vars)s'}

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
        if self.should_skip() or not data:
            return None

        files_list = re.findall('<td.+>(.*?)</td>', data)

        if not files_list:
            logger.log(u'Unable to get the torrent file list for ' + title, logger.ERROR)

        video_files = filter_list(lambda x: x.rpartition('.')[2].lower() in mediaExtensions, files_list)

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
            my_parser = NameParser(show_obj=self.show_obj, indexer_lookup=False)
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

        if ep_obj.show_obj.air_by_date or ep_obj.show_obj.sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            ep_detail = [airdate, 'Season ' + airdate]
        elif ep_obj.show_obj.anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            season = (ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show_obj.is_scene)]
            ep_detail = ['S%02d' % int(season), 'Season %s -Ep*' % season]

        return [{'Season': self._build_search_strings(ep_detail)}]

    def _episode_strings(self, ep_obj, **kwargs):

        return super(ThePirateBayProvider, self)._episode_strings(
            ep_obj, date_or=True,
            ep_detail_anime=lambda x: '%02i' % x, **kwargs)

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': 'detail', 'get': 'download[^"]+magnet', 'tid': r'.*/(\d{5,}).*',
            'verify': '(?:helper|moderator|trusted|vip)', 'size': r'size[^\d]+(\d+(?:[.,]\d+)?\W*[bkmgt]\w+)'})])

        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)

                s_mode = 'browse' if 'Cache' == mode else 'search'
                for i in ('', '2'):
                    search_url = self.urls['%s%s' % (s_mode, i)]
                    if 'Cache' != mode:
                        search_url = search_url % quote(search_string)

                    html = self.get_url(search_url)
                    if self.should_skip():
                        return results

                    if html and not self._has_no_results(html):
                        break
                        
                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        self._url = None
                        raise generic.HaltParseException

                    with BS4Parser(html, parse_only=dict(table={'id': 'searchResult'})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl.find_all('tr')[1:]:
                            cells = tr.find_all('td')
                            if 3 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers = [try_int(cells[head[x]].get_text().strip())
                                                     for x in ('seed', 'leech')]
                                if self._reject_item(seeders, leechers):
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
                                ep_number = int(epcount // len(set(show_name_helpers.allPossibleShowNames(
                                    self.show_obj))))
                                title = self._find_season_quality(title, tid, ep_number)

                            if title and download_magnet:
                                size = None
                                try:
                                    size = rc['size'].findall(tr.find_all(class_='detDesc')[0].get_text())[0]
                                except (BaseException, Exception):
                                    pass

                                items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = ThePirateBayProvider()
