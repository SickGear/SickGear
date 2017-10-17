# Author: Nyaran <nyayukko@gmail.com>
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
import subprocess

import sickbeard
# noinspection PyPep8Naming
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier


class SynologyNotifier(Notifier):

    def _notify(self, title, body, **kwargs):

        synodsmnotify_cmd = ['/usr/syno/bin/synodsmnotify', '@administrators', title, body]
        self._log(u'Executing command ' + str(synodsmnotify_cmd))
        self._log_debug(u'Absolute path to command: ' + ek.ek(os.path.abspath, synodsmnotify_cmd[0]))
        try:
            p = subprocess.Popen(synodsmnotify_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 cwd=sickbeard.PROG_DIR)
            out, err = p.communicate()
            self._log_debug(u'Script result: ' + str(out))
        except OSError as e:
            self._log(u'Unable to run synodsmnotify: ' + ex(e))


notifier = SynologyNotifier
