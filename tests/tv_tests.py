# coding=UTF-8
# Author: Dennis Lutter <lad1337@gmail.com>
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

import unittest
import test_lib as test
import datetime
import copy
from random import randint

import sickgear
from exceptions_helper import MultipleShowObjectsException
from sickgear import db, indexermapper
from sickgear.helpers import find_show_by_id
from sickgear.indexers.indexer_api import TVInfoAPI
from sickgear.indexers.indexer_config import TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVDB, TVINFO_TVMAZE, TVINFO_TVRAGE
from sickgear.scene_exceptions import ReleaseMap
from sickgear.tv import TVEpisode, TVShow, TVidProdid, prodid_bitshift
from tvinfo_base import TVInfoEpisode, TVInfoSeason, TVInfoShow

# noinspection PyUnreachableCode
if False:
    from typing import Optional


class TVShowTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVShowTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}
        _ = ReleaseMap()

    def test_init_indexerid(self):
        show_obj = TVShow(1, 1, 'en')
        self.assertEqual(show_obj.prodid, 1)

    def test_change_indexerid(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987

        show_obj.save_to_db()
        show_obj.load_from_db()

        show_obj.prodid = 2
        show_obj.save_to_db()
        show_obj.load_from_db()

        self.assertEqual(show_obj.prodid, 2)

    def test_set_name(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'newName'
        show_obj.save_to_db()
        show_obj.load_from_db()
        self.assertEqual(show_obj.name, 'newName')


class TVEpisodeTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVEpisodeTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}
        _ = ReleaseMap()

    def test_init_empty_db(self):
        show_obj = TVShow(1, 1, 'en')
        ep_obj = TVEpisode(show_obj, 1, 1)
        ep_obj.name = 'asdasdasdajkaj'
        ep_obj.save_to_db()
        ep_obj.load_from_db(1, 1)
        self.assertEqual(ep_obj.name, 'asdasdasdajkaj')

    def test_airdate_modify_stamp_never_aired(self):
        ep_obj = TVEpisode(TVShow(1, 1, 'en'), 1, 1)
        ep_obj.location = __file__
        stamped = []
        org_touch_file = sickgear.tv.helpers.touch_file
        sickgear.tv.helpers.touch_file = lambda name, atime=None, dir_name=None: stamped.append(atime) or True
        try:
            # a never aired episode keeps the timestamp of year 1 that was made from its air date
            ep_obj._airdate = datetime.date.fromordinal(1)
            ep_obj._timestamp = -62135539200
            ep_obj.airdate_modify_stamp()
            self.assertEqual([], stamped)

            ep_obj._airdate = datetime.date(2020, 1, 2)
            ep_obj._timestamp = 1577923200
            ep_obj.airdate_modify_stamp()
            self.assertEqual(1, len(stamped))
        finally:
            sickgear.tv.helpers.touch_file = org_touch_file


class TVEpisodeLoadTests(test.SickbeardTestDBCase):
    """ an episode that loads from the db is not marked as changed when TV info then gives it the same values """

    def setUp(self):
        super(TVEpisodeLoadTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}
        # load episodes from the db, the test lib replaces the loader with one that does nothing
        self.fake_specify_episode = TVEpisode.specify_episode
        TVEpisode.specify_episode = test.org_specify_episode
        self.release_map_xem = sickgear.scene_exceptions.MEMCACHE.get('release_map_xem', {})
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = {}
        with db.DBConnection() as sg_db:
            sg_db.action(
                'INSERT INTO tv_episodes (indexer, showid, indexerid, season, episode, status, airdate, subtitles)'
                ' VALUES (1, 123456, 1001, 1, 1, ?, 1, "")', [sickgear.common.SKIPPED])
        self.ep_obj = TVShow(1, 123456, 'en').get_episode(1, 1)

    def tearDown(self):
        TVEpisode.specify_episode = self.fake_specify_episode
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = self.release_map_xem
        super(TVEpisodeLoadTests, self).tearDown()

    def test_loaded_episode_is_not_changed(self):
        self.assertEqual(1001, self.ep_obj.epid)
        self.assertFalse(self.ep_obj.dirty)

    def test_metadata_file_flags_load_from_db(self):
        self.assertFalse(self.ep_obj.hasnfo)
        self.assertFalse(self.ep_obj.hastbn)
        with db.DBConnection() as sg_db:
            sg_db.action('UPDATE tv_episodes SET hasnfo = 1, hastbn = 1 WHERE indexer = 1 AND showid = 123456')
        ep_obj = TVShow(1, 123456, 'en').get_episode(1, 1)
        self.assertTrue(ep_obj.hasnfo)
        self.assertTrue(ep_obj.hastbn)
        # the same values again are no change, as a check of the files on disk gives them
        ep_obj.hasnfo = True
        ep_obj.hastbn = True
        self.assertFalse(ep_obj.dirty)

    def test_same_epid_is_no_change(self):
        self.ep_obj.epid = 1001
        self.assertFalse(self.ep_obj.dirty)

    def test_unknown_network_is_stream_is_no_change(self):
        self.ep_obj.network_is_stream = None
        self.assertFalse(self.ep_obj.dirty)

    def test_new_value_is_a_change(self):
        self.ep_obj.network_is_stream = True
        self.assertTrue(self.ep_obj.dirty)

    def test_same_tvinfo_data_is_no_change(self):
        ep_info = TVInfoEpisode()
        for cur_key, cur_value in dict(id=1001, episodename='Pilot', firstaired='2020-01-02', absolute_number=1).items():
            # TV info sources give a value as attribute and as key
            setattr(ep_info, cur_key, cur_value)
            ep_info[cur_key] = cur_value

        def load(network):
            # a new show object each time, as a show update after a restart has
            show_obj = TVShow(1, 123456, 'en')
            show_obj.network = network
            cur_ep_obj = show_obj.get_episode(1, 1)
            cur_ep_obj.load_from_tvinfo(1, 1, update=True, cached_show={1: {1: ep_info}})
            return cur_ep_obj

        for cur_network in ('', 'CBS'):
            ep_obj = load(cur_network)
            self.assertTrue(ep_obj.dirty)
            ep_obj.save_to_db()
            self.assertFalse(load(cur_network).dirty, msg=f'show network "{cur_network}"')


class TVTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}

    @staticmethod
    def test_getEpisode():
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987
        show_obj.save_to_db()
        sickgear.showList = [show_obj]
        sickgear.showDict = {show_obj.sid_int: show_obj}


