# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

import base64

try:
    import json
except ImportError:
    from lib import simplejson as json
import socket
import time
import urllib
import urllib2
import xml.etree.cElementTree as XmlEtree

import sickbeard
from sickbeard.exceptions import ex
from sickbeard.encodingKludge import fixStupidEncodings
from sickbeard.notifiers.generic import Notifier


class XBMCNotifier(Notifier):

    def __init__(self):
        super(XBMCNotifier, self).__init__()

        self.sg_logo_file = 'apple-touch-icon-72x72.png'

    def _get_xbmc_version(self, host, username, password):
        """Returns XBMC JSON-RPC API version (odd # = dev, even # = stable)

        Sends a request to the XBMC host using the JSON-RPC to determine if
        the legacy API or if the JSON-RPC API functions should be used.

        Fallback to testing legacy HTTPAPI before assuming it is just a badly configured host.

        Args:
            host: XBMC webserver host:port
            username: XBMC webserver username
            password: XBMC webserver password

        Returns:
            Returns API number or False

            List of possible known values:
                API | XBMC Version
               -----+---------------
                 2  | v10 (Dharma)
                 3  | (pre Eden)
                 4  | v11 (Eden)
                 5  | (pre Frodo)
                 6  | v12 (Frodo) / v13 (Gotham)

        """

        # since we need to maintain python 2.5 compatability we can not pass a timeout delay
        # to urllib2 directly (python 2.6+) override socket timeout to reduce delay for this call alone
        socket.setdefaulttimeout(10)

        check_command = '{"jsonrpc":"2.0","method":"JSONRPC.Version","id":1}'
        result = self._send_to_xbmc_json(check_command, host, username, password)

        # revert back to default socket timeout
        socket.setdefaulttimeout(sickbeard.SOCKET_TIMEOUT)

        if result:
            return result['result']['version']
        else:
            # fallback to legacy HTTPAPI method
            test_command = {'command': 'Help'}
            request = self._send_to_xbmc(test_command, host, username, password)
            if request:
                # return a fake version number, so it uses the legacy method
                return 1
            else:
                return False

    def _send_update_library(self, host, show_name=None):
        """Internal wrapper for the update library function to branch the logic for JSON-RPC or legacy HTTP API

        Checks the XBMC API version to branch the logic
        to call either the legacy HTTP API or the newer JSON-RPC over HTTP methods.

        Args:
            host: XBMC webserver host:port
            show_name: Name of a TV show to specifically target the library update for

        Returns:
            Returns True or False, if the update was successful

        """

        self._log(u'Sending request to update library for host: "%s"' % host)

        xbmcapi = self._get_xbmc_version(host, sickbeard.XBMC_USERNAME, sickbeard.XBMC_PASSWORD)
        if xbmcapi:
            if 4 >= xbmcapi:
                # try to update for just the show, if it fails, do full update if enabled
                if not self._update_library_http(host, show_name) and sickbeard.XBMC_UPDATE_FULL:
                    self._log_warning(u'Single show update failed, falling back to full update')
                    return self._update_library_http(host)
                else:
                    return True
            else:
                # try to update for just the show, if it fails, do full update if enabled
                if not self._update_library_json(host, show_name) and sickbeard.XBMC_UPDATE_FULL:
                    self._log_warning(u'Single show update failed, falling back to full update')
                    return self._update_library_json(host)
                else:
                    return True

        self._log_debug(u'Failed to detect version for "%s", check configuration and try again' % host)
        return False

    # #############################################################################
    # Legacy HTTP API (pre XBMC 12) methods
    ##############################################################################

    def _send_to_xbmc(self, command, host=None, username=None, password=None):
        """Handles communication to XBMC servers via HTTP API

        Args:
            command: Dictionary of field/data pairs, encoded via urllib and passed to the XBMC API via HTTP
            host: XBMC webserver host:port
            username: XBMC webserver username
            password: XBMC webserver password

        Returns:
            Returns response.result for successful commands or False if there was an error

        """
        if not host:
            self._log_debug(u'No host passed, aborting update')
            return False

        username = self._choose(username, sickbeard.XBMC_USERNAME)
        password = self._choose(password, sickbeard.XBMC_PASSWORD)

        for key in command:
            if type(command[key]) == unicode:
                command[key] = command[key].encode('utf-8')

        enc_command = urllib.urlencode(command)
        self._log_debug(u'Encoded API command: ' + enc_command)

        url = 'http://%s/xbmcCmds/xbmcHttp/?%s' % (host, enc_command)
        try:
            req = urllib2.Request(url)
            # if we have a password, use authentication
            if password:
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = 'Basic %s' % base64string
                req.add_header('Authorization', authheader)
                self._log_debug(u'Contacting (with auth header) via url: ' + fixStupidEncodings(url))
            else:
                self._log_debug(u'Contacting via url: ' + fixStupidEncodings(url))

            response = urllib2.urlopen(req)
            result = response.read().decode(sickbeard.SYS_ENCODING)
            response.close()

            self._log_debug(u'HTTP response: ' + result.replace('\n', ''))
            return result

        except (urllib2.URLError, IOError) as e:
            self._log_warning(u'Couldn\'t contact HTTP at %s %s' % (fixStupidEncodings(url), ex(e)))
            return False

    def _update_library_http(self, host=None, show_name=None):
        """Handles updating XBMC host via HTTP API

        Attempts to update the XBMC video library for a specific tv show if passed,
        otherwise update the whole library if enabled.

        Args:
            host: XBMC webserver host:port
            show_name: Name of a TV show to specifically target the library update for

        Returns:
            Returns True or False

        """

        if not host:
            self._log_debug(u'No host passed, aborting update')
            return False

        self._log_debug(u'Updating XMBC library via HTTP method for host: ' + host)

        # if we're doing per-show
        if show_name:
            self._log_debug(u'Updating library via HTTP method for show ' + show_name)

            # noinspection SqlResolve
            path_sql = 'select path.strPath' \
                       ' from path, tvshow, tvshowlinkpath' \
                       ' where tvshow.c00 = "%s"' \
                       ' and tvshowlinkpath.idShow = tvshow.idShow' \
                       ' and tvshowlinkpath.idPath = path.idPath' % show_name

            # use this to get xml back for the path lookups
            xml_command = dict(command='SetResponseFormat(webheader;false;webfooter;false;header;<xml>;footer;</xml>;'
                                       'opentag;<tag>;closetag;</tag>;closefinaltag;false)')
            # sql used to grab path(s)
            sql_command = dict(command='QueryVideoDatabase(%s)' % path_sql)
            # set output back to default
            reset_command = dict(command='SetResponseFormat()')

            # set xml response format, if this fails then don't bother with the rest
            request = self._send_to_xbmc(xml_command, host)
            if not request:
                return False

            sql_xml = self._send_to_xbmc(sql_command, host)
            self._send_to_xbmc(reset_command, host)

            if not sql_xml:
                self._log_debug(u'Invalid response for ' + show_name + ' on ' + host)
                return False

            enc_sql_xml = urllib.quote(sql_xml, ':\\/<>')
            try:
                et = XmlEtree.fromstring(enc_sql_xml)
            except SyntaxError as e:
                self._log_error(u'Unable to parse XML response: ' + ex(e))
                return False

            paths = et.findall('.//field')

            if not paths:
                self._log_debug(u'No valid paths found for ' + show_name + ' on ' + host)
                return False

            for path in paths:
                # we do not need it double-encoded, gawd this is dumb
                un_enc_path = urllib.unquote(path.text).decode(sickbeard.SYS_ENCODING)
                self._log_debug(u'Updating ' + show_name + ' on ' + host + ' at ' + un_enc_path)
                update_command = dict(command='ExecBuiltIn', parameter='XBMC.updatelibrary(video, %s)' % un_enc_path)
                request = self._send_to_xbmc(update_command, host)
                if not request:
                    self._log_error(u'Update of show directory failed on ' + show_name
                                    + ' on ' + host + ' at ' + un_enc_path)
                    return False
                # sleep for a few seconds just to be sure xbmc has a chance to finish each directory
                if len(paths) > 1:
                    time.sleep(5)
        # do a full update if requested
        else:
            self._log(u'Doing full library update on host: ' + host)
            update_command = {'command': 'ExecBuiltIn', 'parameter': 'XBMC.updatelibrary(video)'}
            request = self._send_to_xbmc(update_command, host)

            if not request:
                self._log_error(u'Full Library update failed on: ' + host)
                return False

        return True

    ##############################################################################
    # JSON-RPC API (XBMC 12+) methods
    ##############################################################################

    def _send_to_xbmc_json(self, command, host=None, username=None, password=None):
        """Handles communication to XBMC servers via JSONRPC

        Args:
            command: Dictionary of field/data pairs, encoded via urllib and passed to the XBMC JSON-RPC via HTTP
            host: XBMC webserver host:port
            username: XBMC webserver username
            password: XBMC webserver password

        Returns:
            Returns response.result for successful commands or False if there was an error

        """
        if not host:
            self._log_debug(u'No host passed, aborting update')
            return False

        username = self._choose(username, sickbeard.XBMC_USERNAME)
        password = self._choose(password, sickbeard.XBMC_PASSWORD)

        command = command.encode('utf-8')
        self._log_debug(u'JSON command: ' + command)

        url = 'http://%s/jsonrpc' % host
        try:
            req = urllib2.Request(url, command)
            req.add_header('Content-type', 'application/json')
            # if we have a password, use authentication
            if password:
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = 'Basic %s' % base64string
                req.add_header('Authorization', authheader)
                self._log_debug(u'Contacting (with auth header) via url: ' + fixStupidEncodings(url))
            else:
                self._log_debug(u'Contacting via url: ' + fixStupidEncodings(url))

            try:
                response = urllib2.urlopen(req)
            except urllib2.URLError as e:
                self._log_warning(u'Error while trying to retrieve API version for "%s": %s' % (host, ex(e)))
                return False

            # parse the json result
            try:
                result = json.load(response)
                response.close()
                self._log_debug(u'JSON response: ' + str(result))
                return result  # need to return response for parsing
            except ValueError:
                self._log_warning(u'Unable to decode JSON: ' + response)
                return False

        except IOError as e:
            self._log_warning(u'Couldn\'t contact JSON API at ' + fixStupidEncodings(url) + ' ' + ex(e))
            return False

    def _update_library_json(self, host=None, show_name=None):
        """Handles updating XBMC host via HTTP JSON-RPC

        Attempts to update the XBMC video library for a specific tv show if passed,
        otherwise update the whole library if enabled.

        Args:
            host: XBMC webserver host:port
            show_name: Name of a TV show to specifically target the library update for

        Returns:
            Returns True or False

        """

        if not host:
            self._log_debug(u'No host passed, aborting update')
            return False

        self._log(u'Updating XMBC library via JSON method for host: ' + host)

        # if we're doing per-show
        if show_name:
            tvshowid = -1
            self._log_debug(u'Updating library via JSON method for show ' + show_name)

            # get tvshowid by showName
            shows_command = '{"jsonrpc":"2.0","method":"VideoLibrary.GetTVShows","id":1}'
            shows_response = self._send_to_xbmc_json(shows_command, host)

            if shows_response and 'result' in shows_response and 'tvshows' in shows_response['result']:
                shows = shows_response['result']['tvshows']
            else:
                self._log_debug(u'No tvshows in TV show list')
                return False

            for show in shows:
                if show['label'] == show_name:
                    tvshowid = show['tvshowid']
                    break  # exit out of loop otherwise the label and showname will not match up

            # this can be big, so free some memory
            del shows

            # we didn't find the show (exact match), thus revert to just doing a full update if enabled
            if -1 == tvshowid:
                self._log_debug(u'Exact show name not matched in TV show list')
                return False

            # lookup tv-show path
            path_command = '{"jsonrpc":"2.0","method":"VideoLibrary.GetTVShowDetails",' \
                           '"params":{"tvshowid":%d, "properties": ["file"]},"id":1}' % tvshowid
            path_response = self._send_to_xbmc_json(path_command, host)

            path = path_response['result']['tvshowdetails']['file']
            self._log_debug(u'Received Show: ' + show_name + ' with ID: ' + str(tvshowid) + ' Path: ' + path)

            if 1 > len(path):
                self._log_warning(u'No valid path found for ' + show_name + ' with ID: '
                                  + str(tvshowid) + ' on ' + host)
                return False

            self._log_debug(u'Updating ' + show_name + ' on ' + host + ' at ' + path)
            update_command = '{"jsonrpc":"2.0","method":"VideoLibrary.Scan","params":{"directory":%s},"id":1}' % (
                json.dumps(path))
            request = self._send_to_xbmc_json(update_command, host)
            if not request:
                self._log_error(u'Update of show directory failed on ' + show_name + ' on ' + host + ' at ' + path)
                return False

            # catch if there was an error in the returned request
            # noinspection PyTypeChecker
            for r in request:
                if 'error' in r:
                    self._log_error(
                        u'Error while attempting to update show directory for ' + show_name
                        + ' on ' + host + ' at ' + path)
                    return False

        # do a full update if requested
        else:
            self._log(u'Doing Full Library update on host: ' + host)
            update_command = '{"jsonrpc":"2.0","method":"VideoLibrary.Scan","id":1}'
            request = self._send_to_xbmc_json(update_command, host, sickbeard.XBMC_USERNAME, sickbeard.XBMC_PASSWORD)

            if not request:
                self._log_error(u'Full Library update failed on: ' + host)
                return False

        return True

    def _notify(self, title, body, hosts=None, username=None, password=None, **kwargs):
        """Internal wrapper for the notify_snatch and notify_download functions

        Detects JSON-RPC version then branches the logic for either the JSON-RPC or legacy HTTP API methods.

        Args:
            title: Title of the notice to send
            body: Message body of the notice to send
            hosts: XBMC webserver host:port
            username: XBMC webserver username
            password: XBMC webserver password

        Returns:
            Returns a list results in the format of host:ip:result
            The result will either be 'OK' or False, this is used to be parsed by the calling function.

        """
        hosts = self._choose(hosts, sickbeard.XBMC_HOST)
        username = self._choose(username, sickbeard.XBMC_USERNAME)
        password = self._choose(password, sickbeard.XBMC_PASSWORD)

        success = False
        result = []
        for cur_host in [x.strip() for x in hosts.split(',')]:
            cur_host = urllib.unquote_plus(cur_host)

            self._log(u'Sending notification to "%s"' % cur_host)

            xbmcapi = self._get_xbmc_version(cur_host, username, password)
            if xbmcapi:
                if 4 >= xbmcapi:
                    self._log_debug(u'Detected version <= 11, using HTTP API')
                    command = dict(command='ExecBuiltIn',
                                   parameter='Notification(' + title.encode('utf-8') + ',' + body.encode('utf-8') + ')')
                    notify_result = self._send_to_xbmc(command, cur_host, username, password)
                    if notify_result:
                        result += [cur_host + ':' + str(notify_result)]
                        success |= 'OK' in notify_result or success
                else:
                    self._log_debug(u'Detected version >= 12, using JSON API')
                    command = '{"jsonrpc":"2.0","method":"GUI.ShowNotification",' \
                              '"params":{"title":"%s","message":"%s", "image": "%s"},"id":1}' % \
                              (title.encode('utf-8'), body.encode('utf-8'), self._sg_logo_url)
                    notify_result = self._send_to_xbmc_json(command, cur_host, username, password)
                    if notify_result.get('result'):
                        result += [cur_host + ':' + notify_result['result'].decode(sickbeard.SYS_ENCODING)]
                        success |= 'OK' in notify_result or success
            else:
                if sickbeard.XBMC_ALWAYS_ON or self._testing:
                    self._log_error(u'Failed to detect version for "%s", check configuration and try again' % cur_host)
                result += [cur_host + ':No response']
                success = False

        return self._choose(('Success, all hosts tested', '<br />\n'.join(result))[not bool(success)], bool(success))

    def update_library(self, show_name=None, **kwargs):
        """Public wrapper for the update library functions to branch the logic for JSON-RPC or legacy HTTP API

        Checks the XBMC API version to branch the logic to call either the legacy HTTP API
        or the newer JSON-RPC over HTTP methods.
        Do the ability of accepting a list of hosts delimited by comma, only one host is updated,
        the first to respond with success.
        This is a workaround for SQL backend users as updating multiple clients causes duplicate entries.
        Future plan is to revist how we store the host/ip/username/pw/options so that it may be more flexible.

        Args:
            show_name: Name of a TV show to specifically target the library update for

        Returns:
            Returns True or False

        """
        if not sickbeard.XBMC_HOST:
            self._log_debug(u'No hosts specified, check your settings')
            return False

        # either update each host, or only attempt to update until one successful result
        result = 0
        for host in [x.strip() for x in sickbeard.XBMC_HOST.split(',')]:
            if self._send_update_library(host, show_name):
                if sickbeard.XBMC_UPDATE_ONLYFIRST:
                    self._log_debug(u'Successfully updated "%s", stopped sending update library commands' % host)
                    return True
            else:
                if sickbeard.XBMC_ALWAYS_ON:
                    self._log_error(u'Failed to detect version for "%s", check configuration and try again' % host)
                result = result + 1

        # needed for the 'update xbmc' submenu command
        # as it only cares of the final result vs the individual ones
        if not 0 != result:
            return False
        return True


notifier = XBMCNotifier
