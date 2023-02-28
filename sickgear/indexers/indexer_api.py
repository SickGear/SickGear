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
import os

from .indexer_config import init_config, tvinfo_config
from sg_helpers import proxy_setting
import sickgear
from lib.tvinfo_base import TVInfoBase

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict


class TVInfoAPI(object):
    def __init__(self, tvid=None):
        self.tvid = int(tvid) if tvid else None

    def __del__(self):
        pass

    def setup(self, *args, **kwargs):
        # type: (...) -> TVInfoBase
        if self.tvid:
            if tvinfo_config[self.tvid]['active'] or ('no_dummy' in kwargs and True is kwargs['no_dummy']):
                if 'no_dummy' in kwargs:
                    kwargs.pop('no_dummy')
                indexer_cache_dir = os.path.join(sickgear.CACHE_DIR, 'tvinfo_cache', tvinfo_config[self.tvid]['name'])
                kwargs['diskcache_dir'] = indexer_cache_dir
                return tvinfo_config[self.tvid]['module'](*args, **kwargs)
            else:
                return TVInfoBase(*args, **kwargs)

    @property
    def config(self):
        # type: () -> Dict
        if self.tvid:
            return tvinfo_config[self.tvid]
        return init_config

    @property
    def name(self):
        # type: () -> AnyStr
        if self.tvid:
            return tvinfo_config[self.tvid]['name']

    @property
    def api_params(self):
        # type: () -> Dict
        if self.tvid:
            if sickgear.CACHE_DIR:
                tvinfo_config[self.tvid]['api_params']['cache'] = os.path.join(
                    sickgear.CACHE_DIR, 'indexers', self.name)
            if sickgear.PROXY_SETTING and sickgear.PROXY_INDEXERS:
                (proxy_address, pac_found) = proxy_setting(sickgear.PROXY_SETTING,
                                                           tvinfo_config[self.tvid]['base_url'],
                                                           force=True)
                if proxy_address:
                    tvinfo_config[self.tvid]['api_params']['proxy'] = proxy_address

            return tvinfo_config[self.tvid]['api_params']

    @property
    def cache(self):
        if sickgear.CACHE_DIR:
            return self.api_params['cache']

    @staticmethod
    def _filter(condition):
        return dict([(int(x['id']), x['name']) for x in list(tvinfo_config.values()) if condition(x)])

    @property
    def sources(self):
        # type: () -> Dict[int, AnyStr]
        return self._filter(lambda x:
                            not x['mapped_only'] and
                            True is not x.get('fallback') and True is not x.get('people_only'))

    @property
    def search_sources(self):
        # type: () -> Dict[int, AnyStr]
        return self._filter(lambda x:
                            not x['mapped_only'] and x.get('active') and not x.get('defunct') and
                            True is not x.get('fallback') and True is not x.get('people_only'))

    @property
    def all_sources(self):
        # type: () -> Dict[int, AnyStr]
        """
        :return: return all indexers for show data including mapped only indexers excluding fallback indexers
        """
        return self._filter(lambda x:
                            True is not x.get('fallback') and True is not x.get('people_only'))

    @property
    def all_non_fallback_sources(self):
        # type: (...) -> Dict[int, AnyStr]
        """
        return all sources with the exclusion of fallback indexer
        """
        return self._filter(lambda x: True is not x.get('fallback'))

    @property
    def fallback_sources(self):
        # type: () -> Dict[int, AnyStr]
        """
        :return: return all fallback indexers
        """
        return self._filter(lambda x: True is x.get('fallback'))

    @property
    def xem_supported_sources(self):
        # type: () -> Dict[int, AnyStr]
        return self._filter(lambda x: x.get('xem_origin'))
