# coding=utf-8
#
# This file is part of SickGear.
# Author: SickGear
# Thanks to: Nic Wolfe
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

try:
    import json
except ImportError:
    from lib import simplejson as json
import time
import urllib
import xml.etree.cElementTree as XmlEtree

import sickbeard
import sickbeard.helpers
from sickbeard import logger
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier


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
        if not sickbeard.KODI_HOST:
            self._log_warning(u'No Kodi hosts specified, check your settings')
            return False

        # either update each host, or only attempt to update until one successful result
        result = 0
        only_first = dict(show='', first='', first_note='')
        show_name and only_first.update(show=' for show;"%s"' % show_name)
        sickbeard.KODI_UPDATE_ONLYFIRST and only_first.update(dict(
            first=' first', first_note=' in line with the "Only update first host"%s' % ' setting'))

        for cur_host in [x.strip() for x in sickbeard.KODI_HOST.split(',')]:

            response = self._send_json(cur_host, dict(method='Profiles.GetCurrentProfile'))
            if self.response and 401 == self.response.get('status_code'):
                self._log_debug(u'Failed to authenticate with %s' % cur_host)
                continue
            if not response:
                self._maybe_log_failed_detection(cur_host)
                continue

            if self._send_library_update(cur_host, show_name):
                only_first.update(dict(profile=response.get('label') or 'Master', host=cur_host))
                self._log('Success: profile;' +
                          u'"%(profile)s" at%(first)s host;%(host)s updated%(show)s%(first_note)s' % only_first)
            else:
                self._maybe_log_failed_detection(cur_host)
                result += 1

            if sickbeard.KODI_UPDATE_ONLYFIRST:
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
            if sickbeard.KODI_UPDATE_FULL:
                self._log_debug(u'%s falling back to full update' % failed_msg)
                return __method_update(host)

            self._log_debug(u'%s consider enabling "Perform full library update" in config/notifications' % failed_msg)
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
            self._log_warning(u'No host specified, aborting update')
            return False

        args = {}
        if not sickbeard.KODI_ALWAYS_ON and not self._testing:
            args['mute_connect_err'] = True

        if self.password or sickbeard.KODI_PASSWORD:
            args['auth'] = (self.username or sickbeard.KODI_USERNAME, self.password or sickbeard.KODI_PASSWORD)

        url = 'http://%s/%sCmds/%sHttp' % (host, self.prefix or 'kodi', self.prefix or 'kodi')
        response = sickbeard.helpers.getURL(url=url, params=command,
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
            self._log_warning(u'No host specified, aborting update')
            return False

        self._log_debug(u'Updating library via HTTP method for host: %s' % host)

        # if we're doing per-show
        if show_name:
            self._log_debug(u'Updating library via HTTP method for show %s' % show_name)

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
                self._log_debug(u'Invalid response for %s on %s' % (show_name, host))
                return False

            try:
                et = XmlEtree.fromstring(urllib.quote(response, ':\\/<>'))
            except SyntaxError as e:
                self._log_error(u'Unable to parse XML in response: %s' % ex(e))
                return False

            paths = et.findall('.//field')
            if not paths:
                self._log_debug(u'No valid path found for %s on %s' % (show_name, host))
                return False

            for path in paths:
                # we do not need it double-encoded, gawd this is dumb
                un_enc_path = urllib.unquote(path.text).decode(sickbeard.SYS_ENCODING)
                self._log_debug(u'Updating %s on %s at %s' % (show_name, host, un_enc_path))

                if not self._send(
                        host, dict(command='ExecBuiltIn', parameter='Kodi.updatelibrary(video, %s)' % un_enc_path)):
                    self._log_error(u'Update of show directory failed for %s on %s at %s'
                                    % (show_name, host, un_enc_path))
                    return False

                # sleep for a few seconds just to be sure kodi has a chance to finish each directory
                if 1 < len(paths):
                    time.sleep(5)
        # do a full update if requested
        else:
            self._log_debug(u'Full library update on host: %s' % host)

            if not self._send(host, dict(command='ExecBuiltIn', parameter='Kodi.updatelibrary(video)')):
                self._log_error(u'Failed full library update on: %s' % host)
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
            self._log_warning(u'No host specified, aborting update')
            return result

        if isinstance(command, dict):
            command.setdefault('jsonrpc', '2.0')
            command.setdefault('id', 'SickGear')
            args = dict(post_json=command)
        else:
            args = dict(data=command)

        if not sickbeard.KODI_ALWAYS_ON and not self._testing:
            args['mute_connect_err'] = True

        if self.password or sickbeard.KODI_PASSWORD:
            args['auth'] = (self.username or sickbeard.KODI_USERNAME, self.password or sickbeard.KODI_PASSWORD)

        response = sickbeard.helpers.getURL(url='http://%s/jsonrpc' % host, timeout=timeout,
                                            headers={'Content-type': 'application/json'}, json=True,
                                            hooks=dict(response=self.cb_response), **args)
        if response:
            if not response.get('error'):
                return 'OK' == response.get('result') and {'OK': True} or response.get('result')

            self._log_error(u'API error; %s from %s in response to command: %s'
                            % (json.dumps(response['error']), host, json.dumps(command)))
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
            self._log_warning(u'No host specified, aborting update')
            return False

        # if we're doing per-show
        if show_name:
            self._log_debug(u'JSON library update. Host: %s Show: %s' % (host, show_name))

            # try fetching tvshowid using show_name with a fallback to getting show list
            show_name = urllib.unquote_plus(show_name)
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
                self._log_debug(u'No items in GetTVShows response')
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
                self._log_debug(u'Doesn\'t have "%s" in it\'s known shows, full library update required' % show_name)
                return False

            # lookup tv-show path if we don't already know it
            if not len(path):
                command = dict(method='VideoLibrary.GetTVShowDetails',
                               params={'tvshowid': tvshowid, 'properties': ['file']})
                response = self._send_json(host, command)
                path = 'tvshowdetails' in response and response['tvshowdetails'].get('file', '') or ''

            if not len(path):
                self._log_warning(u'No valid path found for %s with ID: %s on %s' % (show_name, tvshowid, host))
                return False

            self._log_debug(u'Updating %s on %s at %s' % (show_name, host, path))
            command = dict(method='VideoLibrary.Scan', params={'directory': '%s' % json.dumps(path)[1:-1]})
            response_scan = self._send_json(host, command)
            if not response_scan.get('OK'):
                self._log_error(u'Update of show directory failed for %s on %s at %s response: %s' %
                                (show_name, host, path, response_scan))
                return False

        # do a full update if requested
        else:
            self._log_debug(u'Full library update on host: %s' % host)
            response_scan = self._send_json(host, dict(method='VideoLibrary.Scan'))
            if not response_scan.get('OK'):
                self._log_error(u'Failed full library update on: %s response: %s' % (host, response_scan))
                return False

        return True

    # noinspection PyUnusedLocal
    def cb_response(self, r, *args, **kwargs):
        self.response = dict(status_code=r.status_code)
        return r

    def _maybe_log(self, msg, log_level=logger.WARNING):

        if msg and (sickbeard.KODI_ALWAYS_ON or self._testing):
            self._log(msg + (not sickbeard.KODI_ALWAYS_ON and self._testing and
                             ' (Test mode ignores "Always On")' or ''), log_level)

    def _maybe_log_failed_detection(self, host, msg='connect to'):

        self._maybe_log(u'Failed to %s %s, check device(s) and config' % (msg, host), logger.ERROR)

    def _notify(self, title, body, hosts, username, password, **kwargs):
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

        hosts = self._choose(hosts, sickbeard.KODI_HOST)

        success = True
        message = []
        for host in [x.strip() for x in hosts.split(',')]:
            cur_host = urllib.unquote_plus(host)

            api_version = self._get_kodi_version(cur_host)
            if self.response and 401 == self.response.get('status_code'):
                success = False
                message += ['Fail: Cannot authenticate with %s' % cur_host]
                self._log_debug(u'Failed to authenticate with %s' % cur_host)
            elif not api_version:
                success = False
                message += ['Fail: No supported Kodi found at %s' % cur_host]
                self._maybe_log_failed_detection(cur_host, 'connect and detect version for')
            else:
                if 4 >= api_version:
                    self._log_debug(u'Detected %sversion <= 11, using HTTP API'
                                    % self.prefix and ' ' + self.prefix.capitalize())
                    __method_send = self._send
                    command = dict(command='ExecBuiltIn',
                                   parameter='Notification(%s,%s)' % (title, body))
                else:
                    self._log_debug(u'Detected version >= 12, using JSON API')
                    __method_send = self._send_json
                    command = dict(method='GUI.ShowNotification', params=dict(
                        [('title', title), ('message', body), ('image', self._sg_logo_url)]
                        + ([], [('displaytime', 8000)])[self._testing]))

                response_notify = __method_send(cur_host, command, 10)
                if response_notify:
                    message += ['%s: %s' % ((response_notify, 'OK')['OK' in response_notify], cur_host)]

        return self._choose(('Success, all hosts tested', '<br />\n'.join(message))[not success], success)


notifier = KodiNotifier
