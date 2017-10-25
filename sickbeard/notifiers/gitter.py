# coding=utf-8
#
# This file is part of SickGear.
#
# Thanks to: mallen86, generica
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
from sickbeard.notifiers.generic import Notifier


class GitterNotifier(Notifier):

    def __init__(self):
        super(GitterNotifier, self).__init__()

    def _notify(self, title, body, room_name='', access_token='', **kwargs):

        api_url = 'https://api.gitter.im/v1/'
        params = [('headers', dict(
            Authorization='Bearer %s' % self._choose(access_token, sickbeard.GITTER_ACCESS_TOKEN))), ('json', True)]
        is_locked = False

        # get user of token
        # noinspection PyTypeChecker
        resp = sickbeard.helpers.getURL(**dict([('url', '%suser' % api_url)] + params))
        user_id = resp and 1 == len(resp) and resp[0].get('id') or None
        if None is user_id:
            result = self._failed('bad oath access token?')
        else:
            # get a room
            # noinspection PyTypeChecker
            resp = sickbeard.helpers.getURL(**dict(
                [('url', '%srooms' % api_url),
                 ('post_json', dict(uri=self._choose(room_name, sickbeard.GITTER_ROOM)))] + params))
            room_id = resp and resp.get('id') or None
            if None is room_id:
                result = self._failed('room locked or not found')
            else:
                is_locked = 'private' == resp.get('security', '').lower()

                # join room
                # noinspection PyTypeChecker
                if not sickbeard.helpers.getURL(**dict(
                                [('url', '%suser/%s/rooms' % (api_url, user_id)),
                                 ('post_json', dict(id=room_id))] + params)):
                    result = self._failed('failed to join room')
                else:
                    # send text
                    # noinspection PyTypeChecker
                    resp = sickbeard.helpers.getURL(**dict(
                        [('url', '%srooms/%s/chatMessages' % (api_url, room_id)),
                         ('post_json', dict(text=self._body_only(title, body)))] + params))
                    if None is (resp and resp.get('id') or None):
                        result = self._failed('failed to send text', append=False)
                    else:
                        result = True

        return self._choose(('Error sending notification, %s' % result,
                             'Successful test notice sent%s. (Note: %s clients display icon once in a sequence).' %
                             (('', ' to locked room')[is_locked], self.name))[True is result], result)

    def _failed(self, result, append=True):
        self._log_error('%s failed to send message%s' % (self.name, append and ', %s' % result or ''))
        return self._choose(result, None)


notifier = GitterNotifier
