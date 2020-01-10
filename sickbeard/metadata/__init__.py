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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

__all__ = ['generic', 'helpers', 'kodi', 'mede8er', 'mediabrowser', 'ps3', 'tivo', 'wdtv', 'xbmc', 'xbmc_12plus']

import sys

from . import kodi, mede8er, mediabrowser, ps3, tivo, wdtv, xbmc, xbmc_12plus
from _23 import filter_list


def available_generators():
    return filter_list(lambda x: x not in ('generic', 'helpers'), __all__)


def _getMetadataModule(name):
    name = name.lower()
    prefix = "sickbeard.metadata."
    if name in __all__ and prefix + name in sys.modules:
        return sys.modules[prefix + name]
    return None


def _getMetadataClass(name):
    module = _getMetadataModule(name)

    if not module:
        return None

    return module.metadata_class()


def get_metadata_generator_dict():
    result = {}
    for cur_generator_id in available_generators():
        cur_generator = _getMetadataClass(cur_generator_id)
        if not cur_generator:
            continue
        result[cur_generator.name] = cur_generator

    return result
        
