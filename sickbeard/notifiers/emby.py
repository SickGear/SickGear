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

import sickbeard
from sickbeard import logger
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, SO_BROADCAST, SHUT_RDWR
from lib import simplejson as json


class EmbyNotifier:
    def __init__(self):
        self.sg_logo_url = 'https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/ico/' + \
                           'apple-touch-icon-precomposed.png'
        self.response = None
        self.test_mode = False

    def _notify_emby(self, msg, hosts=None, apikeys=None):
        """ Internal wrapper for the test_notify function

        Args:
            msg: Message body of the notice to send

        Returns:
             2-Tuple True if msg successfully sent otherwise False, Failure message string or None
        """

        if not sickbeard.USE_EMBY and not self.test_mode:
            self._log(u'Notification not enabled, skipping this notification', logger.DEBUG)
            return False, None

        hosts, keys, message = self._check_config(hosts, apikeys)
        if not hosts:
            return False, message

        total_success = True
        messages = []

        args = dict(post_json={'Name': 'SickGear', 'Description': msg, 'ImageUrl': self.sg_logo_url})
        for i, cur_host in enumerate(hosts):

            self.response = None
            response = sickbeard.helpers.getURL(
                'http://%s/emby/Notifications/Admin' % cur_host,
                headers={'Content-type': 'application/json', 'X-MediaBrowser-Token': keys[i]},
                timeout=10, hooks=dict(response=self._cb_response), **args)
            if not response or self.response:
                if self.response and 401 == self.response.get('status_code'):
                    total_success = False
                    messages += ['Fail: Cannot authenticate API key with %s' % cur_host]
                    self._log(u'Failed to authenticate with %s' % cur_host)
                    continue
                elif not response and not self.response or not self.response.get('ok'):
                    total_success = False
                    messages += ['Fail: No supported Emby server found at %s' % cur_host]
                    self._log(u'Warning, could not connect with server at ' + cur_host)
                    continue
            messages += ['OK: %s' % cur_host]

        return total_success, '<br />\n'.join(messages)

    def _update_library(self, show=None):

        hosts, keys, message = self._check_config()
        if not hosts:
            self._log(u'Issue with hosts or api keys, check your settings')
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
                self._log(u'Success: update %s sent to host %s in a library updated call' % (mode_to_log, cur_host),
                          logger.MESSAGE)
                continue
            elif self.response and 401 == self.response.get('status_code'):
                self._log(u'Failed to authenticate with %s' % cur_host)
            elif self.response and 404 == self.response.get('status_code'):
                self._log(u'Warning, Library update responded 404 not found at %s' % cur_host, logger.DEBUG)
            elif not response and not self.response or not self.response.get('ok'):
                self._log(u'Warning, could not connect with server at %s' % cur_host)
            else:
                self._log(u'Warning, unknown response %sfrom %s, can most likely be ignored'
                          % (self.response and '%s ' % self.response.get('status_code') or '', cur_host), logger.DEBUG)
            total_success = False

        return total_success

    # noinspection PyUnusedLocal
    def _cb_response(self, r, *args, **kwargs):

        self.response = dict(status_code=r.status_code, ok=r.ok)
        return r

    @staticmethod
    def _discover_server():
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
                    logger.log('%s found at %s: udp query response (%s)' % (server, host[0], message))
                    result = ('{"Address":' not in message and message.split('|')[1] or
                              json.loads(message).get('Address', ''))
                    if result:
                        break
            except AssertionError:
                sock_issue = True
            except Exception:
                pass
        if not sock_issue:
            cs.shutdown(SHUT_RDWR)
        return result

    def _check_config(self, hosts=None, apikeys=None):

        from sickbeard.helpers import starify

        hosts, keys = hosts or sickbeard.EMBY_HOST, apikeys or sickbeard.EMBY_APIKEY
        hosts = [x.strip() for x in hosts.split(',') if x.strip()]
        keys = [x.strip() for x in keys.split(',') if x.strip()]

        new_keys = []
        has_old_key = False
        for key in keys:
            if starify(key, True):
                has_old_key = True
            else:
                new_keys += [key]

        apikeys = (new_keys, [x.strip() for x in sickbeard.EMBY_APIKEY.split(',') if x.strip()] + new_keys)[has_old_key]

        if len(hosts) != len(apikeys):
            message = ('Not enough Api keys for hosts', 'More Api keys than hosts')[len(apikeys) > len(hosts)]
            self._log(u'%s, check your settings' % message)
            return False, False, message

        return hosts, apikeys, 'OK'

    @staticmethod
    def _log(msg, log_level=logger.WARNING):

        logger.log(u'Emby: %s' % msg, log_level)

    ##############################################################################
    # Public functions
    ##############################################################################

    def discover_server(self):
        return self._discover_server()

    def test_notify(self, host, apikey):

        self.test_mode = True
        result = self._notify_emby('Testing SickGear Emby notifier', host, apikey)
        self.test_mode = False
        return result

    def update_library(self, show=None, force=False):
        """ Wrapper for the update library functions

        :param show: TVShow object
        :param force: True force update process

        Returns: None if no processing done, True if processing succeeded with no issues else False if any issues found
        """
        if sickbeard.USE_EMBY and (sickbeard.EMBY_UPDATE_LIBRARY or force):
            return self._update_library(show)


notifier = EmbyNotifier
