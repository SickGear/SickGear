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

import re
import sickbeard
from sickbeard import logger
from sickbeard.clients.generic import GenericClient


class DownloadStationAPI(GenericClient):

    def __init__(self, host=None, username=None, password=None):

        super(DownloadStationAPI, self).__init__('DownloadStation', host, username, password)

        self.host = self.host.rstrip('/') + '/'
        self.url_base = self.host + 'webapi/'
        self.url_info = self.url_base + 'query.cgi'
        self.url = self.url_base + 'DownloadStation/task.cgi'
        self._errmsg = None

    common_errors = {
        -1: 'Unknown response error', 100: 'Unknown error', 101: 'Invalid parameter',
        102: 'The requested API does not exist', 103: 'The requested method does not exist',
        104: 'The requested version does not support the functionality',
        105: 'The logged in session does not have permission', 106: 'Session timeout',
        107: 'Session interrupted by duplicate login',
    }

    def _error(self, msg):
        self._errmsg = '<br>%s replied with: %s.' % (self.name, msg)
        logger.log('%s replied with: %s' % (self.name, msg), logger.ERROR)

    def _error_task(self, response):
        err_code = response.get('error', {}).get('code', -1)
        return self._error(self.common_errors.get(err_code) or {
            400: 'File upload failed', 401: 'Max number of tasks reached', 402: 'Destination denied',
            403: 'Destination path does not exist', 404: 'Invalid task id', 405: 'Invalid task action',
            406: 'No default destination', 407: 'Set destination failed', 408: 'File does not exist'
        }.get(err_code, 'Unknown error code'))

    def _get_auth(self):

        self._errmsg = None
        response = {}
        try:
            response = self.session.get(self.url_info, verify=False,
                                        params=dict(method='query', api='SYNO.API.Info', version=1,
                                                    query='SYNO.API.Auth,SYNO.DownloadStation.Task')).json()
            if response.get('success') and response.get('data'):
                data = response.get('data')
                for key, member in (('SYNO.API.Auth', 'auth'), ('SYNO.DownloadStation.Task', 'task')):
                    self.__setattr__('_%s_version' % member, data[key]['maxVersion'])
                    self.__setattr__('_%s_path' % member, data[key]['path'])
                self.url = self.url_base + self._task_path
            else:
                raise ValueError
        except (StandardError, BaseException):
            return self._error(self.common_errors.get(response.get('error', {}).get('code', -1)))

        response = {}
        try:
            params = dict(method='login', api='SYNO.API.Auth', version=(1, 2)[1 < self._auth_version],
                          account=self.username, passwd=self.password, session='DownloadStation')
            params.update(({}, dict(format='sid'))[1 < self._auth_version])

            response = self.session.get(self.url_base + self._auth_path, params=params, verify=False).json()
            if response.get('success') and response.get('data'):
                self.auth = response['data']['sid']
            else:
                raise ValueError
        except (StandardError, BaseException):
            err_code = response.get('error', {}).get('code', -1)
            return self._error(self.common_errors.get(err_code) or {
                400: 'No such account or incorrect password', 401: 'Account disabled', 402: 'Permission denied',
                403: '2-step verification code required', 404: 'Failed to authenticate 2-step verification code'
            }.get(err_code, 'Unknown error code'))

        return self.auth

    def _add_torrent_uri(self, result):

        return self._create(uri={'uri': result.url})

    def _add_torrent_file(self, result):

        return self._create(files={'file': ('%s.torrent' % result.name, result.content)})

    def _create(self, uri=None, files=None):

        params = dict(method='create', api='SYNO.DownloadStation.Task', version='1', _sid=self.auth)
        if 1 < self._task_version and sickbeard.TORRENT_PATH:
            params['destination'] = re.sub('^/(volume\d*/)?', '', sickbeard.TORRENT_PATH)
        if uri:
            params.update(uri)

        self._errmsg = None
        response = {}
        try:
            response = self._request(method='post', data=params, files=files).json()
            if not response.get('success'):
                raise ValueError
        except (StandardError, BaseException):
            return self._error_task(response)

        return True

    def _list(self):

        params = dict(method='list', api='SYNO.DownloadStation.Task', version='1', _sid=self.auth,
                      additional='detail,file')

        self._errmsg = None
        response = {}
        try:
            response = self._request(method='get', params=params).json()
            if not response.get('success'):
                raise ValueError
        except (StandardError, BaseException):
            return self._error_task(response)

        # downloading = [x for x in response['data']['tasks'] if x['status'] in ('downloading',)]
        # finished = [x for x in response['data']['tasks'] if x['status'] in ('finished', 'seeding')]

        return True


api = DownloadStationAPI()
