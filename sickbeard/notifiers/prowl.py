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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import socket
from ssl import SSLError
from urllib import urlencode

import sickbeard
from sickbeard.notifiers.generic import Notifier

from lib.six import moves


class ProwlNotifier(Notifier):

    def _notify(self, title, body, prowl_api=None, prowl_priority=None, **kwargs):

        prowl_api = self._choose(prowl_api, sickbeard.PROWL_API)
        prowl_priority = self._choose(prowl_priority, sickbeard.PROWL_PRIORITY)

        self._log_debug('Sending notice with details: title="%s", message="%s", priority=%s, api=%s' % (
            title, body, prowl_priority, prowl_api))

        http_handler = moves.http_client.HTTPSConnection('api.prowlapp.com')

        data = dict(apikey=prowl_api, application='SickGear', event=title,
                    description=body.encode('utf-8'), priority=prowl_priority)

        try:
            http_handler.request('POST', '/publicapi/add',
                                 headers={'Content-type': 'application/x-www-form-urlencoded'}, body=urlencode(data))
        except (SSLError, moves.http_client.HTTPException, socket.error):
            result = 'Connection failed'
            self._log_error(result)
        else:
            response = http_handler.getresponse()
            result = None

            if 200 != response.status:
                if 401 == response.status:
                    result = u'Authentication, %s (bad API key?)' % response.reason
                else:
                    result = 'Http response code "%s"' % response.status

                self._log_error(result)

        return self._choose((True, 'Failed to send notification: %s' % result)[bool(result)], not bool(result))


notifier = ProwlNotifier
