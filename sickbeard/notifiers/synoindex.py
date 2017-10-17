# Author: Sebastien Erard <sebastien_erard@hotmail.com>
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

import os
import subprocess

import sickbeard
# noinspection PyPep8Naming
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import BaseNotifier


# noinspection PyPep8Naming
class SynoIndexNotifier(BaseNotifier):

    def moveFolder(self, old_path, new_path):
        self._move_object(old_path, new_path)

    def moveFile(self, old_file, new_file):
        self._move_object(old_file, new_file)

    def _move_object(self, old_path, new_path):
        if self.is_enabled():
            synoindex_cmd = ['/usr/syno/bin/synoindex', '-N', ek.ek(os.path.abspath, new_path),
                             ek.ek(os.path.abspath, old_path)]
            self._log_debug(u'Executing command ' + str(synoindex_cmd))
            self._log_debug(u'Absolute path to command: ' + ek.ek(os.path.abspath, synoindex_cmd[0]))
            try:
                p = subprocess.Popen(synoindex_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     cwd=sickbeard.PROG_DIR)
                out, err = p.communicate()
                self._log_debug(u'Script result: ' + str(out))
            except OSError as e:
                self._log_error(u'Unable to run synoindex: ' + ex(e))

    def deleteFolder(self, cur_path):
        self._make_object('-D', cur_path)

    def addFolder(self, cur_path):
        self._make_object('-A', cur_path)

    def deleteFile(self, cur_file):
        self._make_object('-d', cur_file)

    def addFile(self, cur_file):
        self._make_object('-a', cur_file)

    def _make_object(self, cmd_arg, cur_path):
        if self.is_enabled():
            synoindex_cmd = ['/usr/syno/bin/synoindex', cmd_arg, ek.ek(os.path.abspath, cur_path)]
            self._log_debug(u'Executing command ' + str(synoindex_cmd))
            self._log_debug(u'Absolute path to command: ' + ek.ek(os.path.abspath, synoindex_cmd[0]))
            try:
                p = subprocess.Popen(synoindex_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     cwd=sickbeard.PROG_DIR)
                out, err = p.communicate()
                self._log_debug(u'Script result: ' + str(out))
            except OSError as e:
                self._log_error(u'Unable to run synoindex: ' + ex(e))

    def update_library(self, ep_obj=None, **kwargs):
        self.addFile(ep_obj.location)


notifier = SynoIndexNotifier
