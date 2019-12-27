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
import time

from .generic import GenericClient
from .. import logger
from ..sgdatetime import SGDatetime
import sickbeard

from _23 import filter_iter, filter_list, map_list, unquote_plus
from six import string_types

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Callable, Optional, Union
    from ..classes import TorrentSearchResult


class DownloadStationAPI(GenericClient):

    def __init__(self, host=None, username=None, password=None):

        super(DownloadStationAPI, self).__init__('DownloadStation', host, username, password)

        self.url_base = self.host + 'webapi/'
        self.url_info = self.url_base + 'query.cgi'
        self.url = self.url_base + 'DownloadStation/task.cgi'
        self._errmsg = None
        self._testmode = False
        self._auth_version = None
        self._auth_path = None
        self._task_version = None
        self._task_path = None

    common_errors = {
        -1: 'Could not get a response', 100: 'Unknown error', 101: 'Invalid parameter',
        102: 'The requested API does not exist', 103: 'The requested method does not exist',
        104: 'The requested version does not support the functionality',
        105: 'The logged in session does not have permission', 106: 'Session timeout',
        107: 'Session interrupted by duplicate login',
    }

    def _error(self, msg):
        # type: (AnyStr) -> None
        out = '%s%s: %s' % (self.name, (' replied with', '')['Could not' in msg], msg)
        self._errmsg = '<br>%s.' % out
        logger.log(out, logger.ERROR)

    def _error_task(self, response):

        err_code = response.get('error', {}).get('code', -1)
        return self._error(self.common_errors.get(err_code) or {
            400: 'File upload failed', 401: 'Max number of tasks reached', 402: 'Destination denied',
            403: 'Destination path does not exist', 404: 'Invalid task id', 405: 'Invalid task action',
            406: 'No default destination', 407: 'Set destination failed', 408: 'File does not exist'
        }.get(err_code, 'Unknown error code'))

    def _active_state(self, ids=None):
        # type: (Optional[list]) -> list
        """
        Fetch state of items, return items that are actually downloading or seeding
        :param ids: Optional id(s) to get state info for. None to get all
        :return: Zero or more object(s) assigned with state `down`loading or `seed`ing
        """
        tasks = self._tinf(ids)
        downloaded = (lambda item, d=0: item.get('size_downloaded') or d)  # bytes
        wanted = (lambda item: item.get('wanted'))  # wanted will == tally/downloaded if all files are selected
        base_state = (lambda t, d, tx, f: dict(
            id=t['id'], title=t['title'], total_size=t.get('size') or 0,
            added_ts=d.get('create_time'), last_completed_ts=d.get('completed_time'),
            last_started_ts=d.get('started_time'), seed_elapsed_secs=d.get('seedelapsed'),
            wanted_size=sum(map_list(lambda tf: wanted(tf) and tf.get('size') or 0, f)) or None,
            wanted_down=sum(map_list(lambda tf: wanted(tf) and downloaded(tf) or 0, f)) or None,
            tally_down=downloaded(tx),
            tally_up=tx.get('size_uploaded'),
            state='done' if re.search('finish', t['status']) else ('seed', 'down')[any(filter_list(
                lambda tf: wanted(tf) and (downloaded(tf, -1) < tf.get('size', 0)), f))]
        ))
        # only available during "download" and "seeding"
        file_list = (lambda t: t.get('additional', {}).get('file', {}))
        valid_stat = (lambda ti: not ti.get('error') and isinstance(ti.get('status'), string_types)
                      and sum(map_list(lambda tf: wanted(tf) and downloaded(tf) or 0, file_list(ti))))
        result = map_list(lambda t: base_state(
            t, t.get('additional', {}).get('detail', {}), t.get('additional', {}).get('transfer', {}), file_list(t)),
                     filter_list(lambda t: t['status'] in ('downloading', 'seeding', 'finished') and valid_stat(t),
                                 tasks))

        return result

    def _tinf(self, ids=None, err=False):
        # type: (Optional[list], bool) -> list
        """
        Fetch client task information
        :param ids: Optional id(s) to get task info for. None to get all task info
        :param err: Optional return error dict instead of empty array
        :return: Zero or more task object(s) from response
        """
        result = []
        rids = (ids if isinstance(ids, (list, type(None))) else [x.strip() for x in ids.split(',')]) or [None]
        getinfo = None is not ids
        for rid in rids:
            try:
                if not self._testmode:
                    # noinspection PyTypeChecker
                    tasks = self._client_request(('list', 'getinfo')[getinfo], t_id=rid,
                                                 t_params=dict(additional='detail,file,transfer'))['data']['tasks']
                else:
                    # noinspection PyUnresolvedReferences
                    tasks = (filter_list(lambda d: d.get('id') == rid, self._testdata), self._testdata)[not rid]
                result += tasks and (isinstance(tasks, list) and tasks or (isinstance(tasks, dict) and [tasks])) \
                    or ([], [{'error': True, 'id': rid}])[err]
            except (BaseException, Exception):
                if getinfo:
                    result += [dict(error=True, id=rid)]
        for t in filter_iter(lambda d: isinstance(d.get('title'), string_types) and d.get('title'), result):
            t['title'] = unquote_plus(t.get('title'))

        return result

    def _set_torrent_pause(self, search_result):
        # type: (TorrentSearchResult) -> bool
        """
        Set torrent as paused used for the "add as paused" feature (overridden class function)
        :param search_result: A populated search result object
        :return: Success or Falsy if fail
        """
        if not sickbeard.TORRENT_PAUSED or not self.created_id:
            return super(DownloadStationAPI, self)._set_torrent_pause(search_result)

        return True is self._pause_torrent(self.created_id)

    @staticmethod
    def _ignore_state(task):
        return bool(task.get('error'))

    def _pause_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Pause item(s)
        :param ids: Id(s) to pause
        :return: True/Falsy if success/failure else Id(s) that failed to be paused
        """
        return self._action(
            'pause', ids,
            lambda t: self._ignore_state(t) or
            (not isinstance(t.get('status'), string_types) or 'paused' not in t.get('status')) and
            True is not self._client_request('pause', t.get('id')))

    def _resume_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Resume task(s) in client
        :param ids: Id(s) to act on
        :return: True if success, Id(s) that could not be resumed, else Falsy if failure
        """
        return self._perform_task(
            'resume', ids,
            lambda t: self._ignore_state(t) or
            (not isinstance(t.get('status'), string_types) or 'paused' in t.get('status')) and
            True is not self._client_request('resume', t.get('id')))

    def _delete_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Delete task(s) from client
        :param ids: Id(s) to act on
        :return: True if success, Id(s) that could not be deleted, else Falsy if failure
        """
        return self._perform_task(
            'delete', ids,
            lambda t: self._ignore_state(t) or
            isinstance(t.get('status'), string_types) and
            True is not self._client_request('delete', t.get('id')),
            pause_first=True)

    def _perform_task(self, method, ids, filter_func, pause_first=False):
        # type: (AnyStr, Union[AnyStr, list], Callable, bool) -> Union[bool, list]
        """
        Set up and send a method to client
        :param method: Either `resume` or `delete`
        :param ids: Id(s) to perform method on
        :param filter_func: Call back function to filter tasks as failed or erroneous
        :param pause_first: True if task should be paused prior to invoking method
        :return: True if success, Id(s) that could not be acted upon, else Falsy if failure
        """
        if isinstance(ids, (string_types, list)):
            rids = ids if isinstance(ids, list) else map_list(lambda x: x.strip(), ids.split(','))

            result = pause_first and self._pause_torrent(rids)  # get items not paused
            result = (isinstance(result, list) and result or [])
            for t_id in list(set(rids) - (isinstance(result, list) and set(result) or set())):  # perform on paused ids
                if True is not self._action(method, t_id, filter_func):
                    result += [t_id]  # failed item

            return result or True

    def _action(self, act, ids, filter_func):

        if isinstance(ids, (string_types, list)):
            item = dict(fail=[], ignore=[])
            for task in filter_iter(filter_func, self._tinf(ids, err=True)):
                item[('fail', 'ignore')[self._ignore_state(task)]] += [task.get('id')]

            # retry items not acted on
            retry_ids = item['fail']
            tries = (1, 3, 5, 10, 15, 15, 30, 60)
            i = 0
            while retry_ids:
                for i in tries:
                    logger.log('%s: retry %s %s item(s) in %ss' % (self.name, act, len(item['fail']), i), logger.DEBUG)
                    time.sleep(i)
                    item['fail'] = []
                    for task in filter_iter(filter_func, self._tinf(retry_ids, err=True)):
                        item[('fail', 'ignore')[self._ignore_state(task)]] += [task.get('id')]

                    if not item['fail']:
                        retry_ids = None
                        break
                    retry_ids = item['fail']
                else:
                    if max(tries) == i:
                        logger.log('%s: failed to %s %s item(s) after %s tries over %s mins, aborted' %
                                   (self.name, act, len(item['fail']), len(tries), sum(tries) / 60), logger.DEBUG)

            return (item['fail'] + item['ignore']) or True

    def _add_torrent_uri(self, search_result):
        # type: (TorrentSearchResult) -> Union[AnyStr, bool]
        """
        Add magnet to client (overridden class function)
        :param search_result: A populated search result object
        :return: Id of task in client, True if added but no ID, else Falsy if nothing added
        """
        if 3 <= self._task_version:
            return self._add_torrent(uri={'uri': search_result.url})

        logger.log('%s: the API at %s doesn\'t support torrent magnet, download skipped' %
                   (self.name, self.host), logger.WARNING)

    def _add_torrent_file(self, search_result):
        # type: (TorrentSearchResult) -> Union[AnyStr, bool]
        """
        Add file to client (overridden class function)
        :param search_result: A populated search result object
        :return: Id of task in client, True if added but no ID, else Falsy if nothing added
        """
        return self._add_torrent(
            files={'file': ('%s.torrent' % re.sub(r'(\.torrent)+$', '', search_result.name), search_result.content)})

    def _add_torrent(self, uri=None, files=None):
        # type: (Optional[dict], Optional[dict]) -> Optional[AnyStr, bool]
        """
        Create client task
        :param uri: URI param for client API
        :param files: file param for client API
        :return: Id of task in client, True if created but no id found, else Falsy if nothing created
        """
        if self._testmode:
            # noinspection PyUnresolvedReferences
            return self._testid

        tasks = self._tinf()
        if self._client_has(tasks, uri=uri):
            return self._error('Could not create task, the magnet URI is in use')
        if self._client_has(tasks, files=files):
            return self._error('Could not create task, torrent file already added')

        params = dict()
        if uri:
            params.update(uri)
        if 1 < self._task_version and sickbeard.TORRENT_PATH:
            params['destination'] = re.sub(r'^/(volume\d*/)?', '', sickbeard.TORRENT_PATH)

        task_stamp = int(SGDatetime.now().totimestamp(default=0))
        response = self._client_request('create', t_params=params, files=files)
        # noinspection PyUnresolvedReferences
        if response and response.get('success'):
            for s in (1, 3, 5, 10, 15, 30, 60):
                tasks = filter_list(lambda t: task_stamp <= t['additional']['detail']['create_time'], self._tinf())
                try:
                    return str(self._client_has(tasks, uri, files)[0].get('id'))
                except IndexError:
                    time.sleep(s)
            return True

    @staticmethod
    def _client_has(tasks, uri=None, files=None):
        # type: (list, Optional[dict], Optional[dict]) -> list
        """
        Check if uri or file exists in task list
        :param tasks: Tasks list
        :param uri: URI to check against
        :param files: File to check against
        :return: Zero or more found record(s).
        """
        result = []
        if uri or files:
            u = isinstance(uri, dict) and (uri.get('uri', '') or '').lower() or None
            f = isinstance(files, dict) and (files.get('file', [''])[0]).lower() or None
            result = filter_list(lambda t: u and t['additional']['detail']['uri'].lower() == u
                                           or f and t['additional']['detail']['uri'].lower() in f, tasks)
        return result

    def _client_request(self, method, t_id=None, t_params=None, files=None):
        # type: (AnyStr, Optional[AnyStr], Optional[dict], Optional[dict]) -> Union[bool, list, object]
        """
        Send a request to client
        :param method: Api task to invoke
        :param t_id: Optional id to perform task on
        :param t_params: Optional additional task request parameters
        :param files: Optional file to send
        :return: True if t_id success, DS API response object if t_params success, list of error items,
         else Falsy if failure
        """
        if self._testmode:
            return True

        params = dict(method=method, api='SYNO.DownloadStation.Task', version='1', _sid=self.auth)
        if t_id:
            params['id'] = t_id
        if t_params:
            params.update(t_params)

        self._errmsg = None
        response = {}
        kw_args = (dict(method='get', params=params), dict(method='post', data=params))[method in ('create',)]
        kw_args.update(dict(files=files))
        try:
            response = self._request(**kw_args).json()
            if not response.get('success'):
                raise ValueError
        except (BaseException, Exception):
            return self._error_task(response)

        if None is not t_id and None is t_params and 'create' != method:
            return filter_list(lambda r: r.get('error'), response.get('data', {})) or True

        return response

    def _get_auth(self):
        # type: (...) -> Union[AnyStr, bool]
        """
        Authenticate with client (overridden class function)
        :return: client auth_id or False on failure
        """
        if self._testmode:
            return True

        self.auth = None
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
        except (BaseException, Exception):
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
        except (BaseException, Exception):
            err_code = response.get('error', {}).get('code', -1)
            return self._error(self.common_errors.get(err_code) or {
                400: 'No such account or incorrect password', 401: 'Account disabled', 402: 'Permission denied',
                403: '2-step verification code required', 404: 'Failed to authenticate 2-step verification code'
            }.get(err_code, 'No known API.Auth response'))

        return self.auth


api = DownloadStationAPI()