class TVLoadEpisodesTests(test.SickbeardTestDBCase):
    """ a show update loads each episode once from the DB and once from TV info """

    def setUp(self):
        super(TVLoadEpisodesTests, self).setUp()
        # load episodes from the db, the test lib replaces the loader with one that does nothing
        self.fake_specify_episode = TVEpisode.specify_episode
        TVEpisode.specify_episode = test.org_specify_episode
        self.release_map_xem = sickgear.scene_exceptions.MEMCACHE.get('release_map_xem', {})
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = {}
        self.loaders = {}
        self.calls = []
        for cur_name in ('load_from_db', 'load_from_tvinfo'):
            self.loaders[cur_name] = getattr(TVEpisode, cur_name)
            setattr(TVEpisode, cur_name, self.counted(cur_name))

        self.show_obj = TVShow(TVINFO_TVDB, 123456, 'en')
        self.show_obj.sxe_ep_obj = {}
        with sickgear.db.DBConnection() as sg_db:
            sg_db.mass_action([[
                'INSERT INTO tv_episodes (indexer, showid, indexerid, season, episode, name, status, airdate,'
                ' subtitles) VALUES (?, 123456, ?, 1, ?, ?, ?, ?, "")',
                [TVINFO_TVDB, 1000 + ep_num, ep_num, f'Old name {ep_num}', sickgear.common.SKIPPED,
                 datetime.date(2020, 1, ep_num).toordinal()]] for ep_num in (1, 2)])

        self.tvinfo_show = TVInfoShow()
        self.tvinfo_show.id = 123456
        self.tvinfo_show[1] = TVInfoSeason(show=self.tvinfo_show, number=1)
        for ep_num in (1, 2, 3):
            ep_info = TVInfoEpisode(season=self.tvinfo_show[1], show=self.tvinfo_show)
            ep_info.id = 1000 + ep_num
            ep_info.episodename = f'New name {ep_num}'
            ep_info.firstaired = f'2020-01-0{ep_num}'
            self.tvinfo_show[1][ep_num] = ep_info

    def tearDown(self):
        for cur_name, cur_loader in self.loaders.items():
            setattr(TVEpisode, cur_name, cur_loader)
        TVEpisode.specify_episode = self.fake_specify_episode
        sickgear.scene_exceptions.MEMCACHE['release_map_xem'] = self.release_map_xem
        super(TVLoadEpisodesTests, self).tearDown()

    def counted(self, name):
        loader = self.loaders[name]

        def count(ep_obj, *args, **kwargs):
            self.calls.append((name, ep_obj.season, ep_obj.episode))
            return loader(ep_obj, *args, **kwargs)
        return count

    def names(self):
        return {_ep_num: _ep_obj.name for _ep_num, _ep_obj in self.show_obj.sxe_ep_obj[1].items()}

    def test_load_episodes_from_tvinfo_loads_each_episode_once(self):
        self.show_obj.load_episodes_from_tvinfo(tvinfo_data=self.tvinfo_show)

        self.assertEqual({1: 'New name 1', 2: 'New name 2', 3: 'New name 3'}, self.names())
        for cur_call in [(_name, 1, _ep_num) for _name in self.loaders for _ep_num in (1, 2, 3)]:
            self.assertEqual(1, self.calls.count(cur_call), cur_call)
        # each episode loads from its own db row, the status of episode 2 is not the default
        self.assertEqual(sickgear.common.SKIPPED, self.show_obj.sxe_ep_obj[1][2].status)

    def test_load_episodes_from_tvinfo_updates_a_loaded_episode(self):
        ep_obj = self.show_obj.get_episode(1, 2)
        self.assertEqual('Old name 2', ep_obj.name)
        self.show_obj.load_episodes_from_tvinfo(tvinfo_data=self.tvinfo_show)
        self.assertIs(ep_obj, self.show_obj.sxe_ep_obj[1][2])
        self.assertEqual('New name 2', ep_obj.name)


