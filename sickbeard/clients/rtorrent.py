# Author: jkaberg <joel.kaberg@gmail.com>, based on fuzemans work (https://github.com/RuudBurger/CouchPotatoServer/blob/develop/couchpotato/core/downloaders/rtorrent/main.py)
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import xmlrpclib
import sickbeard
from sickbeard import helpers
from sickbeard.clients.generic import GenericClient
from lib.rtorrent import RTorrent


class RtorrentAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        if host and host.startswith('scgi:'):
            username = password = None

        super(RtorrentAPI, self).__init__('rTorrent', host, username, password)

        # self.url = self.host

    def _get_auth(self):

        self.auth = None
        if self.host:
            try:
                if self.host and self.host.startswith('scgi:'):
                    self.username = self.password = None
                self.auth = RTorrent(self.host, self.username, self.password, True)
            except (AssertionError, xmlrpclib.ProtocolError) as e:
                pass

        return self.auth

    def _add_torrent(self, cmd, **kwargs):
        torrent = None

        if self.auth:
            try:
                # Send magnet to rTorrent
                if 'file' == cmd:
                    torrent = self.auth.load_torrent(kwargs['file'])
                elif 'magnet' == cmd:
                    torrent = self.auth.load_magnet(kwargs['uri'], kwargs['btih'])

                if torrent:

                    if sickbeard.TORRENT_LABEL:
                        torrent.set_custom(1, sickbeard.TORRENT_LABEL)

                    if sickbeard.TORRENT_PATH:
                        torrent.set_directory(sickbeard.TORRENT_PATH)

                    torrent.start()

            except (StandardError, Exception) as e:
                pass

        return any([torrent])

    def _add_torrent_file(self, result):

        if result:
            return self._add_torrent('file', file=result.content)
        return False

    def _add_torrent_uri(self, result):

        if result:
            return self._add_torrent('magnet', uri=result.url, btih=result.hash)
        return False

    #def _set_torrent_ratio(self, name):

        # if not name:
        # return False
        #
        # if not self.auth:
        # return False
        #
        # views = self.auth.get_views()
        #
        # if name not in views:
        # self.auth.create_group(name)

        # group = self.auth.get_group(name)

        # ratio = int(float(sickbeard.TORRENT_RATIO) * 100)
        #
        # try:
        # if ratio > 0:
        #
        # # Explicitly set all group options to ensure it is setup correctly
        # group.set_upload('1M')
        # group.set_min(ratio)
        # group.set_max(ratio)
        # group.set_command('d.stop')
        # group.enable()
        # else:
        # # Reset group action and disable it
        # group.set_command()
        # group.disable()
        #
        # except:
        # return False

    #    return True

    def test_authentication(self):
        try:
            self._get_auth()

            if None is self.auth:
                return False, 'Error: Unable to get %s authentication, check your config!' % self.name
            return True, 'Success: Connected and Authenticated'

        except (StandardError, Exception):
            return False, 'Error: Unable to connect to %s' % self.name


api = RtorrentAPI()
