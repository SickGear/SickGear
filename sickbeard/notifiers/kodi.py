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

import time
import urllib

import sickbeard
import sickbeard.helpers
from sickbeard.exceptions import ex
from sickbeard import logger, common

try:
    # noinspection PyPep8Naming
    import xml.etree.cElementTree as etree
except ImportError:
    # noinspection PyPep8Naming
    import xml.etree.ElementTree as etree

try:
    import json
except ImportError:
    from lib import simplejson as json


class KodiNotifier:
    def __init__(self):
        self.sg_logo_url = 'https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/ico/' + \
                           'apple-touch-icon-precomposed.png'

        self.username, self.password = (None, None)
        self.response = None
        self.prefix = ''
        self.test_mode = False

    @staticmethod
    def _log(msg, log_level=logger.WARNING):

        logger.log(u'Kodi: %s' % msg, log_level)

    def _maybe_log(self, msg, log_level=logger.WARNING):

        if msg and (sickbeard.KODI_ALWAYS_ON or self.test_mode):
            self._log(msg + (not sickbeard.KODI_ALWAYS_ON and self.test_mode and
                             ' (Test mode ignores "Always On")' or ''), log_level)

    def _maybe_log_failed_detection(self, host, msg='connect to'):

        self._maybe_log(u'Failed to %s %s, check device(s) and config.' % (msg, host), logger.ERROR)

    # noinspection PyUnusedLocal
    def cb_response(self, r, *args, **kwargs):
        self.response = dict(status_code=r.status_code)
        return r

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
        response = self._send_to_kodi_json(host, dict(method='JSONRPC.Version'), timeout)
        if self.response and 401 == self.response.get('status_code'):
            return False

        if response.get('version'):
            version = response.get('version')
            return isinstance(version, dict) and version.get('major') or version

        # fallback to legacy HTTPAPI method
        test_command = {'command': 'Help'}
        if self._send_to_kodi(host, test_command, timeout):
            # return fake version number to use the legacy method
            return 1

        if self.response and 404 == self.response.get('status_code'):
            self.prefix = 'xbmc'
            if self._send_to_kodi(host, test_command, timeout):
                # return fake version number to use the legacy method
                return 1

        return False

    def _notify_kodi(self, msg, title='SickGear', kodi_hosts=None):
        """ Internal wrapper for the notify_snatch and notify_download functions

        Call either the JSON-RPC over HTTP or the legacy HTTP API methods depending on the Kodi API version.

        Args:
            msg: Message body of the notice to send
            title: Title of the notice to send

        Return:
            A list of results in the format of host:ip:result, where result will either be 'OK' or False.
        """

        # fill in omitted parameters
        if not kodi_hosts:
            kodi_hosts = sickbeard.KODI_HOST

        if not sickbeard.USE_KODI and not self.test_mode:
            self._log(u'Notification not enabled, skipping this notification', logger.DEBUG)
            return False, None

        total_success = True
        message = []
        for host in [x.strip() for x in kodi_hosts.split(',')]:
            cur_host = urllib.unquote_plus(host)

            self._log(u'Sending notification to "%s" - %s' % (cur_host, message), logger.DEBUG)

            api_version = self._get_kodi_version(cur_host)
            if self.response and 401 == self.response.get('status_code'):
                total_success = False
                message += ['Fail: Cannot authenticate with %s' % cur_host]
                self._log(u'Failed to authenticate with %s' % cur_host, logger.DEBUG)
            elif not api_version:
                total_success = False
                message += ['Fail: No supported Kodi found at %s' % cur_host]
                self._maybe_log_failed_detection(cur_host, 'connect and detect version for')
            else:
                if 4 >= api_version:
                    self._log(u'Detected %sversion <= 11, using HTTP API'
                              % self.prefix and ' ' + self.prefix.capitalize(), logger.DEBUG)
                    __method_send = self._send_to_kodi
                    command = dict(command='ExecBuiltIn',
                                   parameter='Notification(%s,%s)' % (title, msg))
                else:
                    self._log(u'Detected version >= 12, using JSON API', logger.DEBUG)
                    __method_send = self._send_to_kodi_json
                    command = dict(method='GUI.ShowNotification',
                                   params={'title': '%s' % title,
                                           'message': '%s' % msg,
                                           'image': '%s' % self.sg_logo_url})

                response_notify = __method_send(cur_host, command, 10)
                if response_notify:
                    message += ['%s: %s' % ((response_notify, 'OK')['OK' in response_notify], cur_host)]

        return total_success, '<br />\n'.join(message)

    def _update_library(self, show_name=None):
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
            self._log(u'No Kodi hosts specified, check your settings')
            return False

        # either update each host, or only attempt to update until one successful result
        result = 0
        only_first = dict(show='', first='', first_note='')
        show_name and only_first.update(show=' for show;"%s"' % show_name)
        sickbeard.KODI_UPDATE_ONLYFIRST and only_first.update(dict(
            first=' first', first_note=' in line with the "Only update first host"%s' % ' setting'))

        for cur_host in [x.strip() for x in sickbeard.KODI_HOST.split(',')]:

            response = self._send_to_kodi_json(cur_host, dict(method='Profiles.GetCurrentProfile'))
            if self.response and 401 == self.response.get('status_code'):
                self._log(u'Failed to authenticate with %s' % cur_host, logger.DEBUG)
                continue
            if not response:
                self._maybe_log_failed_detection(cur_host)
                continue

            if self._send_update_library(cur_host, show_name):
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

    def _send_update_library(self, host, show_name=None):
        """ Internal wrapper for the update library function

        Call either the JSON-RPC over HTTP or the legacy HTTP API methods depending on the Kodi API version.

        Args:
            show_name: Name of a TV show to specifically target the library update for

        Return:
            True if the update was successful else False
        """

        self._log(u'Sending request to update library for host: "%s"' % host, logger.DEBUG)

        api_version = self._get_kodi_version(host)
        if api_version:
            # try to update just the show, if it fails, do full update if enabled
            __method_update = (self._update, self._update_json)[4 < api_version]
            if __method_update(host, show_name):
                return True

            failed_msg = 'Single show update failed,'
            if sickbeard.KODI_UPDATE_FULL:
                self._log(u'%s falling back to full update' % failed_msg, logger.DEBUG)
                return __method_update(host)

            self._log(u'%s consider enabling "Perform full library update" in config/notifications' % failed_msg,
                      logger.DEBUG)
        return False

    ##############################################################################
    # Legacy HTTP API (pre Kodi 12) methods
    ##############################################################################

    def _send_to_kodi(self, host, command, timeout=30):
        """ Handle communication to Kodi servers via HTTP API

        Args:
            command: Dictionary encoded via urllib and passed to the Kodi API via HTTP

        Return:
            response.result for successful commands or False if there was an error
        """

        if not host:
            self._log(u'No host specified, aborting update', logger.WARNING)
            return False

        args = {}
        if not sickbeard.KODI_ALWAYS_ON and not self.test_mode:
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
            self._log(u'No host specified, aborting update', logger.WARNING)
            return False

        self._log(u'Updating library via HTTP method for host: %s' % host, logger.DEBUG)

        # if we're doing per-show
        if show_name:
            self._log(u'Updating library via HTTP method for show %s' % show_name, logger.DEBUG)

            path_sql = 'SELECT path.strPath FROM path, tvshow, tvshowlinkpath WHERE ' \
                       'tvshow.c00 = "%s"' % show_name \
                       + ' AND tvshowlinkpath.idShow = tvshow.idShow AND tvshowlinkpath.idPath = path.idPath'

            # set xml response format, if this fails then don't bother with the rest
            if not self._send_to_kodi(
                host, {'command': 'SetResponseFormat(webheader;false;webfooter;false;header;<xml>;footer;</xml>;' +
                                  'opentag;<tag>;closetag;</tag>;closefinaltag;false)'}):
                return False

            # sql used to grab path(s)
            response = self._send_to_kodi(host, {'command': 'QueryVideoDatabase(%s)' % path_sql})
            if not response:
                self._log(u'Invalid response for %s on %s' % (show_name, host), logger.DEBUG)
                return False

            try:
                et = etree.fromstring(urllib.quote(response, ':\\/<>'))
            except SyntaxError as e:
                self._log(u'Unable to parse XML in response: %s' % ex(e), logger.ERROR)
                return False

            paths = et.findall('.//field')
            if not paths:
                self._log(u'No valid path found for %s on %s' % (show_name, host), logger.DEBUG)
                return False

            for path in paths:
                # we do not need it double-encoded, gawd this is dumb
                un_enc_path = urllib.unquote(path.text).decode(sickbeard.SYS_ENCODING)
                self._log(u'Updating %s on %s at %s' % (show_name, host, un_enc_path), logger.DEBUG)

                if not self._send_to_kodi(
                        host, {'command': 'ExecBuiltIn', 'parameter': 'Kodi.updatelibrary(video, %s)' % un_enc_path}):
                    self._log(u'Update of show directory failed for %s on %s at %s'
                              % (show_name, host, un_enc_path), logger.ERROR)
                    return False

                # sleep for a few seconds just to be sure kodi has a chance to finish each directory
                if 1 < len(paths):
                    time.sleep(5)
        # do a full update if requested
        else:
            self._log(u'Full library update on host: %s' % host, logger.DEBUG)

            if not self._send_to_kodi(host, {'command': 'ExecBuiltIn', 'parameter': 'Kodi.updatelibrary(video)'}):
                self._log(u'Failed full library update on: %s' % host, logger.ERROR)
                return False

        return True

    ##############################################################################
    # JSON-RPC API (Kodi 12+) methods
    ##############################################################################

    def _send_to_kodi_json(self, host, command, timeout=30):
        """ Handle communication to Kodi installations via JSONRPC

        Args:
            command: Kodi JSON-RPC command to send via HTTP

        Return:
            response.result dict for successful commands or empty dict if there was an error
        """

        result = {}
        if not host:
            self._log(u'No host specified, aborting update', logger.WARNING)
            return result

        if isinstance(command, dict):
            command.setdefault('jsonrpc', '2.0')
            command.setdefault('id', 'SickGear')
            args = dict(post_json=command)
        else:
            args = dict(data=command)

        if not sickbeard.KODI_ALWAYS_ON and not self.test_mode:
            args['mute_connect_err'] = True

        if self.password or sickbeard.KODI_PASSWORD:
            args['auth'] = (self.username or sickbeard.KODI_USERNAME, self.password or sickbeard.KODI_PASSWORD)

        response = sickbeard.helpers.getURL(url='http://%s/jsonrpc' % host, timeout=timeout,
                                            headers={'Content-type': 'application/json'}, json=True,
                                            hooks=dict(response=self.cb_response), **args)
        if response:
            if not response.get('error'):
                return 'OK' == response.get('result') and {'OK': True} or response.get('result')

            self._log(u'API error; %s from %s in response to command: %s'
                      % (json.dumps(response['error']), host, json.dumps(command)), logger.ERROR)
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
            self._log(u'No host specified, aborting update', logger.WARNING)
            return False

        # if we're doing per-show
        if show_name:
            self._log(u'JSON library update. Host: %s Show: %s' % (host, show_name), logger.DEBUG)

            # try fetching tvshowid using show_name with a fallback to getting show list
            show_name = urllib.unquote_plus(show_name)
            commands = [dict(method='VideoLibrary.GetTVShows',
                             params={'filter': {'field': 'title', 'operator': 'is', 'value': '%s' % show_name},
                                     'properties': ['title']}),
                        dict(method='VideoLibrary.GetTVShows')]

            shows = None
            for command in commands:
                response = self._send_to_kodi_json(host, command)
                shows = response.get('tvshows')
                if shows:
                    break

            if not shows:
                self._log(u'No items in GetTVShows response', logger.DEBUG)
                return False

            tvshowid = -1
            path = ''
            for show in shows:
                if show_name == show.get('title') or show_name == show.get('label'):
                    tvshowid = show.get('tvshowid', -1)
                    path = show.get('file', '')
                    break
            del shows

            # we didn't find the show (exact match), thus revert to just doing a full update if enabled
            if -1 == tvshowid:
                self._log(u'Doesn\'t have "%s" in it\'s known shows, full library update required' % show_name,
                          logger.DEBUG)
                return False

            # lookup tv-show path if we don't already know it
            if not len(path):
                command = dict(method='VideoLibrary.GetTVShowDetails',
                               params={'tvshowid': tvshowid, 'properties': ['file']})
                response = self._send_to_kodi_json(host, command)
                path = 'tvshowdetails' in response and response['tvshowdetails'].get('file', '') or ''

            if not len(path):
                self._log(u'No valid path found for %s with ID: %s on %s' % (show_name, tvshowid, host), logger.WARNING)
                return False

            self._log(u'Updating %s on %s at %s' % (show_name, host, path), logger.DEBUG)
            command = dict(method='VideoLibrary.Scan', params={'directory': '%s' % json.dumps(path)[1:-1]})
            response_scan = self._send_to_kodi_json(host, command)
            if not response_scan.get('OK'):
                self._log(u'Update of show directory failed for %s on %s at %s response: %s' %
                          (show_name, host, path, response_scan), logger.ERROR)
                return False

        # do a full update if requested
        else:
            self._log(u'Full library update on host: %s' % host, logger.DEBUG)
            response_scan = self._send_to_kodi_json(host, dict(method='VideoLibrary.Scan'))
            if not response_scan.get('OK'):
                self._log(u'Failed full library update on: %s response: %s' % (host, response_scan), logger.ERROR)
                return False

        return True

    ##############################################################################
    # Public functions which will call the JSON or Legacy HTTP API methods
    ##############################################################################

    def notify_snatch(self, ep_name):

        if sickbeard.KODI_NOTIFY_ONSNATCH:
            self._notify_kodi(ep_name, common.notifyStrings[common.NOTIFY_SNATCH])

    def notify_download(self, ep_name):

        if sickbeard.KODI_NOTIFY_ONDOWNLOAD:
            self._notify_kodi(ep_name, common.notifyStrings[common.NOTIFY_DOWNLOAD])

    def notify_subtitle_download(self, ep_name, lang):

        if sickbeard.KODI_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notify_kodi('%s: %s' % (ep_name, lang), common.notifyStrings[common.NOTIFY_SUBTITLE_DOWNLOAD])

    def notify_git_update(self, new_version='??'):

        if sickbeard.USE_KODI:
            update_text = common.notifyStrings[common.NOTIFY_GIT_UPDATE_TEXT]
            title = common.notifyStrings[common.NOTIFY_GIT_UPDATE]
            self._notify_kodi('%s %s' % (update_text, new_version), title)

    def test_notify(self, host, username, password):

        self.test_mode, self.username, self.password = True, username, password
        result = self._notify_kodi('Testing SickGear Kodi notifier', 'Test Notification', kodi_hosts=host)
        self.test_mode = False
        return result

    def update_library(self, showName=None, force=False):
        """ Wrapper for the update library functions

        :param showName: Name of a TV show
        :param force: True force update process

        Returns: None if no processing done, True if processing succeeded with no issues else False if any issues found
        """
        if sickbeard.USE_KODI and (sickbeard.KODI_UPDATE_LIBRARY or force):
            return self._update_library(showName)


notifier = KodiNotifier
