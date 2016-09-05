# Authors:
# Pedro Jose Pereira Vieito <pvieito@gmail.com> (Twitter: @pvieito)
#
# URL: https://github.com/mr-orange/Sick-Beard
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
# GNU General Public License for more details
#
# You should have received a copy of the GNU General Public License
# along with SickGear. If not, see <http://www.gnu.org/licenses/>.
#
# Uses the Synology Download Station API:
# http://download.synology.com/download/Document/DeveloperGuide/Synology_Download_Station_Web_API.pdf

import sickbeard
from sickbeard.clients.generic import GenericClient


class DownloadStationAPI(GenericClient):

    def __init__(self, host=None, username=None, password=None):

        super(DownloadStationAPI, self).__init__('DownloadStation', host, username, password)

        self.url = '%swebapi/DownloadStation/task.cgi' % self.host

    def _get_auth(self):

        auth_url = ('%swebapi/auth.cgi?api=SYNO.API.Auth&' % self.host +
                    'version=2&method=login&account=%s&passwd=%s' % (self.username, self.password) +
                    '&session=DownloadStation&format=sid')

        try:
            response = self.session.get(auth_url, verify=False)
            self.auth = response.json()['data']['sid']
        except (StandardError, Exception):
            return None

        return self.auth

    def _add_torrent_uri(self, result):

        return self.send_dsm_request(params={'uri': result.url})

    def _add_torrent_file(self, result):

        return self.send_dsm_request(files={'file': ('%s.torrent' % result.name, result.content)})

    def send_dsm_request(self, params=None, files=None):

        api_params = {
            'method': 'create',
            'version': '1',
            'api': 'SYNO.DownloadStation.Task',
            'session': 'DownloadStation',
            '_sid': self.auth
        }

        if sickbeard.TORRENT_PATH:
            api_params['destination'] = sickbeard.TORRENT_PATH

        data = api_params.copy()
        if params:
            data.update(params)
        response = self._request(method='post', data=data, files=files)

        try:
            result = response.json()['success']
        except (StandardError, Exception):
            result = None

        return result

api = DownloadStationAPI()
