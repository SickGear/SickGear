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

import sickgear
from .scheduler import Job


class ProperSearcher(Job):
    def __init__(self):
        super(ProperSearcher, self).__init__(self.job_run, kwargs={}, thread_lock=True)

    @staticmethod
    def is_enabled():
        # type: (...) -> bool
        return sickgear.DOWNLOAD_PROPERS

    @staticmethod
    def job_run():

        propersearch_queue_item = sickgear.search_queue.ProperSearchQueueItem()
        sickgear.search_queue_scheduler.action.add_item(propersearch_queue_item)