class TVCacheResultTests(test.SickbeardTestDBCase):

    def test_multi_ep_cache_result(self):
        from sickgear import classes, tvcache
        from sickgear.common import Quality

        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.want_episode = lambda *args, **kwargs: True
        sickgear.showList = [show_obj]
        sickgear.showDict = {show_obj.sid_int: show_obj}
        show_obj.sxe_ep_obj[1] = {_n: TVEpisode(show_obj, 1, _n) for _n in (2, 3)}

        class Provider(object):
            name = 'provider'
            anime_only = False

            @staticmethod
            def get_id():
                return 'provider'

            @staticmethod
            def get_result(ep_obj_list, url):
                result = classes.NZBSearchResult(ep_obj_list)
                result.url = url
                return result

        cache = tvcache.TVCache(Provider())
        with cache.get_db() as sg_db:
            sg_db.action(
                'INSERT INTO provider_cache (provider, name, season, episodes, indexerid, url, time, quality,'
                ' release_group, version, indexer, size, uid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ['provider', 'Show.Name.S01E02E03.720p.HDTV.x264-GRP', 1, '|2|3|', 1, 'http://host/nzb', 0,
                 Quality.HDTV, 'GRP', -1, 1, 1234, 'guid-1'])

        ep_obj = show_obj.sxe_ep_obj[1][2]
        ep_obj.wanted_quality = [Quality.HDTV]
        results = cache.search_cache(ep_obj)
        self.assertEqual(1, len(results))
        self.assertEqual([2, 3], results[0].episode_numbers)
        self.assertEqual([2, 3], [_ep.episode for _ep in results[0].ep_obj_list])
        self.assertEqual((1, 1234, 'guid-1'), (results[0].season, results[0].size, results[0].puid))


class TVAiredInSeasonTests(test.SickbeardTestDBCase):

    def test_aired_in_season(self):
        from sickgear.search import get_aired_in_season

        show_obj = TVShow(1, 1, 'en')
        yesterday = datetime.date.today().toordinal() - 1
        with test.db.DBConnection() as sg_db:
            for cur_ep_num in (1, 2, 3):
                sg_db.action('INSERT INTO tv_episodes (indexer, showid, season, episode, airdate, status)'
                             ' VALUES (1, 1, 1, ?, ?, 5)', [cur_ep_num, yesterday])

        ep_obj = TVEpisode(show_obj, 1, 1)
        self.assertEqual(0, ep_obj.eps_aired_in_season)

        self.assertIsNone(get_aired_in_season(show_obj))
        self.assertEqual({1: 3}, show_obj.aired_in_season)
        self.assertEqual(3, ep_obj.eps_aired_in_season)
        self.assertEqual(3, ep_obj.eps_aired_in_scene_season)

        # counts are kept for one day unless reset or sql is requested
        with test.db.DBConnection() as sg_db:
            sg_db.action('INSERT INTO tv_episodes (indexer, showid, season, episode, airdate, status)'
                         ' VALUES (1, 1, 1, 4, ?, 5)', [yesterday])
        get_aired_in_season(show_obj)
        self.assertEqual(3, ep_obj.eps_aired_in_season)
        self.assertEqual(4, len(get_aired_in_season(show_obj, return_sql=True)))
        self.assertEqual(4, ep_obj.eps_aired_in_season)

        # scene seasons are counted on their own
        show_obj = TVShow(1, 2, 'en')
        with test.db.DBConnection() as sg_db:
            for cur_ep_num in (1, 2):
                sg_db.action('INSERT INTO tv_episodes (indexer, showid, season, episode, scene_season, airdate, status)'
                             ' VALUES (1, 2, 1, ?, 2, ?, 5)', [cur_ep_num, yesterday])
        get_aired_in_season(show_obj)
        self.assertEqual({1: 2}, show_obj.aired_in_season)
        self.assertEqual({2: 2}, show_obj.aired_in_scene_season)


