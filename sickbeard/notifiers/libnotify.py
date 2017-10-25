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

import os
import cgi
import sickbeard

from sickbeard.notifiers.generic import Notifier


def diagnose():
    """
    Check the environment for reasons libnotify isn't working.  Return a
    user-readable message indicating possible issues.
    """
    try:
        # noinspection PyPackageRequirements
        import pynotify
    except ImportError:
        return ('Error: pynotify isn\'t installed.  On Ubuntu/Debian, install the '
                '<a href=\'apt:python-notify\'>python-notify</a> package.')
    if 'DISPLAY' not in os.environ and 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
        return ('Error: Environment variables DISPLAY and DBUS_SESSION_BUS_ADDRESS '
                'aren\'t set.  libnotify will only work when you run SickGear '
                'from a desktop login.')
    try:
        import dbus
    except ImportError:
        pass
    else:
        try:
            bus = dbus.SessionBus()
        except dbus.DBusException as e:
            return (u'Error: unable to connect to D-Bus session bus: <code>%s</code>. '
                    u'Are you running SickGear in a desktop session?') % (cgi.escape(e),)
        try:
            bus.get_object('org.freedesktop.Notifications',
                           '/org/freedesktop/Notifications')
        except dbus.DBusException as e:
            return (u'Error: there doesn\'t seem to be a notification daemon available: <code>%s</code> '
                    u'Try installing notification-daemon or notify-osd.') % (cgi.escape(e),)
    return 'Error: Unable to send notification.'


class LibnotifyNotifier(Notifier):

    def __init__(self):
        super(LibnotifyNotifier, self).__init__()

        self.pynotify = None
        self.gobject = None

    def init_pynotify(self):
        if self.pynotify is not None:
            return True

        try:
            # noinspection PyPackageRequirements
            import pynotify
        except ImportError:
            self._log_error(u'Unable to import pynotify. libnotify notifications won\'t work')
            return False

        try:
            # noinspection PyPackageRequirements
            from gi.repository import GObject
        except ImportError:
            self._log_error(u'Unable to import GObject from gi.repository. Cannot catch a GError in display')
            return False

        if not pynotify.init('SickGear'):
            self._log_error(u'Initialization of pynotify failed. libnotify notifications won\'t work')
            return False

        self.pynotify = pynotify
        self.gobject = GObject
        return True

    def _notify(self, title, body, **kwargs):

        result = False
        if self.init_pynotify():

            # Can't make this a global constant because PROG_DIR isn't available
            # when the module is imported.
            icon_path = os.path.join(sickbeard.PROG_DIR, 'data/images/sickbeard_touch_icon.png')
            icon_uri = 'file://' + os.path.abspath(icon_path)

            # If the session bus can't be acquired here a bunch of warning messages
            # will be printed but the call to show() will still return True.
            # pynotify doesn't seem too keen on error handling.
            n = self.pynotify.Notification(title, body, icon_uri)
            try:
                result = n.show()
            except self.gobject.GError:
                pass

        return self._choose((True if result else diagnose()), result)


notifier = LibnotifyNotifier
