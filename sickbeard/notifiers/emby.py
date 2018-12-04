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

import sickbeard
from sickbeard.notifiers.generic import Notifier

from lib import simplejson as json


class EmbyNotifier(Notifier):

    def __init__(self):
        super(EmbyNotifier, self).__init__()

        self.response = None

    def update_library(self, show=None, **kwargs):
        """ Update library function

        :param show: TVShow object

        Returns: None if no processing done, True if processing succeeded with no issues else False if any issues found
        """
        hosts, keys, message = self._check_config()
        if not hosts:
            self._log_warning(u'Issue with hosts or api keys, check your settings')
            return False

        from sickbeard.indexers.indexer_config import INDEXER_TVDB
        args = show and INDEXER_TVDB == show.indexer \
            and dict(post_json={'TvdbId': '%s' % show.indexerid}) or dict(data=None)
        mode_to_log = show and 'show "%s"' % show.name or 'all shows'
        total_success = True
        for i, cur_host in enumerate(hosts):

            self.response = None
            # noinspection PyArgumentList
            response = sickbeard.helpers.getURL(
                'http://%s/emby/Library/Series/Updated' % cur_host,
                headers={'Content-type': 'application/json', 'X-MediaBrowser-Token': keys[i]},
                timeout=20, hooks=dict(response=self._cb_response), **args)
            # Emby will initiate a LibraryMonitor path refresh one minute after this success
            if self.response and 204 == self.response.get('status_code') and self.response.get('ok'):
                self._log(u'Success: update %s sent to host %s in a library updated call' % (mode_to_log, cur_host))
                continue
            elif self.response and 401 == self.response.get('status_code'):
                self._log_warning(u'Failed to authenticate with %s' % cur_host)
            elif self.response and 404 == self.response.get('status_code'):
                self._log_debug(u'Warning, Library update responded 404 not found at %s' % cur_host)
            elif not response and not self.response or not self.response.get('ok'):
                self._log_warning(u'Warning, could not connect with server at %s' % cur_host)
            else:
                self._log_debug(u'Warning, unknown response %sfrom %s, can most likely be ignored'
                                % (self.response and '%s ' % self.response.get('status_code') or '', cur_host))
            total_success = False

        return total_success

    # noinspection PyUnusedLocal
    def _cb_response(self, r, *args, **kwargs):
        self.response = dict(status_code=r.status_code, ok=r.ok)
        return r

    def _discover_server(self):

        cs = socket(AF_INET, SOCK_DGRAM)
        mb_listen_port = 7359

        cs.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        cs.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        cs.settimeout(10)
        result, sock_issue = '', None
        for server in ('EmbyServer', 'MediaBrowserServer'):
            bufr = 'who is %s?' % server
            try:
                assert len(bufr) == cs.sendto(bufr, ('255.255.255.255', mb_listen_port)), \
                    'Not all data sent through the socket'
                message, host = cs.recvfrom(1024)
                if message:
                    self._log('%s found at %s: udp query response (%s)' % (server, host[0], message))
                    result = ('{"Address":' not in message and message.split('|')[1] or
                              json.loads(message).get('Address', ''))
                    if result:
                        break
            except AssertionError:
                sock_issue = True
            except (StandardError, Exception):
                pass
        if not sock_issue:
            try:
                cs.shutdown(SHUT_RDWR)
            except (StandardError, Exception):
                pass
        return result

    def _check_config(self, hosts=None, apikeys=None):

        from sickbeard.helpers import starify

        hosts, keys = self._choose(hosts, sickbeard.EMBY_HOST), self._choose(apikeys, sickbeard.EMBY_APIKEY)
        hosts = [x.strip() for x in hosts.split(',') if x.strip()]
        keys = [x.strip() for x in keys.split(',') if x.strip()]

        new_keys = []
        has_old_key = False
        for key in keys:
            if starify(key, True):
                has_old_key = True
            else:
                new_keys += [key]

        apikeys = has_old_key and [x.strip() for x in sickbeard.EMBY_APIKEY.split(',') if x.strip()] or [] + new_keys

        if len(hosts) != len(apikeys):
            message = ('Not enough Api keys for hosts', 'More Api keys than hosts')[len(apikeys) > len(hosts)]
            self._log_warning(u'%s, check your settings' % message)
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

            self.response = None
            response = sickbeard.helpers.getURL(
                'http://%s/emby/Notifications/Admin' % cur_host,
                headers={'Content-type': 'application/json', 'X-MediaBrowser-Token': keys[i]},
                timeout=10, hooks=dict(response=self._cb_response), **args)
            if not response or self.response:
                if self.response and 401 == self.response.get('status_code'):
                    success = False
                    message += ['Fail: Cannot authenticate API key with %s' % cur_host]
                    self._log_warning(u'Failed to authenticate with %s' % cur_host)
                    continue
                elif not response and not self.response or not self.response.get('ok'):
                    success = False
                    message += ['Fail: No supported Emby server found at %s' % cur_host]
                    self._log_warning(u'Warning, could not connect with server at ' + cur_host)
                    continue
            message += ['OK: %s' % cur_host]

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
