# Author: Frank Fenton
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

import datetime
import os
import traceback

# noinspection PyPep8Naming
import encodingKludge as ek

import sickbeard
from . import helpers, logger, search_queue
from .common import SKIPPED, WANTED
from .indexers.indexer_config import TVINFO_TVRAGE


class TraktChecker(object):
    def __init__(self):
        self.todoWanted = []

    def run(self, force=False):
        try:
            # add shows from trakt.tv watchlist
            if sickbeard.TRAKT_USE_WATCHLIST:
                self.todoWanted = []  # its about to all get re-added
                if len(sickbeard.ROOT_DIRS.split('|')) < 2:
                    logger.log(u"No default root directory", logger.ERROR)
                    return
                self.updateShows()
                self.updateEpisodes()

            # sync trakt.tv library with SickGear library
            if sickbeard.TRAKT_SYNC:
                self.syncLibrary()
        except Exception:
            logger.log(traceback.format_exc(), logger.DEBUG)

    def findShow(self, tvid, prodid):
        library = TraktCall("user/library/shows/all.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)

        if library == 'NULL':
            logger.log(u"No shows found in your library, aborting library update", logger.DEBUG)
            return

        if not library:
            logger.log(u"Could not connect to trakt service, aborting library check", logger.ERROR)
            return

        return filter(lambda x: int(prodid) in [int(x['tvdb_id']) or 0, int(x['tvrage_id'])] or 0, library)

    def syncLibrary(self):
        logger.log(u"Syncing Trakt.tv show library", logger.DEBUG)

        for cur_show_obj in sickbeard.showList:
            self.addShowToTraktLibrary(cur_show_obj)

    def removeShowFromTraktLibrary(self, show_obj):
        data = {}
        if self.findShow(show_obj.tvid, show_obj.prodid):
            # URL parameters
            data['tvdb_id'] = helpers.mapIndexersToShow(show_obj)[1]
            data['title'] = show_obj.name
            data['year'] = show_obj.startyear

        if len(data):
            logger.log(u"Removing " + show_obj.name + " from trakt.tv library", logger.DEBUG)
            TraktCall("show/unlibrary/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD,
                      data)

    def addShowToTraktLibrary(self, show_obj):
        """
        Sends a request to trakt indicating that the given show and all its episodes is part of our library.

        show_obj: The TVShow object to add to trakt
        """

        data = {}

        if not self.findShow(show_obj.tvid, show_obj.prodid):
            # URL parameters
            data['tvdb_id'] = helpers.mapIndexersToShow(show_obj)[1]
            data['title'] = show_obj.name
            data['year'] = show_obj.startyear

        if len(data):
            logger.log(u"Adding " + show_obj.name + " to trakt.tv library", logger.DEBUG)
            TraktCall("show/library/%API%", sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD,
                      data)

    def updateShows(self):
        logger.log(u"Starting trakt show watchlist check", logger.DEBUG)
        watchlist = TraktCall("user/watchlist/shows.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)

        if watchlist == 'NULL':
            logger.log(u"No shows found in your watchlist, aborting watchlist update", logger.DEBUG)
            return

        if not watchlist:
            logger.log(u"Could not connect to trakt service, aborting watchlist update", logger.ERROR)
            return

        for show in watchlist:
            tvid = int(sickbeard.TRAKT_DEFAULT_INDEXER)
            prodid = int(show[('tvdb_id', 'tvrage_id')[TVINFO_TVRAGE == tvid]])

            if int(sickbeard.TRAKT_METHOD_ADD) != 2:
                self.addDefaultShow(tvid, prodid, show["title"], SKIPPED)
            else:
                self.addDefaultShow(tvid, prodid, show["title"], WANTED)

            if int(sickbeard.TRAKT_METHOD_ADD) == 1:
                show_obj = helpers.find_show_by_id({tvid: prodid})
                if None is not show_obj:
                    self.setEpisodeToWanted(show_obj, 1, 1)
                else:
                    self.todoWanted.append((prodid, 1, 1))

    def updateEpisodes(self):
        """
        Sets episodes to wanted that are in trakt watchlist
        """
        logger.log(u"Starting trakt episode watchlist check", logger.DEBUG)
        watchlist = TraktCall("user/watchlist/episodes.json/%API%/" + sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_API, sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)

        if watchlist == 'NULL':
            logger.log(u"No episodes found in your watchlist, aborting watchlist update", logger.DEBUG)
            return

        if not watchlist:
            logger.log(u"Could not connect to trakt service, aborting watchlist update", logger.ERROR)
            return

        for show in watchlist:
            tvid = int(sickbeard.TRAKT_DEFAULT_INDEXER)
            prodid = int(show[('tvdb_id', 'tvrage_id')[TVINFO_TVRAGE == tvid]])

            self.addDefaultShow(tvid, prodid, show['title'], SKIPPED)
            show_obj = helpers.find_show_by_id({tvid: prodid})

            try:
                if show_obj and show_obj.tvid == tvid:
                    for episode in show["episodes"]:
                        if None is not show_obj:
                            self.setEpisodeToWanted(show_obj, episode["season"], episode["number"])
                        else:
                            self.todoWanted.append((prodid, episode["season"], episode["number"]))
            except TypeError:
                logger.log(u"Could not parse the output from trakt for " + show["title"], logger.DEBUG)

    def addDefaultShow(self, tvid, prod_id, name, status):
        """
        Adds a new show with the default settings
        """
        if not helpers.find_show_by_id({int(tvid): int(prodid)}):
            logger.log(u"Adding show " + str(prod_id))
            root_dirs = sickbeard.ROOT_DIRS.split('|')

            try:
                location = root_dirs[int(root_dirs[0]) + 1]
            except:
                location = None

            if location:
                showPath = ek.ek(os.path.join, location, helpers.sanitize_filename(name))
                dir_exists = helpers.make_dir(showPath)
                if not dir_exists:
                    logger.log(u"Unable to create the folder " + showPath + ", can't add the show", logger.ERROR)
                    return
                else:
                    helpers.chmod_as_parent(showPath)

                sickbeard.showQueueScheduler.action.addShow(int(tvid), int(prod_id), showPath, status,
                                                            int(sickbeard.QUALITY_DEFAULT),
                                                            int(sickbeard.FLATTEN_FOLDERS_DEFAULT),
                                                            paused=sickbeard.TRAKT_START_PAUSED)
            else:
                logger.log(u"There was an error creating the show, no root directory setting found", logger.ERROR)
                return

    def setEpisodeToWanted(self, show_obj, s, e):
        """
        Sets an episode to wanted, only is it is currently skipped
        """
        ep_obj = show_obj.get_episode(int(s), int(e))
        if ep_obj:

            with ep_obj.lock:
                if ep_obj.status != SKIPPED or ep_obj.airdate == datetime.date.fromordinal(1):
                    return

                logger.log(u"Setting episode s" + str(s) + "e" + str(e) + " of show " + show_obj.name + " to wanted")
                # figure out what segment the episode is in and remember it so we can backlog it

                ep_obj.status = WANTED
                ep_obj.save_to_db()

            backlog_queue_item = search_queue.BacklogQueueItem(show_obj, [ep_obj])
            sickbeard.searchQueueScheduler.action.add_item(backlog_queue_item)

            logger.log(u"Starting backlog for " + show_obj.name + " season " + str(
                    s) + " episode " + str(e) + " because some eps were set to wanted")

    def manageNewShow(self, show_obj):
        logger.log(u"Checking if trakt watch list wants to search for episodes from new show " + show_obj.name,
                   logger.DEBUG)
        episodes = [i for i in self.todoWanted if i[0] == show_obj.prodid]
        for episode in episodes:
            self.todoWanted.remove(episode)
            self.setEpisodeToWanted(show_obj, episode[1], episode[2])
