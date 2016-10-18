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

import sickbeard

from sickbeard import common, logger
from sickbeard.exceptions import ex
from sickbeard.encodingKludge import fixStupidEncodings

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import elementtree.ElementTree as etree


class PLEXNotifier:

    def __init__(self):

        self.name = 'PLEX'

    def log(self, msg, level=logger.MESSAGE):

        logger.log(u'%s: %s' % (self.name, msg), level)

    def _send_to_plex(self, command, host, username=None, password=None):
        """Handles communication to Plex hosts via HTTP API

        Args:
            command: Dictionary of field/data pairs, encoded via urllib and passed to the legacy xbmcCmds HTTP API
            host: Plex host:port
            username: Plex API username
            password: Plex API password

        Returns:
            Returns 'OK' for successful commands or False if there was an error

        """

        # fill in omitted parameters
        if not username:
            username = sickbeard.PLEX_USERNAME
        if not password:
            password = sickbeard.PLEX_PASSWORD

        if not host:
            self.log(u'No host specified, check your settings', logger.ERROR)
            return False

        for key in command:
            if type(command[key]) == unicode:
                command[key] = command[key].encode('utf-8')

        enc_command = urllib.urlencode(command)
        self.log(u'Encoded API command: ' + enc_command, logger.DEBUG)

        url = 'http://%s/xbmcCmds/xbmcHttp/?%s' % (host, enc_command)
        try:
            req = urllib2.Request(url)
            # if we have a password, use authentication
            if password:
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = 'Basic %s' % base64string
                req.add_header('Authorization', authheader)
                self.log(u'Contacting (with auth header) via url: ' + url, logger.DEBUG)
            else:
                self.log(u'Contacting via url: ' + url, logger.DEBUG)

            response = urllib2.urlopen(req)

            result = response.read().decode(sickbeard.SYS_ENCODING)
            response.close()

            self.log(u'HTTP response: ' + result.replace('\n', ''), logger.DEBUG)
            # could return result response = re.compile('<html><li>(.+\w)</html>').findall(result)
            return 'OK'

        except (urllib2.URLError, IOError) as e:
            self.log(u'Couldn\'t contact Plex at ' + fixStupidEncodings(url) + ' ' + ex(e), logger.WARNING)
            return False

    def _notify_pmc(self, message, title='SickGear', host=None, username=None, password=None, force=False):
        """Internal wrapper for the notify_snatch and notify_download functions

        Args:
            message: Message body of the notice to send
            title: Title of the notice to send
            host: Plex Media Client(s) host:port
            username: Plex username
            password: Plex password
            force: Used for the Test method to override config safety checks

        Returns:
            Returns a list results in the format of host:ip:result
            The result will either be 'OK' or False, this is used to be parsed by the calling function.

        """

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not sickbeard.USE_PLEX and not force:
            return False

        # fill in omitted parameters
        if not host:
            host = sickbeard.PLEX_HOST
        if not username:
            username = sickbeard.PLEX_USERNAME
        if not password:
            password = sickbeard.PLEX_PASSWORD

        result = ''
        for curHost in [x.strip() for x in host.split(',')]:
            self.log(u'Sending notification to \'%s\' - %s' % (curHost, message))

            command = {'command': 'ExecBuiltIn',
                       'parameter': 'Notification(%s,%s)' % (title.encode('utf-8'), message.encode('utf-8'))}
            notify_result = self._send_to_plex(command, curHost, username, password)
            if notify_result:
                result += '%s:%s' % (curHost, str(notify_result))

        return result

