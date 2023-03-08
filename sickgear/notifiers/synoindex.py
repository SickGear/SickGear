# Author: Sebastien Erard <sebastien_erard@hotmail.com>
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

from .generic import BaseNotifier
from exceptions_helper import ex
from sg_helpers import cmdline_runner


# noinspection PyPep8Naming
class SynoIndexNotifier(BaseNotifier):

    def moveFolder(self, old_path, new_path):
        self._move_object(old_path, new_path)

    def moveFile(self, old_file, new_file):
        self._move_object(old_file, new_file)

    def _cmdline_run(self, synoindex_cmd):
        self._log_debug(f'Executing command {str(synoindex_cmd)}')
        self._log_debug(f'Absolute path to command: {os.path.abspath(synoindex_cmd[0])}')
        try:
            output, err, exit_status = cmdline_runner(synoindex_cmd)
            self._log_debug(f'Script result: {output}')
        except (BaseException, Exception) as e:
            self._log_error('Unable to run synoindex: %s' % ex(e))

    def _move_object(self, old_path, new_path):
        if self.is_enabled():
            self._cmdline_run(['/usr/syno/bin/synoindex', '-N', os.path.abspath(new_path), os.path.abspath(old_path)])

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
            self._cmdline_run(['/usr/syno/bin/synoindex', cmd_arg, os.path.abspath(cur_path)])

    def update_library(self, ep_obj=None, **kwargs):
        self.addFile(ep_obj.location)


notifier = SynoIndexNotifier
