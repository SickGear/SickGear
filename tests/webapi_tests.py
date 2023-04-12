# coding=UTF-8
# Author:
# URL: https://github.com/SickGear/SickGear
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
import itertools
import os
import unittest
import warnings
import sys
import test_lib as test

warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')

import sickgear
from exceptions_helper import ex
from sickgear.classes import SearchResult
from sickgear.common import Quality, ARCHIVED, DOWNLOADED, WANTED, UNAIRED, SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, \
    SNATCHED_ANY, SUBTITLED, statusStrings, UNKNOWN
from sickgear.event_queue import Events
from sickgear.tv import TVEpisode, TVShow
from sickgear.webserveInit import WebServer
from sickgear import webapi, scheduler, search_backlog, search_queue, show_queue, history, db
from sickgear.scene_numbering import set_scene_numbering_helper
from lib import requests
from six import integer_types, iteritems, iterkeys, itervalues, string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr

NoneType = type(None)
today = datetime.date.today()
last_week = today - datetime.timedelta(days=5)
old_date = today - datetime.timedelta(days=14)
future = today + datetime.timedelta(days=1)
far_future = today + datetime.timedelta(days=30)

if 'win32' == sys.platform:
    root_folder_tests = [
        # root_dirs, path, expected
        ('1|C:\\dir', 'C:\\folder', None),
        ('1|c:\\dir', 'c:\\dir', 'c:\\dir'),
        ('1|c:\\dir2', 'c:\\dir2\\dir', 'c:\\dir2'),
        ('1|c:\\tv_complete|c:\\tv', 'c:\\tv', 'c:\\tv')
    ]
else:
    root_folder_tests = [
        # root_dirs, path, expected
        ('1|~/dir', '~/dir/dir', '~/dir'),
        ('1|/mnt/hdd/dir', '/mnt/hdd/folder', None),
        ('1|/mnt/hdd/dir', '/mnt/hdd/dir', '/mnt/hdd/dir'),
        ('1|/mnt/hdd/dir2', '/mnt/hdd/dir2/dir', '/mnt/hdd/dir2'),
        ('1|/mnt/hdd/tv_complete|/mnt/hdd/tv', '/mnt/hdd/tv', '/mnt/hdd/tv')
    ]

test_shows = [
    {'tvid': 1, 'prodid': 1234, 'name': 'Test Show', 'runtime': 45, 'airs': 'Mondays, 00:45', 'imdbid': 'tt1234567',
     '_location': r'C:\series\show dir', 'network': 'Network', 'overview': 'Overview text', 'status': 'Continuing',
     'quality_init': [], 'quality_upgrade': [],
     'episodes': {
                1: {
                    1: {'name': 'ep1', 'status': Quality.composite_status(DOWNLOADED, Quality.HDWEBDL),
                        'airdate': old_date, 'description': 'ep1 description'},
                    2: {'name': 'ep2', 'status': WANTED, 'airdate': last_week, 'description': 'ep2 description'},
                    3: {'name': 'ep3', 'status': WANTED, 'airdate': today, 'description': 'ep3 description'},
                    4: {'name': 'ep4', 'status': UNAIRED, 'airdate': future, 'description': 'ep4 description'},
                    5: {'name': 'ep5', 'status': UNAIRED, 'airdate': far_future, 'description': 'ep5 description'},
                }
            }
     },
    {'tvid': 1, 'prodid': 5678, 'name': 'Test Show 2', 'runtime': 45, 'airs': 'Tuesdays, 22:15', 'imdbid': 'tt7775567',
     '_location': r'C:\series\show 2', 'network': 'Network 2', 'overview': 'Overview text 2', 'status': 'Continuing',
     'quality_init': [Quality.HDTV, Quality.FULLHDWEBDL], 'quality_upgrade': [Quality.FULLHDWEBDL],
     'episodes': {
                1: {
                    1: {'name': 'new ep1', 'status': UNAIRED, 'airdate': far_future, 'description': 'ep1 description'},
                    2: {'name': 'new ep2', 'status': UNAIRED, 'airdate': far_future + datetime.timedelta(days=7),
                        'description': 'ep2 description'},
                    3: {'name': 'new ep3', 'status': UNAIRED, 'airdate': far_future + datetime.timedelta(days=14),
                        'description': 'ep3 description'},
                    4: {'name': 'new ep4', 'status': UNAIRED, 'airdate': far_future + datetime.timedelta(days=28),
                        'description': 'ep4 description'},
                    5: {'name': 'new ep5', 'status': UNAIRED, 'description': 'ep5 description'},
                }
            }
     },
]


def fake_action(*args, **kwargs):
    pass


