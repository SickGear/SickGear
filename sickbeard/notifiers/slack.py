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


class SlackNotifier(Notifier):

    def __init__(self):
        super(SlackNotifier, self).__init__()

    def _notify(self, title, body, channel='', as_authed=None, bot_name='', icon_url='', access_token='', **kwargs):

        custom = not self._choose(as_authed, sickbeard.SLACK_AS_AUTHED)
        resp = sickbeard.helpers.getURL(
            url='https://slack.com/api/chat.postMessage',
            post_data=dict(
                [('text', self._body_only(title, body)),
                 ('channel', self._choose(channel, sickbeard.SLACK_CHANNEL)), ('as_authed', not custom),
                 ('token', self._choose(access_token, sickbeard.SLACK_ACCESS_TOKEN))]
                + ([], [('username', self._choose(bot_name, sickbeard.SLACK_BOT_NAME) or 'SickGear'),
                        ('icon_url', self._choose(icon_url, sickbeard.SLACK_ICON_URL) or self._sg_logo_url)])[custom]),
            json=True)

        result = resp and resp.get('ok') or 'response: "%s"' % (resp.get('error') or self._choose(
            'bad oath access token?', None))
        if True is not result:
            self._log_error('Failed to send message, %s' % result)

        return self._choose(('Successful test notice sent. (Note: %s clients display icon once in a sequence)'
                             % self.name, 'Error sending notification, %s' % result)[True is not result], result)


notifier = SlackNotifier