##############################################################################
# Public functions
##############################################################################

    def notify_snatch(self, ep_name):
        if sickbeard.PLEX_NOTIFY_ONSNATCH:
            self._notify_pmc(ep_name, common.notifyStrings[common.NOTIFY_SNATCH])

    def notify_download(self, ep_name):
        if sickbeard.PLEX_NOTIFY_ONDOWNLOAD:
            self._notify_pmc(ep_name, common.notifyStrings[common.NOTIFY_DOWNLOAD])

    def notify_subtitle_download(self, ep_name, lang):
        if sickbeard.PLEX_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notify_pmc(ep_name + ': ' + lang, common.notifyStrings[common.NOTIFY_SUBTITLE_DOWNLOAD])

    def notify_git_update(self, new_version='??'):
        if sickbeard.USE_PLEX:
            update_text = common.notifyStrings[common.NOTIFY_GIT_UPDATE_TEXT]
            title = common.notifyStrings[common.NOTIFY_GIT_UPDATE]
            self._notify_pmc(update_text + new_version, title)

    def test_notify(self, host, username, password, server=False):
        if server:
            return self.update_library(host=host, username=username, password=password, force=False, test=True)
        return self._notify_pmc(
            'This is a test notification from SickGear', 'Test', host, username, password, force=True)

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

    def update_library(self, ep_obj=None, host=None, username=None, password=None, force=True, test=False):
        """Handles updating the Plex Media Server host via HTTP API

        Plex Media Server currently only supports updating the whole video library and not a specific path.

        Returns:
            Returns None for no issue, else a string of host with connection issues

        """

        if sickbeard.USE_PLEX and sickbeard.PLEX_UPDATE_LIBRARY or test:

            if not sickbeard.PLEX_SERVER_HOST and not any([host]):
                msg = u'No Plex Media Server host specified, check your settings'
                self.log(msg, logger.DEBUG)
                return '%sFail: %s' % (('', '<br />')[test], msg)

            if not host:
                host = sickbeard.PLEX_SERVER_HOST
            if not username:
                username = sickbeard.PLEX_USERNAME
            if not password:
                password = sickbeard.PLEX_PASSWORD

            # if username and password were provided, fetch the auth token from plex.tv
            token_arg = None
            if username and password:

                self.log(u'fetching plex.tv credentials for user: ' + username, logger.DEBUG)
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
                    auth_tree = etree.parse(response)
                    token = auth_tree.findall('.//authentication-token')[0].text
                    token_arg = '?X-Plex-Token=' + token

                except urllib2.URLError as e:
                    self.log(u'Error fetching credentials from plex.tv for user %s: %s' % (username, ex(e)))

                except (ValueError, IndexError) as e:
                    self.log(u'Error parsing plex.tv response: ' + ex(e))

            file_location = '' if None is ep_obj else ep_obj.location
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
                    self.log(u'Plex Media Server not running on: ' + cur_host)
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

            if not test:
                hosts_try = (hosts_all.copy(), hosts_match.copy())[any(hosts_match)]
                host_list = []
                for section_key, cur_host in hosts_try.items():
                    refresh_result = None
                    if force:
                        refresh_result = sickbeard.helpers.getURL(
                            '%s/library/sections/%s/refresh%s' % (cur_host, section_key, token_arg or ''))
                    if (force and '' == refresh_result) or not force:
                        host_list.append(cur_host)
                    else:
                        hosts_failed.append(cur_host)
                        self.log(u'Error updating library section for Plex Media Server: %s' % cur_host, logger.ERROR)

                if len(hosts_failed) == len(host_validate):
                    self.log(u'No successful Plex host updated')
                    return 'Fail no successful Plex host updated: %s' % ', '.join(host for host in hosts_failed)
                else:
                    hosts = ', '.join(set(host_list))
                    if len(hosts_match):
                        self.log(u'Hosts updating where TV section paths match the downloaded show: %s' % hosts)
                    else:
                        self.log(u'Updating all hosts with TV sections: %s' % hosts)
                    return ''

            hosts = [
                host.replace('http://', '') for host in filter(lambda x: x.startswith('http:'), hosts_all.values())]
            secured = [
                host.replace('https://', '') for host in filter(lambda x: x.startswith('https:'), hosts_all.values())]
            failed = [
                host.replace('http://', '') for host in filter(lambda x: x.startswith('http:'), hosts_failed)]
            failed_secured = ', '.join(filter(
                lambda x: x not in hosts,
                [host.replace('https://', '') for host in filter(lambda x: x.startswith('https:'), hosts_failed)]))
            return '<br />' + '<br />'.join(result for result in [
                ('', 'Fail: username/password when fetching credentials from plex.tv')[False is token_arg],
                ('', 'OK (secure connect): %s' % ', '.join(secured))[any(secured)],
                ('', 'OK%s: %s' % ((' (legacy connect)', '')[None is token_arg], ', '.join(hosts)))[any(hosts)],
                ('', 'Fail (secure connect): %s' % failed_secured)[any(failed_secured)],
                ('', 'Fail%s: %s' % ((' (legacy connect)', '')[None is token_arg], failed))[any(failed)]] if result)

notifier = PLEXNotifier
