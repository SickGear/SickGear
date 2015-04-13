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

import urllib
import urllib2
import time
import socket
import base64

import sickbeard
from sickbeard import logger
from sickbeard.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, NOTIFY_SUBTITLE_DOWNLOAD, NOTIFY_GIT_UPDATE, NOTIFY_GIT_UPDATE_TEXT
from sickbeard.exceptions import ex

API_URL = 'https://api.pushover.net/1/messages.json'
DEVICE_URL = 'https://api.pushover.net/1/users/validate.json'


class PushoverNotifier:

    def get_devices(self, userKey=None, apiKey=None):
        # fill in omitted parameters
        if not userKey:
            userKey = sickbeard.PUSHOVER_USERKEY
        if not apiKey:
            apiKey = sickbeard.PUSHOVER_APIKEY

        data = urllib.urlencode({
            'token': apiKey,
            'user': userKey
            })

        # get devices from pushover
        try:
            req = urllib2.Request(DEVICE_URL)
            handle = urllib2.urlopen(req, data)
            if handle:
                result = handle.read()
            handle.close()
            return result
        except urllib2.URLError:
            return None
        except socket.timeout:
            return None

    def _sendPushover(self, title, msg, userKey, apiKey, priority, device, sound):
        """
        Sends a pushover notification to the address provided
        
        msg: The message to send (unicode)
        title: The title of the message
        userKey: The pushover user id to send the message to (or to subscribe with)
        
        returns: True if the message succeeded, False otherwise
        """

        # fill in omitted parameters
        if not userKey:
            userKey = sickbeard.PUSHOVER_USERKEY
        if not apiKey:
            apiKey = sickbeard.PUSHOVER_APIKEY

        # build up the URL and parameters
        msg = msg.strip()

        data = urllib.urlencode({
            'token': apiKey,
            'title': title,
            'user': userKey,
            'message': msg.encode('utf-8'),
            'priority': priority,
            'device': device,
            'sound': sound,
            'timestamp': int(time.time())
            })

        # send the request to pushover
        try:
            req = urllib2.Request(API_URL)
            handle = urllib2.urlopen(req, data)
            handle.close()

        except urllib2.URLError, e:
            # HTTP status 404 if the provided email address isn't a Pushover user.
            if e.code == 404:
                logger.log(u'PUSHOVER: Username is wrong/not a Pushover email. Pushover will send an email to it', logger.WARNING)
                return False

            # For HTTP status code 401's, it is because you are passing in either an invalid token, or the user has not added your service.
            elif e.code == 401:

                # HTTP status 401 if the user doesn't have the service added
                subscribeNote = self._sendPushover(title, msg, userKey)
                if subscribeNote:
                    logger.log(u'PUSHOVER: Subscription sent', logger.DEBUG)
                    return True
                else:
                    logger.log(u'PUSHOVER: Subscription could not be sent', logger.ERROR)
                    return False

            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif e.code == 400:
                logger.log(u'PUSHOVER: Wrong data sent to Pushover', logger.ERROR)
                return False

            # If you receive a HTTP status code of 429, it is because the message limit has been reached (free limit is 7,500)
            elif e.code == 429:
                logger.log(u'PUSHOVER: API message limit reached - try a different API key', logger.ERROR)
                return False

            # If you receive a HTTP status code of 500, service is unavailable
            elif e.code == 500:
                logger.log(u'PUSHOVER: Unable to connect to API, service unavailable', logger.ERROR)
                return False

        logger.log(u'PUSHOVER: Notification successful.', logger.MESSAGE)
        return True

    def _notifyPushover(self, title, message, userKey=None, apiKey=None, priority=None, device=None, sound=None, force=False):
        """
        Sends a pushover notification based on the provided info or SG config

        title: The title of the notification to send
        message: The message string to send
        userKey: The userKey to send the notification to 
        force: Enforce sending, for instance for testing
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not sickbeard.USE_PUSHOVER and not force:
            logger.log(u'PUSHOVER: Notifications not enabled, skipping this notification', logger.DEBUG)
            return False

        # fill in omitted parameters
        if not userKey:
            userKey = sickbeard.PUSHOVER_USERKEY
        if not apiKey:
            apiKey = sickbeard.PUSHOVER_APIKEY
        if not priority:
            priority = sickbeard.PUSHOVER_PRIORITY
        if not device:
            device = sickbeard.PUSHOVER_DEVICE
        if not sound:
            sound = sickbeard.PUSHOVER_SOUND

        logger.log(u'PUSHOVER: Sending notice with details: %s - %s, priority: %s, device: %s, sound: %s' % (title, message, priority, device, sound), logger.DEBUG)

        return self._sendPushover(title, message, userKey, apiKey, priority, device, sound)

    def test_notify(self, userKey, apiKey, priority, device, sound):
        return self._notifyPushover('Test', 'This is a test notification from SickGear', userKey, apiKey, priority, device, sound, force=True)

    def notify_snatch(self, ep_name):
        if sickbeard.PUSHOVER_NOTIFY_ONSNATCH:
            self._notifyPushover(notifyStrings[NOTIFY_SNATCH], ep_name)

    def notify_download(self, ep_name):
        if sickbeard.PUSHOVER_NOTIFY_ONDOWNLOAD:
            self._notifyPushover(notifyStrings[NOTIFY_DOWNLOAD], ep_name)

    def notify_subtitle_download(self, ep_name, lang):
        if sickbeard.PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notifyPushover(notifyStrings[NOTIFY_SUBTITLE_DOWNLOAD], ep_name + ': ' + lang)
            
    def notify_git_update(self, new_version = '??'):
        if sickbeard.USE_PUSHOVER:
            update_text=notifyStrings[NOTIFY_GIT_UPDATE_TEXT]
            title=notifyStrings[NOTIFY_GIT_UPDATE]
            self._notifyPushover(title, update_text + new_version) 

notifier = PushoverNotifier
