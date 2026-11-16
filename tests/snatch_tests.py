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

import datetime
import logging
import os
import random
import re
import shutil
import unittest
from unittest import mock
from urllib.parse import urlparse, parse_qs

import test_lib as test  # must be before import sg_helpers and sickgear
import sg_helpers
import sickgear
from sickgear import common, db, failed_history, history, search_queue, helpers, indexermapper, \
    network_timezones
from sickgear.common import Quality, VideoCodec
from sickgear.indexers.indexer_api import TVInfoAPI
from sickgear.indexers.indexer_config import TVINFO_TVDB
from sickgear.tv import TVEpisode, TVShow
from sickgear.providers import newznab
from sickgear.providers.newznab import NewznabProvider
from sickgear.search_queue import ProperSearchQueueItem, FailedQueueItem

sickgear.search_propers_scheduler = sickgear.scheduler.Scheduler(
        sickgear.search_propers.ProperSearcher(),
        cycle_time=datetime.timedelta(days=1),
        run_delay=datetime.timedelta(minutes=30),
        thread_name='PROPERSSEARCH')

newznab_downlaod_url_match = re.compile(r'http://[^/]+/api\?t=get&(?:amp;)?id=', flags=re.I)

test_show_house = {
    'show_name': 'House',
    'show_tvid': TVINFO_TVDB,
    'show_prodid': 123456,
    'start_year': 2000,
    'runtime': 40,
    'network': 'cbs',
    'status': 'Ended',
    'airs': 'Monday',
    'genre': 'crime',
    'quality': Quality.combine_qualities(
    [Quality.SDTV, Quality.SDDVD, Quality.HDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB,
     Quality.HDBLURAY, Quality.FULLHDBLURAY],
    [Quality.SDDVD, Quality.HDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB,
     Quality.HDBLURAY, Quality.FULLHDBLURAY]),
    'episodes': [
        {'season': 1, 'ep_count': 21, 'ep_data': {}},
        {'season': 2, 'ep_count': 10, 'ep_data': {}},
        {'season': 3, 'ep_count': 25, 'ep_data': {}}
    ]
}

test_show_house_item = {
    'release_name': 'House.s01e01.1080p.webrip.x264-grp',
    'show_name': 'House',
    'season': 1,
    'episode': 1,
    'quality': Quality.FULLHDWEBDL,
    'group': 'grp',
    'proper': '',
    'codec': VideoCodec.VC_264,
    'ep_title': '',
    'size': 7987669856,
    'tvdbid': 123456,
    'pubDate': datetime.datetime(2026, 2, 6, 19,58, 6, tzinfo=test.tzinfo_newznab),  # 'Fri, 06 Feb 2026 19:58:06 +0000',
    'guid': test.guid_generator(),
    'item_category': 'TV > HD',
    'category_id': 5000,
    'category_sub_id': 5040,
}

recent_search_tests = [
    {
        'show_data': test_show_house,
        'episodes': [
            {'season': 1, 'episodes': 1,'status': common.UNAIRED,
             'airdate': datetime.date.today() - datetime.timedelta(days=3)},
                     ],
        'tests': [
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024**2 * 1000}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1'}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1'}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024**2 * 600}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024**2 * 1805}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1', 'failed': True}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'nzb_method': 'all'
            },
        ]
    },
]

proper_search_tests = [
    {
        'show_data': test_show_house,
        'tests': [
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1', 'proper': True, 'must_be_proper': True,
                             'p_types': ['proper', 'repack', 'real']}
                          ],
                        'base_item': test_show_house_item
                    }
                ]
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1', 'proper': True, 'must_be_proper': True,
                             'p_types': ['proper', 'repack', 'real']}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
            },
        ]
    }
]

backlog_search_tests = [
    {
        'show_data': test_show_house,
        'tests': [
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 600}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 1200}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 1805}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1,
                             'size': 1024 ** 2 * 1000 * 22}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1,
                             'size': 1024 ** 2 * 600}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': '1-5,10-12,15,17,19-20'}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'},
                            {'season': 1, 'episodes': '5,6,9',
                             'size': 1024**2*600}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'},
                            {'season': 1, 'episodes': '1-5,7,9-20',
                             'size': 1024**2*600},
                            {'season': 1, 'episodes': '2,19',
                             'failed': True}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1},
                'nzb_method': 'all'
            }
        ]
    }
]

