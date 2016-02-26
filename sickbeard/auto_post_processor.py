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
from sickbeard.scheduler import Job


class PostProcessor(Job):
    def __init__(self):
        super(PostProcessor, self).__init__(self.main_task, kwargs={})

    @staticmethod
    def main_task():

        if sickbeard.PROCESS_AUTOMATICALLY:

            if not ek.ek(os.path.isdir, sickbeard.TV_DOWNLOAD_DIR):
                logger.log(u'Automatic post-processing attempted but dir %s does not exist' % sickbeard.TV_DOWNLOAD_DIR,
                           logger.ERROR)

            elif not ek.ek(os.path.isabs, sickbeard.TV_DOWNLOAD_DIR):
                logger.log(u'Automatic post-processing attempted but dir %s is relative '
                           '(and probably not what you really want to process)' % sickbeard.TV_DOWNLOAD_DIR, logger.ERROR)

            else:
                processTV.processDir(sickbeard.TV_DOWNLOAD_DIR)
