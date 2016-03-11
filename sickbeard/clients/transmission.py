# Author: Mr_Orange <mr_orange@hotmail.it>
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
from base64 import b64encode

import sickbeard
from sickbeard import logger
from sickbeard.clients.generic import GenericClient


class TransmissionAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        super(TransmissionAPI, self).__init__('Transmission', host, username, password)

        self.url = self.host + 'transmission/rpc'
        self.blankable, self.download_dir = None, None

    def _get_auth(self):

        try:
            response = self.session.post(self.url, json={'method': 'session-get'},
                                         timeout=120, verify=sickbeard.TORRENT_VERIFY_CERT)
            self.auth = re.search(r'(?i)X-Transmission-Session-Id:\s*(\w+)', response.text).group(1)
        except:
            return None

        self.session.headers.update({'x-transmission-session-id': self.auth})

        # Validating Transmission authorization
        response = self._request(method='post', json={'method': 'session-get', 'arguments': {}})

        try:
            resp = response.json()
            self.blankable = 14386 >= int(re.findall(r'.*[(](\d+)', resp.get('arguments', {}).get('version', '(0)'))[0])
            self.download_dir = resp.get('arguments', {}).get('download-dir', '')
        except:
            pass

        return self.auth

    def _add_torrent_uri(self, result):

        return self._add_torrent({'filename': result.url})

    def _add_torrent_file(self, result):

        return self._add_torrent({'metainfo': b64encode(result.content)})

    def _add_torrent(self, t_object):

        download_dir = None
        if sickbeard.TORRENT_PATH or self.blankable:
            download_dir = sickbeard.TORRENT_PATH
        elif self.download_dir:
            download_dir = self.download_dir
        else:
            logger.log('Path required for Transmission Downloaded files location', logger.ERROR)

        if not download_dir and not self.blankable:
            return False

        t_object.update({'paused': (0, 1)[sickbeard.TORRENT_PAUSED], 'download-dir': download_dir})
        response = self._request(method='post', json={'method': 'torrent-add', 'arguments': t_object})

        return 'success' == response.json().get('result', '')

    def _set_torrent_ratio(self, result):

        ratio, mode = (result.ratio, None)[not result.ratio], 0
        if ratio:
            if -1 == float(ratio):
                ratio, mode = 0, 2
            elif 0 <= float(ratio):
                ratio, mode = float(ratio), 1  # Stop seeding at seedRatioLimit

        response = self._request(method='post', json={
            'method': 'torrent-set',
            'arguments': {'ids': [result.hash], 'seedRatioLimit': ratio, 'seedRatioMode': mode}})

        return 'success' == response.json().get('result', '')

    def _set_torrent_seed_time(self, result):

        if result.provider.seed_time or (sickbeard.TORRENT_SEED_TIME and -1 != sickbeard.TORRENT_SEED_TIME):
            seed_time = result.provider.seed_time or sickbeard.TORRENT_SEED_TIME

            response = self._request(method='post', json={
                'method': 'torrent-set',
                'arguments': {'ids': [result.hash], 'seedIdleLimit': int(seed_time) * 60, 'seedIdleMode': 1}})

            return 'success' == response.json().get('result', '')
        else:
            return True

    def _set_torrent_priority(self, result):

        arguments = {'ids': [result.hash]}

        if -1 == result.priority:
            arguments['priority-low'] = []
        elif 1 == result.priority:
            # set high priority for all files in torrent
            arguments['priority-high'] = []
            # move torrent to the top if the queue
            arguments['queuePosition'] = 0
            if sickbeard.TORRENT_HIGH_BANDWIDTH:
                arguments['bandwidthPriority'] = 1
        else:
            arguments['priority-normal'] = []

        response = self._request(method='post', json={'method': 'torrent-set', 'arguments': arguments})

        return 'success' == response.json().get('result', '')


api = TransmissionAPI()
