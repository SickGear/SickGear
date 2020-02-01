# coding=utf-8
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

import os
from .generic import Notifier
import sickbeard

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex
from lib.apprise.plugins.NotifyTelegram import NotifyTelegram


class TelegramNotifier(Notifier):

    def __init__(self):
        super(TelegramNotifier, self).__init__()

    def _notify(self, title, body, send_icon='', access_token='', chatid='', **kwargs):
        result = None
        cid = ''
        use_icon = bool(self._choose(send_icon, sickbeard.TELEGRAM_SEND_ICON))
        try:
            tg = NotifyTelegram(
                bot_token=self._choose(access_token, sickbeard.TELEGRAM_ACCESS_TOKEN),
                targets=self._choose(chatid, sickbeard.TELEGRAM_CHATID),
                include_image=use_icon
            )
            cid = chatid or isinstance(tg.targets, list) and 1 == len(tg.targets) and tg.targets[0] or ''
            if use_icon:
                tg.icon_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick',
                                     'images', 'ico', 'apple-touch-icon-76x76.png')
                tg.image_size = '72x72'
            result = tg.send(body, title=title)
        except (BaseException, Exception) as e:
            if 'No chat_id' in ex(e):
                result = 'a chat id is not set, and a msg has not been sent to the bot to auto detect one.'

        if True is not result:
            self._log_error('Failed to send message, %s' % result)

        return dict(chatid=cid,
                    result=self._choose(('Successful test notice sent.',
                                         'Error sending notification, %s' % result)[True is not result], result))


notifier = TelegramNotifier
