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
from sickbeard import common, logger


class SlackNotifier:
    def __init__(self):
        self.sg_logo_url = 'https://raw.githubusercontent.com/SickGear/SickGear/master' + \
                           '/gui/slick/images/ico/apple-touch-icon-precomposed.png'

    def _notify(self, msg, channel='', as_user=False, bot_name='', icon_url='', access_token='', force=False):
        custom = (force and not as_user) or (not (force or sickbeard.SLACK_AS_USER))
        resp = (sickbeard.USE_SLACK or force) and sickbeard.helpers.getURL(
            url='https://slack.com/api/chat.postMessage',
            post_data=dict(
                [('text', msg), ('token', (access_token, sickbeard.SLACK_ACCESS_TOKEN)[not access_token]),
                 ('channel', (channel, sickbeard.SLACK_CHANNEL)[not channel]), ('as_user', not custom)] +
                ([], [('username', (bot_name, sickbeard.SLACK_BOT_NAME or 'SickGear')[not bot_name]),
                      ('icon_url', (icon_url, sickbeard.SLACK_ICON_URL or self.sg_logo_url)[not icon_url])])[custom]),
            json=True)

        result = resp and resp['ok'] or resp['error']
        if True is not result:
            logger.log(u'Slack failed sending message, response: "%s"' % resp['error'], logger.ERROR)
        return result

    def _notify_str(self, pre_text, post_text):
        return self._notify('%s: %s' % (common.notifyStrings[pre_text].strip('#: '), post_text))

    def test_notify(self, channel, as_user, bot_name, icon_url, access_token):
        return self._notify('This is a test notification from SickGear',
                            channel, as_user, bot_name, icon_url, access_token, force=True)

    def notify_snatch(self, ep_name):
        return sickbeard.SLACK_NOTIFY_ONSNATCH and self._notify_str(common.NOTIFY_SNATCH, ep_name)

    def notify_download(self, ep_name):
        return sickbeard.SLACK_NOTIFY_ONDOWNLOAD and self._notify_str(common.NOTIFY_DOWNLOAD, ep_name)

    def notify_subtitle_download(self, ep_name, lang):
        return sickbeard.SLACK_NOTIFY_ONSUBTITLEDOWNLOAD and \
               self._notify_str(common.NOTIFY_SUBTITLE_DOWNLOAD, '%s: %s' % (ep_name, lang))

    def notify_git_update(self, new_version='??'):
        return self._notify_str(common.NOTIFY_GIT_UPDATE_TEXT, new_version)


notifier = SlackNotifier
