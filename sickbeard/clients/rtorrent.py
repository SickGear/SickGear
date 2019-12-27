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

from .generic import GenericClient
from .. import logger
import sickbeard
from lib.rtorrent import RTorrent
from lib.rtorrent.compat import xmlrpclib


class RtorrentAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        if host and host.startswith('scgi:'):
            username = password = None

        super(RtorrentAPI, self).__init__('rTorrent', host, username, password)

    def _add_torrent_uri(self, search_result):

        return search_result and self._add_torrent('magnet', search_result) or False

    def _add_torrent_file(self, search_result):

        return search_result and self._add_torrent('file', search_result) or False

    def _add_torrent(self, cmd, data):
        torrent = None

        if self.auth:
            try:
                if self.auth.has_local_id(data.hash):
                    logger.log('%s: Item already exists %s' % (self.name, data.name), logger.WARNING)
                    raise

                custom_var = (1, sickbeard.TORRENT_LABEL_VAR or '')[0 <= sickbeard.TORRENT_LABEL_VAR <= 5]
                params = {
                    'start': not sickbeard.TORRENT_PAUSED,
                    'extra': ([], ['d.set_custom%s=%s' % (custom_var, sickbeard.TORRENT_LABEL)])[
                                 any([sickbeard.TORRENT_LABEL])] +
                             ([], ['d.set_directory=%s' % sickbeard.TORRENT_PATH])[
                                 any([sickbeard.TORRENT_PATH])] or None}
                # Send magnet to rTorrent
                if 'file' == cmd:
                    torrent = self.auth.load_torrent(data.content, **params)
                elif 'magnet' == cmd:
                    torrent = self.auth.load_magnet(data.url, data.hash, **params)

                if torrent and sickbeard.TORRENT_LABEL:
                    label = torrent.get_custom(custom_var)
                    if sickbeard.TORRENT_LABEL != label:
                        logger.log('%s: could not change custom%s label value \'%s\' to \'%s\' for %s' % (
                            self.name, custom_var, label, sickbeard.TORRENT_LABEL, torrent.name), logger.WARNING)

            except (BaseException, Exception):
                pass

        return any([torrent])

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

    def _get_auth(self):

        self.auth = None
        if self.host:
            try:
                if self.host.startswith('scgi:'):
                    self.username = self.password = None
                self.auth = RTorrent(self.host, self.username, self.password)
            except (AssertionError, xmlrpclib.ProtocolError):
                pass

        # do tests here

        return self.auth


api = RtorrentAPI()
