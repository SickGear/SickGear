# coding=utf-8
#
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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
from sickbeard import logger

notify_strings = dict(
    snatch='Started download',
    download='Download finished',
    subtitle_download='Subtitle download finished',
    git_updated='SickGear updated',
    git_updated_text='SickGear updated to commit#: ',
    test_title='SickGear notification test',
    test_body=u'Success testing %s settings from SickGear ʕ•ᴥ•ʔ',
)


class BaseNotifier(object):

    def __init__(self):
        self.sg_logo_file = 'apple-touch-icon-precomposed.png'
        self._testing = False

    @property
    def _sg_logo_url(self):
        return 'https://raw.githubusercontent.com/SickGear/SickGear/master/gui/slick/images/ico/' + self.sg_logo_file

    def _log(self, msg, level=logger.MESSAGE):
        logger.log(u'%s: %s' % (self.name, msg), level)

    def _log_debug(self, msg):
        self._log(msg, logger.DEBUG)

    def _log_error(self, msg):
        self._log(msg, logger.ERROR)

    def _log_warning(self, msg):
        self._log(msg, logger.WARNING)

    @classmethod
    def id(cls):
        return cls.__name__.replace('Notifier', '').upper()

    @property
    def name(self):
        return self.__class__.__name__.replace('Notifier', '')

    @classmethod
    def is_enabled_onsnatch(cls):
        return cls.is_enabled('NOTIFY_ONSNATCH')

    @classmethod
    def is_enabled_ondownload(cls):
        return cls.is_enabled('NOTIFY_ONDOWNLOAD')

    @classmethod
    def is_enabled_onsubtitledownload(cls):
        return cls.is_enabled('NOTIFY_ONSUBTITLEDOWNLOAD')

    @classmethod
    def is_enabled_library(cls):
        return cls.is_enabled('UPDATE_LIBRARY')

    @classmethod
    def is_enabled(cls, action=None):
        return getattr(sickbeard, action and '%s_%s' % (cls.id(), action) or 'USE_%s' % cls.id(), False)

    def notify_snatch(self, *args, **kwargs):
        pass

    def notify_download(self, *args, **kwargs):
        pass

    def notify_subtitle_download(self, *args, **kwargs):
        pass

    def notify_git_update(self, *args, **kwargs):
        pass

    def update_library(self, **kwargs):
        """
        note: nmj_notifier fires its library update when the notify_download is issued (inside notifiers)
        """
        pass

    def _notify(self, *args, **kwargs):
        pass

    def _choose(self, current=True, saved=True):
        if self._testing:
            return current
        return saved

    @staticmethod
    def _body_only(title, body):
        # don't use title with updates or testing, as only one str is used
        return body if 'SickGear' in title else '%s: %s' % (title, body.replace('#: ', '# '))


class Notifier(BaseNotifier):

    def test_notify(self, *args, **kwargs):
        self._testing = True
        r = self._pre_notify('test_title', notify_strings['test_body'] % (self.name + ' notifier'), *args, **kwargs)
        return (r, (('Success, notification sent.', 'Failed to send notification.')[not r]))[r in (True, False)]

    def notify_snatch(self, ep_name, **kwargs):
        self._pre_notify('snatch', ep_name, **kwargs)

    def notify_download(self, ep_name, **kwargs):
        self._pre_notify('download', ep_name, **kwargs)

    def notify_subtitle_download(self, ep_name, lang, **kwargs):
        self._pre_notify('subtitle_download', '%s : %s' % (ep_name, lang), **kwargs)

    def notify_git_update(self, new_version='??', **kwargs):
        self._pre_notify('git_updated', notify_strings['git_updated_text'] + new_version, **kwargs)

    def _pre_notify(self, notify_string, message, *args, **kwargs):
        self._log_debug(u'Sending notification "%s"' % (self._body_only(notify_strings[notify_string], message)))
        try:
            return self._notify(notify_strings[notify_string], message, *args, **kwargs)
        except (StandardError, Exception):
            return False
