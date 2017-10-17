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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import os
from urllib import urlencode
from urllib2 import Request, urlopen, HTTPError

import sickbeard
# noinspection PyPep8Naming
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import BaseNotifier


class PyTivoNotifier(BaseNotifier):

    def update_library(self, ep_obj=None, **kwargs):

        host = sickbeard.PYTIVO_HOST
        share_name = sickbeard.PYTIVO_SHARE_NAME
        tsn = sickbeard.PYTIVO_TIVO_NAME

        # There are two more values required, the container and file.
        #
        # container: The share name, show name and season
        #
        # file: The file name
        #
        # Some slicing and dicing of variables is required to get at these values.
        #
        # There might be better ways to arrive at the values, but this is the best I have been able to
        # come up with.
        #

        # Calculated values

        show_path = ep_obj.show.location
        show_name = ep_obj.show.name
        root_show_and_season = ek.ek(os.path.dirname, ep_obj.location)
        abs_path = ep_obj.location

        # Some show names have colons in them which are illegal in a path location, so strip them out.
        # (Are there other characters?)
        show_name = show_name.replace(':', '')

        root = show_path.replace(show_name, '')
        show_and_season = root_show_and_season.replace(root, '')

        container = share_name + '/' + show_and_season
        file_path = '/' + abs_path.replace(root, '')

        # Finally create the url and make request
        request_url = 'http://%s/TiVoConnect?%s' % (host, urlencode(
            dict(Command='Push', Container=container, File=file_path, tsn=tsn)))

        self._log_debug(u'Requesting ' + request_url)

        request = Request(request_url)

        try:
            urlopen(request)

        except HTTPError as e:
            if hasattr(e, 'reason'):
                self._log_error(u'Error, failed to reach a server - ' + e.reason)
                return False
            elif hasattr(e, 'code'):
                self._log_error(u'Error, the server couldn\'t fulfill the request - ' + e.code)
            return False

        except Exception as e:
            self._log_error(u'Unknown exception: ' + ex(e))
            return False

        self._log(u'Successfully requested transfer of file')
        return True


notifier = PyTivoNotifier
