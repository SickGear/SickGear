# Authors: Mr_Orange <mr_orange@hotmail.it>
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

import re

from .generic import GenericClient
import sickbeard

from _23 import urlencode
from six import iteritems


class uTorrentAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        super(uTorrentAPI, self).__init__('uTorrent', host, username, password)

        self.url = self.host + 'gui/'

    def _request(self, method='get', params=None, files=None, **kwargs):
        params = {} if None is params else params

        return super(uTorrentAPI, self)._request(
            method=method,
            params='token={0:s}&{1:s}'.format(self.auth, '&'.join(
                ['%s' % urlencode(dict([[key, str(value)]]))
                 for key, value in iteritems(params)])) if any(params) else params,
            files=files)

    def _get_auth(self):

        try:
            response = self.session.get(self.url + 'token.html', verify=False)
            self.auth = re.findall('<div.*?>(.*?)</', response.text)[0]
            return self.auth if not 404 == response.status_code else None
        except (BaseException, Exception):
            return None

    def _add_torrent_uri(self, result):

        params = {'action': 'add-url', 's': result.url}
        return self._request(params=params)

    def _add_torrent_file(self, result):

        params = {'action': 'add-file'}
        files = {'torrent_file': (result.name + '.torrent', result.content)}
        return self._request(method='post', params=params, files=files)

    def _set_torrent_label(self, result):

        params = {'action': 'setprops',
                  'hash': result.hash,
                  's': 'label',
                  'v': sickbeard.TORRENT_LABEL
                  }
        return self._request(params=params)

    def _set_torrent_ratio(self, result):

        ratio = None
        if result.ratio:
            ratio = result.ratio

        if ratio:
            params = {'action': 'setprops',
                      'hash': result.hash,
                      's': 'seed_override',
                      'v': '1'
                      }
            if self._request(params=params):
                params = {'action': 'setprops',
                          'hash': result.hash,
                          's': 'seed_ratio',
                          'v': float(ratio) * 10
                          }
                return self._request(params=params)
            else:
                return False

        return True

    def _set_torrent_seed_time(self, result):

        seed_time = result.provider.seed_time or sickbeard.TORRENT_SEED_TIME
        if seed_time:
            params = {'action': 'setprops',
                      'hash': result.hash,
                      's': 'seed_override',
                      'v': '1'}
            if self._request(params=params):
                params = {'action': 'setprops',
                          'hash': result.hash,
                          's': 'seed_time',
                          'v': int(seed_time) * 60}
                return self._request(params=params)
            return False
        return True

    def _set_torrent_priority(self, result):

        if 1 == result.priority:
            params = {'action': 'queuetop', 'hash': result.hash}
            return self._request(params=params)
        return True

    def _set_torrent_pause(self, result):

        if sickbeard.TORRENT_PAUSED:
            params = {'action': 'pause', 'hash': result.hash}
        else:
            params = {'action': 'start', 'hash': result.hash}

        return self._request(params=params)


api = uTorrentAPI()
