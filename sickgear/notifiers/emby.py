# coding=utf-8
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

from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, SO_BROADCAST, SHUT_RDWR

from .generic import Notifier
from json_helper import json_loads
import sickgear

from _23 import decode_bytes, decode_str

# noinspection PyUnreachableCode
if False:
    from sickgear.tv import TVShow


class EmbyNotifier(Notifier):
    EMBY_API = 1
    JELLYFIN_API = 2
    # noinspection HttpUrlsUsage
    SCHEMA = 'http://'

    def __init__(self):
        super(EmbyNotifier, self).__init__()

        self.response = None

    def _request(self, endpoint, host, token, **kwargs):
        self.response = dict()
        return sickgear.helpers.get_url(
            f'{EmbyNotifier.SCHEMA}{host}/emby/{endpoint}',
            headers={'Content-type': 'application/json', 'X-MediaBrowser-Token': token},
            timeout=20, hooks=dict(response=self._cb_response), **kwargs)

    # noinspection PyUnusedLocal
    def _cb_response(self, r, *args, **kwargs):
        self.response = dict(status_code=r.status_code, ok=r.ok)
        return r

    def fetch_info_public(self, host, token):
        return self._request('System/Info/Public', host, token, json=True)

    def check_server_type(self, host, token):
        """

        :param host: Emby/jellyfin host
        :type host: str
        :param token: Accesstoken
        :type token: str
        :return: EmbyNotifier.JELLYFIN_API or EmbyNotifier.EMBY_API
        :rtype: int
        """
        response = self.fetch_info_public(host, token)
        if (self.response.get('ok') and 200 == self.response.get('status_code') and
                isinstance(response, dict) and
                isinstance(response.get('ProductName'), str) and 'jellyfin' in response.get('ProductName').lower()):
            return EmbyNotifier.JELLYFIN_API
        return EmbyNotifier.EMBY_API

    def is_min_server_version(self, version, host, token):
        """ Test if Emby `host` server version is greater than or equal `version` arg

        :param version: Major, Minor, Build, Revision
        :type version: List
        :param host: Emby host
        :type host: Basestring
        :param token: Accesstoken
        :type token: Basestring
        :return: True if Emby `host` server version is greater than or equal `version` arg, otherwise False
        :rtype: bool
        """
        response = self.fetch_info_public(host, token)
        return self.response.get('ok') and 200 == self.response.get('status_code') and \
            version <= list(map(lambda x: int(x), (response and response.get('Version') or '0.0.0.0').split('.')))

    def update_library(self, show_obj=None, **kwargs):
        """ Update library function

        :param show_obj: TVShow object
        :type show_obj: TVShow

        Returns: None if no processing done, True if processing succeeded with no issues else False if any issues found
        """
        hosts, keys, message = self._check_config()
        if not hosts:
            self._log_warning('Issue with hosts or api keys, check your settings')
            return False

        from sickgear.indexers import indexer_config
        tvdb_id = None
        try:
            tvdb_id = show_obj.ids.get(indexer_config.TVINFO_TVDB, {}).get('id', None)
        except (BaseException, Exception):
            pass
        args = (dict(post_json={'TvdbId': f'{tvdb_id}'}), dict(data=None))[not any([tvdb_id])]

        mode_to_log = show_obj and f'show "{show_obj.unique_name}"' or 'all shows'
        total_success = True
        for i, cur_host in enumerate(hosts):
            endpoint = 'Series'
            if None is not show_obj and self.is_min_server_version([4, 3, 0, 31], cur_host, keys[i]):
                endpoint = 'Media'
                if 'data' in args:
                    del(args['data'])
                media_file = show_obj.location
                # media_file = r'V:\Video\tv\The Chi\'
                mode_to_log = f'media "{media_file}"'
                args.update(dict(post_json={'Updates': [{'Path': media_file, 'UpdateType': ''}]}))
            if self.is_min_server_version([4, 3, 0, 0], cur_host, keys[i]):
                if 'data' in args:
                    # del(args['data'])
                    args.update(dict(post_data=True))

            response = self._request(f'Library/{endpoint}/Updated', cur_host, keys[i], **args)
            # Emby will initiate a LibraryMonitor path refresh one minute after this success
            if 200 <= (self.response.get('status_code') or 0) < 300 and self.response.get('ok'):
                self._log(f'Success: update {mode_to_log} sent to host {cur_host} in a library updated call')
                continue
            elif 401 == self.response.get('status_code', 0):
                self._log_warning(f'Failed to authenticate with {cur_host}')
            elif 404 == self.response.get('status_code', 0):
                args = dict(post_json={'Updates': [{'Path': '', 'UpdateType': ''}]})
                self._request(f'Library/Media/Updated', cur_host, keys[i], **args)
                if 200 <= (self.response.get('status_code') or 0) < 300 and self.response.get('ok'):
                    self._log(f'Success: fallback to sending Library/Media/Updated call'
                              f' to scan all shows at host {cur_host}')
                    continue
                self._log_debug(f'Warning, Library update responded 404 not found and'
                                f' fallback to newer /Library/Media/Updated api call failed at {cur_host}')
            elif not response and not self.response.get('ok'):
                self._log_warning(f'Warning, could not connect with server at {cur_host}')
            else:
                self._log_debug(
                    f'Warning, unknown response {self.response and "%s " % self.response.get("status_code") or ""}'
                    f'from {cur_host}, can most likely be ignored')
            total_success = False

        return total_success

    def _discover_server(self):

        cs = socket(AF_INET, SOCK_DGRAM)
        mb_listen_port = 7359

        cs.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        cs.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        cs.settimeout(10)
        result, sock_issue = '', None
        for server in ('EmbyServer', 'MediaBrowserServer', 'JellyfinServer'):
            bufr = f'who is {server}?'
            try:
                assert len(bufr) == cs.sendto(decode_bytes(bufr), ('255.255.255.255', mb_listen_port)), \
                    'Not all data sent through the socket'
                message, host = cs.recvfrom(1024)
                if message:
                    message = decode_str(message)
                    self._log(f'{server} found at {host[0]}: udp query response ({message})')
                    result = ('{"Address":' not in message and message.split('|')[1] or
                              json_loads(message).get('Address', ''))
                    if result:
                        break
            except AssertionError:
                sock_issue = True
            except (BaseException, Exception):
                pass
        if not sock_issue:
            try:
                cs.shutdown(SHUT_RDWR)
            except (BaseException, Exception):
                pass
        return result

    def _check_config(self, hosts=None, apikeys=None):

        from sickgear.helpers import starify

        hosts, keys = self._choose(hosts, sickgear.EMBY_HOST), self._choose(apikeys, sickgear.EMBY_APIKEY)
        hosts = [x.strip() for x in hosts.split(',') if x.strip()]
        keys = [x.strip() for x in keys.split(',') if x.strip()]

        new_keys = []
        has_old_key = False
        for key in keys:
            if starify(key, True):
                has_old_key = True
            else:
                new_keys += [key]

        apikeys = has_old_key and [x.strip() for x in sickgear.EMBY_APIKEY.split(',') if x.strip()] or [] + new_keys

        if len(hosts) != len(apikeys):
            message = ('Not enough Api keys for hosts', 'More Api keys than hosts')[len(apikeys) > len(hosts)]
            self._log_warning(f'{message}, check your settings')
            return False, False, message

        return hosts, apikeys, 'OK'

    def _notify(self, title, body, hosts=None, apikeys=None, **kwargs):
        """ Internal wrapper for the test_notify function

        Args:
            title: The title of the message
            body: Message body of the notice to send

        Returns:
             2-Tuple True if body successfully sent otherwise False, Failure message string or None
        """
        hosts, keys, message = self._check_config(hosts, apikeys)
        if not hosts:
            return self._choose(message, False)

        success = True
        message = []

        args = dict(post_json={'Name': 'SickGear', 'Description': body, 'ImageUrl': self._sg_logo_url})
        for i, cur_host in enumerate(hosts):

            response = self._request('Notifications/Admin', cur_host, keys[i], **args)
            if not response or self.response:
                if 401 == self.response.get('status_code'):
                    success = False
                    message += [f'Fail: Cannot authenticate API key with {cur_host}']
                    self._log_warning(f'Failed to authenticate with {cur_host}')
                    continue
                elif not response and not self.response.get('ok'):
                    success = False
                    message += [f'Fail: No supported Emby server found at {cur_host}']
                    self._log_warning(f'Warning, could not connect with server at {cur_host}')
                    continue
            message += [f'OK: {cur_host}']

        return self._choose(('Success, all hosts tested', '<br />\n'.join(message))[not success], success)

    ##############################################################################
    # Public functions
    ##############################################################################

    def discover_server(self):
        return self._discover_server()

    def check_config(self, hosts=None, apikeys=None):
        self._testing = True  # ensure _choose() uses passed args
        return self._check_config(hosts, apikeys)


notifier = EmbyNotifier
