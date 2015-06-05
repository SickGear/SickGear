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
import socket
import base64
import time

import sickbeard

from sickbeard import logger
from sickbeard import common
from sickbeard.exceptions import ex
from sickbeard.encodingKludge import fixStupidEncodings

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

try:
    import json
except ImportError:
    from lib import simplejson as json


class KODINotifier:
    sg_logo_url = 'https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/ico/apple-touch-icon-precomposed.png'

    def _notify_kodi(self, message, title='SickGear', host=None, username=None, password=None, force=False):

        # fill in omitted parameters
        if not host:
            host = sickbeard.KODI_HOST
        if not username:
            username = sickbeard.KODI_USERNAME
        if not password:
            password = sickbeard.KODI_PASSWORD

        # suppress notifications if the notifier is disabled but the notify options are checked
        if not sickbeard.USE_KODI and not force:
            logger.log(u'KODI: Notifications are not enabled, skipping this notification', logger.DEBUG)
            return False

        result = ''
        for curHost in [x.strip() for x in host.split(',')]:
            logger.log(u'KODI: Sending Kodi notification to \'%s\' - %s' % (curHost, message), logger.MESSAGE)

            command = '{"jsonrpc":"2.0","method":"GUI.ShowNotification","params":{"title":"%s","message":"%s", "image": "%s"},"id":1}' % (title.encode('utf-8'), message.encode('utf-8'), self.sg_logo_url)
            notifyResult = self._send_to_kodi(command, curHost, username, password)
            if notifyResult:
                result += curHost + ':' + notifyResult['result'].decode(sickbeard.SYS_ENCODING)
            else:
                if sickbeard.KODI_ALWAYS_ON or force:
                    result += curHost + ':False'

        return result

    def _send_to_kodi(self, command, host=None, username=None, password=None):

        # fill in omitted parameters
        if not username:
            username = sickbeard.KODI_USERNAME
        if not password:
            password = sickbeard.KODI_PASSWORD

        if not host:
            logger.log(u'KODI: No host specified, check your settings', logger.ERROR)
            return False

        command = command.encode('utf-8')
        logger.log(u'KODI: JSON command: ' + command, logger.DEBUG)

        url = 'http://%s/jsonrpc' % (host)
        try:
            req = urllib2.Request(url, command)
            req.add_header('Content-type', 'application/json')
            # if we have a password, use authentication
            if password:
                base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
                authheader = 'Basic %s' % base64string
                req.add_header('Authorization', authheader)
                logger.log(u'KODI: Contacting (with auth header) via url: ' + fixStupidEncodings(url), logger.DEBUG)
            else:
                logger.log(u'KODI: Contacting via url: ' + fixStupidEncodings(url), logger.DEBUG)

            try:
                response = urllib2.urlopen(req)
            except urllib2.URLError as e:
                logger.log(u'KODI: Warning: Couldn\'t contact Kodi at ' + host + '- ' + ex(e), logger.WARNING)
                return False

            # parse the json result
            try:
                result = json.load(response)
                response.close()
                logger.log(u'KODI: JSON response: ' + str(result), logger.DEBUG)
                return result  # need to return response for parsing
            except ValueError as e:
                logger.log(u'KODI: Unable to decode JSON response: ' + response, logger.WARNING)
                return False

        except IOError as e:
            logger.log(u'KODI: Warning: Couldn\'t contact Kodi at ' + host + ' - ' + ex(e), logger.WARNING)
            return False

    def _update_library(self, host=None, showName=None):

        if not host:
            logger.log(u'KODI: No host specified, check your settings', logger.DEBUG)
            return False

        logger.log(u'KODI: Updating library on host: ' + host, logger.MESSAGE)

        # if we're doing per-show
        if showName:
            tvshowid = -1
            logger.log(u'KODI: Updating library for show ' + showName, logger.DEBUG)

            # get tvshowid by showName
            showsCommand = '{"jsonrpc":"2.0","method":"VideoLibrary.GetTVShows","id":1}'
            showsResponse = self._send_to_kodi(showsCommand, host)

            if showsResponse and 'result' in showsResponse and 'tvshows' in showsResponse['result']:
                shows = showsResponse['result']['tvshows']
            else:
                logger.log(u'KODI: No TV shows in Kodi TV show list', logger.DEBUG)
                return False

            for show in shows:
                if (show['label'] == showName):
                    tvshowid = show['tvshowid']
                    break  # exit out of loop otherwise the label and showname will not match up

            # this can be big, so free some memory
            del shows

            # we didn't find the show (exact match), thus revert to just doing a full update if enabled
            if (tvshowid == -1):
                logger.log(u'KODI: Exact show name not matched in KODI TV show list', logger.DEBUG)
                return False

            # lookup tv-show path
            pathCommand = '{"jsonrpc":"2.0","method":"VideoLibrary.GetTVShowDetails","params":{"tvshowid":%d, "properties": ["file"]},"id":1}' % (tvshowid)
            pathResponse = self._send_to_kodi(pathCommand, host)

            path = pathResponse['result']['tvshowdetails']['file']
            logger.log(u'KODI: Received Show: ' + showName + ' with ID: ' + str(tvshowid) + ' Path: ' + path, logger.DEBUG)

            if (len(path) < 1):
                logger.log(u'KODI: No valid path found for ' + showName + ' with ID: ' + str(tvshowid) + ' on ' + host, logger.WARNING)
                return False

            logger.log(u'KODI: Updating ' + showName + ' on ' + host + ' at ' + path, logger.DEBUG)
            updateCommand = '{"jsonrpc":"2.0","method":"VideoLibrary.Scan","params":{"directory":%s},"id":1}' % (json.dumps(path))
            request = self._send_to_kodi(updateCommand, host)
            if not request:
                logger.log(u'KODI: Update of show directory failed on ' + showName + ' on ' + host + ' at ' + path, logger.ERROR)
                return False

            # catch if there was an error in the returned request
            for r in request:
                if 'error' in r:
                    logger.log(u'KODI: Error while attempting to update show directory for ' + showName + ' on ' + host + ' at ' + path, logger.ERROR)
                    return False

        # do a full update if requested
        else:
            logger.log(u'KODI: Performing full library update on host: ' + host, logger.DEBUG)
            updateCommand = '{"jsonrpc":"2.0","method":"VideoLibrary.Scan","id":1}'
            request = self._send_to_kodi(updateCommand, host, sickbeard.KODI_USERNAME, sickbeard.KODI_PASSWORD)

            if not request:
                logger.log(u'KODI: Full library update failed on host: ' + host, logger.ERROR)
                return False

        return True

    def notify_snatch(self, ep_name):
        if sickbeard.KODI_NOTIFY_ONSNATCH:
            self._notify_kodi(ep_name, common.notifyStrings[common.NOTIFY_SNATCH])

    def notify_download(self, ep_name):
        if sickbeard.KODI_NOTIFY_ONDOWNLOAD:
            self._notify_kodi(ep_name, common.notifyStrings[common.NOTIFY_DOWNLOAD])

    def notify_subtitle_download(self, ep_name, lang):
        if sickbeard.KODI_NOTIFY_ONSUBTITLEDOWNLOAD:
            self._notify_kodi(ep_name + ': ' + lang, common.notifyStrings[common.NOTIFY_SUBTITLE_DOWNLOAD])
            
    def notify_git_update(self, new_version = '??'):
        if sickbeard.USE_KODI:
            update_text=common.notifyStrings[common.NOTIFY_GIT_UPDATE_TEXT]
            title=common.notifyStrings[common.NOTIFY_GIT_UPDATE]
            self._notify_kodi(update_text + new_version, title)

    def test_notify(self, host, username, password):
        return self._notify_kodi('Testing Kodi notifications from SickGear', 'Test', host, username, password, force=True)

    def update_library(self, showName=None):

        if sickbeard.USE_KODI and sickbeard.KODI_UPDATE_LIBRARY:
            if not sickbeard.KODI_HOST:
                logger.log(u'KODI: No host specified, check your settings', logger.DEBUG)
                return False

            # either update each host, or only attempt to update first only
            result = 0
            for host in [x.strip() for x in sickbeard.KODI_HOST.split(',')]:
                if self._update_library(host, showName):
                    if sickbeard.KODI_UPDATE_ONLYFIRST:
                        logger.log(u'KODI: Update first host successful on host ' + host + ', stopped sending library update commands', logger.DEBUG)
                        return True
                else:
                    if sickbeard.KODI_ALWAYS_ON:
                        result = result + 1

            # needed for the 'update kodi' submenu command
            # as it only cares of the final result vs the individual ones
            if result == 0:
                return True
            else:
                return False

notifier = KODINotifier
