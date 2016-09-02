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

import re
import traceback
import urllib

from . import generic
from sickbeard import logger, show_name_helpers, tvcache
from sickbeard.helpers import tryInt
from sickbeard.bs4_parser import BS4Parser


class TokyoToshokanProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TokyoToshokan', anime_only=True)

        self.url_base = self.url = 'https://tokyotosho.info/'

        self.cache = TokyoToshokanCache(self)

    def _search_provider(self, search_string, search_mode='eponly', **kwargs):

        results = []
        if self.show and not self.show.is_anime:
            return results

        params = urllib.urlencode({'terms': search_string.encode('utf-8'),
                                   'type': 1})  # get anime types

        search_url = '%ssearch.php?%s' % (self.url, params)
        mode = ('Episode', 'Season')['sponly' == search_mode]

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'stats': 'S:\s*?(\d)+\s*L:\s*(\d+)', 'size': 'size:\s*(\d+[.,]\d+\w+)'}.iteritems())

        html = self.get_url(search_url)
        if html:
            try:
                with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                    torrent_table = soup.find('table', class_='listing')
                    torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')
                    if torrent_rows:
                        a = (0, 1)[None is not torrent_rows[0].find('td', class_='centertext')]

                        for top, bottom in zip(torrent_rows[a::2], torrent_rows[a+1::2]):
                            try:
                                bottom_text = bottom.get_text() or ''
                                stats = rc['stats'].findall(bottom_text)
                                seeders, leechers = (0, 0) if not stats else [tryInt(n) for n in stats[0]]

                                size = rc['size'].findall(bottom_text)
                                size = size and size[0] or -1

                                info = top.find('td', class_='desc-top')
                                title = info and re.sub(r'[ .]{2,}', '.', info.get_text().strip())
                                urls = info and sorted([x.get('href') for x in info.find_all('a') or []])
                                download_url = urls and urls[0].startswith('http') and urls[0] or urls[1]
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                results.append((title, download_url, seeders, self._bytesizer(size)))

            except (StandardError, Exception):
                logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

        self._log_search(mode, len(results), search_url)

        return self._sort_seeding(mode, results)

    def _season_strings(self, ep_obj, **kwargs):

        return [x.replace('.', ' ') for x in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj)]

    def _episode_strings(self, ep_obj, **kwargs):

        return [x.replace('.', ' ') for x in show_name_helpers.makeSceneSearchString(self.show, ep_obj)]


class TokyoToshokanCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 15

    def _cache_data(self):

        mode = 'Cache'
        search_url = '%srss.php?%s' % (self.provider.url, urllib.urlencode({'filter': '1'}))
        data = self.getRSSFeed(search_url)

        results = []
        if data and 'entries' in data:

            rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'size': 'size:\s*(\d+[.,]\d+\w+)'}.iteritems())

            for cur_item in data.get('entries', []):
                try:
                    title, download_url = self._title_and_url(cur_item)
                    size = rc['size'].findall(cur_item.get('summary_detail', {'value': ''}).get('value', ''))
                    size = size and size[0] or -1

                except (AttributeError, TypeError, ValueError):
                    continue

                if title and download_url:
                    # feed does not carry seed, leech counts
                    results.append((title, download_url, 0, self.provider._bytesizer(size)))

        self.provider._log_search(mode, len(results), search_url)

        return results


provider = TokyoToshokanProvider()
