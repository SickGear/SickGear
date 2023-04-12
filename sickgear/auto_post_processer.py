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

import os.path

import sickgear
from . import logger, processTV


class PostProcesser(object):
    def __init__(self):
        self.amActive = False

    @staticmethod
    def is_enabled():
        return sickgear.PROCESS_AUTOMATICALLY

    def run(self):
        if self.is_enabled():
            self.amActive = True
            self._main()
            self.amActive = False

    @staticmethod
    def _main():

        if not os.path.isdir(sickgear.TV_DOWNLOAD_DIR):
            logger.error('Automatic post-processing attempted but dir %s doesn\'t exist' % sickgear.TV_DOWNLOAD_DIR)
            return

        if not os.path.isabs(sickgear.TV_DOWNLOAD_DIR):
            logger.error('Automatic post-processing attempted but dir %s is relative '
                         '(and probably not what you really want to process)' % sickgear.TV_DOWNLOAD_DIR)
            return

        processTV.processDir(sickgear.TV_DOWNLOAD_DIR, is_basedir=True)
