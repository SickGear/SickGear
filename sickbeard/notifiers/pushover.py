# Author: Marvin Pinto <me@marvinp.ca>
# Author: Dennis Lutter <lad1337@gmail.com>
# Author: Aaron Bieber <deftly@gmail.com>
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

import base64
import socket
import time
import urllib
import urllib2

import sickbeard
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier

API_URL = 'https://api.pushover.net/1/messages.json'
DEVICE_URL = 'https://api.pushover.net/1/users/validate.json'


class PushoverNotifier(Notifier):

    def get_devices(self, user_key=None, api_key=None):

        user_key = self._choose(user_key, sickbeard.PUSHOVER_USERKEY)
        api_key = self._choose(api_key, sickbeard.PUSHOVER_APIKEY)

        data = urllib.urlencode(dict(token=api_key, user=user_key))

        # get devices from pushover
        result = False
        try:
            req = urllib2.Request(DEVICE_URL)
            handle = urllib2.urlopen(req, data)
            if handle:
                result = handle.read()
            handle.close()
        except (urllib2.URLError, socket.timeout):
            pass

        return ('{}', result)[bool(result)]

    def _notify(self, title, body, user_key=None, api_key=None, priority=None, device=None, sound=None, **kwargs):
        """
        Sends a pushover notification to the address provided

        title: The title of the message
        msg: The message to send (unicode)
        user_key: The pushover user id to send the message to (or to subscribe with)

        returns: True if the message succeeded, False otherwise
        """
        user_key = self._choose(user_key, sickbeard.PUSHOVER_USERKEY)
        api_key = self._choose(api_key, sickbeard.PUSHOVER_APIKEY)
        priority = self._choose(priority, sickbeard.PUSHOVER_PRIORITY)
        device = self._choose(device, sickbeard.PUSHOVER_DEVICE)
        sound = self._choose(sound, sickbeard.PUSHOVER_SOUND)

        # build up the URL and parameters
        params = dict(title=title, message=body.strip().encode('utf-8'), user=user_key, timestamp=int(time.time()))
        if api_key:
            params.update(token=api_key)
        if priority:
            params.update(priority=priority)
        if not device:
            params.update(device=device)
        if not sound:
            params.update(sound=sound)

        # send the request to pushover
        result = None
        try:
            req = urllib2.Request(API_URL)
            handle = urllib2.urlopen(req, urllib.urlencode(params))
            handle.close()

        except urllib2.URLError as e:
            # HTTP status 404 if the provided email address isn't a Pushover user.
            if 404 == e.code:
                result = 'Username is wrong/not a Pushover email. Pushover will send an email to it'
                self._log_warning(result)

            # For HTTP status code 401's, it is because you are passing in either an invalid token,
            # or the user has not added your service.
            elif 401 == e.code:

                # HTTP status 401 if the user doesn't have the service added
                subscribe_note = self._send_pushover(title, body, user_key)
                if subscribe_note:
                    self._log_debug('Subscription sent')
                    # return True
                else:
                    result = 'Subscription could not be sent'
                    self._log_error(result)
            else:
                # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
                if 400 == e.code:
                    result = 'Wrong data sent to Pushover'

                # If you receive a HTTP status code of 429,
                #  it is because the message limit has been reached (free limit is 7,500)
                elif 429 == e.code:
                    result = 'API message limit reached - try a different API key'

                # If you receive a HTTP status code of 500, service is unavailable
                elif 500 == e.code:
                    result = 'Unable to connect to API, service unavailable'

                else:
                    result = 'Http response code "%s"' % response.status

                self._log_error(result)

        return self._choose((True, 'Failed to send notification: %s' % result)[bool(result)], not bool(result))


notifier = PushoverNotifier
