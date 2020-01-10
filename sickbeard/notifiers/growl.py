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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import re

from .generic import Notifier, notify_strings
from exceptions_helper import ex
from lib.apprise.plugins.NotifyGrowl.gntp import notifier as growl_notifier
import sickbeard

from six import string_types


class GrowlNotifier(Notifier):

    def __init__(self):
        super(GrowlNotifier, self).__init__()

    def _send_growl_msg(self, options, message=None):

        notice = growl_notifier.GrowlNotifier(applicationName=options['app'],
                                              applicationIcon=self._sg_logo_url,
                                              hostname=options['host'],
                                              password=None if not options['password'] else options['password'],
                                              port=options['port'],
                                              notifications=['Test'] + [notify_strings[s] for s in
                                                                        ('snatch', 'download', 'git_updated',
                                                                         'subtitle_download', 'test_title')]
                                              )

        def _send_growl():
            try:
                r = notice.notify(noteType=options['name'], title=options['title'], sticky=bool(options['sticky']),
                                  priority=options['priority'],
                                  description=message if isinstance(message, string_types) and 0 < len(message.strip())
                                  else 'Test')
            except (BaseException, Exception):
                return False
            return r

        result = _send_growl()
        if isinstance(result, bool):
            return result
        # check if growl is not yet registered with the app
        if isinstance(result, tuple) and '401' == result[0]:
            try:
                notice.register()
            except (BaseException, Exception):
                return False
            result = _send_growl()
            if isinstance(result, bool):
                return result

        return False

    def _notify(self, title, body, name=None, host=None, password=None, **kwargs):

        name = name or title or 'SickGear Notification'

        hosts = [h.strip() for h in self._choose(host, sickbeard.GROWL_HOST).split(',')]
        growl_hosts = []
        host_re = re.compile(r'^(?:(?P<password>[^@]+?)@)?(?P<host>[^:]+?)(?::(?P<port>\d+))?$')
        for h in hosts:
            host_parts = host_re.match(h)
            if host_parts:
                host, port, password = host_parts.group('host'), host_parts.group('port'), host_parts.group('password')
                if host:
                    growl_hosts += [(host, 23053 if not port else int(port), None if not password else password)]

        opts = dict(title=title, name=name, app='SickGear', sticky=None, priority=None,
                    icon=True, debug=False)

        success = False
        for pc in growl_hosts:
            opts['host'] = pc[0]
            opts['port'] = pc[1]
            opts['password'] = pc[2]
            try:
                if self._send_growl_msg(opts, body):
                    success = True

            except (BaseException, Exception) as e:
                self._log_warning(u'Unable to send growl to %s:%s - %s' % (opts['host'], opts['port'], ex(e)))

        return success


notifier = GrowlNotifier
