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

import urllib
import urllib2
import socket
import base64

import sickbeard

from sickbeard import logger
from sickbeard.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, NOTIFY_SUBTITLE_DOWNLOAD, NOTIFY_GIT_UPDATE, NOTIFY_GIT_UPDATE_TEXT
from sickbeard.exceptions import ex

PUSHAPI_ENDPOINT = 'https://api.pushbullet.com/v2/pushes'
DEVICEAPI_ENDPOINT = 'https://api.pushbullet.com/v2/devices'


class PushbulletNotifier:

    def get_devices(self, accessToken=None):
        # fill in omitted parameters
        if not accessToken:
            accessToken = sickbeard.PUSHBULLET_ACCESS_TOKEN

        # get devices from pushbullet
        try:
            req = urllib2.Request(DEVICEAPI_ENDPOINT)
            base64string = base64.encodestring('%s:%s' % (accessToken, ''))[:-1]
            req.add_header('Authorization', 'Basic %s' % base64string)
            handle = urllib2.urlopen(req)
            if handle:
                result = handle.read()
            handle.close()
            return result
        except urllib2.URLError:
            return None
        except socket.timeout:
            return None

    def _sendPushbullet(self, title, body, accessToken, device_iden):

        # build up the URL and parameters
        body = body.strip().encode('utf-8')

        data = urllib.urlencode({
            'type': 'note',
            'title': title,
            'body': body,
            'device_iden': device_iden
            })

        # send the request to pushbullet
        try:
            req = urllib2.Request(PUSHAPI_ENDPOINT)
            base64string = base64.encodestring('%s:%s' % (accessToken, ''))[:-1]
            req.add_header('Authorization', 'Basic %s' % base64string)
            handle = urllib2.urlopen(req, data)
            handle.close()
        except socket.timeout:
            return False
        except urllib2.URLError as e:

            if e.code == 404:
                logger.log(u'PUSHBULLET: Access token is wrong/not associated to a device.', logger.ERROR)
            elif e.code == 401:
                logger.log(u'PUSHBULLET: Unauthorized, not a valid access token.', logger.ERROR)
            elif e.code == 400:
                logger.log(u'PUSHBULLET: Bad request, missing required parameter.', logger.ERROR)
            elif e.code == 503:
                logger.log(u'PUSHBULLET: Pushbullet server to busy to handle the request at this time.', logger.WARNING)
            return False

        logger.log(u'PUSHBULLET: Notification successful.', logger.MESSAGE)
        return True

    def _notifyPushbullet(self, title, body, accessToken=None, device_iden=None, force=False):
        """
        Sends a pushbullet notification based on the provided info or SG config

        title: The title of the notification to send
        body: The body string to send
        accessToken: The access token to grant access
        device_iden: The iden of a specific target, if none provided send to all devices
        force: If True then the notification will be sent even if Pushbullet is disabled in the config
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not sickbeard.USE_PUSHBULLET and not force:
            return False

        # fill in omitted parameters
        if not accessToken:
            accessToken = sickbeard.PUSHBULLET_ACCESS_TOKEN
        if not device_iden:
            device_iden = sickbeard.PUSHBULLET_DEVICE_IDEN

        logger.log(u'PUSHBULLET: Sending notice with details: \"%s - %s\", device_iden: %s' % (title, body, device_iden), logger.DEBUG)

        return self._sendPushbullet(title, body, accessToken, device_iden)

    def notify_snatch(self, ep_name):
        if sickbeard.PUSHBULLET_NOTIFY_ONSNATCH:
            self._notifyPushbullet(notifyStrings[NOTIFY_SNATCH], ep_name)

    def notify_download(self, ep_name):
        if sickbeard.PUSHBULLET_NOTIFY_ONDOWNLOAD:
            self._notifyPushbullet(notifyStrings[NOTIFY_DOWNLOAD], ep_name)

    def notify_subtitle_download(self, ep_name, lang):
        if sickbeard.PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notifyPushbullet(notifyStrings[NOTIFY_SUBTITLE_DOWNLOAD], ep_name + ': ' + lang)

    def notify_git_update(self, new_version = '??'):
        if sickbeard.USE_PUSHBULLET:
            update_text=notifyStrings[NOTIFY_GIT_UPDATE_TEXT]
            title=notifyStrings[NOTIFY_GIT_UPDATE]
            self._notifyPushbullet(title, update_text + new_version)

    def test_notify(self, accessToken, device_iden):
        return self._notifyPushbullet('Test', 'This is a test notification from SickGear', accessToken, device_iden, force=True)

notifier = PushbulletNotifier
