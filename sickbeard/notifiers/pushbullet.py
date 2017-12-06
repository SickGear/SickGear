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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear. If not, see <http://www.gnu.org/licenses/>.

import base64
import simplejson as json

import sickbeard
from sickbeard.notifiers.generic import Notifier

import requests

PUSHAPI_ENDPOINT = 'https://api.pushbullet.com/v2/pushes'
DEVICEAPI_ENDPOINT = 'https://api.pushbullet.com/v2/devices'


class PushbulletNotifier(Notifier):

    @staticmethod
    def get_devices(access_token=None):
        # fill in omitted parameters
        if not access_token:
            access_token = sickbeard.PUSHBULLET_ACCESS_TOKEN

        # get devices from pushbullet
        try:
            base64string = base64.encodestring('%s:%s' % (access_token, ''))[:-1]
            headers = dict(Authorization='Basic %s' % base64string)
            return requests.get(DEVICEAPI_ENDPOINT, headers=headers).text
        except (StandardError, Exception):
            return json.dumps(dict(error=dict(message='Error failed to connect')))

    def _notify(self, title, body, access_token=None, device_iden=None, **kwargs):
        """
        Sends a pushbullet notification based on the provided info or SG config

        title: The title of the notification to send
        body: The body string to send
        access_token: The access token to grant access
        device_iden: The iden of a specific target, if none provided send to all devices
        """
        access_token = self._choose(access_token, sickbeard.PUSHBULLET_ACCESS_TOKEN)
        device_iden = self._choose(device_iden, sickbeard.PUSHBULLET_DEVICE_IDEN)

        # send the request to Pushbullet
        result = None
        try:
            base64string = base64.encodestring('%s:%s' % (access_token, ''))[:-1]
            headers = {'Authorization': 'Basic %s' % base64string, 'Content-Type': 'application/json'}
            resp = requests.post(PUSHAPI_ENDPOINT, headers=headers,
                                 data=json.dumps(dict(
                                     type='note', title=title, body=body.strip().encode('utf-8'),
                                     device_iden=device_iden)))
            resp.raise_for_status()
        except (StandardError, Exception):
            try:
                # noinspection PyUnboundLocalVariable
                result = resp.json()['error']['message']
            except (StandardError, Exception):
                result = 'no response'
            self._log_warning(u'%s' % result)

        return self._choose((True, 'Failed to send notification: %s' % result)[bool(result)], not bool(result))


notifier = PushbulletNotifier
