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

from __future__ import with_statement

import sickbeard
from sickbeard.scheduler import Job

class ProperSearcher(Job):
    def __init__(self):
        super(ProperSearcher, self).__init__(self.queue_task, kwargs={}, thread_lock=True)

    @staticmethod
    def queue_task():

        propersearch_queue_item = sickbeard.search_queue.ProperSearchQueueItem()
        sickbeard.searchQueueScheduler.action.add_item(propersearch_queue_item)
