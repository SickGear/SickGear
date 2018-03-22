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

import threading

import sickbeard
from sickbeard import watchedstate_queue


class WatchedStateUpdater(object):
    def __init__(self, name, queue_item):

        self.amActive = False
        self.lock = threading.Lock()
        self.name = name
        self.queue_item = queue_item

    @property
    def prevent_run(self):
        return sickbeard.watchedStateQueueScheduler.action.is_in_queue(self.queue_item)

    def run(self):
        if self.is_enabled():
            self.amActive = True
            new_item = self.queue_item()
            sickbeard.watchedStateQueueScheduler.action.add_item(new_item)
            self.amActive = False


class EmbyWatchedStateUpdater(WatchedStateUpdater):

    def __init__(self):
        super(EmbyWatchedStateUpdater, self).__init__('Emby', watchedstate_queue.EmbyWatchedStateQueueItem)

    @staticmethod
    def is_enabled():
        return sickbeard.USE_EMBY and sickbeard.EMBY_WATCHEDSTATE_SCHEDULED


class PlexWatchedStateUpdater(WatchedStateUpdater):

    def __init__(self):
        super(PlexWatchedStateUpdater, self).__init__('Plex', watchedstate_queue.PlexWatchedStateQueueItem)

    @staticmethod
    def is_enabled():
        return sickbeard.USE_PLEX and sickbeard.PLEX_WATCHEDSTATE_SCHEDULED
