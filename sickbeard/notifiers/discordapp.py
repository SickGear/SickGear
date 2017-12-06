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


class DiscordappNotifier(Notifier):

    def __init__(self):
        super(DiscordappNotifier, self).__init__()

    def _notify(self, title, body, as_authed=None, username='', icon_url='', as_tts='', access_token='', **kwargs):
        params = [] if not bool(self._choose(not as_authed, sickbeard.DISCORDAPP_AS_AUTHED)) else \
            [('username', self._choose(username, sickbeard.DISCORDAPP_USERNAME) or 'SickGear'),
             ('avatar_url', self._choose(icon_url, sickbeard.DISCORDAPP_ICON_URL) or self._sg_logo_url)]
        as_tts = self._choose(as_tts, bool(sickbeard.DISCORDAPP_AS_TTS))

        resp = sickbeard.helpers.getURL(
            url=self._choose(access_token, sickbeard.DISCORDAPP_ACCESS_TOKEN),
            post_json=dict([('content', self._body_only(title, body)), ('tts', as_tts)] + params))

        result = '' == resp or self._choose('bad webhook?', None)
        if True is not result:
            self._log_error('%s failed to send message: %s' % (self.name, result))

        return self._choose(('Success, notification sent. (Note: %s clients display icon once in a sequence)'
                             % self.name, 'Failed to send notification, %s' % result)[True is not result], result)


notifier = DiscordappNotifier