manual_search_tests = [
    {
        'show_data': test_show_house,
        'tests': [
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 600}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': '1,2'},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 1200}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': '1,2'},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1/2',
                             'size': 1024 ** 2 * 1805}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': '1,2'},
                'search_fallback': True
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': 2}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': 2}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'},
                            {'season': 1, 'episodes': 2,
                             'size': 1024**2*600}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1, 'episodes': 2}
            },
        ]
    }
]

failed_search_tests = [
    {
        'show_data': test_show_house,
        'tests': [
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'}
                          ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1}
            },
            {
                'items_gen': [
                    {
                        'ep_nbs': [
                            {'season': 1, 'episodes': '1-20'},
                            {'season': 2, 'episodes': '5,6,9'},
                            {'season': 1, 'episodes': 2,
                             'size': 1024 ** 2 * 600}
                        ],
                        'base_item': test_show_house_item
                    }
                ],
                'search': {'season': 1}
            },
        ]
    }
]


proper_found_leg_reges = re.compile(r'Found Proper \[(.+)\]', flags=re.I)
proper_regex = re.compile(r'\b(?:repack|proper|real)\b', flags=re.I)
puid_regex = re.compile(r'^\[[^]]+]]-(.+)$', flags=re.I)
_all_clients = ['blackhole', 'sabnzbd', 'nzbget']


# helper class to call post processing withoug runngin webserver
class mock_web():
    def send_message(self, *args, **kwargs):
        pass

    def redirect(self, *args, **kwargs):
        pass


class mock_class():
    pass


class SnatchTestLogger(logging.Handler):

    def __init__(self, level=0, processor=None):
        super().__init__(level)
        self._processor = processor

    def emit(self, record):
        if None is not self._processor:
            self._processor(record)


