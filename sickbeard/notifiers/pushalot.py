# Author: Maciej Olesinski (https://github.com/molesinski/)
# Based on prowl.py by Nic Wolfe <nic@wolfeden.ca>
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


class PushalotNotifier(Notifier):

    def _notify(self, title, body, pushalot_auth_token=None, **kwargs):

        pushalot_auth_token = self._choose(pushalot_auth_token, sickbeard.PUSHALOT_AUTHORIZATIONTOKEN)

        self._log_debug(u'Title: %s, Message: %s, API: %s' % (title, body, pushalot_auth_token))

        http_handler = moves.http_client.HTTPSConnection('pushalot.com')

        try:
            http_handler.request('POST', '/api/sendmessage',
                                 body=urlencode(dict(Title=title.encode('utf-8'), Body=body.encode('utf-8'),
                                                     AuthorizationToken=pushalot_auth_token)),
                                 headers={'Content-type': 'application/x-www-form-urlencoded'})
        except (SSLError, moves.http_client.HTTPException, socket.error):
            result = 'Connection failed'
            self._log_error(result)
        else:
            response = http_handler.getresponse()
            result = None

            if 200 != response.status:
                if 410 == response.status:
                    result = u'Authentication, %s (bad API key?)' % response.reason
                else:
                    result = 'Http response code "%s"' % response.status

                self._log_error(result)

        return self._choose((True, 'Failed to send notification: %s' % result)[bool(result)], not bool(result))


notifier = PushalotNotifier
