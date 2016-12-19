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

from . import generic
from sickbeard import show_name_helpers, tvcache
import time


class AnizbProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'Anizb', anime_only=True)

        self.url = 'https://anizb.org/'
        self.cache = AnizbCache(self)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if self.show and not self.show.is_anime:
            return results

        for mode in search_params.keys():
            for params in search_params[mode]:

                search_url = '%sapi/%s' % (self.url, params and (('?q=%s', '?q=%(q)s')['q' in params] % params) or '')
                data = self.cache.getRSSFeed(search_url)
                time.sleep(1.1)

                cnt = len(results)
                for entry in (data and data.get('entries', []) or []):
                    if entry.get('title') and entry.get('link', '').startswith('http'):
                        results.append(entry)

                self.log_result(mode=mode, count=len(results) - cnt, url=search_url)

        return list(set(results))

    def _season_strings(self, ep_obj, **kwargs):
        return [{'Season': [
            x.replace('.', ' ') for x in show_name_helpers.makeSceneSeasonSearchString(self.show, ep_obj)]}]

    def _episode_strings(self, ep_obj, **kwargs):
        return [{'Episode': [
            x.replace('.', ' ') for x in show_name_helpers.makeSceneSearchString(self.show, ep_obj)]}]


class AnizbCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)
        self.update_freq = 6

    def _cache_data(self):
        return self.provider.cache_data()


provider = AnizbProvider()
