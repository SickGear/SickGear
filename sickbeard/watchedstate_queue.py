#
#  This file is part of SickGear.
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

from . import logger, generic_queue
from .webserve import History

EMBYWATCHEDSTATE = 10
PLEXWATCHEDSTATE = 20


class WatchedStateQueue(generic_queue.GenericQueue):
    def __init__(self):
        super(WatchedStateQueue, self).__init__()
        # self.queue_name = 'WATCHEDSTATEQUEUE'
        self.queue_name = 'Q'

    def is_in_queue(self, itemtype):
        with self.lock:
            for cur_item in self.queue + [self.currentItem]:
                if isinstance(cur_item, itemtype):
                    return True
            return False

    # method for possible UI usage, can be removed if not used
    def queue_length(self):
        length = {'emby': 0, 'plex': 0}
        with self.lock:
            for cur_item in [self.currentItem] + self.queue:
                if isinstance(cur_item, EmbyWatchedStateQueueItem):
                    length['emby'] += 1
                elif isinstance(cur_item, PlexWatchedStateQueueItem):
                    length['plex'] += 1

        return length

    def add_item(self, item):
        if isinstance(item, EmbyWatchedStateQueueItem) and not self.is_in_queue(EmbyWatchedStateQueueItem):
            # emby watched state item
            generic_queue.GenericQueue.add_item(self, item)
        elif isinstance(item, PlexWatchedStateQueueItem) and not self.is_in_queue(PlexWatchedStateQueueItem):
            # plex watched state item
            generic_queue.GenericQueue.add_item(self, item)
        else:
            logger.log(u'Not adding item, it\'s already in the queue', logger.DEBUG)


class EmbyWatchedStateQueueItem(generic_queue.QueueItem):
    def __init__(self):
        super(EmbyWatchedStateQueueItem, self).__init__('Emby Watched', EMBYWATCHEDSTATE)

    def run(self):
        super(EmbyWatchedStateQueueItem, self).run()
        try:
            History.update_watched_state_emby()
        finally:
            self.finish()


class PlexWatchedStateQueueItem(generic_queue.QueueItem):
    def __init__(self):
        super(PlexWatchedStateQueueItem, self).__init__('Plex Watched', PLEXWATCHEDSTATE)

    def run(self):
        super(PlexWatchedStateQueueItem, self).run()
        try:
            History.update_watched_state_plex()
        finally:
            self.finish()
