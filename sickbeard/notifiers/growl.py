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
import socket
import urllib

import sickbeard
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier, notify_strings

from lib.growl import gntp


class GrowlNotifier(Notifier):

    def __init__(self):
        super(GrowlNotifier, self).__init__()

        self.sg_logo_file = 'apple-touch-icon-72x72.png'

    def _send_growl_msg(self, options, message=None):

        # Send Notification
        notice = gntp.GNTPNotice()

        # Required
        notice.add_header('Application-Name', options['app'])
        notice.add_header('Notification-Name', options['name'])
        notice.add_header('Notification-Title', options['title'])

        if options['password']:
            notice.set_password(options['password'])

        # Optional
        if options['sticky']:
            notice.add_header('Notification-Sticky', options['sticky'])
        if options['priority']:
            notice.add_header('Notification-Priority', options['priority'])
        if options['icon']:
            notice.add_header('Notification-Icon',
                              'https://raw.github.com/SickGear/SickGear/master/gui/slick/images/sickgear.png')

        if message:
            notice.add_header('Notification-Text', message)

        response = self._send(options['host'], options['port'], notice.encode(), options['debug'])
        if isinstance(response, gntp.GNTPOK):
            return True
        return False

    @staticmethod
    def _send(host, port, data, debug=False):

        if debug:
            print('<Sending>\n', data, '\n</Sending>')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.send(data)
        response = gntp.parse_gntp(s.recv(1024))
        s.close()

        if debug:
            print('<Recieved>\n', response, '\n</Recieved>')

        return response

    def _send_registration(self, host=None, password=None):

        host_parts = self._choose(host, sickbeard.GROWL_HOST).split(':')
        port = 23053 if (2 != len(host_parts) or '' == host_parts[1]) else int(host_parts[1])
        password = self._choose(password, sickbeard.GROWL_PASSWORD)

        opts = dict(app='SickGear', host=host_parts[0], port=port, password=password, debug=False)

        # Send Registration
        register = gntp.GNTPRegister()
        register.add_header('Application-Name', opts['app'])
        register.add_header('Application-Icon', self._sg_logo_url)

        register.add_notification('Test', True)
        register.add_notification(notify_strings['snatch'], True)
        register.add_notification(notify_strings['download'], True)
        register.add_notification(notify_strings['git_updated'], True)

        if opts['password']:
            register.set_password(opts['password'])

        try:
            return self._send(opts['host'], opts['port'], register.encode(), opts['debug'])
        except Exception as e:
            self._log_warning(u'Unable to send growl to %s:%s - %s' % (opts['host'], opts['port'], ex(e)))
            return False

    def _notify(self, title, body, name=None, host=None, password=None, **kwargs):

        name = name or title or 'SickGear Notification'

        host_parts = self._choose(host, sickbeard.GROWL_HOST).split(':')
        port = (int(host_parts[1]), 23053)[len(host_parts) != 2 or '' == host_parts[1]]
        growl_hosts = [(host_parts[0], port)]
        password = self._choose(password, sickbeard.GROWL_PASSWORD)

        opts = dict(title=title, name=name, app='SickGear', sticky=None, priority=None,
                    password=password, icon=True, debug=False)

        for pc in growl_hosts:
            opts['host'] = pc[0]
            opts['port'] = pc[1]
            try:
                if self._send_growl_msg(opts, body):
                    return True

                if self._send_registration(host, password):
                    return self._send_growl_msg(opts, body)

            except Exception as e:
                self._log_warning(u'Unable to send growl to %s:%s - %s' % (opts['host'], opts['port'], ex(e)))

            return False

    def test_notify(self, host, password):
        self._testing = True
        self._send_registration(host, password)
        return ('Success, registered and tested', 'Failed registration and testing')[
                   True is not super(GrowlNotifier, self).test_notify(name='Test', host=host, password=password)] + \
               (urllib.unquote_plus(host) + ' with password: ' + password, '')[password in (None, '')]


notifier = GrowlNotifier
