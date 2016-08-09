# Author: Mr_Orange
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

import traceback
import urllib

from . import generic
from sickbeard import logger, show_name_helpers, tvcache
from sickbeard.bs4_parser import BS4Parser


class TokyoToshokanProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TokyoToshokan', anime_only=True)

        self.url_base = self.url = 'http://tokyotosho.info/'

        self.cache = TokyoToshokanCache(self)

    def _search_provider(self, search_string, search_mode='eponly', **kwargs):

        results = []
        if self.show and not self.show.is_anime:
            return results

        params = {'terms': search_string.encode('utf-8'),
                  'type': 1}  # get anime types

        search_url = self.url + 'search.php?' + urllib.urlencode(params)
        logger.log(u'Search string: ' + search_url, logger.DEBUG)

        html = self.get_url(search_url)
        if html:
            try:
                with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                    torrent_table = soup.find('table', attrs={'class': 'listing'})
                    torrent_rows = torrent_table.find_all('tr') if torrent_table else []
                    if torrent_rows:
                        a = (0, 1)[None is not torrent_rows[0].find('td', attrs={'class': 'centertext'})]

                        for top, bottom in zip(torrent_rows[a::2], torrent_rows[a::2]):
                            title = top.find('td', attrs={'class': 'desc-top'}).text
                            url = top.find('td', attrs={'class': 'desc-top'}).find('a')['href']

                            if title and url:
                                results.append((title.lstrip(), url))

            except Exception:
                logger.log(u'Failed to parsing ' + self.name + ' Traceback: ' + traceback.format_exc(), logger.ERROR)

        return results

    def find_search_results(self, show, episodes, search_mode, manual_search=False):

        return generic.TorrentProvider.find_search_results(self, show, episodes, search_mode, manual_search)

    def _season_strings(self, ep_obj, **kwargs):

        return [x.replace('.', ' ') for x in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj)]

    def _episode_strings(self, ep_obj, **kwargs):

        return [x.replace('.', ' ') for x in show_name_helpers.makeSceneSearchString(self.show, ep_obj)]


class TokyoToshokanCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 15  # cache update frequency

    def _cache_data(self):
        params = {'filter': '1'}

        url = self.provider.url + 'rss.php?' + urllib.urlencode(params)
        logger.log(u'TokyoToshokan cache update URL: ' + url, logger.DEBUG)

        data = self.getRSSFeed(url)
        if data and 'entries' in data:
            return data.entries
        return []


provider = TokyoToshokanProvider()
