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
import re

from ..common import USER_AGENT
from .generic import Notifier

from exceptions_helper import ex
import sickgear
from sickgear.image_cache import ImageCache
from sg_helpers import get_url


class TelegramNotifier(Notifier):

    def __init__(self):
        super(TelegramNotifier, self).__init__()

    def _notify(self, title, body, send_icon='', quiet=False, access_token='', chatid='', ep_obj=None, **kwargs):
        result = None
        use_icon = bool(self._choose(send_icon, sickgear.TELEGRAM_SEND_IMAGE))
        quiet = bool(self._choose(quiet, sickgear.TELEGRAM_QUIET))
        access_token = self._choose(access_token, sickgear.TELEGRAM_ACCESS_TOKEN)
        cid = self._choose(chatid, sickgear.TELEGRAM_CHATID)
        try:
            msg = self._body_only(('' if not title else f'<b>{title}</b>'), body)
            msg = msg.replace(f'<b>{title}</b>: ', f'<b>{("SickGear " + title, title)[use_icon]}:</b>\r\n')
            # HTML spaces (&nbsp;) and tabs (&emsp;) aren't supported
            # See https://core.telegram.org/bots/api#html-style
            msg = re.sub('(?i)&nbsp;?', ' ', msg)
            # Tabs become 3 spaces
            msg = re.sub('(?i)&emsp;?', '   ', msg)

            if use_icon:
                image_path = os.path.join(sickgear.PROG_DIR, 'gui', 'slick', 'images', 'banner_thumb.jpg')
                if not self._testing:
                    show_obj = ep_obj.show_obj
                    banner_path = ImageCache().banner_thumb_path(show_obj.tvid, show_obj.prodid)
                    if os.path.isfile(banner_path):
                        image_path = banner_path

                with open(image_path, 'rb') as f:
                    response = self.post('sendPhoto', access_token, cid, quiet,
                                         dict(files={'photo': ('image.png', f)}, post_data=dict(caption=msg)))

            else:
                response = self.post('sendMessage', access_token, cid, quiet, dict(post_data=dict(text=msg)))

            result = response and response.get('ok') or False

        except (BaseException, Exception) as e:
            if 'No chat_id' in ex(e):
                result = 'a chat id is not set, and a msg has not been sent to the bot to auto detect one.'

        if True is not result:
            self._log_error('Failed to send message, %s' % result)

        return dict(chatid=cid,
                    result=self._choose(('Successful test notice sent.',
                                         'Error sending notification, %s' % result)[True is not result], result))

    @staticmethod
    def post(action, access_token, cid, quiet, params):
        params.update(dict(headers={'User-Agent': USER_AGENT}, verify=True, json=True))
        params['post_data'].update(dict(chat_id=cid, parse_mode='HTML', disable_notification=quiet))
        return get_url('https://api.telegram.org/bot%s/%s' % (access_token, action), **params)


notifier = TelegramNotifier
