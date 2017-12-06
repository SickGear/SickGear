# Author: Dieter Blomme <dieterblomme@gmail.com>
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

import sickbeard
from sickbeard.notifiers.generic import BaseNotifier

from lib.libtrakt import TraktAPI, exceptions


class TraktNotifier(BaseNotifier):
    """
    A "notifier" for trakt.tv which keeps track of what has and hasn't been added to your library.
    """
    @classmethod
    def is_enabled_library(cls):
        if sickbeard.TRAKT_ACCOUNTS:
            for tid, locations in sickbeard.TRAKT_UPDATE_COLLECTION.items():
                if tid in sickbeard.TRAKT_ACCOUNTS.keys():
                    return True
        return False

    def update_library(self, ep_obj=None, **kwargs):

        self._update_collection(ep_obj)

    def _update_collection(self, ep_obj):
        """
        Sends a request to trakt indicating that the given episode is part of our collection.

        :param ep_obj: The TVEpisode object to add to trakt
        """

        if sickbeard.TRAKT_ACCOUNTS:

            # URL parameters
            data = dict(shows=[
                dict(title=ep_obj.show.name, year=ep_obj.show.startyear, ids={})
            ])

            from sickbeard.indexers.indexer_config import INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_IMDB, INDEXER_TMDB, \
                INDEXER_TRAKT

            supported_indexer = {INDEXER_TRAKT: 'trakt', INDEXER_TVDB: 'tvdb', INDEXER_TVRAGE: 'tvrage',
                                 INDEXER_IMDB: 'imdb', INDEXER_TMDB: 'tmdb'}
            indexer_priorities = [INDEXER_TRAKT, INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_IMDB, INDEXER_TMDB]

            indexer = indexerid = None
            if ep_obj.show.indexer in supported_indexer:
                indexer, indexerid = supported_indexer[ep_obj.show.indexer], ep_obj.show.indexerid
            else:
                for i in indexer_priorities:
                    if 0 < ep_obj.show.ids.get(i, {'id': 0}).get('id', 0):
                        indexer, indexerid = supported_indexer[i], ep_obj.show.ids[i]['id']
                        break

            if None is indexer or None is indexerid:
                self._log_warning('Missing trakt supported id, could not add to collection')
                return

            data['shows'][0]['ids'][indexer] = indexerid

            # Add Season and Episode + Related Episodes
            data['shows'][0]['seasons'] = [{'number': ep_obj.season, 'episodes': []}]

            for relEp_Obj in [ep_obj] + ep_obj.relatedEps:
                data['shows'][0]['seasons'][0]['episodes'].append({'number': relEp_Obj.episode})

            for tid, locations in sickbeard.TRAKT_UPDATE_COLLECTION.items():
                if tid not in sickbeard.TRAKT_ACCOUNTS.keys():
                    continue
                for loc in locations:
                    if not ep_obj.location.startswith('%s%s' % (loc.rstrip(os.path.sep), os.path.sep)):
                        continue

                    warn, msg = False, ''
                    try:
                        resp = TraktAPI().trakt_request('sync/collection', data, send_oauth=tid)
                        if 'added' in resp and 'episodes' in resp['added'] \
                                and 0 < sickbeard.helpers.tryInt(resp['added']['episodes']):
                            msg = 'Added episode to'
                        elif 'updated' in resp and 'episodes' in resp['updated'] \
                                and 0 < sickbeard.helpers.tryInt(resp['updated']['episodes']):
                            msg = 'Updated episode in'
                        elif 'existing' in resp and 'episodes' in resp['existing'] \
                                and 0 < sickbeard.helpers.tryInt(resp['existing']['episodes']):
                            msg = 'Episode is already in'
                        elif 'not_found' in resp and 'episodes' in resp['not_found'] \
                                and 0 < sickbeard.helpers.tryInt(resp['not_found']['episodes']):
                            msg = 'Episode not found on Trakt, not adding to'
                        else:
                            warn, msg = True, 'Could not add episode to'
                    except (exceptions.TraktAuthException, exceptions.TraktException):
                        warn, msg = True, 'Error adding episode to'
                    msg = 'Trakt: %s your %s collection' % (msg, sickbeard.TRAKT_ACCOUNTS[tid].name)
                    if not warn:
                        self._log(msg)
                    else:
                        self._log_warning(msg)


notifier = TraktNotifier