class TVFormatPatternTests(test.SickbeardTestDBCase):

    def setUp(self):
        super(TVFormatPatternTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}

    def test_getEpisode(self):
        show_obj = TVShow(1, 1, 'en')
        show_obj.name = 'show name'
        show_obj.tvrname = 'show name'
        show_obj.network = 'cbs'
        show_obj.genre = 'crime'
        show_obj.runtime = 40
        show_obj.status = '5'
        show_obj.airs = 'monday'
        show_obj.startyear = 1987
        sickgear.showList = [show_obj]
        sickgear.showDict = {show_obj.sid_int: show_obj}
        show_obj.sxe_ep_obj[1] = {}
        show_obj.sxe_ep_obj[1][1] = TVEpisode(show_obj, 1, 1, '16)')
        show_obj.sxe_ep_obj[1][1].dirty = False
        show_obj.sxe_ep_obj[1][1].name = None
        self.assertEqual(show_obj.sxe_ep_obj[1][1].dirty, False)
        self.assertEqual(
            show_obj.sxe_ep_obj[1][1]._format_pattern('%SN - %Sx%0E - %EN - %QN'),
            'show name - 1x01 - tba - Unknown')
        show_obj.sxe_ep_obj[1][1].dirty = False
        show_obj.sxe_ep_obj[1][1].name = 'ep name'
        self.assertEqual(show_obj.sxe_ep_obj[1][1].dirty, True)
        self.assertEqual(
            show_obj.sxe_ep_obj[1][1]._format_pattern('%SN - %Sx%0E - %EN - %QN'),
            'show name - 1x01 - ep name - Unknown')


class TVidProdidTests(test.SickbeardTestDBCase):
    @staticmethod
    def max_bits(b):
        return (1 << b) - 1

    def test_TVidProdid(self):
        max_tvid = self.max_bits(prodid_bitshift)
        max_prodid = self.max_bits(60)
        i = 0
        while 1000 > i:
            i += 1
            tvid = randint(1, max_tvid)
            prodid = randint(1, max_prodid)
            tvid_prodid_obj = TVidProdid({tvid: prodid})

            msg_vars = f': tvid = {tvid} ; prodid = {prodid}'

            self.assertEqual(tvid, tvid_prodid_obj.tvid, msg=f'dict tvid test{msg_vars}')
            self.assertEqual(prodid, tvid_prodid_obj.prodid, msg=f'dict prodid test{msg_vars}')

            self.assertEqual((tvid, prodid), tvid_prodid_obj.tuple, msg=f'tuple test{msg_vars}')
            self.assertEqual({tvid: prodid}, tvid_prodid_obj.dict, msg=f'dict test{msg_vars}')
            self.assertEqual([tvid, prodid], tvid_prodid_obj.list, msg=f'list test{msg_vars}')

            new_sid = prodid << prodid_bitshift | tvid
            self.assertEqual(new_sid, tvid_prodid_obj.int, msg=f'int test{msg_vars}')

            sid = tvid_prodid_obj.int
            reverse_obj = TVidProdid(sid)
            self.assertEqual(tvid, reverse_obj.tvid, msg=f'reverse int tvid test{msg_vars}')
            self.assertEqual(prodid, reverse_obj.prodid, msg=f'reverse int prodid test{msg_vars}')

            str_reverse_obj = TVidProdid(f'{tvid}{TVidProdid.glue}{prodid}')
            self.assertEqual(tvid, str_reverse_obj.tvid, msg=f'reverse str tvid test{msg_vars}')
            self.assertEqual(prodid, str_reverse_obj.prodid, msg=f'reverse str prodid test{msg_vars}')


ids_base = {source: {'id': 0, 'status': indexermapper.MapStatus.NO_AUTOMATIC_CHANGE, 'date': datetime.date.today()}
            for source in TVInfoAPI().all_sources}

