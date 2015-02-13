# Author: Rafael Silva <rpluto@gmail.com>
# Author: Marvin Pinto <me@marvinp.ca>
# Author: Dennis Lutter <lad1337@gmail.com>
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

import urllib
import urllib2
import time

import sickbeard

from sickbeard import logger
from sickbeard.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, NOTIFY_SUBTITLE_DOWNLOAD, NOTIFY_GIT_UPDATE, NOTIFY_GIT_UPDATE_TEXT
from sickbeard.exceptions import ex

API_URL = 'https://new.boxcar.io/api/notifications'


class Boxcar2Notifier:
    def _sendBoxcar2(self, title, msg, accesstoken, sound):
        """
        Sends a boxcar2 notification to the address provided
        
        msg: The message to send
        title: The title of the message
        accesstoken: to send to this device	

        returns: True if the message succeeded, False otherwise
        """

        # build up the URL and parameters
        # more info goes here - https://boxcar.uservoice.com/knowledgebase/articles/306788-how-to-send-your-boxcar-account-a-notification
        msg = msg.strip().encode('utf-8')

        data = urllib.urlencode({
                'user_credentials': accesstoken,
                'notification[title]': title + ' - ' + msg,
                'notification[long_message]': msg,
                'notification[sound]': sound,
                'notification[source_name]': 'SickGear',
                'notification[icon_url]': 'https://cdn.rawgit.com/SickGear/SickGear/master/gui/slick/images/ico/apple-touch-icon-60x60.png'
            })

        # send the request to boxcar2
        try:
            req = urllib2.Request(API_URL)
            handle = urllib2.urlopen(req, data)
            handle.close()

        except urllib2.URLError, e:
            # if we get an error back that doesn't have an error code then who knows what's really happening
            if not hasattr(e, 'code'):
                logger.log(u'BOXCAR2: Notification failed.' + ex(e), logger.ERROR)
            else:
                logger.log(u'BOXCAR2: Notification failed. Error code: ' + str(e.code), logger.ERROR)

            if e.code == 404:
                logger.log(u'BOXCAR2: Access token is wrong/not associated to a device.', logger.ERROR)
            elif e.code == 401:
                logger.log(u'BOXCAR2: Access token not recognized.', logger.ERROR)
            elif e.code == 400:
                logger.log(u'BOXCAR2: Wrong data sent to boxcar.', logger.ERROR)
            elif e.code == 503:
                logger.log(u'BOXCAR2: Boxcar server to busy to handle the request at this time.', logger.WARNING)
            return False

        logger.log(u'BOXCAR2: Notification successful.', logger.MESSAGE)
        return True

    def _notifyBoxcar2(self, title, message, accesstoken=None, sound=None, force=False):
        """
        Sends a boxcar2 notification based on the provided info or SG config

        title: The title of the notification to send
        message: The message string to send
        accesstoken: to send to this device
        force: If True then the notification will be sent even if Boxcar is disabled in the config		
        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not sickbeard.USE_BOXCAR2 and not force:
            logger.log(u'BOXCAR2: Notifications are not enabled, skipping this notification', logger.DEBUG)
            return False

        # fill in omitted parameters
        if not accesstoken:
            accesstoken = sickbeard.BOXCAR2_ACCESSTOKEN
        if not sound:
            sound = sickbeard.BOXCAR2_SOUND

        logger.log(u'BOXCAR2: Sending notification for ' + message, logger.DEBUG)

        self._sendBoxcar2(title, message, accesstoken, sound)
        return True

    def test_notify(self, accesstoken, sound, force=True):
        return self._sendBoxcar2('Test', 'This is a test notification from SickGear', accesstoken, sound)

    def notify_snatch(self, ep_name):
        if sickbeard.BOXCAR2_NOTIFY_ONSNATCH:
            self._notifyBoxcar2(notifyStrings[NOTIFY_SNATCH], ep_name)

    def notify_download(self, ep_name):
        if sickbeard.BOXCAR2_NOTIFY_ONDOWNLOAD:
            self._notifyBoxcar2(notifyStrings[NOTIFY_DOWNLOAD], ep_name)

    def notify_subtitle_download(self, ep_name, lang):
        if sickbeard.BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notifyBoxcar2(notifyStrings[NOTIFY_SUBTITLE_DOWNLOAD], ep_name + ': ' + lang)
            
    def notify_git_update(self, new_version = '??'):
        if sickbeard.USE_BOXCAR2:
            update_text=notifyStrings[NOTIFY_GIT_UPDATE_TEXT]
            title=notifyStrings[NOTIFY_GIT_UPDATE]
            self._notifyBoxcar2(title, update_text + new_version)

notifier = Boxcar2Notifier