class WebAPICase(test.SickbeardTestDBCase):
    webserver = None
    instance = None

    def __init__(self, *args, **kwargs):
        super(WebAPICase, self).__init__(*args, **kwargs)
        self.org_mass_action = None
        self.show_save_db = None

    @classmethod
    def setUpClass(cls):
        super(WebAPICase, cls).setUpClass()
        # web server options
        sickgear.WEB_PORT = 8080
        cls.web_options = dict(
            host='127.0.0.1',
            port=sickgear.WEB_PORT,
            web_root=None,
            data_root=os.path.join(sickgear.PROG_DIR, 'gui', sickgear.GUI_NAME),
            log_dir=sickgear.LOG_DIR,
            username=sickgear.WEB_USERNAME,
            password=sickgear.WEB_PASSWORD,
            handle_reverse_proxy=sickgear.HANDLE_REVERSE_PROXY,
            enable_https=False,
            https_cert=None,
            https_key=None,
        )
        # start web server
        try:
            # used to check if existing SG instances have been started
            sickgear.helpers.wait_for_free_port(
                sickgear.WEB_IPV6 and '::1' or cls.web_options['host'], cls.web_options['port'])

            cls.webserver = WebServer(options=cls.web_options)
            cls.webserver.start()
            # wait for server thread to be started
            cls.webserver.wait_server_start()
            cls.webserver.switch_handlers()
            sickgear.started = True
            sickgear.API_KEYS = [['unit test key', '1234567890']]
            sickgear.USE_API = True
        except (BaseException, Exception) as e:
            print('Failed to start WebServer: %s' % ex(e))

    @classmethod
    def tearDownClass(cls):
        super(WebAPICase, cls).tearDownClass()
        # shutdown web server
        if cls.webserver:
            cls.webserver.shut_down()
            try:
                cls.webserver.join(10)
            except (BaseException, Exception):
                pass
        if cls.instance:
            super(WebAPICase, cls.instance).tearDown()

    def setUp(self):
        self.reset_show_data = False
        self.org_mass_action = None
        self.show_save_db = None
        if not WebAPICase.instance:
            WebAPICase.instance = self
            super(WebAPICase, self).setUp()
            sickgear.events = Events(None)
            sickgear.show_queue_scheduler = scheduler.Scheduler(
                show_queue.ShowQueue(),
                cycle_time=datetime.timedelta(seconds=3),
                thread_name='SHOWQUEUE')
            sickgear.search_queue_scheduler = scheduler.Scheduler(
                search_queue.SearchQueue(),
                cycle_time=datetime.timedelta(seconds=3),
                thread_name='SEARCHQUEUE')
            sickgear.backlog_search_scheduler = search_backlog.BacklogSearchScheduler(
                search_backlog.BacklogSearcher(),
                cycle_time=datetime.timedelta(minutes=60),
                run_delay=datetime.timedelta(minutes=60),
                thread_name='BACKLOG')
            sickgear.indexermapper.indexer_list = [i for i in sickgear.indexers.indexer_api.TVInfoAPI().all_sources]
            for root_dirs, path, expected in root_folder_tests:
                sickgear.ROOT_DIRS = root_dirs
            for cur_show in test_shows:
                show_obj = TVShow(cur_show['tvid'], cur_show['prodid'])
                for k, v in iteritems(cur_show):
                    if k in ('tvid', 'prodid', 'episodes', 'quality_init', 'quality_upgrade'):
                        continue
                    if '_%s' % k in show_obj.__dict__:
                        show_obj.__dict__['_%s' % k] = v
                    elif k in show_obj.__dict__:
                        show_obj.__dict__[k] = v
                if 'quality_init' in cur_show and cur_show['quality_init']:
                    show_obj.quality = Quality.combine_qualities(cur_show['quality_init'],
                                                                 cur_show.get('quality_upgrade', []))
                show_obj.dirty = True

                show_obj.save_to_db(True)
                sickgear.showList.append(show_obj)
                sickgear.showDict.update({show_obj.sid_int: show_obj})

                for season, eps in iteritems(cur_show['episodes']):
                    for ep, data in iteritems(eps):
                        ep_obj = TVEpisode(show_obj, season, ep)
                        for k, v in iteritems(data):
                            if '_%s' % k in ep_obj.__dict__:
                                ep_obj.__dict__['_%s' % k] = v
                            elif k in ep_obj.__dict__:
                                ep_obj.__dict__[k] = v
                        show_obj.sxe_ep_obj.setdefault(season, {})[ep] = ep_obj
                        ep_obj.save_to_db(True)
                        status, quality = Quality.split_composite_status(ep_obj.status)
                        if status in (DOWNLOADED, SNATCHED):
                            s_r = SearchResult([ep_obj])
                            s_r.show_obj, s_r.quality, s_r.provider, s_r.name = \
                                show_obj, quality, None, '%s.S%sE%s.group' % (
                                    show_obj.name, ep_obj.season, ep_obj.episode)
                            history.log_snatch(s_r)
                            if DOWNLOADED == status:
                                history.log_download(ep_obj, '%s.S%sE%s.group.mkv' % (
                                    show_obj.name, ep_obj.season, ep_obj.episode), quality, 'group')

            sickgear.webserve.Home.make_showlist_unique_names()

    def tearDown(self):
        if None is not self.org_mass_action:
            db.DBConnection.mass_action = self.org_mass_action
        if None is not self.show_save_db:
            sickgear.tv.TVShow.save_to_db = self.show_save_db
        sickgear.show_queue_scheduler.action.queue = []
        sickgear.search_queue_scheduler.action.queue = []
        if self.reset_show_data:
            for cur_show in test_shows:
                show_obj = sickgear.helpers.find_show_by_id({cur_show['tvid']: cur_show['prodid']})
                if 'quality_init' in cur_show and cur_show['quality_init']:
                    show_obj.quality = Quality.combine_qualities(cur_show['quality_init'],
                                                                 cur_show.get('quality_upgrade', []))
                else:
                    show_obj.quality = int(sickgear.QUALITY_DEFAULT)
                show_obj.upgrade_once = int(cur_show.get('upgrade_once', 0))
                show_obj.scene = int(cur_show.get('scene', 0))
                show_obj.save_to_db()
                for season, data in iteritems(cur_show['episodes']):
                    for ep_nb, cur_ep in iteritems(data):
                        ep_obj = show_obj.get_episode(season, ep_nb)
                        ep_obj.status = cur_ep.get('status')
                        ep_obj.save_to_db()
                        set_scene_numbering_helper(
                            cur_show['tvid'], cur_show['prodid'], season, ep_nb,
                            scene_season=cur_ep.get('scene_season'), scene_episode=cur_ep.get('scene_episode'))

    @staticmethod
    def _request_from_api(cmd, params=None):
        param = {'cmd': webapi._functionMaper_reversed[cmd]}
        if isinstance(params, dict):
            param.update(params)
        return requests.get('http://127.0.0.1:%s/api/%s' % (sickgear.WEB_PORT, sickgear.API_KEYS[0][1]),
                            params=param).json()

    @staticmethod
    def _check_types(data, fields):
        result, msg = True, []
        missing_list, wrong_type = [], {}
        for f in fields:
            if f[0] not in data:
                missing_list.append(f[0])
                result = False
            elif not isinstance(data[f[0]], f[1]):
                wrong_type[f[0]] = 'Expected: %s, Got: %s' % (type(data[f[0]]), str(f[1]))
                result = False
        if missing_list:
            msg.append('Missing fields: %s' % ', '.join(missing_list))
        if wrong_type:
            msg.append('Wrong field type: %s' % ', '.join(['%s: %s' % (k, v) for k, v in iteritems(wrong_type)]))
        return result, ('', ', %s' % ', '.join(msg))[0 < len(msg)]

    def _check_success_base_response(self, data, endpoint, message='', data_type=dict):
        # type: (Any, Any, AnyStr, type) -> None
        r, msg = self._check_types(data, [('result', string_types), ('data', data_type), ('message', string_types)])
        self.assertTrue(r, msg='Failed command: %s%s' % (webapi._functionMaper_reversed[endpoint], msg))
        self.assertEqual(data['result'], 'success')
        self.assertEqual(data['message'], message)

    def _check_episode_data(self, data, endpoint):
        r, msg = self._check_types(
            data,
            [('absolute_number', integer_types), ('airdate', string_types), ('description', string_types),
             ('name', string_types), ('quality', string_types), ('scene_absolute_number', integer_types),
             ('scene_episode', integer_types), ('scene_season', integer_types), ('status', string_types),
             ('timezone', (NoneType, string_types))]
        )
        self.assertTrue(r, msg='Failed command: %s - data episode dict%s' % (
            webapi._functionMaper_reversed[endpoint], msg))

    def test_sg(self):
        data = self._request_from_api(webapi.CMD_SickGear)
        r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
        self.assertTrue(r, msg='Failed command: %s%s' % (webapi._functionMaper_reversed[webapi.CMD_SickGear], msg))
        r, msg = self._check_types(data['data'], [('api_commands', list), ('api_version', integer_types),
                                             ('fork', string_types), ('sb_version', string_types)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGear], msg))
        needed_ele = [(k, string_types) for k in iterkeys(webapi._functionMaper) if 'listcommands' != k]
        r = all(v[0] in data['data']['api_commands'] for v in needed_ele)
        if not r:
            i = list(set(n[0] for n in needed_ele) - set(data['data']['api_commands']))
        else:
            i = []
        self.assertTrue(r, msg='Failed command: %s - api_commands list%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGear], ('', ', missing: %s' % ','.join(i))[0 < len(i)]))

    def _check_show_fields(self, data, endpoint, include_season_list=True):
        r, msg = self._check_types(
            data,
            [('air_by_date', integer_types), ('airs', string_types), ('anime', integer_types), ('cache', dict),
             ('classification', string_types), ('flatten_folders', integer_types), ('genre', list),
             ('global_exclude_ignore', string_types), ('global_exclude_require', string_types), ('ids', dict),
             ('ignorewords', string_types), ('imdb_id', string_types), ('indexer', integer_types),
             ('indexerid', integer_types), ('language', string_types), ('location', string_types),
             ('network', string_types), ('next_ep_airdate', string_types), ('paused', integer_types),
             ('prune', integer_types), ('quality', string_types), ('quality_details', dict),
             ('requirewords', string_types), ('runtime', integer_types), ('scenenumbering', bool),
             ('show_name', string_types), ('sports', integer_types), ('startyear', integer_types),
             ('status', string_types), ('subtitles', integer_types), ('tag', string_types),
             ('timezone', (NoneType, string_types)), ('tvrage_id', integer_types),
             ('tvrage_name', string_types), ('upgrade_once', integer_types)] +
            ([], [('season_list', list)])[include_season_list]
        )
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[endpoint], msg))
        r, msg = self._check_types(data['ids'],
                                   [('%s' % k, integer_types) for k in sickgear.indexermapper.indexer_list])
        self.assertTrue(r, msg='Failed shows "ids" check: %s' % msg)
        r, msg = self._check_types(
            data['quality_details'],
            [('archive', list), ('initial', list)]
        )
        self.assertTrue(r, msg='Failed shows "quality_details" check: %s' % msg)

    def test_show(self):
        # test not found
        data = self._request_from_api(webapi.CMD_SickGearShow, params={'indexer': 1, 'indexerid': 98765})
        r, msg = self._check_types(data, [('result', string_types), ('data', dict), ('message', string_types)])
        self.assertTrue(r, msg='Failed command: %s%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearShow], msg))
        self.assertEqual(data['result'], 'failure')
        self.assertEqual(data['message'], 'Show not found')
        # test existing show
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShow,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShow)
            self._check_show_fields(data['data'], webapi.CMD_SickGearShow)

    def test_seasons(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowSeasons,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowSeasons)
            for season, eps in iteritems(cur_show['episodes']):
                r, msg = self._check_types(data['data'], [('%s' % season, dict)])
                self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                    webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasons], msg))
                for cur_ep in iterkeys(eps):
                    r, msg = self._check_types(data['data']['%s' % season], [('%s' % cur_ep, dict)])
                    self.assertTrue(r, msg='Failed command: %s - data season dict%s' % (
                        webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasons], msg))
                    self._check_episode_data(data['data']['%s' % season]['%s' % cur_ep], webapi.CMD_SickGearShowSeasons)

    def test_coming_episodes(self):
        data = self._request_from_api(webapi.CMD_SickGearComingEpisodes)
        self._check_success_base_response(data, webapi.CMD_SickGearComingEpisodes)
        r, msg = self._check_types(data['data'], [('later', list), ('missed', list), ('soon', list), ('today', list)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearComingEpisodes], msg))
        self.assertTrue(all(0 < len(data['data'][t]) for t in ('later', 'missed', 'soon', 'today')),
                        msg='Not all categories returned')
        for t_p in ('later', 'missed', 'soon', 'today'):
            for cur_ep in data['data'][t_p]:
                r, msg = self._check_types(
                    cur_ep,
                    [('airdate', string_types), ('airs', string_types), ('data_network', string_types),
                     ('data_show_name', string_types), ('ep_name', string_types), ('ep_plot', string_types),
                     ('episode', integer_types), ('ids', dict), ('local_datetime', string_types),
                     ('network', string_types), ('parsed_datetime', string_types), ('paused', integer_types),
                     ('prod_id', integer_types), ('quality', string_types), ('runtime', integer_types),
                     ('season', integer_types), ('show_name', string_types), ('show_status', string_types),
                     ('status', integer_types), ('status_str', string_types), ('timezone', (NoneType, string_types)),
                     ('tv_id', integer_types), ('tvdbid', integer_types), ('weekday', integer_types)]
                )
                self.assertTrue(r, msg='Failed command: %s - data %s dict%s' % (
                    webapi._functionMaper_reversed[webapi.CMD_SickGearComingEpisodes], t_p, msg))
                r, msg = self._check_types(cur_ep['ids'],
                                           [('%s' % k, integer_types) for k in sickgear.indexermapper.indexer_list])
                self.assertTrue(r, msg='Failed %s "ids" check: %s' % (t_p, msg))

    def test_all_shows(self):
        data = self._request_from_api(webapi.CMD_SickGearShows)
        self._check_success_base_response(data, webapi.CMD_SickGearShows)
        for show_id, cur_show in iteritems(data['data']):
            self._check_show_fields(cur_show, webapi.CMD_SickGearShows, include_season_list=False)

    def test_episode(self):
        # not found episode
        data = self._request_from_api(webapi.CMD_SickGearEpisode,
                                      params={'indexer': 1, 'indexerid': 1234, 'season': 10, 'episode': 11})
        r, msg = self._check_types(data, [('result', string_types), ('data', dict), ('message', string_types)])
        self.assertTrue(r, msg='Failed command: %s%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearEpisode], msg))
        self.assertEqual(data['result'], 'error')
        self.assertEqual(data['message'], 'Episode not found')
        # found episode
        for cur_show in test_shows:
            for season, eps in iteritems(cur_show['episodes']):
                for cur_ep in iterkeys(eps):
                    data = self._request_from_api(webapi.CMD_SickGearEpisode,
                                                  params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid'],
                                                          'season': season, 'episode': cur_ep})
                    self._check_success_base_response(data, webapi.CMD_SickGearEpisode)
                    r, msg = self._check_types(
                        data['data'],
                        [('absolute_number', integer_types), ('airdate', string_types), ('description', string_types),
                         ('file_size', integer_types), ('file_size_human', string_types), ('location', string_types),
                         ('name', string_types), ('quality', string_types), ('release_name', string_types),
                         ('scene_absolute_number', (NoneType, integer_types)),
                         ('scene_episode', (NoneType, integer_types)), ('scene_season', (NoneType, integer_types)),
                         ('status', string_types), ('subtitles', string_types), ('timezone', (NoneType, string_types))]
                    )
                    self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                        webapi._functionMaper_reversed[webapi.CMD_SickGearEpisode], msg))

    def test_shutdown(self):
        data = self._request_from_api(webapi.CMD_SickGearShutdown)
        r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
        self.assertTrue(r, msg='basic test failed for shutdown')
        self.assertEqual(data['message'], 'SickGear is shutting down...')
        self.assertEqual(data['result'], 'success')

    def test_restart(self):
        data = self._request_from_api(webapi.CMD_SickGearRestart)
        r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
        self.assertTrue(r, msg='basic test failed for shutdown')
        self.assertEqual(data['message'], 'SickGear is restarting...')
        self.assertEqual(data['result'], 'success')

    def test_ping(self):
        data = self._request_from_api(webapi.CMD_SickGearPing)
        r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
        self.assertTrue(r, msg='basic test failed for shutdown')
        self.assertEqual(data['message'], 'Pong')
        self.assertEqual(data['result'], 'success')

    def test_get_indexers(self):
        data = self._request_from_api(webapi.CMD_SickGearGetIndexers)
        self._check_success_base_response(data, webapi.CMD_SickGearGetIndexers)
        r, msg = self._check_types(data['data'], [('%s' % k, dict) for k in sickgear.indexermapper.indexer_list])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearGetIndexers], msg))
        for i in sickgear.indexermapper.indexer_list:
            r, msg = self._check_types(
                data['data']['%s' % i],
                [('id', integer_types), ('main_url', string_types), ('name', string_types), ('searchable', bool),
                 ('show_url', string_types)])
            self.assertTrue(r, msg='Failed command: %s - data %s dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearGetIndexers], i, msg))

    def test_get_seasonlist(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowSeasonList,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowSeasonList, data_type=list)
            r = all(isinstance(v, integer_types) for v in data['data'])
            self.assertTrue(r, msg='Failed command: %s - data dict incorrect type' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasonList]))

    def test_get_episodelist(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowSeasons,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowSeasons)
            r, msg = self._check_types(data['data'], [('%s' % i, dict) for i in iterkeys(cur_show['episodes'])])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasons], msg))
            for season, eps in iteritems(cur_show['episodes']):
                r, msg = self._check_types(data['data'], [('%s' % season, dict)])
                self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                    webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasons], msg))
                for cur_ep in iterkeys(eps):
                    r, msg = self._check_types(data['data']['%s' % season], [('%s' % cur_ep, dict)])
                    self.assertTrue(r, msg='Failed command: %s - data season dict%s' % (
                        webapi._functionMaper_reversed[webapi.CMD_SickGearShowSeasons], msg))
                    self._check_episode_data(data['data']['%s' % season]['%s' % cur_ep], webapi.CMD_SickGearShowSeasons)

    def test_get_require_words(self):
        # global
        data = self._request_from_api(webapi.CMD_SickGearListRequireWords)
        self._check_success_base_response(data, webapi.CMD_SickGearListRequireWords, message='Global require word list')
        r, msg = self._check_types(data['data'], [('require words', list), ('type', string_types), ('use regex', bool)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearListRequireWords], msg))
        # show based
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearListRequireWords,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearListRequireWords,
                                              message='%s: require word list' % cur_show['name'])
            r, msg = self._check_types(
                data['data'],
                [('require words', list), ('type', string_types), ('use regex', bool),
                 ('global exclude require', list), ('indexer', integer_types), ('indexerid', integer_types),
                 ('show name', string_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearListRequireWords], msg))

    def test_get_ignore_words(self):
        # global
        data = self._request_from_api(webapi.CMD_SickGearListIgnoreWords)
        self._check_success_base_response(data, webapi.CMD_SickGearListIgnoreWords, message='Global ignore word list')
        r, msg = self._check_types(data['data'], [('ignore words', list), ('type', string_types), ('use regex', bool)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearListIgnoreWords], msg))
        # show based
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearListIgnoreWords,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearListIgnoreWords,
                                              message='%s: ignore word list' % cur_show['name'])
            r, msg = self._check_types(
                data['data'],
                [('ignore words', list), ('type', string_types), ('use regex', bool),
                 ('global exclude ignore', list), ('indexer', integer_types), ('indexerid', integer_types),
                 ('show name', string_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearListIgnoreWords], msg))

    def test_get_search_queue(self):
        data = self._request_from_api(webapi.CMD_SickGearSearchQueue)
        self._check_success_base_response(data, webapi.CMD_SickGearSearchQueue)
        r, msg = self._check_types(
            data['data'],
            [(t, list) for t in ('backlog', 'failed', 'manual', 'proper')] + [('recent', integer_types)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearSearchQueue], msg))

    def test_get_system_default(self):
        data = self._request_from_api(webapi.CMD_SickGearGetDefaults)
        self._check_success_base_response(data, webapi.CMD_SickGearGetDefaults)
        r, msg = self._check_types(
            data['data'],
            [('archive', list), ('flatten_folders', integer_types), ('future_show_paused', integer_types),
             ('initial', list), ('status', string_types)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearGetDefaults], msg))

    def test_get_all_qualities(self):
        data = self._request_from_api(webapi.CMD_SickGearGetQualities)
        self._check_success_base_response(data, webapi.CMD_SickGearGetQualities)
        r, msg = self._check_types(data['data'], [(q, integer_types) for q in iterkeys(webapi.quality_map)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearGetQualities], msg))

    def test_get_human_qualities(self):
        data = self._request_from_api(webapi.CMD_SickGearGetqualityStrings)
        self._check_success_base_response(data, webapi.CMD_SickGearGetqualityStrings)
        r, msg = self._check_types(data['data'], [('%s' % q, string_types) for q in iterkeys(Quality.qualityStrings)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearGetqualityStrings], msg))

    def test_get_scene_qualities(self):
        # global
        data = self._request_from_api(webapi.CMD_SickGearExceptions)
        self._check_success_base_response(data, webapi.CMD_SickGearExceptions)
        r = all(isinstance(e, string_types) for e in data['data'])
        self.assertTrue(r, msg='Failed command: %s - data dict' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearExceptions]))
        # show specific
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearExceptions,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearExceptions, data_type=list)
            r = all(isinstance(e, string_types) for e in data['data'])
            self.assertTrue(r, msg='Failed command: %s - data dict' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearExceptions]))

    def test_history(self):
        data = self._request_from_api(webapi.CMD_SickGearHistory)
        self._check_success_base_response(data, webapi.CMD_SickGearHistory, data_type=list)
        for cur_show in data['data']:
            self.assertTrue(isinstance(cur_show, dict), msg='wrong type')
            r, msg = self._check_types(
                cur_show,
                [('date', string_types), ('episode', integer_types), ('indexer', integer_types),
                 ('indexerid', integer_types), ('provider', string_types), ('quality', string_types),
                 ('resource', string_types), ('resource_path', string_types), ('season', integer_types),
                 ('show_name', string_types), ('status', string_types), ('tvdbid', integer_types),
                 ('version', integer_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearHistory], msg))

    def test_shows_stats(self):
        data = self._request_from_api(webapi.CMD_SickGearShowsStats)
        self._check_success_base_response(data, webapi.CMD_SickGearShowsStats)
        r, msg = self._check_types(
            data['data'],
            [('ep_downloaded', integer_types), ('ep_total', integer_types), ('shows_active', integer_types),
             ('shows_total', integer_types)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearShowsStats], msg))

    def test_show_stats(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowStats,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowStats)
            r, msg = self._check_types(
                data['data'],
                [(statusStrings.statusStrings[status].lower().replace(" ", "_").replace("(", "").replace(
                    ")", ""), integer_types) for status in statusStrings.statusStrings
                 if status not in SNATCHED_ANY + [UNKNOWN, DOWNLOADED]] + [('downloaded', dict), ('snatched', dict)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearShowStats], msg))
            for s in ('downloaded', 'snatched'):
                r, msg = self._check_types(
                    data['data'][s],
                    [(t.lower().replace(" ", "_").replace("(", "").replace(")", ""), integer_types)
                     for k, t in iteritems(Quality.qualityStrings) if Quality.NONE != k])
                self.assertTrue(r, msg='Failed command: %s - data dict - %s:%s' % (
                    webapi._functionMaper_reversed[webapi.CMD_SickGearShowStats], s, msg))

    def test_get_root_dirs(self):
        data = self._request_from_api(webapi.CMD_SickGearGetRootDirs)
        self._check_success_base_response(data, webapi.CMD_SickGearGetRootDirs, data_type=list)
        for r_d in data['data']:
            r, msg = self._check_types(r_d, [('default', integer_types), ('location', string_types),
                                             ('valid', integer_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearListIgnoreWords], msg))

    def test_get_schedules(self):
        data = self._request_from_api(webapi.CMD_SickGearCheckScheduler)
        self._check_success_base_response(data, webapi.CMD_SickGearCheckScheduler)
        r, msg = self._check_types(
            data['data'],
            [('backlog_is_paused', integer_types), ('backlog_is_running', integer_types),
             ('last_backlog', string_types), ('next_backlog', string_types)])
        self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
            webapi._functionMaper_reversed[webapi.CMD_SickGearCheckScheduler], msg))

    def test_do_show_update(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowUpdate,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowUpdate,
                                              message='%s has queued to be updated' % cur_show['name'])
        # check that duplicate adding fails
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowUpdate,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearShowUpdate], msg))
            self.assertTrue('Unable to update %s.' % cur_show['name'] in data['message'], msg='Wrong failure message')

    def test_do_show_refresh(self):
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowRefresh,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            self._check_success_base_response(data, webapi.CMD_SickGearShowUpdate,
                                              message='%s has queued to be refreshed' % cur_show['name'])
        # check that duplicate adding fails
        for cur_show in test_shows:
            data = self._request_from_api(webapi.CMD_SickGearShowRefresh,
                                          params={'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']})
            r, msg = self._check_types(data, [('data', dict), ('message', string_types), ('result', string_types)])
            self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                webapi._functionMaper_reversed[webapi.CMD_SickGearShowRefresh], msg))
            self.assertTrue('Unable to refresh %s.' % cur_show['name'] in data['message'], msg='Wrong failure message')

    def test_pause_show(self):
        self.reset_show_data = True
        self.show_save_db = sickgear.tv.TVShow.save_to_db
        sickgear.tv.TVShow.save_to_db = fake_action
        for set_pause in (None, 0, 1, 0):
            for cur_show in test_shows:
                params = {'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']}
                if None is not set_pause:
                    params.update({'pause': set_pause})
                data = self._request_from_api(webapi.CMD_SickGearShowPause, params=params)
                self._check_success_base_response(data, webapi.CMD_SickGearShowPause,
                                                  message='%s has been %spaused' % (
                                                      cur_show['name'], ('', 'un')[set_pause in (None, 0, False)]))

    def test_set_scene_numbering(self):
        self.reset_show_data = True
        self.show_save_db = sickgear.tv.TVShow.save_to_db
        sickgear.tv.TVShow.save_to_db = fake_action
        for set_scene in (1, 0):
            for cur_show in test_shows:
                params = {'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']}
                if None is not set_scene:
                    params.update({'activate': set_scene})
                data = self._request_from_api(webapi.CMD_SickGearActivateSceneNumber, params=params)
                self._check_success_base_response(data, webapi.CMD_SickGearActivateSceneNumber,
                                                  message='Scene Numbering %sactivated' % (
                                                      ('', 'de')[set_scene in (None, 0, False)]))
                r, msg = self._check_types(
                    data['data'],
                    [('indexer', integer_types), ('indexerid', integer_types), ('scenenumbering', bool),
                     ('show_name', string_types)])
                self.assertTrue(r, msg='Failed command: %s - data dict%s' % (
                    webapi._functionMaper_reversed[webapi.CMD_SickGearActivateSceneNumber], msg))
                self.assertTrue(data['data']['scenenumbering'] == bool(set_scene))
                self.assertTrue(data['data']['show_name'] == cur_show['name'])

    def test_set_show_quality(self):
        self.reset_show_data = True
        self.show_save_db = sickgear.tv.TVShow.save_to_db
        sickgear.tv.TVShow.save_to_db = fake_action
        for set_quality in [
            {'init': [Quality.SDTV],
             'upgrade': [],
             'upgrade_once': 0},
            {'init': [Quality.SDTV],
             'upgrade': [],
             'upgrade_once': 1},
            {'init': [Quality.SDTV],
             'upgrade': [Quality.FULLHDWEBDL, Quality.FULLHDBLURAY],
             'upgrade_once': 0},
            {'init': [Quality.SDTV],
             'upgrade': [Quality.FULLHDWEBDL, Quality.FULLHDBLURAY],
             'upgrade_once': 1},
            {'init': [Quality.SDTV, Quality.SDDVD, Quality.HDTV],
             'upgrade': [],
             'upgrade_once': 0},
            {'init': [Quality.SDTV, Quality.SDDVD, Quality.HDTV],
             'upgrade': [],
             'upgrade_once': 1},
            {'init': [Quality.SDTV, Quality.SDDVD, Quality.HDTV],
             'upgrade': [Quality.SDDVD, Quality.HDWEBDL],
             'upgrade_once': 0},
            {'init': [Quality.SDTV, Quality.SDDVD, Quality.HDTV],
             'upgrade': [Quality.SDDVD, Quality.HDWEBDL],
             'upgrade_once': 1},
        ]:
            for cur_show in test_shows:
                show_obj = sickgear.helpers.find_show_by_id({cur_show['tvid']: cur_show['prodid']})
                params = {'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']}
                for t in ('init', 'upgrade', 'upgrade_once'):
                    if set_quality[t]:
                        params.update({t: set_quality[t]})
                data = self._request_from_api(webapi.CMD_SickGearShowSetQuality, params=params)
                self._check_success_base_response(
                    data,
                    webapi.CMD_SickGearShowSetQuality,
                    message='%s quality has been changed to %s' % (
                        cur_show['name'], webapi._get_quality_string(show_obj.quality)))
                self.assertEqual(show_obj.upgrade_once, int(set_quality['upgrade_once']))

    def test_set_show_scene_numbers(self):
        self.reset_show_data = True
        self.show_save_db = sickgear.tv.TVShow.save_to_db
        sickgear.tv.TVShow.save_to_db = fake_action
        for set_numbers in [
            {'forSeason': 1,
             'forEpisode': 1,
             'forAbsolute': None,
             'sceneSeason': 1,
             'sceneEpisode': 2,
             'sceneAbsolute': None,
             },
        ]:
            for cur_show in test_shows:
                params = {'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid']}
                set_scene_params = params.copy()
                set_scene_params.update({'activate': 1})
                data = self._request_from_api(webapi.CMD_SickGearActivateSceneNumber,
                                              params=set_scene_params)
                self._check_success_base_response(data, webapi.CMD_SickGearActivateSceneNumber,
                                                  message='Scene Numbering activated')
                for t in ('forSeason', 'forEpisode', 'forAbsolute', 'sceneSeason', 'sceneEpisode', 'sceneAbsolute'):
                    if set_numbers[t]:
                        params.update({t: set_numbers[t]})
                data = self._request_from_api(webapi.CMD_SickGearSetSceneNumber, params=params)
                self._check_success_base_response(data, webapi.CMD_SickGearSetSceneNumber)
                self._check_types(
                    data['data'],
                    [(t, integer_types) for t in ('forSeason', 'forEpisode', 'sceneSeason', 'sceneEpisode')] +
                    [('success', bool)])
                for t in ('forSeason', 'forEpisode', 'sceneSeason', 'sceneEpisode'):
                    self.assertEqual(data['data'][t], set_numbers[t])

    def test_set_episode_status(self):
        self.org_mass_action = db.DBConnection.mass_action
        db.DBConnection.mass_action = fake_action
        self.reset_show_data = True
        failed_msg = 'Failed to set all or some status. Check data.'
        success_msg = 'All status set successfully.'
        for cur_quality_str, cur_quality in itertools.chain(iteritems(webapi.quality_map), iteritems({'None': None})):
            for cur_value, cur_status in iteritems(statusStrings.statusStrings):
                if (cur_quality and cur_value not in (SNATCHED, DOWNLOADED, ARCHIVED)) or \
                        (None is cur_quality and SNATCHED == cur_value):
                    continue
                cur_status = cur_status.lower()
                # print('Testing setting episode status to: %s %s' % (cur_status, cur_quality_str))
                if cur_value in (UNKNOWN, UNAIRED, SNATCHED_PROPER, SNATCHED_BEST, SUBTITLED):
                    continue
                for cur_show in test_shows:
                    for season, eps in iteritems(cur_show['episodes']):
                        for ep_nb, cur_ep in iteritems(eps):
                            ep_obj = sickgear.helpers.find_show_by_id({cur_show['tvid']: cur_show['prodid']}).\
                                get_episode(season, ep_nb)
                            params = {'indexer': cur_show['tvid'], 'indexerid': cur_show['prodid'], 'season': season,
                                      'episode': ep_nb, 'status': cur_status}
                            if cur_quality:
                                params.update({'quality': cur_quality_str})
                            old_status = ep_obj.status
                            status, quality = Quality.split_composite_status(ep_obj.status)
                            expect_fail = UNAIRED == status or (DOWNLOADED == status and not cur_quality)
                            expected_msg = (success_msg, failed_msg)[expect_fail]
                            data = self._request_from_api(webapi.CMD_SickGearEpisodeSetStatus, params=params)
                            r, msg = self._check_types(data,
                                                       [('result', string_types), ('data', (dict, list)[expect_fail]),
                                                        ('message', string_types)])
                            self.assertTrue(r, msg=msg)
                            self.assertTrue(data['message'].startswith(expected_msg))
                            # reset status
                            ep_obj.status = old_status
                            # ep_obj.save_to_db()


if __name__ == '__main__':
    print('==================')
    print('STARTING - WebAPI TESTS')
    print('==================')
    print('######################################################################')
    suite = unittest.TestLoader().loadTestsFromTestCase(WebAPICase)
    unittest.TextTestRunner(verbosity=2).run(suite)
