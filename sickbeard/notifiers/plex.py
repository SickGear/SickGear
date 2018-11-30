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

import urllib
import urllib2
import base64
import re
import xml.etree.cElementTree as XmlEtree

import sickbeard
from sickbeard.encodingKludge import fixStupidEncodings
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier


class PLEXNotifier(Notifier):

    def __init__(self):
        super(PLEXNotifier, self).__init__()

    def _send_to_plex(self, command, host, username=None, password=None):
        """Handles communication to Plex hosts via HTTP API

        Args:
            command: Dictionary of field/data pairs, encoded via urllib and passed to the legacy xbmcCmds HTTP API
            host: Plex host:port
            username: Plex API username
            password: Plex API password

        Returns:
            Returns True for successful commands or False if there was an error

        """
        if not host:
            self._log_error(u'No host specified, check your settings')
            return False

        for key in command:
            if type(command[key]) == unicode:
                command[key] = command[key].encode('utf-8')

        enc_command = urllib.urlencode(command)
        self._log_debug(u'Encoded API command: ' + enc_command)

        url = 'http://%s/xbmcCmds/xbmcHttp/?%s' % (host, enc_command)
        try:
            req = urllib2.Request(url)
            if password:
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = 'Basic %s' % base64string
                req.add_header('Authorization', authheader)
                self._log_debug(u'Contacting (with auth header) via url: ' + url)
            else:
                self._log_debug(u'Contacting via url: ' + url)

            response = urllib2.urlopen(req)
            result = response.read().decode(sickbeard.SYS_ENCODING)
            response.close()

            self._log_debug(u'HTTP response: ' + result.replace('\n', ''))
            return True

        except (urllib2.URLError, IOError) as e:
            self._log_warning(u'Couldn\'t contact Plex at ' + fixStupidEncodings(url) + ' ' + ex(e))
            return False

    @staticmethod
    def _get_host_list(host='', enable_secure=False):
        """
        Return a list of hosts from a host CSV string
        """
        host_list = []

        user_list = [x.strip().lower() for x in host.split(',')]
        for cur_host in user_list:
            if cur_host.startswith('https://'):
                host_list += ([], [cur_host])[enable_secure]
            else:
                host_list += ([], ['https://%s' % cur_host])[enable_secure] + ['http://%s' % cur_host]

        return host_list

    def _notify(self, title, body, host=None, username=None, password=None, **kwargs):
        """Internal wrapper for the notify_snatch and notify_download functions

        Args:
            title: Title of the notice to send
            body: Message body of the notice to send
            host: Plex Media Client(s) host:port
            username: Plex username
            password: Plex password

        Returns:
            Returns a test result string for ui output while testing, otherwise True if all tests are a success
        """
        host = self._choose(host, sickbeard.PLEX_HOST)
        username = self._choose(username, sickbeard.PLEX_USERNAME)
        password = self._choose(password, sickbeard.PLEX_PASSWORD)

        command = {'command': 'ExecBuiltIn',
                   'parameter': 'Notification(%s,%s)' % (title.encode('utf-8'), body.encode('utf-8'))}

        results = []
        for cur_host in [x.strip() for x in host.split(',')]:
            cur_host = urllib.unquote_plus(cur_host)
            self._log(u'Sending notification to \'%s\'' % cur_host)
            result = self._send_to_plex(command, cur_host, username, password)
            results += [self._choose(('%s Plex client ... %s' % (('Successful test notice sent to',
                                                                  'Failed test for')[not result], cur_host)), result)]

        return self._choose('<br>\n'.join(results), all(results))

    ##############################################################################
    # Public functions
    ##############################################################################

    def notify_git_update(self, new_version='??', **kwargs):
        # ensure PMS is setup, this is not for when clients are
        if sickbeard.PLEX_HOST:
            super(PLEXNotifier, self).notify_git_update(new_version, **kwargs)

    def test_update_library(self, host=None, username=None, password=None):
        self._testing = True
        result = self.update_library(host=urllib.unquote_plus(host), username=username, password=password)
        if '<br>' == result:
            result += 'Fail: No valid host set to connect with'
        return (('Test result for', 'Successful test of')['Fail' not in result]
                + ' Plex server(s) ... %s<br>\n' % result)

    def update_library(self, ep_obj=None, host=None, username=None, password=None, location=None, **kwargs):
        """Handles updating the Plex Media Server host via HTTP API

        Plex Media Server currently only supports updating the whole video library and not a specific path.

        Returns:
            Returns None for no issue, else a string of host with connection issues

        """
        host = self._choose(host, sickbeard.PLEX_SERVER_HOST)
        if not host:
            msg = u'No Plex Media Server host specified, check your settings'
            self._log_debug(msg)
            return '%sFail: %s' % (('', '<br>')[self._testing], msg)

        username = self._choose(username, sickbeard.PLEX_USERNAME)
        password = self._choose(password, sickbeard.PLEX_PASSWORD)

        # if username and password were provided, fetch the auth token from plex.tv
        token_arg = None
        if username and password:

            self._log_debug(u'Fetching plex.tv credentials for user: ' + username)
            req = urllib2.Request('https://plex.tv/users/sign_in.xml', data='')
            authheader = 'Basic %s' % base64.encodestring('%s:%s' % (username, password))[:-1]
            req.add_header('Authorization', authheader)
            req.add_header('X-Plex-Device-Name', 'SickGear')
            req.add_header('X-Plex-Product', 'SickGear Notifier')
            req.add_header('X-Plex-Client-Identifier', '5f48c063eaf379a565ff56c9bb2b401e')
            req.add_header('X-Plex-Version', '1.0')
            token_arg = False

            try:
                response = urllib2.urlopen(req)
                auth_tree = XmlEtree.parse(response)
                token = auth_tree.findall('.//authentication-token')[0].text
                token_arg = '?X-Plex-Token=' + token

            except urllib2.URLError as e:
                self._log(u'Error fetching credentials from plex.tv for user %s: %s' % (username, ex(e)))

            except (ValueError, IndexError) as e:
                self._log(u'Error parsing plex.tv response: ' + ex(e))

        file_location = location if None is not location else '' if None is ep_obj else ep_obj.location
        host_validate = self._get_host_list(host, all([token_arg]))
        hosts_all = {}
        hosts_match = {}
        hosts_failed = []
        for cur_host in host_validate:
            response = sickbeard.helpers.getURL(
                '%s/library/sections%s' % (cur_host, token_arg or ''), timeout=10,
                mute_connect_err=True, mute_read_timeout=True, mute_connect_timeout=True)
            if response:
                response = sickbeard.helpers.parse_xml(response)
            if not response:
                hosts_failed.append(cur_host)
                continue

            sections = response.findall('.//Directory')
            if not sections:
                self._log(u'Plex Media Server not running on: ' + cur_host)
                hosts_failed.append(cur_host)
                continue

            for section in filter(lambda x: 'show' == x.attrib['type'], sections):
                if str(section.attrib['key']) in hosts_all:
                    continue
                keyed_host = [(str(section.attrib['key']), cur_host)]
                hosts_all.update(keyed_host)
                if not file_location:
                    continue

                for section_location in section.findall('.//Location'):
                    section_path = re.sub(r'[/\\]+', '/', section_location.attrib['path'].lower())
                    section_path = re.sub(r'^(.{,2})[/\\]', '', section_path)
                    location_path = re.sub(r'[/\\]+', '/', file_location.lower())
                    location_path = re.sub(r'^(.{,2})[/\\]', '', location_path)

                    if section_path in location_path:
                        hosts_match.update(keyed_host)
                        break

        if not self._testing:
            hosts_try = (hosts_all.copy(), hosts_match.copy())[any(hosts_match)]
            host_list = []
            for section_key, cur_host in hosts_try.items():
                refresh_result = None
                if not self._testing:
                    refresh_result = sickbeard.helpers.getURL(
                        '%s/library/sections/%s/refresh%s' % (cur_host, section_key, token_arg or ''))
                if (not self._testing and '' == refresh_result) or self._testing:
                    host_list.append(cur_host)
                else:
                    hosts_failed.append(cur_host)
                    self._log_error(u'Error updating library section for Plex Media Server: %s' % cur_host)

            if len(hosts_failed) == len(host_validate):
                self._log(u'No successful Plex host updated')
                return 'Fail no successful Plex host updated: %s' % ', '.join(host for host in hosts_failed)
            else:
                hosts = ', '.join(set(host_list))
                if len(hosts_match):
                    self._log(u'Hosts updating where TV section paths match the downloaded show: %s' % hosts)
                else:
                    self._log(u'Updating all hosts with TV sections: %s' % hosts)
                return ''

        hosts = [
            host.replace('http://', '') for host in filter(lambda x: x.startswith('http:'), hosts_all.values())]
        secured = [
            host.replace('https://', '') for host in filter(lambda x: x.startswith('https:'), hosts_all.values())]
        failed = ', '.join([
            host.replace('http://', '') for host in filter(lambda x: x.startswith('http:'), hosts_failed)])
        failed_secured = ', '.join(filter(
            lambda x: x not in hosts,
            [host.replace('https://', '') for host in filter(lambda x: x.startswith('https:'), hosts_failed)]))
        return '<br>' + '<br>'.join(result for result in [
            ('', 'Fail: username/password when fetching credentials from plex.tv')[False is token_arg],
            ('', 'OK (secure connect): %s' % ', '.join(secured))[any(secured)],
            ('', 'OK%s: %s' % ((' (legacy connect)', '')[None is token_arg], ', '.join(hosts)))[any(hosts)],
            ('', 'Fail (secure connect): %s' % failed_secured)[any(failed_secured)],
            ('', 'Fail%s: %s' % ((' (legacy connect)', '')[None is token_arg], failed))[bool(failed)]] if result)


notifier = PLEXNotifier