shows = [{'tvid': TVINFO_TVDB, 'prodid': 123,
          'ids': {TVINFO_TVMAZE: {'id': 22}, TVINFO_IMDB: {'id': 54321}, TVINFO_TMDB: {'id': 9877}}},
         {'tvid': TVINFO_TVDB, 'prodid': 222,
          'ids': {TVINFO_TVMAZE: {'id': 854}, TVINFO_IMDB: {'id': 9435}, TVINFO_TMDB: {'id': 2457}}},
         {'tvid': TVINFO_TVMAZE, 'prodid': 123,
          'ids': {TVINFO_TVMAZE: {'id': 957}, TVINFO_IMDB: {'id': 4751}, TVINFO_TMDB: {'id': 659}}},
         {'tvid': TVINFO_TMDB, 'prodid': 123,
          'ids': {TVINFO_TVMAZE: {'id': 428}, TVINFO_IMDB: {'id': 999}, TVINFO_TMDB: {'id': 754}}}
         ]

find_tests = [
    {'para': {'show_id': {TVINFO_TVMAZE: 22, TVINFO_TVRAGE: 785}, 'no_mapped_ids': False},
     'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'search via mapped id'},
    {'para': {'show_id': {TVINFO_TVDB: 123}}, 'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'simple standard search via main id dict'},
    {'para': {'show_id': {TVINFO_TVDB: 12345}}, 'result': None,
     'description': 'simple standard search via main id dict, for non-existing show'},
    {'para': {'show_id': {TVINFO_TVDB: 123, TVINFO_TVMAZE: 123}, 'check_multishow': True},
     'result': {'success': False},
     'description': 'search via 2 ids matching multiple shows and multi show check'},
    {'para': {'show_id': {TVINFO_TVDB: 5555, TVINFO_TVMAZE: 123}, 'check_multishow': True},
     'result': {'tvid': TVINFO_TVMAZE, 'prodid': 123},
     'description': 'search via 2 ids matching only 1 show and multi show check'},
    {'para': {'show_id': {TVINFO_TVDB: 123, TVINFO_TVMAZE: 123}},
     'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'search via 2 ids matching only 1 show without multi show check #1'},
    {'para': {'show_id': {TVINFO_TVDB: 123, TVINFO_TVRAGE: 22}},
     'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'search via 2 ids matching only 1 show without multi show check #2'},
    {'para': {'show_id': {TVINFO_TVMAZE: 22, TVINFO_TVRAGE: 785}},
     'result': None,
     'description': 'search for 2 non-existing ids without mapping'},
    {'para': {'show_id': {TVINFO_IMDB: 123}},
     'result': None, 'description': 'invalid sid search (tvid above tvid_bitmask)'},
    {'para': {'show_id': f'{TVINFO_TVDB}:123'}, 'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'simple search via tvid_prodid string'},
    {'para': {'show_id': f'{TVINFO_TVDB}:123', 'check_multishow': True},
     'result': {'tvid': TVINFO_TVDB, 'prodid': 123},
     'description': 'simple search via tvid_prodid string and check multishow'},
]


class TVFindTests(test.SickbeardTestDBCase):
    def setUp(self):
        super(TVFindTests, self).setUp()
        sickgear.showList = []
        sickgear.showDict = {}
        sickgear.indexermapper.indexer_list = [i for i in TVInfoAPI().all_sources]
        for show in shows:
            sh = TVShow(show['tvid'], show['prodid'])
            ids = copy.deepcopy(ids_base)
            if show.get('ids'):
                for sub_ids in show['ids']:
                    ids[sub_ids].update(show['ids'][sub_ids])
            ids[show['tvid']]['status'] = indexermapper.MapStatus.SOURCE
            ids[show['tvid']]['id'] = show['prodid']
            sh.ids = ids
            sickgear.showList.append(sh)
            sickgear.showDict[sh.sid_int] = sh

    def test_find_show_by_id(self):
        result = None  # type: Optional[TVShow]
        for show_test in find_tests:
            success = True
            try:
                result = find_show_by_id(**show_test['para'])
            except MultipleShowObjectsException:
                success = False
            if isinstance(show_test['result'], dict) and None is not show_test['result'].get('success', None):
                self.assertEqual(success, show_test['result'].get('success', None),
                                 msg='error finding show (%s) with para: %s' %
                                     (show_test.get('description'), show_test['para']))
            else:
                self.assertEqual(result and {'tvid': result.tvid, 'prodid': result.prodid}, show_test['result'],
                                 msg='error finding show (%s) with para: %s' %
                                     (show_test.get('description'), show_test['para']))


if '__main__' == __name__:
    print('==================')
    print('STARTING - TV TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVShowTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVEpisodeTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVEpisodeLoadTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVLoadEpisodesTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVCacheResultTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVAiredInSeasonTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVFormatPatternTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVidProdidTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(TVFindTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
