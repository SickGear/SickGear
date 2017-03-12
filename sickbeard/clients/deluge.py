# coding=utf-8
#
# This file is part of SickGear.
#
# Original author: Mr_Orange <mr_orange@hotmail.it>
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

import json
from base64 import b64encode

import sickbeard
from sickbeard import logger
from sickbeard.clients.generic import GenericClient
from lib.requests.exceptions import RequestException


class DelugeAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        super(DelugeAPI, self).__init__('Deluge', host, username, password)

        self.url = '%s/json' % self.host.rstrip('/')

    def _post_json(self, data, process=True):
        result = self.session.post(self.url, json=data, timeout=10, verify=sickbeard.TORRENT_VERIFY_CERT)
        if process:
            return result.json()['result']

    def _request_json(self, data, process=None):
        result = self._request(method='post', json=data, timeout=10)
        if process:
            return result.json()['result']

    def _get_auth(self):

        try:
            self.auth = self._post_json({'method': 'auth.login', 'params': [self.password], 'id': 1})

            connected = self._post_json({'method': 'web.connected', 'params': [], 'id': 10})

            if not connected:
                hosts = self._post_json({'method': 'web.get_hosts', 'params': [], 'id': 11})
                if 0 == len(hosts):
                    logger.log('%s: WebUI does not contain daemons' % self.name, logger.ERROR)
                    return None

                self._post_json({'method': 'web.connect', 'params': [hosts[0][0]], 'id': 11}, False)

                connected = self._post_json({'method': 'web.connected', 'params': [], 'id': 10})

            if not connected:
                logger.log('%s: WebUI could not connect to daemon' % self.name, logger.ERROR)
                return None
        except RequestException:
            return None

        return self.auth

    def _add_torrent_uri(self, result):

        result.hash = self._request_json({
            'method': 'core.add_torrent_magnet',
            'params': [result.url,
                       {'move_completed': 'true',
                        'move_completed_path': sickbeard.TV_DOWNLOAD_DIR}],
            'id': 2}, True)

        return result.hash

    def _add_torrent_file(self, result):

        result.hash = self._request_json({
            'method': 'core.add_torrent_file',
            'params': ['%s.torrent' % result.name,
                       b64encode(result.content),
                       {'move_completed': 'true',
                        'move_completed_path': sickbeard.TV_DOWNLOAD_DIR}],
            'id': 2}, True)

        return result.hash

    def _set_torrent_label(self, result):

        label = sickbeard.TORRENT_LABEL
        if ' ' in label:
            logger.log('%s: Invalid label. Label must not contain a space' % self.name, logger.ERROR)
            return False

        if label:
            # check if label already exists and create it if not
            labels = self._request_json({
                'method': 'label.get_labels',
                'params': [],
                'id': 3}, True)

            if None is not labels:
                if label not in labels:
                    logger.log('%s: %s label does not exist in Deluge we must add it' % (self.name, label),
                               logger.DEBUG)
                    self._request_json({
                        'method': 'label.add',
                        'params': [label],
                        'id': 4})
                    logger.log('%s: %s label added to Deluge' % (self.name, label), logger.DEBUG)

                # add label to torrent
                self._request_json({
                    'method': 'label.set_torrent',
                    'params': [result.hash, label],
                    'id': 5})
                logger.log('%s: %s label added to torrent' % (self.name, label), logger.DEBUG)
            else:
                logger.log('%s: label plugin not detected' % self.name, logger.DEBUG)
                return False

        return True

    def _set_torrent_ratio(self, result):

        ratio = None
        if result.ratio:
            ratio = result.ratio

        if ratio:
            self._request_json({
                'method': 'core.set_torrent_stop_at_ratio',
                'params': [result.hash, True],
                'id': 5})

            self._request_json({
                'method': 'core.set_torrent_stop_ratio',
                'params': [result.hash, float(ratio)],
                'id': 6})
        return True

    def _set_torrent_path(self, result):

        if sickbeard.TORRENT_PATH:
            self._request_json({
                'method': 'core.set_torrent_move_completed',
                'params': [result.hash, True],
                'id': 7})

            self._request_json({
                'method': 'core.set_torrent_move_completed_path',
                'params': [result.hash, sickbeard.TORRENT_PATH],
                'id': 8})
        return True

    def _set_torrent_pause(self, result):

        if sickbeard.TORRENT_PAUSED:
            self._request_json({
                'method': 'core.pause_torrent',
                'params': [[result.hash]],
                'id': 9})
        return True


api = DelugeAPI()
