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

import sickbeard
from sickbeard import logger
from sickbeard.exceptions import ex

try:
    import json
except ImportError:
    import simplejson as json

class EmbyNotifier:

    def _notify_emby(self, message, host=None, emby_apikey=None):
        """Handles notifying Emby Server host via HTTP API

        Returns: True if the request succeeded, False otherwise

        """

        # fill in omitted parameters
        if not host:
            host = sickbeard.EMBY_HOST
        if not emby_apikey:
            emby_apikey = sickbeard.EMBY_APIKEY

        url = 'http://%s/emby/Notifications/Admin' % (host)
        values = {'Name': 'SickGear', 'Description': message, 'ImageUrl': 'https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/ico/apple-touch-icon-precomposed.png'}
        data = json.dumps(values)

        try:
            req = urllib2.Request(url, data)
            req.add_header('X-MediaBrowser-Token', emby_apikey)
            req.add_header('Content-Type', 'application/json')

            response = urllib2.urlopen(req)
            response.close()

        except (urllib2.URLError, IOError) as e:
            logger.log(u'EMBY: Warning: Couldn\'t contact Emby Server at ' + url + ' ' + ex(e), logger.WARNING)
            return False

        logger.log(u'EMBY: Notification successful.', logger.MESSAGE)
        return True

    def test_notify(self, host, emby_apikey):
        return self._notify_emby('This is a test notification from SickGear', host, emby_apikey)

    def update_library(self):
        """Handles updating the Emby Server host via HTTP API

        Returns: True if the request succeeded, False otherwise

        """

        if sickbeard.USE_EMBY:

            if not sickbeard.EMBY_HOST:
                logger.log(u'EMBY: No host specified, check your settings', logger.DEBUG)
                return False

            url = 'http://%s/emby/Library/Series/Updated' % (sickbeard.EMBY_HOST)
            values = {}
            data = urllib.urlencode(values)

            try:
                req = urllib2.Request(url, data)
                req.add_header('X-MediaBrowser-Token', sickbeard.EMBY_APIKEY)

                response = urllib2.urlopen(req)
                response.close()

            except (urllib2.URLError, IOError) as e:
                logger.log(u'EMBY: Warning: Couldn\'t contact Emby Server at ' + url + ' ' + ex(e), logger.WARNING)
                return False

            logger.log(u'EMBY: Updating library on host: %s' % sickbeard.EMBY_HOST, logger.MESSAGE)
            return True

notifier = EmbyNotifier
