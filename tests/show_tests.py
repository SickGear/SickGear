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

import datetime
import unittest

import sickbeard
import test_lib as test
from sickbeard import db
from sickbeard.common import Quality, UNAIRED, SKIPPED, WANTED, wantedQualities, statusStrings
from sickbeard.show_queue import QueueItemAdd
from sickbeard.tv import TVEpisode, TVShow

# noinspection DuplicatedCode
wanted_tests = [
    dict(
        name='Start and End',
        show=dict(indexer=1, indexerid=1, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=4, end_wanted=1,
        result=dict(
            start=dict(
                count=2, episodes={
                    1: {1: WANTED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }),
            end=dict(
                count=0, episodes={
                    1: {1: WANTED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }))
    ),

    dict(
        name='Start and End, entire season',
        show=dict(indexer=1, indexerid=10, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 2)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=-1, end_wanted=-1,
        result=dict(
            start=dict(
                count=4, episodes={
                    1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }),
            end=dict(
                count=0, episodes={
                    1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }))
    ),

    dict(
        name='End only',
        show=dict(indexer=1, indexerid=2, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 3)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=0, end_wanted=1,
        result=dict(
            start=dict(
                count=0, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }),
            end=dict(
                count=1, episodes={
                    1: {1: SKIPPED, 2: WANTED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }))
    ),

    dict(
        name='End only, entire season',
        show=dict(indexer=1, indexerid=20, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 4)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=0, end_wanted=-1,
        result=dict(
            start=dict(
                count=0, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }),
            end=dict(
                count=3, episodes={
                    1: {1: WANTED, 2: WANTED, 3: WANTED, 4: UNAIRED, 5: UNAIRED},
                    2: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED},
                    3: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED}
                }))
    ),

    dict(
        name='End only, multi season',
        show=dict(indexer=1, indexerid=3, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 5)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=0, end_wanted=1,
        result=dict(
            start=dict(
                count=0, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                    2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                    3: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED}
                }),
            end=dict(
                count=1, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                    2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                    3: {1: SKIPPED, 2: WANTED, 3: UNAIRED}
                }))
    ),

    dict(
        name='End only, multi season, entire season',
        show=dict(indexer=1, indexerid=30, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 6)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=0, end_wanted=-1,
        result=dict(
            start=dict(
                count=0, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                    2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                    3: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED}
                }),
            end=dict(
                count=2, episodes={
                    1: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED, 5: SKIPPED},
                    2: {1: SKIPPED, 2: SKIPPED, 3: SKIPPED, 4: SKIPPED},
                    3: {1: WANTED, 2: WANTED, 3: UNAIRED}
                }))
    ),

    dict(
        name='End only, multi season, cross season',
        show=dict(indexer=1, indexerid=33, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 7)),
            dict(season=1, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date(2019, 1, 1)),
            dict(season=1, episode=5, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=3, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=2, episode=4, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=1, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=2, status=SKIPPED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=3, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=7, end_wanted=3,
        result=dict(
            start=dict(
                count=7, episodes={
                    1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: WANTED},
                    2: {1: WANTED, 2: WANTED, 3: SKIPPED, 4: SKIPPED},
                    3: {1: SKIPPED, 2: SKIPPED, 3: UNAIRED}
                }),
            end=dict(
                count=3, episodes={
                    1: {1: WANTED, 2: WANTED, 3: WANTED, 4: WANTED, 5: WANTED},
                    2: {1: WANTED, 2: WANTED, 3: SKIPPED, 4: WANTED},
                    3: {1: WANTED, 2: WANTED, 3: UNAIRED}
                }))
    ),

    dict(
        name='all episodes unaired',
        show=dict(indexer=1, indexerid=35, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
            dict(season=1, episode=1, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=1, episode=2, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=1, episode=3, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=1, episode=4, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
            dict(season=1, episode=5, status=UNAIRED, quality=Quality.NONE, airdate=datetime.date.fromordinal(1)),
        ],
        start_wanted=7, end_wanted=3,
        result=dict(
            start=dict(
                count=0, episodes={
                    1: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                }),
            end=dict(
                count=0, episodes={
                    1: {1: UNAIRED, 2: UNAIRED, 3: UNAIRED, 4: UNAIRED, 5: UNAIRED},
                }))
    ),

    dict(
        name='no episodes',
        show=dict(indexer=1, indexerid=36, quality=Quality.combineQualities([Quality.SDTV], [])),
        episodes=[
        ],
        start_wanted=7, end_wanted=3,
        result=dict(
            start=dict(
                count=0, episodes={
                }),
            end=dict(
                count=0, episodes={
                }))
    ),
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
                              w['start_wanted'], w['end_wanted'], None, None)
            qi.show = show
            # start tests
            tr = qi._get_wanted(cur_db, w['start_wanted'], False)
            self.assertEqual(
                tr, w['result']['start'].get('count'),
                msg='%s: start: got: %s, expected: %s' % (w['name'], tr, w['result']['start'].get('count')))
            results = cur_db.select('SELECT status, season, episode FROM tv_episodes WHERE indexer = ? AND showid = ?'
                                    ' ORDER BY season, episode',
                                    [show.indexer, show.indexerid])
            for r in results:
                expected = w['result']['start'].get('episodes').get(r['season'], {}).get(r['episode'], None)
                self.assertEqual(
                    r['status'], expected,
                    msg='%s: start %sx%s: got: %s, expected: %s' %
                        (w['name'], r['season'], r['episode'], statusStrings[r['status']], statusStrings[expected]))

            # end tests
            tr = qi._get_wanted(cur_db, w['end_wanted'], True)
            self.assertEqual(tr, w['result']['end'].get('count'),
                             msg='%s: end: got: %s, expected: %s' % (w['name'], tr, w['result']['end'].get('count')))
            results = cur_db.select('SELECT status, season, episode FROM tv_episodes WHERE indexer = ? AND showid = ?'
                                    ' ORDER BY season, episode',
                                    [show.indexer, show.indexerid])
            for r in results:
                expected = w['result']['end'].get('episodes').get(r['season'], {}).get(r['episode'], None)
                self.assertEqual(r['status'], expected,
                                 msg='%s: end %sx%s: got: %s, expected: %s' %
                                     (w['name'], r['season'], r['episode'], statusStrings[r['status']],
                                      statusStrings[expected]))


if '__main__' == __name__:
    print('==================')
    print('STARTING - SHOW TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(ShowAddTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
