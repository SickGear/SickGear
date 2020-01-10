# Author: Nic Wolfe <nic@wolfeden.ca>
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

# noinspection PyUnresolvedReferences
from sg_helpers import http_error_code

__all__ = ['deluge', 'download_station', 'qbittorrent', 'rtorrent', 'transmission', 'utorrent']

default_host = {
    'deluge': 'http://localhost:8112',
    'download_station': 'http://localhost:5000',
    'rtorrent': 'scgi://localhost:5000',
    'qbittorrent': 'http://localhost:8080',
    'transmission': 'http://localhost:9091',
    'utorrent': 'http://localhost:8000'}


def get_client_instance(name):

    module = __import__('sickbeard.clients.%s' % name.lower(), fromlist=__all__)
    return getattr(module, module.api.__class__.__name__)
