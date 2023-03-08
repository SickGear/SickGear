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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import time

from .generic import Notifier
from .. import logger
import sickgear
import sickgear.helpers
from exceptions_helper import ex
from json_helper import json_dumps

from _23 import decode_str, etree, quote, unquote, unquote_plus


class KodiNotifier(Notifier):

    def __init__(self):
        super(KodiNotifier, self).__init__()

        self.username, self.password = (None, None)
        self.response = None
        self.prefix = ''

    def _get_kodi_version(self, host):
        """ Return Kodi JSON-RPC API version (odd # = dev, even # = stable)

        Communicate with Kodi hosts using JSON-RPC to determine whether to use the legacy API or the JSON-RPC API.

        Fallback to testing legacy HTTP API before assuming it is a badly configured host.

        Returns:
            Returns API number or False

                API | Kodi Version
               -----+---------------
                 2  | v10 (Dharma)
                 3  | (pre Eden)
                 4  | v11 (Eden)
                 5  | (pre Frodo)
                 6  | v12 (Frodo) / v13 (Gotham)
        """

        timeout = 10
        response = self._send_json(host, dict(method='JSONRPC.Version'), timeout)
        if self.response and 401 == self.response.get('status_code'):
            return False

        if response.get('version'):
            version = response.get('version')
            return isinstance(version, dict) and version.get('major') or version

        # fallback to legacy HTTPAPI method
        test_command = {'command': 'Help'}
        if self._send(host, test_command, timeout):
            # return fake version number to use the legacy method
            return 1

        if self.response and 404 == self.response.get('status_code'):
            self.prefix = 'xbmc'
            if self._send(host, test_command, timeout):
                # return fake version number to use the legacy method
                return 1

        return False

    def update_library(self, show_name=None, **kwargs):
        """ Wrapper for the update library functions

        Call either the JSON-RPC over HTTP or the legacy HTTP API methods depending on the Kodi API version.

        Uses a list of comma delimited hosts where only one is updated, the first to respond with success. This is a
        workaround for SQL backend users because updating multiple clients causes duplicate entries.

        Future plan is to revisit how host/ip/username/pw/options are stored so that this may become more flexible.

        Args:
            show_name: Name of a TV show to target for a library update

        Returns: True if processing succeeded with no issues else False if any issues found
        """
        if not sickgear.KODI_HOST:
            self._log_warning('No Kodi hosts specified, check your settings')
            return False

        # either update each host, or only attempt to update until one successful result
        result = 0
        only_first = dict(show='', first='', first_note='')
        show_name and only_first.update(show=' for show;"%s"' % show_name)
        sickgear.KODI_UPDATE_ONLYFIRST and only_first.update(dict(
            first=' first', first_note=' in line with the "Only update first host"%s' % ' setting'))

        for cur_host in [x.strip() for x in sickgear.KODI_HOST.split(',')]:

            response = self._send_json(cur_host, dict(method='Profiles.GetCurrentProfile'))
            if self.response and 401 == self.response.get('status_code'):
                self._log_debug(f'Failed to authenticate with {cur_host}')
                continue
            if not response:
                self._maybe_log_failed_detection(cur_host)
                continue

            if self._send_library_update(cur_host, show_name):
                only_first.update(dict(profile=response.get('label') or 'Master', host=cur_host))
                self._log('Success: profile;' +
                          '"%(profile)s" at%(first)s host;%(host)s updated%(show)s%(first_note)s' % only_first)
            else:
                self._maybe_log_failed_detection(cur_host)
                result += 1

            if sickgear.KODI_UPDATE_ONLYFIRST:
                return True

        # needed for the 'update kodi' submenu command as it only cares of the final result vs the individual ones
        return 0 == result

    def _send_library_update(self, host, show_name=None):
        """ Internal wrapper for the update library function

        Call either the JSON-RPC over HTTP or the legacy HTTP API methods depending on the Kodi API version.

        Args:
            show_name: Name of a TV show to specifically target the library update for

        Return:
            True if the update was successful else False
        """
        api_version = self._get_kodi_version(host)
        if api_version:
            # try to update just the show, if it fails, do full update if enabled
            __method_update = (self._update, self._update_json)[4 < api_version]
            if __method_update(host, show_name):
                return True

            failed_msg = 'Single show update failed,'
            if sickgear.KODI_UPDATE_FULL:
                self._log_debug(f'{failed_msg} falling back to full update')
                return __method_update(host)

            self._log_debug(f'{failed_msg} consider enabling "Perform full library update" in config/notifications')
        return False

    ##############################################################################
    # Legacy HTTP API (pre Kodi 12) methods
    ##############################################################################

    def _send(self, host, command, timeout=30):
        """ Handle communication to Kodi servers via HTTP API

        Args:
            command: Dictionary encoded via urllib and passed to the Kodi API via HTTP

        Return:
            response.result for successful commands or False if there was an error
        """

        if not host:
            self._log_warning('No host specified, aborting update')
            return False

        args = {}
        if not sickgear.KODI_ALWAYS_ON and not self._testing:
            args['mute_connect_err'] = True

        if self.password or sickgear.KODI_PASSWORD:
            args['auth'] = (self.username or sickgear.KODI_USERNAME, self.password or sickgear.KODI_PASSWORD)

        url = 'http://%s/%sCmds/%sHttp' % (host, self.prefix or 'kodi', self.prefix or 'kodi')
        response = sickgear.helpers.get_url(url=url, params=command,
                                             timeout=timeout, hooks=dict(response=self.cb_response), **args)

        return response or False

    def _update(self, host=None, show_name=None):
        """ Handle updating Kodi host via HTTP API

        Update the video library for a specific tv show if passed, otherwise update the whole library if option enabled.

        Args:
            show_name: Name of a TV show to target for a library update

        Return:
            True or False
        """

        if not host:
            self._log_warning('No host specified, aborting update')
            return False

        self._log_debug(f'Updating library via HTTP method for host: {host}')

        # if we're doing per-show
        if show_name:
            self._log_debug(f'Updating library via HTTP method for show {show_name}')

            # noinspection SqlResolve
            path_sql = 'SELECT path.strPath' \
                       ' FROM path, tvshow, tvshowlinkpath' \
                       ' WHERE tvshow.c00 = "%s"' % show_name \
                       + ' AND tvshowlinkpath.idShow = tvshow.idShow' \
                         ' AND tvshowlinkpath.idPath = path.idPath'

            # set xml response format, if this fails then don't bother with the rest
            if not self._send(
                host, {'command': 'SetResponseFormat(webheader;false;webfooter;false;header;<xml>;footer;</xml>;'
                                  'opentag;<tag>;closetag;</tag>;closefinaltag;false)'}):
                return False

            # sql used to grab path(s)
            response = self._send(host, {'command': 'QueryVideoDatabase(%s)' % path_sql})
            if not response:
                self._log_debug(f'Invalid response for {show_name} on {host}')
                return False

            try:
                et = etree.fromstring(quote(response, ':\\/<>'))
            except SyntaxError as e:
                self._log_error(f'Unable to parse XML in response: {ex(e)}')
                return False

            paths = et.findall('.//field')
            if not paths:
                self._log_debug(f'No valid path found for {show_name} on {host}')
                return False

            for path in paths:
                # we do not need it double-encoded, gawd this is dumb
                un_enc_path = decode_str(unquote(path.text), sickgear.SYS_ENCODING)
                self._log_debug(f'Updating {show_name} on {host} at {un_enc_path}')

                if not self._send(
                        host, dict(command='ExecBuiltIn', parameter='Kodi.updatelibrary(video, %s)' % un_enc_path)):
                    self._log_error(f'Update of show directory failed for {show_name} on {host} at {un_enc_path}')
                    return False

                # sleep for a few seconds just to be sure kodi has a chance to finish each directory
                if 1 < len(paths):
                    time.sleep(5)
        # do a full update if requested
        else:
            self._log_debug(f'Full library update on host: {host}')

            if not self._send(host, dict(command='ExecBuiltIn', parameter='Kodi.updatelibrary(video)')):
                self._log_error(f'Failed full library update on: {host}')
                return False

        return True

    ##############################################################################
    # JSON-RPC API (Kodi 12+) methods
    ##############################################################################

    def _send_json(self, host, command, timeout=30):
        """ Handle communication to Kodi installations via JSONRPC

        Args:
            command: Kodi JSON-RPC command to send via HTTP

        Return:
            response.result dict for successful commands or empty dict if there was an error
        """

        result = {}
        if not host:
            self._log_warning('No host specified, aborting update')
            return result

        if isinstance(command, dict):
            command.setdefault('jsonrpc', '2.0')
            command.setdefault('id', 'SickGear')
            args = dict(post_json=command)
        else:
            args = dict(data=command)

        if not sickgear.KODI_ALWAYS_ON and not self._testing:
            args['mute_connect_err'] = True

        if self.password or sickgear.KODI_PASSWORD:
            args['auth'] = (self.username or sickgear.KODI_USERNAME, self.password or sickgear.KODI_PASSWORD)

        response = sickgear.helpers.get_url(url='http://%s/jsonrpc' % host, timeout=timeout,
                                             headers={'Content-type': 'application/json'}, parse_json=True,
                                             hooks=dict(response=self.cb_response), **args)
        if response:
            if not response.get('error'):
                return 'OK' == response.get('result') and {'OK': True} or response.get('result')

            self._log_error(f'API error; {json_dumps(response["error"])} from {host}'
                            f' in response to command: {json_dumps(command)}')
        return result

    def _update_json(self, host=None, show_name=None):
        """ Handle updating Kodi host via HTTP JSON-RPC

        Update the video library for a specific tv show if passed, otherwise update the whole library if option enabled.

        Args:
            show_name: Name of a TV show to target for a library update

        Return:
            True or False
        """

        if not host:
            self._log_warning('No host specified, aborting update')
            return False

        # if we're doing per-show
        if show_name:
            self._log_debug(f'JSON library update. Host: {host} Show: {show_name}')

            # try fetching tvshowid using show_name with a fallback to getting show list
            show_name = unquote_plus(show_name)
            commands = [dict(method='VideoLibrary.GetTVShows',
                             params={'filter': {'field': 'title', 'operator': 'is', 'value': '%s' % show_name},
                                     'properties': ['title']}),
                        dict(method='VideoLibrary.GetTVShows')]

            shows = None
            for command in commands:
                response = self._send_json(host, command)
                shows = response.get('tvshows')
                if shows:
                    break

            if not shows:
                self._log_debug('No items in GetTVShows response')
                return False

            tvshowid = -1
            path = ''
            # noinspection PyTypeChecker
            for show in shows:
                if show_name == show.get('title') or show_name == show.get('label'):
                    tvshowid = show.get('tvshowid', -1)
                    path = show.get('file', '')
                    break
            del shows

            # we didn't find the show (exact match), thus revert to just doing a full update if enabled
            if -1 == tvshowid:
                self._log_debug(f'Doesn\'t have "{show_name}" in it\'s known shows, full library update required')
                return False

            # lookup tv-show path if we don't already know it
            if not len(path):
                command = dict(method='VideoLibrary.GetTVShowDetails',
                               params={'tvshowid': tvshowid, 'properties': ['file']})
                response = self._send_json(host, command)
                path = 'tvshowdetails' in response and response['tvshowdetails'].get('file', '') or ''

            if not len(path):
                self._log_warning(f'No valid path found for {show_name} with ID: {tvshowid} on {host}')
                return False

            self._log_debug(f'Updating {show_name} on {host} at {path}')
            command = dict(method='VideoLibrary.Scan',
                           params={'directory': '%s' % json_dumps(path)[1:-1].replace('\\\\', '\\')})
            response_scan = self._send_json(host, command)
            if not response_scan.get('OK'):
                self._log_error(f'Update of show directory failed for {show_name} on {host} at {path}'
                                f' response: {response_scan}')
                return False

        # do a full update if requested
        else:
            self._log_debug(f'Full library update on host: {host}')
            response_scan = self._send_json(host, dict(method='VideoLibrary.Scan'))
            if not response_scan.get('OK'):
                self._log_error(f'Failed full library update on: {host} response: {response_scan}')
                return False

        return True

    # noinspection PyUnusedLocal
    def cb_response(self, r, *args, **kwargs):
        self.response = dict(status_code=r.status_code)
        return r

    def _maybe_log(self, msg, log_level=logger.WARNING):

        if msg and (sickgear.KODI_ALWAYS_ON or self._testing):
            self._log(msg + (not sickgear.KODI_ALWAYS_ON and self._testing and
                             ' (Test mode ignores "Always On")' or ''), log_level)

    def _maybe_log_failed_detection(self, host, msg='connect to'):

        self._maybe_log(f'Failed to {msg} {host}, check device(s) and config', logger.ERROR)

    def _notify(self, title, body, hosts=None, username=None, password=None, **kwargs):
        """ Internal wrapper for the notify_snatch and notify_download functions

        Call either the JSON-RPC over HTTP or the legacy HTTP API methods depending on the Kodi API version.

        Args:
            title: Title of the notice to send
            body: Message body of the notice to send

        Return:
            A list of results in the format of host:ip:result, where result will either be 'OK' or False.
        """
        self.username, self.password = username, password

        title = title or 'SickGear'

        hosts = self._choose(hosts, sickgear.KODI_HOST)

        success = True
        message = []
        for host in [x.strip() for x in hosts.split(',')]:
            cur_host = unquote_plus(host)

            api_version = self._get_kodi_version(cur_host)
            if self.response and 401 == self.response.get('status_code'):
                success = False
                message += ['Fail: Cannot authenticate with %s' % cur_host]
                self._log_debug(f'Failed to authenticate with {cur_host}')
            elif not api_version:
                success = False
                message += ['Fail: No supported Kodi found at %s' % cur_host]
                self._maybe_log_failed_detection(cur_host, 'connect and detect version for')
            else:
                if 4 >= api_version:
                    self._log_debug(f'Detected {self.prefix and " " + self.prefix.capitalize()}version <= 11,'
                                    f' using HTTP API')
                    __method_send = self._send
                    command = dict(command='ExecBuiltIn',
                                   parameter='Notification(%s,%s)' % (title, body))
                else:
                    self._log_debug('Detected version >= 12, using JSON API')
                    __method_send = self._send_json
                    command = dict(method='GUI.ShowNotification', params=dict(
                        [('title', title), ('message', body), ('image', self._sg_logo_url)]
                        + ([], [('displaytime', 8000)])[self._testing]))

                response_notify = __method_send(cur_host, command, 10)
                if response_notify:
                    message += ['%s: %s' % ((response_notify, 'OK')['OK' in response_notify], cur_host)]

        return self._choose(('Success, all hosts tested', '<br />\n'.join(message))[not success], success)


notifier = KodiNotifier
