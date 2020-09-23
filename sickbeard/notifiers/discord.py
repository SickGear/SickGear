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

import re
from .generic import Notifier
import sickbeard


class DiscordNotifier(Notifier):

    def __init__(self):
        super(DiscordNotifier, self).__init__()

    def _notify(self, title, body, as_authed=None, username='', icon_url='', as_tts='', access_token='', **kwargs):
        params = [] if not bool(self._choose(not as_authed, sickbeard.DISCORD_AS_AUTHED)) else \
            [('username', self._choose(username, sickbeard.DISCORD_USERNAME) or 'SickGear'),
             ('avatar_url', self._choose(icon_url, sickbeard.DISCORD_ICON_URL) or self._sg_logo_url)]
        as_tts = self._choose(as_tts, bool(sickbeard.DISCORD_AS_TTS))

        url = self._choose(access_token, sickbeard.DISCORD_ACCESS_TOKEN)
        success_and_deprecated_msg = ''
        if 'discordapp' in url:
            # upgrade webhook url for get_url, and notify user on test to update setting
            url = re.sub(r'^(https?://discord)app', r'\1', url)
            success_and_deprecated_msg = '<br><br>Note2: Please change `discordapp.com` ' \
                                         'in Discord channel webhook to `discord.com`'

        resp = sickbeard.helpers.get_url(
            url=url,
            post_json=dict([('content', self._body_only(title, body)), ('tts', as_tts)] + params))

        result = '' == resp or self._choose('bad webhook?', None)
        if True is not result:
            self._log_error('%s failed to send message: %s' % (self.name, result))

        return self._choose(('Success, notification sent. (Note: %s displays the icon once in a sequence)%s'
                             % (self.name, success_and_deprecated_msg),
                             'Failed to send notification, %s' % result)[True is not result], result)


notifier = DiscordNotifier
