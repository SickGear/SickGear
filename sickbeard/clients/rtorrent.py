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

from lib.rtorrent.compat import xmlrpclib
from lib.rtorrent import RTorrent
from sickbeard import helpers, logger
from sickbeard.clients.generic import GenericClient
import sickbeard


class RtorrentAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        if host and host.startswith('scgi:'):
            username = password = None

        super(RtorrentAPI, self).__init__('rTorrent', host, username, password)

    def _get_auth(self):

        self.auth = None
        if self.host:
            try:
                if self.host.startswith('scgi:'):
                    self.username = self.password = None
                self.auth = RTorrent(self.host, self.username, self.password)
            except (AssertionError, xmlrpclib.ProtocolError):
                pass

        return self.auth

    def _add_torrent(self, cmd, data):
        torrent = None

        if self.auth:
            try:
                if self.auth.has_local_id(data.hash):
                    logger.log('%s: Item already exists %s' % (self.name, data.name), logger.WARNING)
                    raise

                params = {
                    'start': not sickbeard.TORRENT_PAUSED,
                    'extra': ([], ['d.set_custom1=%s' % sickbeard.TORRENT_LABEL])[any([sickbeard.TORRENT_LABEL])] +
                             ([], ['d.set_directory=%s' % sickbeard.TORRENT_PATH])[any([sickbeard.TORRENT_PATH])]
                    or None}
                # Send magnet to rTorrent
                if 'file' == cmd:
                    torrent = self.auth.load_torrent(data.content, **params)
                elif 'magnet' == cmd:
                    torrent = self.auth.load_magnet(data.url, data.hash, **params)

                if torrent and sickbeard.TORRENT_LABEL:
                    label = torrent.get_custom(1)
                    if sickbeard.TORRENT_LABEL != label:
                        logger.log('%s: could not change custom1 category \'%s\' to \'%s\' for %s' % (
                            self.name, label, sickbeard.TORRENT_LABEL, torrent.name), logger.WARNING)

            except(Exception, BaseException):
                pass

        return any([torrent])

    def _add_torrent_file(self, result):

        return result and self._add_torrent('file', result) or False

    def _add_torrent_uri(self, result):

        return result and self._add_torrent('magnet', result) or False

    # def _set_torrent_ratio(self, name):

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
            if not self._get_auth():
                return False, 'Error: Unable to get %s authentication, check your config!' % self.name
            return True, 'Success: Connected and Authenticated'

        except (StandardError, Exception):
            return False, 'Error: Unable to connect to %s' % self.name


api = RtorrentAPI()
