# Author: Dieter Blomme <dieterblomme@gmail.com>
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
import sickgear
from lib.api_trakt import TraktAPI, exceptions
from exceptions_helper import ConnectionSkipException

from _23 import list_keys
from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import Dict


class TraktNotifier(BaseNotifier):
    """
    A "notifier" for trakt.tv which keeps track of what has and hasn't been added to your library.
    """
    @classmethod
    def is_enabled_library(cls):
        if sickgear.TRAKT_ACCOUNTS:
            for tid, locations in iteritems(sickgear.TRAKT_UPDATE_COLLECTION):
                if tid in list_keys(sickgear.TRAKT_ACCOUNTS):
                    return True
        return False

    def update_library(self, ep_obj=None, **kwargs):

        self._update_collection(ep_obj)

    def _update_collection(self, ep_obj):
        """
        Sends a request to trakt indicating that the given episode is part of our collection.

        :param ep_obj: The TVEpisode object to add to trakt
        """

        if sickgear.TRAKT_ACCOUNTS:

            # URL parameters
            data = dict(shows=[
                dict(title=ep_obj.show_obj.name, year=ep_obj.show_obj.startyear, ids={})
            ])

            from sickgear.indexers.indexer_config import TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_IMDB, TVINFO_TMDB, \
                TVINFO_TRAKT

            supported_indexer = {TVINFO_TRAKT: 'trakt', TVINFO_TVDB: 'tvdb', TVINFO_TVRAGE: 'tvrage',
                                 TVINFO_IMDB: 'imdb', TVINFO_TMDB: 'tmdb'}  # type: Dict
            indexer_priorities = [TVINFO_TRAKT, TVINFO_TMDB, TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_IMDB]

            tvid = prodid = None
            if ep_obj.show_obj.tvid in supported_indexer:
                tvid, prodid = supported_indexer[ep_obj.show_obj.tvid], ep_obj.show_obj.prodid
            else:
                for i in indexer_priorities:
                    if 0 < ep_obj.show_obj.ids.get(i, {'id': 0}).get('id', 0):
                        tvid, prodid = supported_indexer[i], ep_obj.show_obj.ids[i]['id']
                        break

            if None is tvid or None is prodid:
                self._log_warning('Missing trakt supported id, could not add to collection')
                return

            data['shows'][0]['ids'][tvid] = prodid

            # Add Season and Episode + Related Episodes
            data['shows'][0]['seasons'] = [{'number': ep_obj.season, 'episodes': []}]

            for cur_ep_obj in [ep_obj] + ep_obj.related_ep_obj:
                data['shows'][0]['seasons'][0]['episodes'].append({'number': cur_ep_obj.episode})

            for tid, locations in iteritems(sickgear.TRAKT_UPDATE_COLLECTION):
                if tid not in list_keys(sickgear.TRAKT_ACCOUNTS):
                    continue
                for loc in locations:
                    if not ep_obj.location.startswith('%s%s' % (loc.rstrip(os.path.sep), os.path.sep)):
                        continue

                    warn, msg = False, ''
                    try:
                        resp = TraktAPI().trakt_request('sync/collection', data, send_oauth=tid)
                        if 'added' in resp and 'episodes' in resp['added'] \
                                and 0 < sickgear.helpers.try_int(resp['added']['episodes']):
                            msg = 'Added episode to'
                        elif 'updated' in resp and 'episodes' in resp['updated'] \
                                and 0 < sickgear.helpers.try_int(resp['updated']['episodes']):
                            msg = 'Updated episode in'
                        elif 'existing' in resp and 'episodes' in resp['existing'] \
                                and 0 < sickgear.helpers.try_int(resp['existing']['episodes']):
                            msg = 'Episode is already in'
                        elif 'not_found' in resp and 'episodes' in resp['not_found'] \
                                and 0 < sickgear.helpers.try_int(resp['not_found']['episodes']):
                            msg = 'Episode not found on Trakt, not adding to'
                        else:
                            warn, msg = True, 'Could not add episode to'
                    except (ConnectionSkipException, exceptions.TraktAuthException, exceptions.TraktException):
                        warn, msg = True, 'Error adding episode to'
                    msg = 'Trakt: %s your %s collection' % (msg, sickgear.TRAKT_ACCOUNTS[tid].name)
                    if not warn:
                        self._log(msg)
                    else:
                        self._log_warning(msg)


notifier = TraktNotifier
