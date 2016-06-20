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
import re
import traceback
import urllib

from . import generic
from sickbeard import config, logger, show_name_helpers, tvcache
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import (has_anime, tryInt)
from sickbeard.common import Quality, mediaExtensions
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from lib.unidecode import unidecode


class KATProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'KickAssTorrents')

        self.url_base = 'https://kat.cr/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'base': [self.url_base, 'http://katproxy.com/'],
                     'search': 'usearch/%s/',
                     'sorted': '?field=time_add&sorder=desc'}

        self.proper_search_terms = None
        self.url = self.urls['config_provider_home_uri']

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False
        self.cache = KATCache(self)

    def _find_season_quality(self, title, torrent_link, ep_number):
        """ Return the modified title of a Season Torrent with the quality found inspecting torrent file list """

        quality = Quality.UNKNOWN

        file_name = None

        data = self.get_url(torrent_link)
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

    def _season_strings(self, ep_obj, **kwargs):

        if ep_obj.show.air_by_date or ep_obj.show.is_sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            ep_detail = [airdate, 'Season ' + airdate]
        elif ep_obj.show.is_anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            season = (ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show.is_scene)]
            ep_detail = ['S%(s)02i -S%(s)02iE' % {'s': season}, 'Season %s -Ep*' % season]

        return [{'Season': self._build_search_strings(ep_detail)}]

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, date_or=True,
                                                        ep_detail=lambda x: '%s|%s' % (config.naming_ep_type[2] % x,
                                                                                       config.naming_ep_type[0] % x),
                                                        ep_detail_anime=lambda x: '%02i' % x, **kwargs)

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, **kwargs):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'link': 'normal', 'get': '^magnet', 'verif': 'verif'}.items())
        url = 0
        for mode in search_params.keys():
            search_show = mode in ['Season', 'Episode']
            if not search_show and has_anime():
                search_params[mode] *= (1, 2)['Cache' == mode]
                'Propers' == mode and search_params[mode].append('v1|v2|v3|v4|v5')

            for enum, search_string in enumerate(search_params[mode]):
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                self.url = self.urls['base'][url]
                search_url = self.url + (self.urls['search'] % urllib.quote('%scategory:%s' % (
                    ('', '%s ' % search_string)['Cache' != mode],
                    ('tv', 'anime')[(search_show and bool(self.show and self.show.is_anime)) or bool(enum)])))

                self.session.headers.update({'Referer': search_url})
                html = self.get_url(search_url + self.urls['sorted'])

                cnt = len(items[mode])
                try:
                    if not html or 'kastatus.com' not in html or self._has_no_results(html) or re.search(r'(?is)<(?:h\d)[^>]*>.*?(?:did\snot\smatch)', html):
                        if html and 'kastatus.com' not in html:
                            url += (1, 0)[url == len(self.urls['base'])]
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', attrs={'class': 'data'})
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            try:
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in (-2, -1, -5)]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.find('div', {'class': 'torrentname'})
                                title = (info.find_all('a')[1].get_text() or info.find('a', 'cellMainLink').get_text())\
                                    .strip()
                                link = self.url + info.find('a', {'class': rc['link']})['href'].lstrip('/')

                                download_magnet = tr.find('a', href=rc['get'])['href']
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if self.confirmed and not (tr.find('a', title=rc['verif']) or tr.find('i', title=rc['verif'])):
                                logger.log(u'Skipping untrusted non-verified result: %s' % title, logger.DEBUG)
                                continue

                            # Check number video files = episode in season and find the real Quality for full season torrent analyzing files in torrent
                            if 'Season' == mode and 'sponly' == search_mode:
                                ep_number = int(epcount / len(set(show_name_helpers.allPossibleShowNames(self.show))))
                                title = self._find_season_quality(title, link, ep_number)

                            if title and download_magnet:
                                items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            self._sort_seeders(mode, items)

            results = list(set(results + items[mode]))

        return results


class KATCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 20  # cache update frequency

    def _cache_data(self):

        return self.provider.cache_data()


provider = KATProvider()
