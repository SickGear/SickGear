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

import re
import time

from .generic import GenericClient
from .. import logger
from ..helpers import get_url, try_int
from ..sgdatetime import SGDatetime
import sickbeard

from requests.exceptions import HTTPError

from _23 import filter_iter, filter_list, map_list, unquote_plus
from six import string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Callable, Optional, Union
    from ..classes import TorrentSearchResult


class QbittorrentAPI(GenericClient):

    def __init__(self, host=None, username=None, password=None):

        super(QbittorrentAPI, self).__init__('qBittorrent', host, username, password)

        self.url = self.host
        self.session.headers.update({'Origin': self.host})
        self.api_ns = None

    def _active_state(self, ids=None):
        # type: (Optional[AnyStr, list]) -> list
        """
        Fetch state of items, return items that are actually downloading or seeding
        :param ids: Optional id(s) to get state info for. None to get all
        :return: Zero or more object(s) assigned with state `down`loading or `seed`ing
        """
        downloaded = (lambda item: float(item.get('progress') or 0) * (item.get('size') or 0))  # bytes
        wanted = (lambda item: item.get('priority'))  # wanted will == tally/downloaded if all files are selected
        base_state = (lambda t, gp, f: dict(
            id=t['hash'], title=t['name'], total_size=gp.get('total_size') or 0,
            added_ts=gp.get('addition_date'), last_completed_ts=gp.get('completion_date'),
            last_started_ts=None, seed_elapsed_secs=gp.get('seeding_time'),
            wanted_size=sum(map_list(lambda tf: wanted(tf) and tf.get('size') or 0, f)) or None,
            wanted_down=sum(map_list(lambda tf: wanted(tf) and downloaded(tf) or 0, f)) or None,
            tally_down=sum(map_list(lambda tf: downloaded(tf) or 0, f)) or None,
            tally_up=gp.get('total_uploaded'),
            state='done' if 'pausedUP' == t.get('state') else ('down', 'seed')['up' in t.get('state').lower()]
        ))
        file_list = (lambda ti: self._client_request(
            ('torrents/files', 'query/propertiesFiles/%s' % ti['hash'])[not self.api_ns],
            params=({'hash': ti['hash']}, {})[not self.api_ns], json=True) or {})
        valid_stat = (lambda ti: not self._ignore_state(ti)
                      and sum(map_list(lambda tf: wanted(tf) and downloaded(tf) or 0, file_list(ti))))
        result = map_list(lambda t: base_state(t, self._tinf(t['hash'])[0], file_list(t)),
                          filter_list(lambda t: re.search('(?i)queue|stall|(up|down)load|pausedUP', t['state']) and
                                      valid_stat(t), self._tinf(ids, False)))

        return result

    def _tinf(self, ids=None, use_props=True, err=False):
        # type: (Optional[list], bool, bool) -> list
        """
        Fetch client task information
        :param ids: Optional id(s) to get task info for. None to get all task info
        :param use_props: Optional override forces retrieval of torrents info instead of torrent generic properties
        :param err: Optional return error dict instead of empty array
        :return: Zero or more task object(s) from response
        """
        result = []
        rids = (ids if isinstance(ids, (list, type(None))) else [x.strip() for x in ids.split(',')]) or [None]
        getinfo = use_props and None is not ids
        params = {}
        cmd = ('torrents/info', 'query/torrents')[not self.api_ns]
        if not getinfo:
            label = sickbeard.TORRENT_LABEL.replace(' ', '_')
            if label and not ids:
                params['category'] = label
        for rid in rids:
            if getinfo:
                if self.api_ns:
                    cmd = 'torrents/properties'
                    params['hash'] = rid
                else:
                    cmd = 'query/propertiesGeneral/%s' % rid
            elif rid:
                params['hashes'] = rid
            try:
                tasks = self._client_request(cmd, params=params, timeout=60, json=True)
                result += tasks and (isinstance(tasks, list) and tasks or (isinstance(tasks, dict) and [tasks])) \
                    or ([], [{'state': 'error', 'hash': rid}])[err]
            except (BaseException, Exception):
                if getinfo:
                    result += [dict(error=True, id=rid)]
        for t in filter_iter(lambda d: isinstance(d.get('name'), string_types) and d.get('name'),
                             (result, [])[getinfo]):
            t['name'] = unquote_plus(t.get('name'))

        return result

    def _set_torrent_pause(self, search_result):
        # type: (TorrentSearchResult) -> bool
        """
        Set torrent as paused used for the "add as paused" feature (overridden class function)
        :param search_result: A populated search result object
        :return: Success or Falsy if fail
        """
        if not sickbeard.TORRENT_PAUSED:
            return super(QbittorrentAPI, self)._set_torrent_pause(search_result)

        return True is self._pause_torrent(search_result.hash)

    def _set_torrent_label(self, search_result):
        if not sickbeard.TORRENT_LABEL.replace(' ', '_'):
            return super(QbittorrentAPI, self)._set_torrent_label(search_result)

        return True is self._label_torrent(search_result.hash)

    def _set_torrent_priority(self, search_result):
        if 1 != search_result.priority:
            return super(QbittorrentAPI, self)._set_torrent_priority(search_result)

        return True is self._maxpri_torrent(search_result.hash)

    @staticmethod
    def _ignore_state(task):
        return bool(re.search(r'(?i)error', task.get('state') or ''))

    def _maxpri_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Set maximal priority in queue to torrent task
        :param ids: ID(s) to promote
        :return: True/Falsy if success/failure else Id(s) that failed to be changed
        """
        def _maxpri_filter(t):
            mark_fail = True
            if not self._ignore_state(t):
                if 1 >= t.get('priority'):
                    return not mark_fail

                params = {'hashes': t.get('hash')}
                post_data = None
                if not self.api_ns:
                    post_data = params
                    params = None

                response = self._client_request(
                        '%s/topPrio' % ('torrents', 'command')[not self.api_ns],
                        params=params, post_data=post_data, raise_status_code=True)
                if True is response:
                    task = self._tinf(t.get('hash'), use_props=False, err=True)[0]
                    return 1 < task.get('priority') or self._ignore_state(task)  # then mark fail
                elif isinstance(response, string_types) and 'queueing' in response.lower():
                    logger.log('%s: %s' % (self.name, response), logger.ERROR)
                    return not mark_fail
            return mark_fail

        return self._action('topPrio', ids, lambda t: _maxpri_filter(t))

    def _label_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Set label/category to torrent task
        :param ids: ID(s) to change
        :return: True/Falsy if success/failure else Id(s) that failed to be changed
        """
        def _label_filter(t):
            mark_fail = True
            if not self._ignore_state(t):
                label = sickbeard.TORRENT_LABEL.replace(' ', '_')
                if label in t.get('category'):
                    return not mark_fail

                response = self._client_request(
                        '%s/setCategory' % ('torrents', 'command')[not self.api_ns],
                        post_data={'hashes': t.get('hash'), 'category': label, 'label': label}, raise_status_code=True)
                if True is response:
                    task = self._tinf(t.get('hash'), use_props=False, err=True)[0]
                    return label not in task.get('category') or self._ignore_state(task)  # then mark fail
                elif isinstance(response, string_types) and 'incorrect' in response.lower():
                    logger.log('%s: %s. "%s" isn\'t known to qB' % (self.name, response, label), logger.ERROR)
                    return not mark_fail
            return mark_fail

        return self._action('label', ids, lambda t: _label_filter(t))

    def _pause_torrent(self, ids):
        # type: (Union[AnyStr, list]) -> Union[bool, list]
        """
        Pause item(s)
        :param ids: Id(s) to pause
        :return: True/Falsy if success/failure else Id(s) that failed to be paused
        """
        def _pause_filter(t):
            mark_fail = True
            if not self._ignore_state(t):
                if 'paused' in t.get('state'):
                    return not mark_fail
                if True is self._client_request(
                        '%s/pause' % ('torrents', 'command')[not self.api_ns],
                        post_data={'hash' + ('es', '')[not self.api_ns]: t.get('hash')}):
                    task = self._tinf(t.get('hash'), use_props=False, err=True)[0]
                    return 'paused' not in task.get('state') or self._ignore_state(task)  # then mark fail
            return mark_fail

        # check task state stability, and call pause where not paused
        sample_size = 10
        iv = 0.5
        states = []
        for i in range(0, sample_size):
            states += [self._tinf(ids, False)[0]['state']]
            if 'paused' not in states[-1]:
                self._action('pause', ids, lambda t: _pause_filter(t))
                break
            time.sleep(iv)

        # as precaution, if was unstable, do another pass
        sample_size = 10
        iterations = int((5 + sample_size) * iv * (1 / iv))  # timeout, ought never happen
        while 1 != len(set(states)) and iterations:
            for i in range(0, sample_size):
                states += [self._tinf(ids, False)[0]['state']]
                if 'paused' not in states[-1] and True is not self._action('pause', ids, lambda t: _pause_filter(t)):
                    time.sleep(iv)
                    iterations -= 1
                    if iterations:
                        continue
                iterations = None
                break
            states = states[-sample_size:]

        return 'paused' in states[-1]

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
            ('paused' in t.get('state')) and
            True is not self._client_request(
                '%s/resume' % ('torrents', 'command')[not self.api_ns],
                post_data={'hash' + ('es', '')[not self.api_ns]: t.get('hash')}))

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
            True is not self._client_request(
                ('torrents/delete', 'command/deletePerm')[not self.api_ns],
                post_data=dict([('hashes', t.get('hash'))] + ([('deleteFiles', True)], [])[not self.api_ns])),
            pause_first=True)

    def _perform_task(self, method, ids, filter_func, pause_first=False):
        # type: (AnyStr, Union[AnyStr, list], Callable, bool) -> Union[bool, list]
        """
        Set up and send a method to client
        :param method: Either `resume` or `delete`
        :param ids: Id(s) to perform method on
        :param filter_func: Call back function passed to _action that will filter tasks as failed or erroneous
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
            for task in filter_iter(filter_func, self._tinf(ids, use_props=False, err=True)):
                item[('fail', 'ignore')[self._ignore_state(task)]] += [task.get('hash')]

            # retry items that are not acted on
            retry_ids = item['fail']
            tries = (1, 3, 5, 10, 15, 15, 30, 60)
            i = 0
            while retry_ids:
                for i in tries:
                    logger.log('%s: retry %s %s item(s) in %ss' % (self.name, act, len(item['fail']), i), logger.DEBUG)
                    time.sleep(i)
                    item['fail'] = []
                    for task in filter_iter(filter_func, self._tinf(retry_ids, use_props=False, err=True)):
                        item[('fail', 'ignore')[self._ignore_state(task)]] += [task.get('hash')]

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
        # type: (TorrentSearchResult) -> Optional[bool]
        """
        Add magnet to client (overridden class function)
        :param search_result: A populated search result object
        :return: True if created, else Falsy if nothing created
        """
        return search_result and self._add_torrent('download', search_result) or False

    def _add_torrent_file(self, search_result):
        # type: (TorrentSearchResult) -> Optional[bool]
        """
        Add file to client (overridden class function)
        :param search_result: A populated search result object
        :return: True if created, else Falsy if nothing created
        """
        return search_result and self._add_torrent('upload', search_result) or False

    def _add_torrent(self, cmd, data):
        # type: (AnyStr, TorrentSearchResult) -> Optional[bool]
        """
        Create client task
        :param cmd: Command for client API v6, converted up for newer API
        :param data: A populated search result object
        :return: True if created, else Falsy if nothing created
        """
        if self._tinf(data.hash):
            logger.log('Could not create task, the hash is already in use', logger.ERROR)
            return

        label = sickbeard.TORRENT_LABEL.replace(' ', '_')
        params = dict(
            ([('category', label), ('label', label)], [])[not label]
            + ([('paused', ('false', 'true')[bool(sickbeard.TORRENT_PAUSED)])], [])[not sickbeard.TORRENT_PAUSED]
            + ([('savepath', sickbeard.TORRENT_PATH)], [])[not sickbeard.TORRENT_PATH]
        )

        if 'download' == cmd:
            params.update(dict(urls=data.url))
            kwargs = dict(post_data=params)
        else:
            kwargs = dict(post_data=params, files={'torrents': ('%s.torrent' % data.name, data.content)})

        task_stamp = int(SGDatetime.now().totimestamp(default=0))
        response = self._client_request(('torrents/add', 'command/%s' % cmd)[not self.api_ns], **kwargs)

        if True is response:
            for s in (1, 3, 5, 10, 15, 30, 60):
                if filter_list(lambda t: task_stamp <= t['addition_date'], self._tinf(data.hash)):
                    return data.hash
                time.sleep(s)
            return True

    def api_found(self):

        try:
            v = self._client_request('app/webapiVersion').split('.')
            return (2, 0) < tuple([try_int(x) for x in '.'.join(v + ['0'] * (4 - len(v))).split('.')])
        except AttributeError:
            return 6 < try_int(self._client_request('version/api'))

    def _client_request(self, cmd='', **kwargs):
        # type: (AnyStr, Any) -> Optional[AnyStr, bool, dict, list]
        """
        Send a request to client
        :param cmd: Api task to invoke
        :param kwargs: keyword arguments to pass thru to helpers getURL function
        :return: JSON decoded response dict, True if success and no response body, Text error or None if failure,
        """
        authless = bool(re.search('(?i)login|version', cmd))
        if authless or self.auth:
            if not authless and not self._get_auth():
                logger.log('%s: Authentication failed' % self.name, logger.ERROR)
                return

            # self._log_request_details('%s%s' % (self.api_ns, cmd.strip('/')), **kwargs)
            response = None
            try:
                response = get_url('%s%s%s' % (self.host, self.api_ns, cmd.strip('/')),
                                   session=self.session, **kwargs)
            except HTTPError as e:
                if e.response.status_code in (409, 403):
                    response = e.response.text
            except (BaseException, Exception):
                pass
            if isinstance(response, string_types):
                if response[0:3].lower() in ('', 'ok.'):
                    return True
                elif response[0:4].lower() == 'fail':
                    return False
            return response

    def _get_auth(self):
        """
        Authenticate with client (overridden class function)
        :return: True on success, or False on failure
        :rtype: Boolean
        """
        post_data = dict(username=self.username, password=self.password)
        self.api_ns = 'api/v2/'
        response = self._client_request('auth/login', post_data=post_data, raise_status_code=True)
        if isinstance(response, string_types) and 'banned' in response.lower():
            logger.log('%s: %s' % (self.name, response), logger.ERROR)
            response = False
        elif not response:
            self.api_ns = ''
            response = self._client_request('login', post_data=post_data)
        self.auth = response and self.api_found()
        return self.auth


api = QbittorrentAPI()
