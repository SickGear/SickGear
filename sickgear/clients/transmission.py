# Author: Mr_Orange <mr_orange@hotmail.it>
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

from .generic import GenericClient
from .. import logger
import sickgear

from _23 import b64encodestring


class TransmissionAPI(GenericClient):
    # RPC spec; https://github.com/transmission/transmission/blob/master/extras/rpc-spec.txt

    def __init__(self, host=None, username=None, password=None):

        super(TransmissionAPI, self).__init__('Transmission', host, username, password)

        self.url = self.host + 'transmission/rpc'
        self.blankable, self.download_dir = None, None
        self.rpc_version = 0

    def _get_auth(self):

        auth = None
        try:
            response = self.session.post(self.url, json={'method': 'session-get'},
                                         timeout=120, verify=sickgear.TORRENT_VERIFY_CERT)
            auth = re.search(r'(?i)X-Transmission-Session-Id:\s*(\w+)', response.text).group(1)
        except (BaseException, Exception):
            try:
                # noinspection PyUnboundLocalVariable
                auth = response.headers.get('X-Transmission-Session-Id')
                if not auth:
                    resp = response.json()
                    auth = resp['arguments']['session-id']
            except (BaseException, Exception):
                pass

        if not self.auth:
            if not auth:
                return False
            self.auth = auth

        self.session.headers.update({'x-transmission-session-id': self.auth})

        # Validating Transmission authorization
        response = self._request(method='post', json={'method': 'session-get', 'arguments': {}})

        resp = {}
        try:
            resp = response.json()
            self.blankable = 14386 >= int(re.findall(r'.*[(](\d+)', resp.get('arguments', {}).get('version', '(0)'))[0])
        except (BaseException, Exception):
            pass

        self.rpc_version = resp.get('arguments', {}).get('rpc-version', 0)
        self.download_dir = resp.get('arguments', {}).get('download-dir', '')
        client_text = '%s %s' % (self.name, resp.get('arguments', {}).get('version', '0').split()[0] or '')
        return True, 'Success: Connected and authenticated to %s' % client_text

    def _add_torrent_uri(self, result):

        return self._add_torrent({'filename': result.url})

    def _add_torrent_file(self, result):

        return self._add_torrent({'metainfo': b64encodestring(result.content)})

    def _add_torrent(self, t_object):

        # populate blankable and download_dir
        if not self._get_auth():
            logger.log('%s: Authentication failed' % self.name, logger.ERROR)
            return False

        download_dir = None
        if sickgear.TORRENT_PATH or self.blankable:
            download_dir = sickgear.TORRENT_PATH
        elif self.download_dir:
            download_dir = self.download_dir
        else:
            logger.log('Path required for Transmission Downloaded files location', logger.ERROR)

        if not download_dir and not self.blankable:
            return False

        t_object.update({'paused': (0, 1)[sickgear.TORRENT_PAUSED], 'download-dir': download_dir})
        response = self._request(method='post', json={'method': 'torrent-add', 'arguments': t_object})

        return 'success' == response.json().get('result', '')

    def _rpc_torrent_set(self, arguments):
        try:
            response = self._request(method='post', json={'method': 'torrent-set', 'arguments': arguments})
            return 'success' == response.json().get('result', '')
        except(BaseException, Exception):
            return False

    def _set_torrent_ratio(self, result):

        ratio, mode = (result.ratio, None)[not result.ratio], 0
        if ratio:
            if -1 == float(ratio):
                ratio, mode = 0, 2
            elif 0 <= float(ratio):
                ratio, mode = float(ratio), 1  # Stop seeding at seedRatioLimit

        return self._rpc_torrent_set(dict(ids=[result.hash], seedRatioLimit=ratio, seedRatioMode=mode))

    def _set_torrent_seed_time(self, result):

        if result.provider.seed_time or (sickgear.TORRENT_SEED_TIME and -1 != sickgear.TORRENT_SEED_TIME):
            seed_time = result.provider.seed_time or sickgear.TORRENT_SEED_TIME

            return self._rpc_torrent_set(dict(ids=[result.hash], seedIdleLimit=int(seed_time) * 60, seedIdleMode=1))

        return True

    def _set_torrent_priority(self, result):

        arguments = dict(ids=[result.hash])

        level = 'priority-normal'
        if -1 == result.priority:
            level = 'priority-low'
        elif 1 == result.priority:
            # set high priority for all files in torrent
            level = 'priority-high'
            # move torrent to the top if the queue
            arguments['queuePosition'] = 0
            if sickgear.TORRENT_HIGH_BANDWIDTH:
                arguments['bandwidthPriority'] = 1

        arguments[level] = []

        return self._rpc_torrent_set(arguments)

    def _set_torrent_label(self, search_result):

        label = sickgear.TORRENT_LABEL

        if 16 > self.rpc_version or not label:
            return super(TransmissionAPI, self)._set_torrent_label(search_result)

        return self._rpc_torrent_set(dict(ids=[search_result.hash], labels=label.split(',')))


api = TransmissionAPI()
