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

import re
import traceback

from . import generic
from ..indexers.indexer_config import TVINFO_IMDB
from .. import logger
from ..helpers import try_int


class EztvProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'EZTV')

        self.url_base = 'https://eztvx.to/'
        self.urls = {
            'config_provider_home_uri': self.url_base,
            'browse': f'{self.url_base}api/get-torrents?limit=100&page=%s',
            'search': f'{self.url_base}api/get-torrents?limit=100&page=%s&imdb_id='
        }

        self.minseed = None

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)EZTV\s-\sTV\sTorrents', data[0:300])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        # a recent search (Cache) and a Propers search are made with no ids
        imdb_id = try_int(((kwargs.get('ids') or {}).get(TVINFO_IMDB) or {}).get('id'))
        data = {
            # the API needs the leading zeros of the IMDb id (e.g. 0096697), the stored id is a number without them
            'imdb_id': '%07d' % imdb_id,
            'torrents_count': 0,
            'torrents': []
        }
        for mode in search_params:
            if 'Cache' != mode and not imdb_id:
                continue  # the API gives every release for a search with no id, so search only by a known show id
            data['torrents_count'], data['torrents'] = 0, []
            # the API query uses no search string, only the page and the show id, so fetch the pages once per mode
            for _ in search_params[mode][:1]:
                for page in (1, 2):
                    if 'Cache' == mode:
                        search_url = self.urls['browse'] % page
                    else:
                        # 2026-05-21: IMDb id is supported HOWEVER EZTV beta** search doesn't yet support targeted
                        # search using both season episode numbers, it may never. Therefore, fetch 2x100 releases in
                        # the chance that at least one episode file qualifies more often than not.
                        search_url = f'{self.urls["search"]}{data.get("imdb_id")}' % page

                    html = self.get_url(search_url, parse_json=True)
                    if not isinstance(html, dict) or not html.get('torrents'):
                        break
                    data['torrents_count'] += len(html['torrents'])
                    data['torrents'] += html['torrents']  #type: list

                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not data.get('torrents'):
                        raise generic.HaltParseException

                    for cur_rls in data.get('torrents'):  #type: dict
                        seeders = try_int(cur_rls.get('seeds'))
                        if self._reject_item(seeders):
                            continue

                        try:
                            title = cur_rls.get('title')
                            size = cur_rls.get('size_bytes')
                            download_url = self._link(cur_rls.get('magnet_url'))
                        except (BaseException, Exception):
                            continue

                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (generic.HaltParseException, IndexError):
                    pass
                except (BaseException, Exception):
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _cache_data(self, **kwargs):

        return self._search_provider({'Cache': [0, 1]})


provider = EztvProvider()