class SearchTest(test.SickbeardTestDBCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result_data = []
        self._failed_results = []
        self._proper_results = []
        self._set_failed = []
        self.expected_res = []
        self.expected_proper_res = []
        self.count = 300
        self._nzbget_host = 'localhost:9876'
        self._sab_host = r'http://localhost:9875/'
        self.show_dir = os.path.join(sickgear.DATA_DIR, 'shows')
        self.download_dir = os.path.join(sickgear.DATA_DIR, 'download')
        self._proper_search_run = None

    @classmethod
    def tearDownClass(cls):
        super(SearchTest, cls).tearDownClass()
        # the mock get_url fails the network timezone fetch, its retry delay would stop the fetch of tests that run later
        network_timezones.reset_last_retry()

    def setUp(self):
        super().setUp()
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.show_dir, exist_ok=True)
        sickgear.ROOT_DIRS = self.show_dir
        sickgear.PROCESS_METHOD = 'move'
        sickgear.TV_DOWNLOAD_DIR = self.download_dir
        self.count = 300
        self._proper_search_run = None
        sickgear.USE_FAILED_DOWNLOADS = True
        sickgear.search_queue_scheduler = mock_class()
        sickgear.search_queue_scheduler.action = mock_class()
        sickgear.search_queue_scheduler.action.add_item = self._mock_add_item
        sickgear.USE_NZBS = True
        sickgear.tv.TVEpisode.specify_episode = test.org_specify_episode
        self._xem_refresh = sickgear.scene_numbering.xem_refresh
        sickgear.scene_numbering.xem_refresh = self.mock_xem_refresh
        sickgear.WANTEDLIST_CACHE = common.WantedQualities()
        self._old_serverproxy = sickgear.nzbget.ServerProxy
        sickgear.nzbget.ServerProxy = test.MockServerProxy(self._process_nzbget_responce)
        # skip provider paging delays, they made this test take minutes
        self._old_newznab_time = newznab.time
        newznab.time = mock.Mock(wraps=newznab.time, sleep=lambda *_: None)
        self._old_get_url = sg_helpers.get_url
        sg_helpers.get_url = self.mock_get_url
        helpers.get_url = self.mock_get_url
        self.logger = SnatchTestLogger(processor=self._process_log)
        logging.getLogger().addHandler(self.logger)
        sickgear.indexermapper.indexer_list = [i for i in TVInfoAPI().all_sources
                                               if TVInfoAPI(i).config.get('show_url')
                                               and True is not TVInfoAPI(i).config.get('people_only')]
        self.mock_provider_domains = []
        sickgear.name_parser.parser.name_parser_cache = sickgear.name_parser.parser.NameParserCache()
        # settings changed below, restored at tearDown so that tests that run later are not affected
        self._old_settings = {k: getattr(sickgear, k) for k in (
            'NZB_METHOD', 'NZBGET_USE_HTTPS', 'NZBGET_HOST', 'NZBGET_CATEGORY', 'NZBGET_USERNAME',
            'NZBGET_PASSWORD', 'SAB_HOST', 'SAB_APIKEY', 'SAB_CATEGORY', 'SAB_PASSWORD', 'SAB_USERNAME',
            'NZB_DIR')}
        sickgear.NZB_METHOD = 'nzbget'
        sickgear.NZBGET_USE_HTTPS = False
        sickgear.NZBGET_HOST = self._nzbget_host
        sickgear.NZBGET_CATEGORY = 'Series'
        sickgear.NZBGET_USERNAME = 'nzbget'
        sickgear.NZBGET_PASSWORD = 'password'
        sickgear.SAB_HOST = self._sab_host
        sickgear.SAB_APIKEY = 'ohoih87dh'
        sickgear.SAB_CATEGORY = 'Series'
        sickgear.SAB_PASSWORD = 'password'
        sickgear.SAB_USERNAME = 'sab'
        sickgear.NZB_DIR = sickgear.CACHE_DIR
        for provider in sickgear.providers.sorted_sources():
            if 'Newznab' in type(provider).__name__:
                provider.enabled = True
                provider.enable_backlog = True
                provider.enable_recentsearch = True
                provider.enable_scheduled_backlog = True
                self._test_provider_settings = {'url': provider.url}
                provider.url = f'http://localhost:1234/'
                provider.api_key = '989h998'
                self.mock_provider_domains.append(urlparse(provider.url).netloc)
                self.test_provider = provider  # type: NewznabProvider
                break

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.download_dir)
        shutil.rmtree(self.show_dir)
        sickgear.name_parser.parser.name_parser_cache = sickgear.name_parser.parser.NameParserCache()
        sickgear.USE_NZBS = False
        sickgear.search_queue_scheduler = None
        sickgear.scene_numbering.xem_refresh = self._xem_refresh
        sickgear.tv.TVEpisode.specify_episode = test._fake_specify_ep
        sg_helpers.get_url = self._old_get_url
        newznab.time = self._old_newznab_time
        for k, v in self._old_settings.items():
            setattr(sickgear, k, v)
        helpers.get_url = self._old_get_url
        sickgear.nzbget.ServerProxy = self._old_serverproxy
        for provider in sickgear.providers.sorted_sources():
            if self.test_provider == provider:
                provider.enabled = False
                provider.enable_backlog = False
                provider.enable_recentsearch = False
                provider.api_key = ''
                provider.enable_scheduled_backlog = False
                provider.url = self._test_provider_settings['url']

    def _mock_add_item(
            self,
            item,  # type: Union[RecentSearchQueueItem, ProperSearchQueueItem, BacklogQueueItem, ManualSearchQueueItem, FailedQueueItem]
            add_to_db=True,  # type: bool
            *args, **kwargs
    ):
        if isinstance(item, ProperSearchQueueItem):
            self._proper_search_run = True
            item.run()
        elif isinstance(item, FailedQueueItem):
            self._failed_results.append(item)
            item.run()

    def _process_nzbget_responce(self, method_name, *arg, **kwargs):
        if 'version' == method_name:
            return '26.1-testing-20260317'
        if 'append' == method_name:
            (nzbname, result_url, category, priority, addtotop, addpaused, dupekey, dupescore, dupemode, autocat,
             ppparameters) = arg
            if pp := [p[1] for p in ppparameters or [] if 'sickgear_puid' == p[0]]:
                puid = pp[0]
            else:
                puid = None
            nzb_id = random.randint(1, 1000000)
            # self.result_data.append((result_url, nzbname, puid, nzbname, dupekey, dupescore))
            self.result_data.append({'url': result_url, 'filename': nzbname, 'puid': puid, 'dupekey': dupekey,
                                     'dupescore': dupescore, 'nzb_id': nzb_id})
            return nzb_id

    def mock_xem_refresh(self, *args, **kwargs):
        pass

    def _process_log(self, record):
        if res := proper_found_leg_reges.search(record.msg):
            self._proper_results.append(res.group(1))

    def mock_get_url(self, url, post_data=None, params=None, **kwargs):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        parsed_q = parse_qs(parsed_url.query)
        if isinstance(params, dict):
            parsed_q.update(params)
        # newznab indexer
        if any(domain == d for d in self.mock_provider_domains):
            return test.generate_newznab_responce(self, domain, url, parsed_q,  **kwargs)
        # sabnzbd client
        if domain in self._sab_host:
            if 'mode' in parsed_q and 'addurl' == parsed_q['mode']:
                if ('json' == parsed_q.get('output') and sickgear.SAB_APIKEY == parsed_q.get('apikey')
                        and sickgear.SAB_CATEGORY == parsed_q.get('cat')):
                    nzb_id = random.randint(1, 10000000)
                    self.result_data.append({'filename': parsed_q.get('nzbname'), 'url': parsed_q.get('name'),
                                             'nzb_id': nzb_id})
                    return {'status': True, 'nzo_ids': [f'{nzb_id}']}

    def _add_show_data(self, cur_test):
        # type: (dict) -> TVShow
        show_data = cur_test['show_data']
        show_obj = TVShow(TVINFO_TVDB, 123456, 'en')
        show_obj.name = show_data.get('show_name', 'House')
        show_obj.tvrname = show_data.get('show_name', 'House')
        show_obj.network = show_data.get('network', 'cbs')
        show_obj.genre = show_data.get('genre', 'crime')
        show_obj.runtime = show_data.get('runtime', 10)
        show_obj.status = show_data.get('status', 'Ended')
        show_obj.airs = show_data.get('airs', 'monday')
        show_obj.startyear = show_data.get('start_year', 2000)
        show_obj.quality = show_data.get('quality', Quality.combine_qualities(
            [Quality.SDTV, Quality.SDDVD, Quality.HDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB,
             Quality.HDBLURAY, Quality.FULLHDBLURAY],
            [Quality.SDDVD, Quality.HDTV, Quality.HDWEBDL, Quality.FULLHDWEBDL, Quality.UHD4KWEB,
             Quality.HDBLURAY, Quality.FULLHDBLURAY]))
        show_obj.sxe_ep_obj = {}
        location = os.path.join(self.show_dir, show_obj.name)
        os.makedirs(location, exist_ok=True)
        show_obj.location = location
        show_obj.save_to_db()
        sickgear.showList = [show_obj]
        sickgear.showDict = {show_obj.sid_int: show_obj}

        ep_settings = {}
        for ep in cur_test.get('episodes', []):
            ep_data = {k: v for k, v in ep.items() if k not in ('season', 'episodes')}
            for en in self._split_ep_nbs(ep['episodes']):
                en_s = en
                if not isinstance(en, tuple):
                    en_s = [en]
                for _e in en_s:
                    ep_settings.setdefault(f'{ep["season"]}x{_e}', {}).update(ep_data)

        cl = []
        for cur_ep in show_data.get('episodes') or [
            {'season': 1, 'ep_count': 8, 'ep_data': {}},
            {'season': 2, 'ep_count': 15, 'ep_data': {}},
            {'season': 3, 'ep_count': 20, 'ep_data': {}}
        ]:
            for ep_nb in range(1, cur_ep['ep_count'] + 1):
                episode = TVEpisode(show_obj, cur_ep['season'], ep_nb)
                ep_str = f'{cur_ep["season"]}x{ep_nb}'
                episode.epid = random.randint(1, 100000000)
                episode.name = f'Tile #{ep_nb}'
                episode.status = common.WANTED
                episode.airdate = datetime.date(2005 + cur_ep['season'], 9, ep_nb)
                if (e_id := f'{cur_ep["season"]}x{ep_nb}') in cur_ep.get('ep_data', {}):
                    for a, v in cur_ep['ep_data'][e_id].items():
                        setattr(episode, a, v)
                if ep_str in ep_settings:
                    for k, v in ep_settings[ep_str].items():
                        setattr(episode, k, v)
                cl.append(episode.get_sql())

        with db.DBConnection() as my_db:
            my_db.mass_action(cl)
        indexermapper.load_mapped_ids()
        return show_obj

    def _remove_all_show_data(self):
        shutil.rmtree(self.show_dir)
        os.makedirs(self.show_dir, exist_ok=True)
        sickgear.showList = []
        sickgear.showDict = {}
        cl = [
            ['DELETE FROM tv_shows'],
            ['DELETE FROM tv_episodes'],
            ['DELETE FROM history']
        ]
        with db.DBConnection() as my_db:
            my_db.mass_action(cl)

    def _clear_cache_db(self):
        cl = [
            ['DELETE FROM lastSearch'],
            ['DELETE FROM lastUpdate'],
            ['DELETE FROM provider_cache'],
            ['DELETE FROM provider_fails'],
            ['DELETE FROM provider_fails_count'],
            ['DELETE FROM search_queue'],
            ['DELETE FROM show_queue'],
            ['DELETE FROM people_queue'],
            ['DELETE FROM lastrecentsearch'],
            ['DELETE FROM connection_fails'],
            ['DELETE FROM connection_fails_count'],
            ['DELETE FROM backlogparts'],
        ]
        with db.DBConnection('cache.db') as my_db:
            my_db.mass_action(cl)

    def _clear_failed_db(self):
        cl = [
            ['DELETE FROM history'],
            ['DELETE FROM failed'],
        ]
        with db.DBConnection('failed.db') as my_db:
            my_db.mass_action(cl)

    def _clear_all_data(self):
        sickgear.name_parser.parser.name_parser_cache = sickgear.name_parser.parser.NameParserCache()
        self._remove_all_show_data()
        self._clear_cache_db()
        self._clear_failed_db()
        self.result_data = []
        self._failed_results = []
        self._proper_results = []
        self.expected_res = []
        self.expected_proper_res = []
        self._set_failed = []
        self._proper_search_run = None

    def _check_results(self):
        self.assertTrue(self._proper_search_run in (None, True), msg=f'Required Proper search not triggered')
        expected_res = self.expected_res.copy()
        expected_proper_res = self.expected_proper_res.copy()
        for rd in self.result_data:
            self.assertTrue(bool(newznab_downlaod_url_match.search(rd['url'])),
                            msg=f'wrong download url: {rd["url"]}')
            result_name = os.path.splitext(rd['filename'])[0]
            self.assertTrue(result_name in expected_res, msg=f'wrong download file: {rd["filename"]}')
            if 'puid' in rd:
                puid = puid_regex.search(rd['puid']).group(1)
                self.assertTrue(any(puid in c['guid'] for c in self.cur_items), msg='puid is not correct')
            expected_res.remove(result_name)
        self.assertListEqual(expected_res, [], msg=f'Results missing: {expected_res}')

        for rp in self._proper_results:
            self.assertTrue(rp in expected_proper_res,
                            msg=f'Unexpected proper in results: {rp}')
            expected_proper_res.remove(rp)
        self.assertListEqual(expected_proper_res, [],
                             msg=f'Expected propers missing: {expected_proper_res}')

        if not self.result_data:
            self.assertTrue(False, msg='Failed to get any result')

    def _split_ep_nbs(self, nb_str):
        # type: (str) -> list
        if isinstance(nb_str, int):
            return [nb_str]
        elif ',' in nb_str:
            nbs = []
            for _n in nb_str.split(','):
                nbs.extend(self._split_ep_nbs(_n))
            return nbs
        elif '-' in nb_str:
            start, stop = nb_str.split('-')
            return list(range(int(start.strip()), int(stop.strip()) + 1))
        elif '/' in nb_str:
            start, end = nb_str.split('/')
            return [(int(start), int(end))]
        else:
            return [int(nb_str.strip())]

    def _items_generator(self, cur_test_case):
        # type: (dict) -> None
        items = []
        items.extend(cur_test_case.get('items', []))
        for cur_items in cur_test_case.get('items_gen', []):
            items_dict = {}
            base_item = cur_items['base_item']
            ep_nbs = cur_items['ep_nbs']
            for segment in ep_nbs:
                nbs = [None] if 'episodes' not in segment else self._split_ep_nbs(segment['episodes'])
                for ep in nbs:
                    ep_str = ep
                    end_ep = None
                    if isinstance(ep, tuple):
                        ep_str = f'{ep[0]}-{ep[1]}'
                        end_ep = ep[1]
                        ep = ep[0]
                    if None is ep:
                        cur_id = f'{segment["season"]:02d}'
                    else:
                        cur_id = f'{segment["season"]:02d}x{ep:02d}'
                    if cur_id in items_dict:
                        new_item = items_dict[cur_id]
                    else:
                        new_item = base_item.copy()
                        if None is not end_ep:
                            new_item['end_episode'] = end_ep
                        new_item['release_name'] = test.generate_release_name(
                            season=segment['season'], episodes=ep_str, p_types=segment.get('p_types'),
                            random_proper=segment.get('proper'),
                            must_be_proper=segment.get('must_be_proper', False), data_set=base_item)
                        new_item['season'] = segment['season']
                        new_item['episode'] = ep
                    for k, v in segment.items():
                        if k not in ('season', 'episodes'):
                            new_item[k] = v
                    if cur_id not in items_dict:
                        items.append(new_item)
                        items_dict[cur_id] = new_item
        guid_list = set()
        count = len(items)
        while True:
            guid_list.add(test.guid_generator())
            if count <= len(guid_list):
                break
        for _i in items:
            _i['guid'] = guid_list.pop()
        self.cur_items = items

    def _make_ep_list(self, episodes):
        if isinstance(episodes, int):
            return [episodes]
        if ',' in episodes:
            return [ep for eps in episodes.split(',') for ep in self._make_ep_list(eps)]
        if '-' in episodes:
            start, stop = episodes.split('-')
            return list(range(int(start.strip()), int(stop.strip())+1))
        return [int(episodes.strip())]

    def _get_expected_result(self, cur_test_case, ep_nbs):
        # type: (dict, list) -> None
        res = [c for c in self.cur_items
               if None is ep_nbs or 'season' not in cur_test_case.get('search', {}) or
               (cur_test_case['search']['season'] == c['season']
                and ('episodes' not in cur_test_case['search'] or c['episode'] in ep_nbs))]
        self._set_failed += [r['release_name'] for r in res if r.get('failed', False)]
        self.expected_res = [r['release_name'] for r in res]
        self.expected_proper_res = [_r for _r in self.expected_res if proper_regex.search(_r)]

    def _create_downloads(self):
        # type:() -> None
        new_result_data = []
        for bf in self.result_data:
            _fs = []
            # check for season pack
            if _sn := re.search(r'\bS(\d+)\b', bf['filename'], flags=re.I):
                file_basename = os.path.splitext(bf['filename'])[0]
                f_i = next((c for c in self.cur_items if c['release_name'] == file_basename), None)
                _s = int(_sn.group(1))
                ep_nbs = [_ep.episode for _ep in self.show_obj.get_all_episodes(_s)]
                for e in ep_nbs:
                    _ni = bf.copy()
                    _ni['filename'] = re.sub(f'S{_sn.group(1)}', f'S{_sn.group(1)}E{e:02d}',
                                             _ni['filename'], flags=re.I)
                    _fs.append(_ni)
                    n_i = f_i.copy()
                    n_i['release_name'] = re.sub(f'S{_sn.group(1)}', f'S{_sn.group(1)}E{e:02d}',
                                                 n_i['release_name'], flags=re.I)
                    n_i['episode'] = e
                    self.cur_items.append(n_i)
            else:
                _fs = [bf]
            new_result_data += _fs
            for f in _fs:
                file_basename = os.path.splitext(f['filename'])[0]
                base_dir = os.path.join(self.download_dir, file_basename)
                n_f = os.path.join(base_dir, f'{file_basename}.mkv')
                os.makedirs(base_dir, exist_ok=True)
                with open(n_f, 'w') as m:
                    m.write('test file not 0 bytes')

        self.result_data = new_result_data

    def _process_downlaods(self, show_obj, cur_test_case):
        # type: (TVShow, dict) -> None
        for f in self.result_data:
            file_basename = os.path.splitext(f['filename'])[0]
            failed = file_basename in self._set_failed
            down_dir = os.path.join(self.show_dir, file_basename)
            f_i = next((c for c in self.cur_items if c['release_name'] == file_basename), None)
            ep_obj = show_obj.get_episode(f_i['season'], f_i['episode'])  # type: TVEpisode
            old_status = ep_obj.status
            # used for failed check, snatch quality will be removed after pp
            old_video_codec = VideoCodec.split_vc(ep_obj.video_codec)[1]
            old_release_name = ep_obj.release_name
            sickgear.webserve.HomeProcessMedia.process_files(mock_web(),
                down_dir, f['filename'], quiet='1', force='1', failed=('0', '1')[failed],
                stream=('0', '1')['nzbget' == sickgear.NZB_METHOD], dupekey=f.get('dupekey'),
                client=sickgear.NZB_METHOD, nzbid=f.get('nzb_id'), puid=f.get('puid'))
            # check if file was processed
            filename = f'{file_basename}.mkv'
            target_file = os.path.join(show_obj.location, filename)
            if failed:
                ep_nb = f'{f_i["season"]}x{f_i["episode"]}'
                self.assertTrue(ep_nb in [f'{ep.season}x{ep.episode}' for fr in self._failed_results
                                          for ep in fr.segment],
                                msg=f'Failed episode not processed: {file_basename}')
                self.assertFalse(os.path.isfile(target_file), msg=f'Failed file was post-processed: {filename}')
                self._check_failed_history(f, f_i, file_basename)
                self.assertTrue(old_release_name == ep_obj.release_name,
                                msg=f'release name is set for failed episode: {f_i["release_name"]}')
                self.assertTrue(old_status != ep_obj.status,
                                msg=f'failed episode status not correctly set: {f_i["release_name"]}')
                self.assertTrue((old_video_codec or None) == ep_obj.video_codec,
                                msg=f'failed episode video codec not correctly set: {f_i["release_name"]}')
            else:
                self.assertTrue(os.path.isfile(target_file), msg=f'File not post processed: {filename}')
                self.assertTrue(ep_obj.release_name == f_i['release_name'],
                                msg=f'release name is correctly set: {f_i["release_name"]}')
                self.assertTrue(ep_obj.status == Quality.composite_status(common.DOWNLOADED, f_i['quality']),
                                msg=f'episode status not correctly set: {f_i["release_name"]}')
                self.assertTrue(ep_obj.video_codec == f_i['codec'],
                                msg=f'episode video codec not correctly set: {f_i["release_name"]}')

    def _check_failed_history(self, failed_item, failed_matched, file_basename):
        if failed_item.get('puid'):
            self.assertTrue(failed_history.has_failed(puid=failed_item['puid']),
                            msg=f'Release puid missing in failed history: {failed_item["filename"]}')
        if ((client := common.DOWNLOAD_CLIENTS.IDS.get(sickgear.NZB_METHOD))
                in common.DOWNLOAD_CLIENTS.TRUSTED_CLIENT_IDS and failed_item.get('nzb_id')):
            self.assertTrue(failed_history.has_failed(client=client, client_uid=failed_item['nzb_id']),
                            msg=f'Release client_id missing in failed history: {failed_item["filename"]}')
        self.assertTrue(failed_history.has_failed(release=file_basename, size=failed_matched.get('size')),
                        msg=f'Release name/size missing in failed history: {failed_item["filename"]}')

    def _check_puid_lookups(self, show_obj):
        # type: (TVShow) -> None
        if sickgear.NZB_METHOD in ('nzbget', ):
            for r in self.result_data:
                parsed_show_obj = history.find_show_by_puidstr(r['puid'])
                self.assertEqual(parsed_show_obj, show_obj, msg=f'puid lockup in history failed: {r["filename"]}')

    def _check_client_uid_loockups(self, show_obj):
        # type: (TVShow) -> None
        if common.DOWNLOAD_CLIENTS.IDS.get(sickgear.NZB_METHOD) in common.DOWNLOAD_CLIENTS.TRUSTED_CLIENT_IDS:
            client = common.DOWNLOAD_CLIENTS.IDS.get(sickgear.NZB_METHOD, None)
            for r in self.result_data:
                parsed_show_obj = history.find_show_by_client_uid(client, r['nzb_id'])
                self.assertEqual(parsed_show_obj, show_obj, msg=f'client/client_id lockup in history failed: {r["filename"]}')
                parsed_show_obj, parsed_puid = history.find_show_puid_by_client_uid(client, r['nzb_id'])
                self.assertEqual(parsed_show_obj, show_obj, msg=f'client/client_id lockup for show_obj in history failed: {r["filename"]}')
                file_basename = os.path.splitext(r['filename'])[0]
                f_i = next((c for c in self.cur_items if c['release_name'] == file_basename), None)
                if f_i and 'guid' in f_i:
                    parsed_base_puid = puid_regex.search(parsed_puid).group(1)
                    self.assertEqual(parsed_base_puid, f_i['guid'], msg=f'client/client_id lockup for puid in history failed: {r["filename"]}')

    def _check_history_lookups(self, show_obj):
        # type: (TVShow) -> None
        self._check_puid_lookups(show_obj)
        self._check_client_uid_loockups(show_obj)

    def _run_all_checks(self, show_obj, cur_test_case):
        self._check_results()
        self._check_history_lookups(show_obj)
        self._create_downloads()
        self._process_downlaods(show_obj, cur_test_case)

    def _get_ep_nbs(self, cur_test_case):
        return 'episodes' in cur_test_case.get('search', {}) and self._make_ep_list(cur_test_case['search']['episodes'])

    def _cur_test(self, search_tests, test_name):
        # type: (list, str) -> dict
         for cur_test in search_tests:
            for _t_n ,_t in enumerate(cur_test['tests']):
                _clients = _t.get('nzb_method', ['nzbget'])
                _clients = (_clients, _all_clients)[isinstance(_clients, str) and 'all' == _clients]
                if (not isinstance(_clients, list)
                        or any(not isinstance(_c, str) for _c in _clients)
                        or any(_c not in _all_clients for _c in _clients)):
                    raise Exception(f'nzb_methods are invalid: {_clients}')
                self.test_provider.search_fallback = _t.get('search_fallback', False)
                for _client in _clients:
                    self._clear_all_data()
                    sickgear.NZB_METHOD = _client
                    self.show_obj = self._add_show_data(cur_test)
                    self._items_generator(_t)
                    self.ep_nbs = self._get_ep_nbs(_t)
                    self._get_expected_result(_t, self.ep_nbs)
                    print(f'snatch test: "{test_name}" #{_t_n} - "{_client}"')
                    yield _t

    def test_recent_search(self):
        for cur_test_case in self._cur_test(recent_search_tests, 'recent'):
            recent = search_queue.RecentSearchQueueItem()
            recent.run()
            self._run_all_checks(self.show_obj, cur_test_case)

    def _prepare_db_for_proper(self, cur_test_case, show_obj):
        proper_remove_re = re.compile(r'\b(?:proper|real|repack)\b', flags=re.I)
        dot_re = re.compile(r'\.+')
        for i in self.cur_items:
            ep_obj = show_obj.get_episode(i['season'], i['episode'])  # type: TVEpisode
            res = sickgear.classes.NZBSearchResult([ep_obj])
            res.provider = self.test_provider
            res.name = dot_re.sub('.', proper_remove_re.sub('.', i['release_name']))
            ep_obj.release_name = res.name
            ep_obj.release_group = i['group']
            ep_obj.status = Quality.composite_status(common.DOWNLOADED, i['quality'])
            ep_obj.airdate = datetime.date.today() - datetime.timedelta(days=3)
            ep_obj.save_to_db()
            res.quality = i['quality']
            res.show_obj = show_obj
            res.size = i['size']
            res.release_group = i['group']
            history.log_snatch(res)
            history.log_download(ep_obj, res.name, res.quality, release_group=res.release_group)

    def test_proper_search(self):
        sickgear.DOWNLOAD_PROPERS = True
        for cur_test_case in self._cur_test(proper_search_tests, 'proper'):
            self._prepare_db_for_proper(cur_test_case, self.show_obj)
            proper = search_queue.ProperSearchQueueItem()
            proper.run()
            self._run_all_checks(self.show_obj, cur_test_case)

    def test_recent_proper_search(self):
        sickgear.DOWNLOAD_PROPERS = True
        for cur_test_case in self._cur_test(proper_search_tests, 'recent proper'):
            self._proper_search_run = False
            self._prepare_db_for_proper(cur_test_case, self.show_obj)
            recent = search_queue.RecentSearchQueueItem()
            recent.run()
            self._run_all_checks(self.show_obj, cur_test_case)

    def _get_segment(self, cur_test_case, show_obj, ep_nbs):
        # type (list, TVShow, list) -> list
        return [ep for ep in show_obj.get_all_episodes(cur_test_case['search']['season'])
                if 'episodes' not in cur_test_case['search'] or ep.episode in ep_nbs]

    def test_backlog_search(self):
        for cur_test_case in self._cur_test(backlog_search_tests, 'backlog'):
            segment = self._get_segment(cur_test_case, self.show_obj, self.ep_nbs)
            backlog = search_queue.BacklogQueueItem(self.show_obj, segment)
            backlog.run()
            self._run_all_checks(self.show_obj, cur_test_case)

    def test_manual_search(self):
        for cur_test_case in self._cur_test(manual_search_tests, 'manual'):
            ep_nbs = self._split_ep_nbs(cur_test_case['search']['episodes'])
            segment = self.show_obj.get_episode(cur_test_case['search']['season'], ep_nbs[0])
            manual = search_queue.ManualSearchQueueItem(self.show_obj, segment)
            manual.run()
            self._run_all_checks(self.show_obj, cur_test_case)

    def test_failed_search(self):
        for cur_test_case in self._cur_test(failed_search_tests, 'failed'):
            segment = self._get_segment(cur_test_case, self.show_obj, self.ep_nbs)
            failed = search_queue.FailedQueueItem(self.show_obj, segment)
            failed.run()
            self._run_all_checks(self.show_obj, cur_test_case)


if '__main__' == __name__:
    print('==================')
    print('STARTING - Snatch TESTS')
    print('==================')
    print('######################################################################')

    suite = unittest.TestLoader().loadTestsFromTestCase(SearchTest)
    unittest.TextTestRunner(verbosity=2).run(suite)
