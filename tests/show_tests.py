# coding=UTF-8
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

from __future__ import print_function
import unittest
import datetime
import test_lib as test

import sickbeard
from sickbeard import db
from sickbeard.tv import TVEpisode, TVShow
from sickbeard.show_queue import QueueItemAdd
from sickbeard.common import Quality, UNAIRED, SKIPPED, WANTED, DOWNLOADED, SNATCHED, wantedQualities, statusStrings


wanted_tests = [{'name': 'Start and End',
                 'show': {'indexer': 1, 'indexerid': 1, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': 4,
                'end_wanted': 1,
                'result': {'start': {'count': 2,
                                     'episodes': {
                                         1: {1: WANTED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                                         2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                         3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                     },
                           'end': {'count': 0,
                                   'episodes': {
                                       1: {1: WANTED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                                       2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                       3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                   }
                           }
                 },
                {'name': 'Start and End, entire season',
                 'show': {'indexer': 1, 'indexerid': 10, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': -1,
                'end_wanted': -1,
                'result': {'start': {'count': 4,
                                     'episodes': {
                                         1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: UNAIRED},
                                         2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                         3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                     },
                           'end': {'count': 0,
                                   'episodes': {
                                       1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: UNAIRED},
                                       2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                       3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                   }
                           }
                 },
                {'name': 'End only',
                 'show': {'indexer': 1, 'indexerid': 2, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': 0,
                'end_wanted': 1,
                'result': {'start': {'count': 0,
                                     'episodes': {
                                         1: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                                         2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                         3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                     },
                           'end': {'count': 1,
                                   'episodes': {
                                       1: {1: SKIPPED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                                       2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                       3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                   }
                           }
                 },
                {'name': 'End only, entire season',
                 'show': {'indexer': 1, 'indexerid': 20, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': 0,
                'end_wanted': -1,
                'result': {'start': {'count': 0,
                                     'episodes': {
                                         1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: UNAIRED, 5: UNAIRED},
                                         2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                         3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                     },
                           'end': {'count': 3,
                                   'episodes': {
                                       1: {1: WANTED, 2: WANTED, 3: WANTED, 4: UNAIRED, 5: UNAIRED},
                                       2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                                       3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}},
                                   }
                           }
                 },
                {'name': 'End only, multi season',
                 'show': {'indexer': 1, 'indexerid': 3, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': 0,
                'end_wanted': 1,
                'result': {'start': {'count': 0,
                                     'episodes': {
                                         1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                                         2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                                         3: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED}},
                                     },
                           'end': {'count': 1,
                                   'episodes': {
                                       1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                                       2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                                       3: {1: SKIPPED, 2: WANTED, 3: UNAIRED}},
                                   }
                           }
                 },
                {'name': 'End only, multi season, entire season',
                 'show': {'indexer': 1, 'indexerid': 30, 'quality': Quality.combineQualities([Quality.SDTV], [])},
                'episodes': [
                    {'season': 1, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 4, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date(2019, 1, 1)},
                    {'season': 1, 'episode': 5, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 3, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 2, 'episode': 4, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 1, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 2, 'status': SKIPPED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                    {'season': 3, 'episode': 3, 'status': UNAIRED, 'quality': Quality.NONE,
                     'airdate': datetime.date.fromordinal(1)},
                ],
                'start_wanted': 0,
                'end_wanted': -1,
                'result': {'start': {'count': 0,
                                     'episodes': {
                                         1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                                         2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                                         3: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED}},
                                     },
                           'end': {'count': 2,
                                   'episodes': {
                                       1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                                       2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                                       3: {1: WANTED, 2: WANTED, 3: UNAIRED}},
                                   }
                           }
                 }
                ]


class ShowAddTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(ShowAddTests, self).setUp()
        sickbeard.showList = []
        sickbeard.WANTEDLIST_CACHE = wantedQualities()

    def test_getWanted(self):
        for ep_base, w in enumerate(wanted_tests):
            show = TVShow(w['show']['indexer'], w['show']['indexerid'], 'en')
            show.name = 'show name'
            show.tvrname = 'show name'
            show.quality = w['show']['quality']
            show.network = 'cbs'
            show.genre = 'crime'
            show.runtime = 40
            show.status = '5'
            show.airs = 'monday'
            show.startyear = 1987
            show.saveToDB()
            sickbeard.showList = [show]
            cl = []
            ep_id = ep_base * 10000
            for ep in w['episodes']:
                ep_id += 1
                if ep['season'] not in show.episodes:
                    show.episodes[ep['season']] = {}
                show.episodes[ep['season']][ep['episode']] = TVEpisode(show, ep['season'], ep['episode'])
                show.episodes[ep['season']][ep['episode']].status = Quality.compositeStatus(ep['status'], ep['quality'])
                show.episodes[ep['season']][ep['episode']].airdate = ep['airdate']
                show.episodes[ep['season']][ep['episode']].name = 'nothing'
                show.episodes[ep['season']][ep['episode']].indexerid = ep_id
                show.episodes[ep['season']][ep['episode']].show = show
                show.episodes[ep['season']][ep['episode']].indexer = show.indexer
                cl.append(show.episodes[ep['season']][ep['episode']].get_sql())

            cur_db = db.DBConnection()
            if cl:
                cur_db.mass_action(cl)

            qi = QueueItemAdd(w['show']['indexer'], w['show']['indexerid'], '', None, None,
                                          None, None, None, False, False, False, None, None,
                                          w['start_wanted'], w['end_wanted'], None, None
                                          )
            qi.show = show
            # start tests
            tr = qi._get_wanted(cur_db, w['start_wanted'], False)
            self.assertEqual(tr, w['result']['start']['count'],
                             msg='%s: start: got: %s, expected: %s' % (w['name'], tr, w['result']['start']['count']))
            results = cur_db.select('SELECT status, season, episode FROM tv_episodes WHERE indexer = ? AND showid = ?'
                                    ' ORDER BY season, episode',
                                    [show.indexer, show.indexerid])
            for r in results:
                expected = w['result']['start']['episodes'].get(r['season'], {}).get(r['episode'], None)
                self.assertEqual(r['status'], expected,
                                 msg='%s: start %sx%s: got: %s, expected: %s' %
                                     (w['name'], r['season'], r['episode'], statusStrings[r['status']],
                                      statusStrings[expected]))

            # end tests
            tr = qi._get_wanted(cur_db, w['end_wanted'], True)
            self.assertEqual(tr, w['result']['end']['count'],
                             msg='%s: end: got: %s, expected: %s' % (w['name'], tr, w['result']['end']['count']))
            results = cur_db.select('SELECT status, season, episode FROM tv_episodes WHERE indexer = ? AND showid = ?'
                                    ' ORDER BY season, episode',
                                    [show.indexer, show.indexerid])
            for r in results:
                expected = w['result']['end']['episodes'].get(r['season'], {}).get(r['episode'], None)
                self.assertEqual(r['status'], expected,
                                 msg='%s: start %sx%s: got: %s, expected: %s' %
                                     (w['name'], r['season'], r['episode'], statusStrings[r['status']],
                                      statusStrings[expected]))


if __name__ == '__main__':
    print('==================')
    print('STARTING - SHOW TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(ShowAddTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
