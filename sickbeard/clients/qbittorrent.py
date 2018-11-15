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

import sickbeard
from sickbeard import helpers
from sickbeard.clients.generic import GenericClient


class QbittorrentAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        super(QbittorrentAPI, self).__init__('qBittorrent', host, username, password)

        self.url = self.host
        self.session.headers.update({'Origin': self.host})

    def _get_auth(self):

        self.auth = (6 < self.api_version() and
                     'Ok' in helpers.getURL('%slogin' % self.host, session=self.session,
                                            post_data={'username': self.username, 'password': self.password}))
        return self.auth

    def api_version(self):

        return helpers.tryInt(helpers.getURL('%sversion/api' % self.host, session=self.session))

    def _post_api(self, cmd='', **kwargs):

        return helpers.getURL('%scommand/%s' % (self.host, cmd), session=self.session, **kwargs) in ('', 'Ok.')

    def _add_torrent(self, cmd, **kwargs):

        label = sickbeard.TORRENT_LABEL.replace(' ', '_')
        label_dict = {'label': label, 'category': label, 'savepath': sickbeard.TORRENT_PATH}
        if 'post_data' in kwargs:
            kwargs['post_data'].update(label_dict)
        else:
            kwargs.update({'post_data': label_dict})
        return self._post_api(cmd, **kwargs)

    def _add_torrent_uri(self, result):

        return self._add_torrent('download', post_data={'urls': result.url})

    def _add_torrent_file(self, result):

        return self._add_torrent('upload', files={'torrents': ('%s.torrent' % result.name, result.content)})

    ###
    # An issue in qB can lead to actions being ignored during the initial period after a file is added.
    # Therefore, actions that need to be applied to existing items will be disabled unless fixed.
    ###
    # def _set_torrent_priority(self, result):
    #
    #    return self._post_api('%screasePrio' % ('de', 'in')[1 == result.priority], post_data={'hashes': result.hash})

    # def _set_torrent_pause(self, result):
    #
    #    return self._post_api(('resume', 'pause')[sickbeard.TORRENT_PAUSED], post_data={'hash': result.hash})


api = QbittorrentAPI()
