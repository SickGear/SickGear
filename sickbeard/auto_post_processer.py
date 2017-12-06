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

import os.path

import sickbeard
from sickbeard import logger, processTV
from sickbeard import encodingKludge as ek


class PostProcesser():
    def __init__(self):
        self.amActive = False

    def run(self):
        if not sickbeard.PROCESS_AUTOMATICALLY:
            return

        self.amActive = True

        if not ek.ek(os.path.isdir, sickbeard.TV_DOWNLOAD_DIR):
            logger.log(u"Automatic post-processing attempted but dir %s doesn't exist" % sickbeard.TV_DOWNLOAD_DIR,
                       logger.ERROR)
            return

        if not ek.ek(os.path.isabs, sickbeard.TV_DOWNLOAD_DIR):
            logger.log(u'Automatic post-processing attempted but dir %s is relative '
                       '(and probably not what you really want to process)' % sickbeard.TV_DOWNLOAD_DIR, logger.ERROR)
            return

        processTV.processDir(sickbeard.TV_DOWNLOAD_DIR, is_basedir=True)

        self.amActive = False
