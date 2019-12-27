# Author: Nic Wolfe <nic@wolfeden.ca>
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
import os
import time

from .indexer_config import init_config, tvinfo_config
from ..helpers import proxy_setting
import sickbeard

from _23 import list_values

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict


class ShowContainer(dict):
    """
    Simple dict that holds a series of Show instances
    """

    # noinspection PyMissingConstructor
    def __init__(self):
        self._stack = []
        self._lastgc = time.time()

    def __setitem__(self, key, value):
        self._stack.append(key)

        # keep only the 100th latest results
        if time.time() - self._lastgc > 20:
            for o in self._stack[:-100]:
                del self[o]

            self._stack = self._stack[-100:]

            self._lastgc = time.time()

        super(ShowContainer, self).__setitem__(key, value)


class DummyIndexer(object):
    # noinspection PyUnusedLocal
    def __init__(self, *args, **kwargs):
        self.config = {
            'apikey': '',
            'debug_enabled': False,
            'custom_ui': None,
            'proxy': None,
            'cache_enabled': False,
            'cache_location': '',
            'valid_languages': [],
            'langabbv_to_id': {},
            'language': 'en',
            'base_url': '',
        }

        self.corrections = {}
        self.shows = ShowContainer()

    def __getitem__(self, key):
        return None

    def __repr__(self):
        return str(self.shows)

    # noinspection PyUnusedLocal
    @staticmethod
    def search(series):
        return []


class TVInfoAPI(object):
    def __init__(self, tvid=None):
        self.tvid = int(tvid) if tvid else None

    def __del__(self):
        pass

    def setup(self, *args, **kwargs):
        if self.tvid:
            if tvinfo_config[self.tvid]['active'] or ('no_dummy' in kwargs and True is kwargs['no_dummy']):
                if 'no_dummy' in kwargs:
                    kwargs.pop('no_dummy')
                return tvinfo_config[self.tvid]['module'](*args, **kwargs)
            else:
                return DummyIndexer(*args, **kwargs)

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
            if sickbeard.CACHE_DIR:
                tvinfo_config[self.tvid]['api_params']['cache'] = os.path.join(
                    sickbeard.CACHE_DIR, 'indexers', self.name)
            if sickbeard.PROXY_SETTING and sickbeard.PROXY_INDEXERS:
                (proxy_address, pac_found) = proxy_setting(sickbeard.PROXY_SETTING,
                                                           tvinfo_config[self.tvid]['base_url'],
                                                           force=True)
                if proxy_address:
                    tvinfo_config[self.tvid]['api_params']['proxy'] = proxy_address

            return tvinfo_config[self.tvid]['api_params']

    @property
    def cache(self):
        if sickbeard.CACHE_DIR:
            return self.api_params['cache']

    @property
    def sources(self):
        # type: () -> Dict[int, AnyStr]
        return dict([(int(x['id']), x['name']) for x in list_values(tvinfo_config) if not x['mapped_only'] and
                     True is not x.get('fallback')])

    @property
    def search_sources(self):
        # type: () -> Dict[int, AnyStr]
        return dict([(int(x['id']), x['name']) for x in list_values(tvinfo_config) if not x['mapped_only'] and
                     x.get('active') and not x.get('defunct') and True is not x.get('fallback')])

    @property
    def all_sources(self):
        # type: () -> Dict[int, AnyStr]
        """
        :return: return all indexers including mapped only indexers excluding fallback indexers
        """
        return dict([(int(x['id']), x['name']) for x in list_values(tvinfo_config) if True is not x.get('fallback')])

    @property
    def fallback_sources(self):
        # type: () -> Dict[int, AnyStr]
        """
        :return: return all fallback indexers
        """
        return dict([(int(x['id']), x['name']) for x in list_values(tvinfo_config) if True is x.get('fallback')])

    @property
    def xem_supported_sources(self):
        # type: () -> Dict[int, AnyStr]
        return dict([(int(x['id']), x['name']) for x in list_values(tvinfo_config) if x.get('xem_origin')])
